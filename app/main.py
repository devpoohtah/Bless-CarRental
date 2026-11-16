from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.routes import admin, admin_bookings, admin_services, pages
from app.core.config import STATIC_DIR, settings


def create_app() -> FastAPI:
    app = FastAPI(title=settings.business_name)
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    app.include_router(pages.router)
    app.include_router(admin.router)
    app.include_router(admin_services.router)
    app.include_router(admin_bookings.router)
    return app


app = create_app()
