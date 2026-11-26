"""Security headers middleware. Runs on every response."""

import secrets
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response


# Base CSP without nonce - used for pages with third-party widgets (login)
LOGIN_CSP = (
    "default-src 'self'; "
    "script-src 'self' https://cdn.jsdelivr.net https://challenges.cloudflare.com https://www.gstatic.com https://apis.google.com 'unsafe-inline'; "
    "style-src 'self' https://fonts.googleapis.com https://cdn.jsdelivr.net 'unsafe-inline'; "
    "font-src 'self' https://fonts.gstatic.com https://cdn.jsdelivr.net; "
    "img-src 'self' https: data:; "
    "connect-src 'self' https://challenges.cloudflare.com https://*.challenges.cloudflare.com https://hagen.challenges.cloudflare.com https://brunhild.challenges.cloudflare.com https://*.alg13.dnstest.challenges.cloudflare.com https://*.mldsa44.dnstest.challenges.cloudflare.com https://*.firebaseio.com https://identitytoolkit.googleapis.com https://www.gstatic.com https://apis.google.com https://securetoken.googleapis.com https://ca1.cloudflarecaptcha.com https://ca2.cloudflarecaptcha.com https://dnstest.dev data:; "
    "frame-src https://challenges.cloudflare.com https://apis.google.com https://bless-rental.firebaseapp.com https://*.firebaseapp.com; "
    "worker-src 'self' blob:; "
    "base-uri 'self'; "
    "form-action 'self';"
)

# Strict CSP with nonce - used for all other pages
# Added Firestore origins for onSnapshot listener (connect-src) and Firebase SDK script origin (script-src)
# apis.google.com: the Firebase auth SDK loads its gapi helper script from there.
# challenges.cloudflare.com: the Turnstile widget on the booking forms (script, its iframe, and its checks).
# blob: needed for image upload preview (URL.createObjectURL)
STRICT_CSP_TEMPLATE = (
    "default-src 'self'; "
    "script-src 'self' https://cdn.jsdelivr.net https://challenges.cloudflare.com https://www.gstatic.com https://apis.google.com 'nonce-{nonce}'; "
    "style-src 'self' https://fonts.googleapis.com https://cdn.jsdelivr.net 'nonce-{nonce}'; "
    "font-src 'self' https://fonts.gstatic.com https://cdn.jsdelivr.net; "
    "img-src 'self' https: data: blob:; "
    "connect-src 'self' https://cdn.jsdelivr.net https://challenges.cloudflare.com https://firestore.googleapis.com https://securetoken.googleapis.com https://identitytoolkit.googleapis.com https://firebaseinstallations.googleapis.com https://fcmregistrations.googleapis.com; "
    "frame-src https://challenges.cloudflare.com https://bless-rental.firebaseapp.com; "
    "base-uri 'self'; "
    "form-action 'self';"
)

# Pages that need relaxed CSP for third-party widgets
RELAXED_CSP_PATHS = {"/admin/login"}


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to every response with nonce-based CSP."""

    async def dispatch(self, request: Request, call_next):
        # Generate nonce for this request
        nonce = secrets.token_urlsafe(16)
        request.state.csp_nonce = nonce

        # Choose CSP based on path
        path = request.url.path
        if path in RELAXED_CSP_PATHS:
            csp = LOGIN_CSP
        else:
            csp = STRICT_CSP_TEMPLATE.format(nonce=nonce)

        response: Response = await call_next(request)

        # HSTS: 1 year, include subdomains, preload-ready
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains; preload"

        # Prevent clickjacking
        response.headers["X-Frame-Options"] = "DENY"

        # Prevent MIME sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"

        # Referrer policy
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # Permissions policy
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=(), payment=()"

        # CSP
        response.headers["Content-Security-Policy"] = csp

        return response