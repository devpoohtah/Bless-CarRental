"""Firebase Admin SDK start-up. Backend only: this uses the service account credentials."""

import logging
from functools import lru_cache
from pathlib import Path

import firebase_admin
from fastapi import HTTPException
from firebase_admin import credentials, firestore

from app.core import config

log = logging.getLogger(__name__)


def is_configured() -> bool:
    """True when a service account is set. Without it the app serves sample data only."""
    return bool(config.integrations.google_credentials)


def require_configured() -> None:
    """Guard for every write: without a database the admin is read-only sample data."""
    if not is_configured():
        raise HTTPException(status_code=503, detail="The database is not connected. Set GOOGLE_APPLICATION_CREDENTIALS in .env.")


@lru_cache(maxsize=1)
def init_app() -> firebase_admin.App:
    path = Path(config.integrations.google_credentials)
    if not path.is_absolute():
        path = config.PROJECT_ROOT / path
    if not path.is_file():
        raise RuntimeError(f"GOOGLE_APPLICATION_CREDENTIALS points to a missing file: {path}")
    options = {"projectId": config.integrations.firebase_project_id} if config.integrations.firebase_project_id else None
    return firebase_admin.initialize_app(credentials.Certificate(str(path)), options)


def get_db():
    return firestore.client(init_app())
