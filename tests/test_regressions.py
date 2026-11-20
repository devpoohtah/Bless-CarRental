"""Regression tests for bugs found in the 8552ee0 audit."""

import re
import types

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.testclient import TestClient

import app.api.routes.auth as auth_route
from app.core.csrf import CSRFMiddleware
from tests.test_admin import client as admin_client


def test_csrf_middleware_does_not_swallow_the_form_body():
    """Reading the form to check the token used to leave the route with empty fields."""
    app = FastAPI()
    app.add_middleware(CSRFMiddleware)

    @app.get("/admin/x")
    def page():
        return {"ok": True}

    @app.post("/admin/x")
    def save(name: str = Form(""), image: UploadFile | None = File(None)):
        return {"name": name, "bytes": len(image.file.read()) if image else None}

    c = TestClient(app)
    c.get("/admin/x")
    token = c.cookies.get("csrf_token")
    r = c.post("/admin/x", data={"csrf_token": token, "name": "Island Tour"},
               files={"image": ("a.jpg", b"x" * 5000)})
    assert r.json() == {"name": "Island Tour", "bytes": 5000}
    assert c.post("/admin/x", data={"csrf_token": "wrong", "name": "Bad"}).status_code == 403


def test_admin_inline_script_nonce_matches_the_csp_header():
    r = admin_client.get("/admin/dashboard")
    header_nonce = re.search(r"'nonce-([^']+)'", r.headers["content-security-policy"]).group(1)
    nonces = re.findall(r'<script nonce="([^"]*)">', r.text)
    assert nonces and all(n == header_nonce for n in nonces)


def test_session_errors_are_json_so_the_login_page_can_show_them(monkeypatch):
    monkeypatch.setattr(auth_route.firebase, "is_configured", lambda: True)
    monkeypatch.setattr(auth_route.turnstile, "passed", lambda token, ip: False)
    r = admin_client.post("/admin/session", data={"id_token": "x"})
    assert r.status_code == 403 and r.headers["content-type"].startswith("application/json")
    assert r.json()["detail"]["code"] == "turnstile"
