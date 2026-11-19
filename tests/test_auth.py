"""Admin sign-in: the allowlist, the verified-email rule, and the session cookie."""

import pytest
from fastapi.testclient import TestClient
from firebase_admin.exceptions import InvalidArgumentError

from app.core import auth, config
from app.db import firebase
from app.main import app
from dataclasses import replace

client = TestClient(app)

ALLOWED = {"email": "owner@example.com", "email_verified": True, "uid": "u1", "admin": True}


@pytest.fixture
def firebase_auth(monkeypatch, real_auth):
    """Real sign-in checks, with Firebase itself replaced by controllable fakes."""
    monkeypatch.setattr(config, "integrations", replace(
        config.integrations, google_credentials="fake.json", admin_emails=frozenset({"owner@example.com"})))
    monkeypatch.setattr(firebase, "init_app", lambda: None)
    state = {"cookie_claims": ALLOWED, "token_claims": ALLOWED}

    def verify_cookie(cookie, check_revoked=False):
        if cookie != "good-cookie":
            raise InvalidArgumentError("bad cookie")
        return state["cookie_claims"]

    monkeypatch.setattr(auth.fb_auth, "verify_session_cookie", verify_cookie)
    monkeypatch.setattr(auth.fb_auth, "verify_id_token", lambda token: state["token_claims"])
    monkeypatch.setattr(auth.fb_auth, "create_session_cookie", lambda token, expires_in: "good-cookie")
    return state


def _post_with_csrf(url: str):
    """Helper to POST with CSRF token from the cookie."""
    client.get(url.replace("/edit", "").replace("/delete", "").replace("/new", ""))
    csrf_token = client.cookies.get("csrf_token", "")
    headers = {"X-CSRF-Token": csrf_token}
    return client.post(url, data={}, headers=headers, follow_redirects=False)


def test_admin_pages_redirect_to_login_without_a_session(firebase_auth):
    for url in ("/admin/dashboard", "/admin/bookings", "/admin/services/cars", "/admin/calendar", "/admin"):
        response = client.get(url, follow_redirects=False)
        assert response.status_code == 303 and response.headers["location"] == "/admin/login", url
    assert _post_with_csrf("/admin/services/cars/new").status_code == 303


def test_login_page_is_public_and_carries_only_the_public_web_config(firebase_auth, monkeypatch):
    from app.core.templating import templates
    monkeypatch.setitem(templates.env.globals, "firebase_config", {
        "apiKey": "k", "authDomain": "a", "projectId": "p", "messagingSenderId": "m", "appId": "i"})
    html = client.get("/admin/login").text
    assert 'id="firebase-config"' in html and "Continue with Google" in html and 'type="password"' in html
    assert "fake.json" not in html and "private" not in html.lower()


def test_login_page_explains_when_firebase_web_config_is_missing(firebase_auth, monkeypatch):
    from app.core.templating import templates
    monkeypatch.setitem(templates.env.globals, "firebase_config", None)
    assert "Sign-in is not set up" in client.get("/admin/login").text


def test_valid_session_cookie_for_an_allowed_admin_opens_the_dashboard(firebase_auth, fake_db):
    client.cookies.set("bless_admin_session", "good-cookie")
    try:
        assert client.get("/admin/dashboard").status_code == 200
    finally:
        client.cookies.clear()


def test_invalid_cookie_unverified_email_and_unlisted_email_are_refused(firebase_auth):
    client.cookies.set("bless_admin_session", "garbage")
    assert client.get("/admin/dashboard", follow_redirects=False).status_code == 303
    client.cookies.set("bless_admin_session", "good-cookie")
    try:
        firebase_auth["cookie_claims"] = {**ALLOWED, "email_verified": False}
        assert client.get("/admin/dashboard", follow_redirects=False).status_code == 303
        firebase_auth["cookie_claims"] = {**ALLOWED, "email": "stranger@example.com"}
        assert client.get("/admin/dashboard", follow_redirects=False).status_code == 303
    finally:
        client.cookies.clear()


def test_allowlist_ignores_case_and_blank_entries(monkeypatch):
    monkeypatch.setenv("ADMIN_EMAILS", " Owner@Example.com, ,second@example.com ,")
    assert config._admin_emails() == frozenset({"owner@example.com", "second@example.com"})
    monkeypatch.setattr(config, "integrations", replace(config.integrations, admin_emails=config._admin_emails()))
    assert auth.is_allowed({"email": "OWNER@example.com", "email_verified": True, "admin": True})
    assert not auth.is_allowed({"email": "owner@example.com"})  # no email_verified claim
    assert not auth.is_allowed({})  # no admin claim


def test_session_is_created_for_an_allowed_account_with_a_hardened_cookie(firebase_auth):
    response = client.post("/admin/session", json={"id_token": "t"})
    assert response.status_code == 200
    cookie = response.headers["set-cookie"].lower()
    assert "bless_admin_session=good-cookie" in cookie
    assert "httponly" in cookie and "samesite=lax" in cookie and "path=/admin" in cookie


def test_session_is_refused_for_accounts_off_the_list_or_unverified(firebase_auth):
    firebase_auth["token_claims"] = {**ALLOWED, "email": "stranger@example.com"}
    response = client.post("/admin/session", json={"id_token": "t"})
    assert response.status_code == 403 and "set-cookie" not in response.headers
    firebase_auth["token_claims"] = {**ALLOWED, "email_verified": False}
    assert client.post("/admin/session", json={"id_token": "t"}).status_code == 403


def test_session_rejects_a_bad_token(firebase_auth, monkeypatch):
    def reject(token):
        raise ValueError("bad token")
    monkeypatch.setattr(auth.fb_auth, "verify_id_token", reject)
    # JSON still works (for backward compat) but fails with bad token
    assert client.post("/admin/session", json={"id_token": "t"}).status_code == 401
    # Form with bad token also fails (now accepts form data with Turnstile + CSRF)
    assert client.post("/admin/session", data={"id_token": "t"}).status_code == 401


def test_empty_allowlist_lets_nobody_in(firebase_auth, monkeypatch):
    monkeypatch.setattr(config, "integrations", replace(config.integrations, admin_emails=frozenset()))
    assert client.post("/admin/session", json={"id_token": "t"}).status_code == 403


def test_admin_pages_are_not_cached():
    assert client.get("/admin/dashboard").headers["cache-control"] == "no-store"
    assert "no-store" not in client.get("/").headers.get("cache-control", "")
