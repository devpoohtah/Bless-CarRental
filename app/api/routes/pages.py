from datetime import date

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, HTMLResponse

from app.core.clock import today_ph
from app.core.config import STATIC_DIR
from app.core.templating import templates
from app.services import content
from app.services.content import get_home_context

router = APIRouter()


@router.get("/", response_class=HTMLResponse, include_in_schema=False)
def home(request: Request) -> HTMLResponse:
    context = get_home_context() | {"current_year": date.today().year, "today_iso": today_ph().isoformat()}
    return templates.TemplateResponse(request, "customer/pages/home.html", context)


def _catalog_page(request: Request, template: str, **context) -> HTMLResponse:
    """The full car and tour lists. Same navbar as the landing page, whose links point back to its sections."""
    context |= {"nav_links": content.NAV_LINKS, "nav_base": "/", "current_year": date.today().year,
                "today_iso": today_ph().isoformat()}
    return templates.TemplateResponse(request, f"customer/pages/{template}", context)


@router.get("/cars", response_class=HTMLResponse, include_in_schema=False)
def cars(request: Request) -> HTMLResponse:
    return _catalog_page(request, "cars.html", vehicles=content.list_vehicles())


@router.get("/tours", response_class=HTMLResponse, include_in_schema=False)
def tours(request: Request) -> HTMLResponse:
    return _catalog_page(request, "tours.html", tours=content.list_tours())


@router.get("/favicon.ico", include_in_schema=False)
async def favicon() -> FileResponse:
    # Browsers request /favicon.ico on their own; serve the SVG favicon instead of a 404.
    return FileResponse(STATIC_DIR / "shared" / "img" / "favicon.svg", media_type="image/svg+xml")
