"""Admin sign-in. Firebase Auth proves who the person is; ADMIN_EMAILS decides whether that
person may use the admin. Every check happens here on the server, never in the browser.
"""

from dataclasses import dataclass
from datetime import timedelta

from fastapi import Request
from firebase_admin import auth as fb_auth
from firebase_admin.exceptions import FirebaseError

from app.core import config
from app.db import firebase

COOKIE_NAME = "bless_admin_session"
COOKIE_PATH = "/admin"
SESSION_LENGTH = timedelta(hours=12)

AUTH_ERRORS = (ValueError, FirebaseError)


@dataclass(frozen=True)
class AdminUser:
    email: str
    uid: str


class LoginRequired(Exception):
    """Raised by require_admin; main.py turns it into a redirect to /admin/login."""


def is_allowed(claims: dict) -> bool:
    """On the admin list AND a verified email, so an unverified account cannot claim an address."""
    email = str(claims.get("email") or "").lower()
    return bool(claims.get("email_verified")) and email in config.integrations.admin_emails


def require_admin(request: Request) -> AdminUser:
    """Dependency for every /admin page. Verifies the session cookie with Firebase."""
    cookie = request.cookies.get(COOKIE_NAME)
    if not cookie or not firebase.is_configured():
        raise LoginRequired
    try:
        firebase.init_app()
        claims = fb_auth.verify_session_cookie(cookie, check_revoked=True)
    except AUTH_ERRORS:
        raise LoginRequired from None
    if not is_allowed(claims):
        raise LoginRequired
    return AdminUser(email=claims["email"], uid=claims["uid"])


def create_session(id_token: str) -> str | None:
    """Exchange a fresh Firebase ID token for a session cookie. None if the account is not allowed.

    Raises one of AUTH_ERRORS when the token itself is invalid.
    """
    firebase.init_app()
    claims = fb_auth.verify_id_token(id_token)
    if not is_allowed(claims):
        return None
    return fb_auth.create_session_cookie(id_token, expires_in=SESSION_LENGTH)
