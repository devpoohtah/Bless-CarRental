"""Desktop alerts: saving browser tokens, sending a push for a new booking, and the admin page wiring."""

from dataclasses import replace

import re

import pytest
from fastapi.testclient import TestClient
from firebase_admin import exceptions, messaging

from app.core import config
from app.db import firebase
from app.db import repositories as repo
from app.main import app
from app.services import notify, push
from tests.test_telegram_alert import car_booking

client = TestClient(app)
TOKEN_A = "fAkEtOkEn_aaaaaaaaaaaaaaaaaaaaaaaaaaa:APA91b-AAAAAAAAAAAAAAAAAAAA"
TOKEN_B = "fAkEtOkEn_bbbbbbbbbbbbbbbbbbbbbbbbbbb:APA91b-BBBBBBBBBBBBBBBBBBBB"


def _push_headers():
    """Get headers with CSRF token for push endpoints."""
    client.get("/admin/dashboard")  # sets the cookie
    csrf_token = client.cookies.get("csrf_token", "")
    return {"X-CSRF-Token": csrf_token}


@pytest.fixture
def admins(monkeypatch):
    monkeypatch.setattr(config, "integrations", replace(
        config.integrations, admin_emails=frozenset({"owner@example.com", "manager@example.com"})))


def stored(db) -> dict:
    return db.data.get("push_tokens", {})


# ---- saving a token ----
def test_a_token_is_saved_for_the_signed_in_admin(fake_db):
    response = client.post("/admin/push/register", json={"token": TOKEN_A}, headers=_push_headers())
    assert response.status_code == 200
    (row,) = stored(fake_db).values()
    assert row["token"] == TOKEN_A and row["admin_email"] == "admin@example.com"


def test_registering_the_same_token_twice_keeps_one_row(fake_db):
    for _ in range(2):
        assert client.post("/admin/push/register", json={"token": TOKEN_A}, headers=_push_headers()).status_code == 200
    assert len(stored(fake_db)) == 1


@pytest.mark.parametrize("token", ["", "short", "x" * 5000, "has spaces in it aaaaaaaaaaaaaaaa", "<script>alert(1)</script>aaaa"])
def test_a_bad_token_is_refused(fake_db, token):
    assert client.post("/admin/push/register", json={"token": token}, headers=_push_headers()).status_code == 422
    assert stored(fake_db) == {}


def test_saving_a_token_needs_a_database():
    assert client.post("/admin/push/register", json={"token": TOKEN_A}, headers=_push_headers()).status_code == 503


def test_saving_a_token_needs_an_admin_sign_in(fake_db, real_auth):
    response = client.post("/admin/push/register", json={"token": TOKEN_A}, follow_redirects=False)
    assert response.status_code in (303, 401, 403) and stored(fake_db) == {}


# ---- sending ----
def sent_to(monkeypatch, errors=None):
    """Replaces the FCM call; records (tokens, data) per call and answers each token with errors.get(token)."""
    calls = []

    def fake(tokens, data):
        calls.append((tokens, data))
        return [(errors or {}).get(t) for t in tokens]
    monkeypatch.setattr(push, "_send_multicast", fake)
    return calls


def test_a_push_goes_to_every_admin_browser(fake_db, admins, monkeypatch):
    push.register_token(TOKEN_A, "owner@example.com")
    push.register_token(TOKEN_B, "manager@example.com")
    calls = sent_to(monkeypatch)
    assert push.send_to_admins("T", "B", "/admin/bookings/x", "x") == 2
    (tokens, data), = calls
    assert set(tokens) == {TOKEN_A, TOKEN_B}
    assert data == {"title": "T", "body": "B", "url": "/admin/bookings/x", "tag": "x"}


def test_a_browser_of_a_removed_admin_gets_nothing(fake_db, admins, monkeypatch):
    push.register_token(TOKEN_A, "owner@example.com")
    push.register_token(TOKEN_B, "fired@example.com")
    calls = sent_to(monkeypatch)
    assert push.send_to_admins("T", "B", "/admin/bookings/x", "x") == 1
    assert calls[0][0] == [TOKEN_A]


def test_nothing_is_sent_without_tokens_or_a_database(fake_db, admins, monkeypatch):
    calls = sent_to(monkeypatch)
    assert push.send_to_admins("T", "B", "/u", "t") == 0 and calls == []


def test_a_dead_token_is_removed_and_a_temporary_failure_is_kept(fake_db, admins, monkeypatch):
    push.register_token(TOKEN_A, "owner@example.com")
    push.register_token(TOKEN_B, "manager@example.com")
    sent_to(monkeypatch, errors={TOKEN_A: messaging.UnregisteredError("gone", None, None),
                                 TOKEN_B: exceptions.UnavailableError("later", None, None)})
    assert push.send_to_admins("T", "B", "/u", "t") == 0
    assert [row["token"] for row in stored(fake_db).values()] == [TOKEN_B]


def test_fcm_answers_are_matched_to_their_tokens(monkeypatch):
    class Result:
        def __init__(self, ok, exception=None): self.success, self.exception = ok, exception
    boom = RuntimeError("x")
    monkeypatch.setattr(firebase, "init_app", lambda: None)
    monkeypatch.setattr(messaging, "send_each_for_multicast", lambda message, app: type(
        "R", (), {"responses": [Result(True), Result(False, boom)]})())
    assert push._send_multicast([TOKEN_A, TOKEN_B], {"title": "t"}) == [None, boom]


# ---- the booking triggers it ----
def test_a_new_booking_pushes_without_the_phone_number(fake_db, admins, monkeypatch):
    push.register_token(TOKEN_A, "owner@example.com")
    calls = sent_to(monkeypatch)
    monkeypatch.setattr(notify, "send_telegram", lambda text: True)
    notify.notify_new_booking(car_booking())
    (tokens, data), = calls
    assert data["title"] == "New car rental request" and data["url"] == "/admin/bookings/abc123"
    assert "Ana Reyes" in data["body"] and "Toyota Vios" in data["body"]
    assert "0917" not in str(data)


def test_a_telegram_failure_does_not_stop_the_push(fake_db, admins, monkeypatch):
    push.register_token(TOKEN_A, "owner@example.com")
    calls = sent_to(monkeypatch)
    monkeypatch.setattr(notify, "send_telegram", lambda text: 1 / 0)
    notify.notify_new_booking(car_booking())
    assert len(calls) == 1


def test_a_push_failure_does_not_stop_anything_and_never_raises(fake_db, admins, monkeypatch):
    push.register_token(TOKEN_A, "owner@example.com")
    texts = []
    monkeypatch.setattr(notify, "send_telegram", lambda text: texts.append(text) or True)
    monkeypatch.setattr(push, "_send_multicast", lambda tokens, data: 1 / 0)
    notify.notify_new_booking(car_booking())
    assert len(texts) == 1


# ---- the admin pages ----
@pytest.fixture
def push_on(monkeypatch, fake_db):
    monkeypatch.setattr(config, "integrations", replace(
        config.integrations, firebase_api_key="key", firebase_auth_domain="x.firebaseapp.com", firebase_project_id="proj",
        firebase_sender_id="123", firebase_app_id="1:123:web:abc", firebase_vapid_key="PUBLIC-VAPID-KEY"))


def test_the_admin_pages_carry_the_public_config_and_the_button_when_alerts_are_set_up(push_on):
    html = client.get("/admin/dashboard").text
    assert 'id="push-config"' in html and "PUBLIC-VAPID-KEY" in html and "data-push-toggle" in html
    assert 'src="/static/admin/js/push.js' in html


def test_nothing_about_alerts_is_on_the_page_when_they_are_not_set_up():
    html = client.get("/admin/dashboard").text
    assert "push-config" not in html and "data-push-toggle" not in html and "push.js" not in html


def test_no_alert_settings_without_the_vapid_key_or_the_database(monkeypatch, fake_db):
    monkeypatch.setattr(config, "integrations", replace(
        config.integrations, firebase_api_key="key", firebase_auth_domain="x", firebase_project_id="p",
        firebase_sender_id="1", firebase_app_id="a", firebase_vapid_key=""))
    assert config.integrations.push_web_config is None
    monkeypatch.setattr(config, "integrations", replace(config.integrations, firebase_vapid_key="K", google_credentials=""))
    assert config.integrations.push_web_config is None


def test_the_service_worker_is_served_from_the_site_root_and_only_opens_admin_pages():
    response = client.get("/service-worker.js")
    assert response.status_code == 200 and "javascript" in response.headers["content-type"]
    assert response.headers["cache-control"] == "no-cache"
    assert 'addEventListener("push"' in response.text and 'addEventListener("notificationclick"' in response.text
    assert 'startsWith("/admin/")' in response.text
    assert "importScripts" not in response.text and "gstatic" not in response.text  # no Firebase code inside the worker


def test_push_js_registers_the_root_worker_for_the_admin_area_only():
    js = client.get("/static/admin/js/push.js").text
    assert 'SW_URL = "/service-worker.js"' in js and "scope: SW_SCOPE" in js and 'SW_SCOPE = "/admin/"' in js


def test_the_admin_page_and_push_js_carry_the_csrf_token_to_register():
    # The CSRF cookie is httponly, so script cannot read it: the page has to hand the token over.
    assert re.search(r'<meta name="csrf-token" content="[^"]+">', client.get("/admin/dashboard").text)
    assert '"X-CSRF-Token"' in client.get("/static/admin/js/push.js").text
