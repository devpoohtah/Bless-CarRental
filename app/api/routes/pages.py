from datetime import date

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, HTMLResponse

from app.core.config import STATIC_DIR
from app.core.templating import templates
from app.services.content import get_home_context

router = APIRouter()


@router.get("/", response_class=HTMLResponse, include_in_schema=False)
def home(request: Request) -> HTMLResponse:
    context = get_home_context() | {"current_year": date.today().year}
    return templates.TemplateResponse(request, "customer/pages/home.html", context)


@router.get("/favicon.ico", include_in_schema=False)
async def favicon() -> FileResponse:
    # Browsers request /favicon.ico on their own; serve the SVG favicon instead of a 404.
    return FileResponse(STATIC_DIR / "shared" / "img" / "favicon.svg", media_type="image/svg+xml")
