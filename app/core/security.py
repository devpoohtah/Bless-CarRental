"""Security headers middleware. Runs on every response."""

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to every response.

    CSP is restrictive but allows the CDN fonts and Cloudinary images we use.
    """

    CSP = (
        "default-src 'self'; "
        "script-src 'self' https://cdn.jsdelivr.net https://challenges.cloudflare.com; "
        "style-src 'self' https://fonts.googleapis.com https://cdn.jsdelivr.net; "
        "font-src 'self' https://fonts.gstatic.com https://cdn.jsdelivr.net; "
        "img-src 'self' https: data:; "
        "connect-src 'self' https://challenges.cloudflare.com https://*.firebaseio.com https://identitytoolkit.googleapis.com; "
        "frame-src https://challenges.cloudflare.com; "
        "base-uri 'self'; "
        "form-action 'self';"
    )

    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)

        # HSTS: 1 year, include subdomains, preload-ready
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains; preload"

        # Prevent clickjacking
        response.headers["X-Frame-Options"] = "DENY"

        # Prevent MIME sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"

        # Referrer policy: same-origin for privacy, but allow cross-origin for our own assets
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # Permissions policy: restrict browser features we don't use
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=(), payment=()"

        # CSP
        response.headers["Content-Security-Policy"] = self.CSP

        return response