from datetime import date, timedelta

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse, Response

from app.core.clock import today_ph
from app.core.config import STATIC_DIR
from app.core.templating import absolute_url, templates
from app.services import content
from app.services.content import get_home_context

router = APIRouter()

MAX_BOOKING_DAYS = 730  # 2 years, matches Flatpickr maxDate


def _base_context() -> dict:
    today = today_ph()
    return {
        "current_year": date.today().year,
        "today_iso": today.isoformat(),
        "max_date_iso": (today + timedelta(days=MAX_BOOKING_DAYS)).isoformat(),
    }


@router.get("/", response_class=HTMLResponse, include_in_schema=False)
def home(request: Request) -> HTMLResponse:
    context = get_home_context() | _base_context()
    return templates.TemplateResponse(request, "customer/pages/home.html", context)


def _catalog_page(request: Request, template: str, **context) -> HTMLResponse:
    """The full car and tour lists. Same navbar as the landing page, whose links point back to its sections."""
    context |= {"nav_links": content.NAV_LINKS, "nav_base": "/"} | _base_context()
    return templates.TemplateResponse(request, f"customer/pages/{template}", context)


@router.get("/cars", response_class=HTMLResponse, include_in_schema=False)
def cars(request: Request) -> HTMLResponse:
    return _catalog_page(request, "cars.html", vehicles=content.list_vehicles())


@router.get("/cars/{car_id}", response_class=HTMLResponse, include_in_schema=False)
def car_detail(request: Request, car_id: str) -> HTMLResponse:
    vehicle = next((v for v in content.list_vehicles() if v.id == car_id), None)
    if vehicle is None:
        raise HTTPException(status_code=404, detail="Vehicle not found")
    return _catalog_page(request, "car_detail.html", vehicle=vehicle)


@router.get("/tours", response_class=HTMLResponse, include_in_schema=False)
def tours(request: Request) -> HTMLResponse:
    return _catalog_page(request, "tours.html", tours=content.list_tours())


@router.get("/favicon.ico", include_in_schema=False)
async def favicon() -> FileResponse:
    # Browsers request /favicon.ico on their own; serve the logo instead of a 404.
    return FileResponse(STATIC_DIR / "shared" / "img" / "bless-logo.webp", media_type="image/webp")


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
    car_paths = [f"/cars/{v.id}" for v in content.list_vehicles()]
    all_paths = paths + car_paths
    urls = "".join(f"<url><loc>{absolute_url(request, path)}</loc></url>" for path in all_paths)
    xml = f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>'
    return Response(xml, media_type="application/xml")
