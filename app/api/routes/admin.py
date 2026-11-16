from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.core.auth import require_admin
from app.core.templating import templates
from app.services.admin import get_dashboard_context
from app.services.bookings import STATUS_LABELS

router = APIRouter(prefix="/admin", include_in_schema=False, dependencies=[Depends(require_admin)])


@router.get("")
async def admin_home() -> RedirectResponse:
    return RedirectResponse("/admin/dashboard")


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request) -> HTMLResponse:
    context = get_dashboard_context() | {"active_nav": "dashboard", "status_labels": STATUS_LABELS}
    return templates.TemplateResponse(request, "admin/pages/dashboard.html", context)
