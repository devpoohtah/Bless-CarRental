"""Admin login, session and logout. These routes are the only /admin routes without the
require_admin dependency."""

import sys

from fastapi import APIRouter, Form, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel

from app.core import auth
from app.core.ratelimit import RateLimiter
from app.core.templating import templates
from app.db import firebase
from app.services import turnstile

router = APIRouter(prefix="/admin", include_in_schema=False)

# Rate limit for session creation: 10 attempts per IP per 10 minutes
session_limiter = RateLimiter(max_hits=10, window_seconds=600)


class SessionRequest(BaseModel):
    id_token: str


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "admin/pages/login.html", {})


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _error(status: int, msg: str, code: str = "") -> HTTPException:
    return HTTPException(status_code=status, detail={"message": msg, "code": code})


@router.post("/session")
def create_session(
    request: Request, response: Response,
    id_token: str = Form(""),
    cf_turnstile_response: str = Form("", alias="cf-turnstile-response"),
) -> dict:
    """Called by the login page after Firebase sign-in. Form (not JSON) so it carries CSRF + Turnstile."""
    client = _client_ip(request)

    if not session_limiter.allow(client):
        raise _error(429, "Too many sign-in attempts. Please wait a few minutes.", "rate_limited")

    if not firebase.is_configured():
        raise _error(503, "The database is not connected.")

    # Turnstile: if configured, a valid token is required. Fails closed.
    if not turnstile.passed(cf_turnstile_response, client):
        raise _error(403, "We could not confirm you are human. Please try again.", "turnstile")

    try:
        cookie = auth.create_session(id_token)
    except auth.AUTH_ERRORS:
        raise _error(401, "Sign-in could not be verified. Try again.")
    if cookie is None:
        raise _error(403, "This account is not allowed to use the admin. It must be on the admin list, have a verified email, and be granted admin access.")

    response.set_cookie(
        auth.COOKIE_NAME, cookie, max_age=int(auth.SESSION_LENGTH.total_seconds()),
        httponly=True, secure=request.url.scheme == "https", samesite="lax", path=auth.COOKIE_PATH,
    )
    return {"ok": True}


@router.post("/logout")
async def logout() -> RedirectResponse:
    response = RedirectResponse("/admin/login", status_code=303)
    response.delete_cookie(auth.COOKIE_NAME, path=auth.COOKIE_PATH)
    return response