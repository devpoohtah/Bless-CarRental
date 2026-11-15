from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.routes import pages
from app.core.config import STATIC_DIR, settings


def create_app() -> FastAPI:
    app = FastAPI(title=settings.business_name)
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    app.include_router(pages.router)
    return app


app = create_app()
