from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.core.auth import AdminUser, require_staff
from app.core.templating import templates
from app.services.admin import get_dashboard_context
from app.services.bookings import STATUS_LABELS

router = APIRouter(prefix="/admin", include_in_schema=False, dependencies=[Depends(require_staff)])


@router.get("")
async def admin_home() -> RedirectResponse:
    return RedirectResponse("/admin/dashboard")


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, admin: AdminUser = Depends(require_staff)) -> HTMLResponse:
    context = get_dashboard_context() | {"active_nav": "dashboard", "status_labels": STATUS_LABELS, "admin_role": admin.role.value}
    return templates.TemplateResponse(request, "admin/pages/dashboard.html", context)
