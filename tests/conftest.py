from dataclasses import replace

import pytest

from app.core import config
from app.core.auth import AdminUser, require_admin
from app.db import firebase
from app.main import app
from tests.fakes import FakeDb


@pytest.fixture(autouse=True)
def isolate_from_real_services(monkeypatch):
    """Tests must never reach the real Firebase or Cloudinary, even when .env has credentials.
    Without a database the app serves sample data; admin pages are opened as a test admin."""
    monkeypatch.setattr(config, "integrations", replace(
        config.integrations, google_credentials="", cloudinary_cloud_name="", cloudinary_api_key="",
        cloudinary_api_secret="", admin_emails=frozenset()))
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
