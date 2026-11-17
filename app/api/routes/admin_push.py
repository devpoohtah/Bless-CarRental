"""Saves the browser token that desktop alerts are sent to. Admin only."""

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.core.auth import AdminUser, require_admin
from app.db.firebase import require_configured
from app.services import push

router = APIRouter(prefix="/admin/push", include_in_schema=False, dependencies=[Depends(require_admin)])


class Registration(BaseModel):
    # FCM tokens are long strings of letters, digits, "-", "_" and ":".
    token: str = Field(min_length=20, max_length=4096, pattern=r"^[A-Za-z0-9_:\-]+$")


@router.post("/register")
def register(body: Registration, admin: AdminUser = Depends(require_admin)) -> JSONResponse:
    require_configured()
    push.register_token(body.token, admin.email)
    return JSONResponse({"ok": True})
