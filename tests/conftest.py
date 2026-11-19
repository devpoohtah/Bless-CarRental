from dataclasses import replace

import pytest

from app.core import config
from app.core.auth import AdminUser, require_admin
from app.api.routes import bookings as bookings_route
from app.core.ratelimit import RateLimiter
from app.db import firebase
from app.services import otp
from app.main import app
from tests.fakes import FakeDb


@pytest.fixture(autouse=True)
def isolate_from_real_services(monkeypatch):
    """Tests must never reach the real Firebase, Cloudinary or Telegram, even when .env has credentials.
    Without a database the app serves sample data; admin pages are opened as a test admin."""
    monkeypatch.setattr(config, "integrations", replace(
        config.integrations, google_credentials="", cloudinary_cloud_name="", cloudinary_api_key="",
        cloudinary_api_secret="", admin_emails=frozenset(), telegram_bot_token="", telegram_chat_id="",
        admin_base_url="", firebase_vapid_key="", otp_delivery="", gmail_user="", gmail_app_password="",
        resend_api_key="", turnstile_site_key="", turnstile_secret_key=""))
    app.dependency_overrides[require_admin] = lambda: AdminUser(email="admin@example.com", uid="test-uid")
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def fake_db(monkeypatch) -> FakeDb:
    """Connects the app to an in-memory Firestore."""
    db = FakeDb()
    monkeypatch.setattr(config, "integrations", replace(config.integrations, google_credentials="fake.json"))
    monkeypatch.setattr(firebase, "get_db", lambda: db)
    return db


@pytest.fixture
def real_auth():
    """Turns the admin bypass off so the real sign-in checks run."""
    app.dependency_overrides.pop(require_admin, None)


@pytest.fixture
def simulated_otp(monkeypatch):
    """Booking codes without email: OTP_DELIVERY=simulated (fixed code 123456), a fresh code store, roomy limits.
    Requires ENVIRONMENT=development so simulated mode is allowed."""
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setattr(config, "integrations", replace(config.integrations, otp_delivery="simulated"))
    monkeypatch.setattr(otp, "store", otp.OtpStore())
    monkeypatch.setattr(bookings_route, "email_limiter", RateLimiter(max_hits=500, window_seconds=3600))
    monkeypatch.setattr(bookings_route, "limiter", RateLimiter(max_hits=500, window_seconds=600))
