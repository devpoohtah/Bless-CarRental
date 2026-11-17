import logging

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import admin, admin_bookings, admin_services, auth, bookings, pages
from app.core.auth import LoginRequired
from app.core.config import STATIC_DIR, settings
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
    return app


app = create_app()
