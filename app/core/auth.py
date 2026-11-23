"""Admin sign-in. Firebase Auth proves who the person is; ADMIN_EMAILS/STAFF_EMAILS decides whether that
person may use the admin. Every check happens here on the server, never in the browser.
"""

from dataclasses import dataclass
from datetime import timedelta
from enum import Enum

from fastapi import HTTPException, Request
from firebase_admin import auth as fb_auth
from firebase_admin.exceptions import FirebaseError

from app.core import config
from app.db import firebase

COOKIE_NAME = "bless_admin_session"
COOKIE_PATH = "/admin"
SESSION_LENGTH = timedelta(hours=12)

AUTH_ERRORS = (ValueError, FirebaseError)


class Role(str, Enum):
    ADMIN = "admin"
    STAFF = "staff"


@dataclass(frozen=True)
class AdminUser:
    email: str
    uid: str
    role: Role


class LoginRequired(Exception):
    """Raised by require_admin/require_staff; main.py turns it into a redirect to /admin/login."""


class Forbidden(Exception):
    """Raised when an authenticated user lacks the required role (e.g., staff hitting admin-only route)."""


def _role_from_claims(claims: dict) -> Role | None:
    """Determine role from custom claims. Admin claim wins if both are present."""
    if claims.get("admin") is True:
        return Role.ADMIN
    if claims.get("staff") is True:
        return Role.STAFF
    return None


def is_allowed_admin(claims: dict) -> bool:
    """On the admin list AND verified email AND has admin custom claim."""
    email = str(claims.get("email") or "").lower()
    return (
        bool(claims.get("email_verified"))
        and email in config.integrations.admin_emails
        and claims.get("admin") is True
    )


def is_allowed_staff(claims: dict) -> bool:
    """On the staff list AND verified email AND has staff custom claim (and NOT admin)."""
    email = str(claims.get("email") or "").lower()
    return (
        bool(claims.get("email_verified"))
        and email in config.integrations.staff_emails
        and claims.get("staff") is True
        and claims.get("admin") is not True  # admin claim never grants staff; admin wins
    )


def require_admin(request: Request) -> AdminUser:
    """Dependency for admin-only /admin routes. Verifies the session cookie with Firebase."""
    cookie = request.cookies.get(COOKIE_NAME)
    if not cookie or not firebase.is_configured():
        raise LoginRequired
    try:
        firebase.init_app()
        claims = fb_auth.verify_session_cookie(cookie, check_revoked=True)
    except AUTH_ERRORS:
        raise LoginRequired from None
    if not is_allowed_admin(claims):
        raise LoginRequired
    return AdminUser(email=claims["email"], uid=claims["uid"], role=Role.ADMIN)


def require_staff(request: Request) -> AdminUser:
    """Dependency for staff-allowed /admin routes (admin OR staff)."""
    cookie = request.cookies.get(COOKIE_NAME)
    if not cookie or not firebase.is_configured():
        raise LoginRequired
    try:
        firebase.init_app()
        claims = fb_auth.verify_session_cookie(cookie, check_revoked=True)
    except AUTH_ERRORS:
        raise LoginRequired from None
    if is_allowed_admin(claims):
        return AdminUser(email=claims["email"], uid=claims["uid"], role=Role.ADMIN)
    if is_allowed_staff(claims):
        return AdminUser(email=claims["email"], uid=claims["uid"], role=Role.STAFF)
    raise LoginRequired


def create_session(id_token: str) -> str | None:
    """Exchange a fresh Firebase ID token for a session cookie. None if the account is not allowed.

    Raises one of AUTH_ERRORS when the token itself is invalid.
    """
    firebase.init_app()
    claims = fb_auth.verify_id_token(id_token)
    if not (is_allowed_admin(claims) or is_allowed_staff(claims)):
        return None
    return fb_auth.create_session_cookie(id_token, expires_in=SESSION_LENGTH)
