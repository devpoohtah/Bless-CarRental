from datetime import date

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse, Response

from app.core.clock import today_ph
from app.core.config import STATIC_DIR
from app.core.templating import absolute_url, templates
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


def _legal_page(request: Request, template: str) -> HTMLResponse:
    return _catalog_page(request, template, legal_is_draft=content.LEGAL_IS_DRAFT, legal_updated=content.LEGAL_UPDATED)


@router.get("/privacy", response_class=HTMLResponse, include_in_schema=False)
def privacy(request: Request) -> HTMLResponse:
    return _legal_page(request, "privacy.html")


@router.get("/terms", response_class=HTMLResponse, include_in_schema=False)
def terms(request: Request) -> HTMLResponse:
    return _legal_page(request, "terms.html")


@router.get("/robots.txt", response_class=PlainTextResponse, include_in_schema=False)
def robots(request: Request) -> PlainTextResponse:
    # Keep the admin area and the booking forms out of search results; point crawlers at the sitemap.
    lines = ["User-agent: *", "Disallow: /admin", "Disallow: /book", "", f"Sitemap: {absolute_url(request, '/sitemap.xml')}"]
    return PlainTextResponse("\n".join(lines) + "\n")


@router.get("/sitemap.xml", include_in_schema=False)
def sitemap(request: Request) -> Response:
    paths = ["/", "/tours", "/cars", "/privacy", "/terms"]
    urls = "".join(f"<url><loc>{absolute_url(request, path)}</loc></url>" for path in paths)
    xml = f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>'
    return Response(xml, media_type="application/xml")
