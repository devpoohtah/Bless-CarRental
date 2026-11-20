import logging
import os

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import admin, admin_bookings, admin_push, admin_services, auth, bookings, pages
from app.core.auth import LoginRequired
from app.core.config import STATIC_DIR, integrations, settings
from app.core.csrf import CSRFMiddleware, csrf_token
from app.core.security import SecurityHeadersMiddleware
from app.core.templating import templates
from app.db import firebase

log = logging.getLogger(__name__)


def _is_dev() -> bool:
    """True only when ENVIRONMENT is explicitly development/dev/local. Unset = production."""
    env = os.environ.get("ENVIRONMENT", "").strip().lower()
    return env in ("development", "dev", "local")


def is_admin_request(request: Request) -> bool:
    return request.url.path.startswith("/admin")


def create_app() -> FastAPI:
    # API docs only in dev
    dev = _is_dev()
    app = FastAPI(
        title=settings.business_name,
        docs_url="/docs" if dev else None,
        redoc_url="/redoc" if dev else None,
        openapi_url="/openapi.json" if dev else None,
    )
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    app.include_router(pages.router)
    app.include_router(bookings.router)
    app.include_router(auth.router)
    app.include_router(admin.router)
    app.include_router(admin_services.router)
    app.include_router(admin_bookings.router)
    app.include_router(admin_push.router)

    @app.get("/service-worker.js", include_in_schema=False)
    def service_worker() -> FileResponse:
        # Served from the site root, not /static/, so it can be registered for the whole /admin/ area.
        # no-cache: the browser re-checks it on every visit, so a fixed worker is picked up at once.
        return FileResponse(STATIC_DIR / "admin" / "js" / "service-worker.js", media_type="text/javascript",
                            headers={"Cache-Control": "no-cache"})

    # Middleware order matters: first added = outermost = runs first on request, last on response
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(CSRFMiddleware)

    @app.exception_handler(LoginRequired)
    async def send_to_login(request: Request, exc: LoginRequired) -> RedirectResponse:
        return RedirectResponse("/admin/login", status_code=303)

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException) -> HTMLResponse:
        status = exc.status_code
        if isinstance(exc.detail, dict):
            # Structured detail ({"message", "code"}) is for fetch() callers such as the login page.
            return JSONResponse({"detail": exc.detail}, status_code=status)
        admin = is_admin_request(request)
        template_dir = "admin/errors" if admin else "customer/errors"
        template = f"{template_dir}/{status}.html"
        fallback = f"{template_dir}/500.html"
        context = {"active_nav": "dashboard" if admin else None}
        try:
            return templates.TemplateResponse(request, template, context, status_code=status)
        except Exception:
            # Fallback to 500 if error template not found
            return templates.TemplateResponse(request, fallback, context, status_code=500)

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> HTMLResponse:
        log.exception("Unhandled error")
        admin = is_admin_request(request)
        template_dir = "admin/errors" if admin else "customer/errors"
        context = {"active_nav": "dashboard" if admin else None}
        return templates.TemplateResponse(
            request,
            f"{template_dir}/500.html",
            context,
            status_code=500,
        )

    @app.middleware("http")
    async def no_store_for_admin(request: Request, call_next):
        # Keep admin pages out of the browser cache so Back after sign-out shows nothing.
        response = await call_next(request)
        if request.url.path.startswith("/admin"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.middleware("http")
    async def custom_404_handler(request: Request, call_next):
        # Intercept 404 responses and render custom error page
        response = await call_next(request)
        if response.status_code == 404:
            admin = is_admin_request(request)
            template_dir = "admin/errors" if admin else "customer/errors"
            context = {"active_nav": "dashboard" if admin else None}
            try:
                return templates.TemplateResponse(
                    request, f"{template_dir}/404.html", context, status_code=404
                )
            except Exception:
                pass  # Fall through to default 404
        return response

    if firebase.is_configured():
        firebase.init_app()  # fail at start-up, not on the first request, if the key file is wrong
    else:
        log.warning("GOOGLE_APPLICATION_CREDENTIALS is not set: serving sample data, admin sign-in disabled.")
    mode = integrations.otp_mode
    if mode == "simulated":
        log.warning("OTP_DELIVERY=simulated: booking codes are NOT emailed and 123456 is accepted. Never use this in production.")
    elif not mode:
        log.warning("No way to send booking codes (set OTP_DELIVERY and its credentials): online booking is turned off.")
    if not integrations.turnstile_ready:
        log.warning("TURNSTILE_SITE_KEY / TURNSTILE_SECRET_KEY are not set: the booking form has no bot challenge.")
    return app


app = create_app()
