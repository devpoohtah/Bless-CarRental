import logging

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import admin, admin_bookings, admin_push, admin_services, auth, bookings, pages
from app.core.auth import LoginRequired
from app.core.config import STATIC_DIR, integrations, settings
from app.db import firebase

log = logging.getLogger(__name__)


def create_app() -> FastAPI:
    app = FastAPI(title=settings.business_name)
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    app.include_router(pages.router)
    app.include_router(bookings.router)
    app.include_router(auth.router)
    app.include_router(admin.router)
    app.include_router(admin_services.router)
    app.include_router(admin_bookings.router)
    app.include_router(admin_push.router)

    @app.exception_handler(LoginRequired)
    async def send_to_login(request: Request, exc: LoginRequired) -> RedirectResponse:
        return RedirectResponse("/admin/login", status_code=303)

    @app.middleware("http")
    async def no_store_for_admin(request: Request, call_next):
        # Keep admin pages out of the browser cache so Back after sign-out shows nothing.
        response = await call_next(request)
        if request.url.path.startswith("/admin"):
            response.headers["Cache-Control"] = "no-store"
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
