from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.core.templating import templates
from app.services.admin import get_dashboard_context

router = APIRouter(prefix="/admin", include_in_schema=False)


@router.get("")
async def admin_home() -> RedirectResponse:
    # Temporary: send /admin to the dashboard. Point this at /admin/login once login exists.
    return RedirectResponse("/admin/dashboard")


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request) -> HTMLResponse:
    context = get_dashboard_context() | {"active_nav": "dashboard"}
    return templates.TemplateResponse(request, "admin/pages/dashboard.html", context)
