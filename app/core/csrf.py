"""CSRF protection middleware.

- Generates a token per session (stored in a cookie, read by JS for forms)
- Validates on POST/PUT/DELETE/PATCH for /admin and /book routes
- Exempts: /admin/session (JSON, Firebase ID token), /admin/logout (POST but safe), static files
"""

import secrets
from typing import Callable

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.status import HTTP_403_FORBIDDEN

from app.core.config import settings

CSRF_COOKIE_NAME = "csrf_token"
CSRF_HEADER_NAME = "X-CSRF-Token"
CSRF_FORM_FIELD = "csrf_token"


def generate_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def get_csrf_token(request: Request) -> str:
    """Get or create a CSRF token for this session."""
    token = request.cookies.get(CSRF_COOKIE_NAME)
    if not token:
        token = generate_csrf_token()
    return token


def set_csrf_cookie(response: Response, token: str, secure: bool) -> None:
    response.set_cookie(
        CSRF_COOKIE_NAME,
        token,
        max_age=60 * 60 * 24,  # 24h cookie lifetime
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
    )


EXEMPT_PATHS = {
    "/admin/session",   # JSON, protected by Firebase ID token
    "/admin/logout",    # POST but no side effect beyond session clear
    "/health",          # optional health check
}


def is_exempt(path: str) -> bool:
    if path in EXEMPT_PATHS:
        return True
    # Static files and API docs
    if path.startswith("/static") or path.startswith("/docs") or path.startswith("/openapi"):
        return True
    return False


def needs_csrf(method: str) -> bool:
    return method.upper() in ("POST", "PUT", "DELETE", "PATCH")


def is_protected_route(path: str) -> bool:
    """Routes that require CSRF validation."""
    return path.startswith("/admin") or path.startswith("/book")


class CSRFMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable):
        path = request.url.path
        method = request.method

        # Skip entirely for exempt paths
        if is_exempt(path):
            return await call_next(request)

        # Generate token for this session (available to templates via request.state)
        token = get_csrf_token(request)
        request.state.csrf_token = token

        # Validate on state-changing requests to protected routes
        if needs_csrf(method) and is_protected_route(path):
            # Check header first (for JS submissions), then form field
            submitted = request.headers.get(CSRF_HEADER_NAME)
            if not submitted and method == "POST":
                # Parse form without consuming: use cached _form if available, else parse and cache
                if hasattr(request, "_form") and request._form is not None:
                    form = request._form
                else:
                    form = await request.form()
                    # Ensure it's cached for downstream handlers
                    request._form = form
                submitted = form.get(CSRF_FORM_FIELD)

            if not submitted or not secrets.compare_digest(submitted, token):
                return JSONResponse(
                    {"error": "Invalid CSRF token. Please refresh the page and try again."},
                    status_code=HTTP_403_FORBIDDEN,
                )

        response = await call_next(request)

        # Set cookie on every response so it's always fresh
        secure = request.url.scheme == "https"
        set_csrf_cookie(response, token, secure)

        return response


def csrf_token(request=None) -> str:
    """Template helper: returns the current CSRF token.

    If request is not available (e.g. in tests) or is Undefined, generates a new token.
    """
    # Handle Jinja2 Undefined - accessing any attribute raises UndefinedError
    try:
        if request is None or not hasattr(request, "state"):
            return generate_csrf_token()
    except Exception:
        return generate_csrf_token()
    return getattr(request.state, "csrf_token", get_csrf_token(request))