"""Admin login, session and logout. These routes are the only /admin routes without the
require_admin dependency."""

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel

from app.core import auth
from app.core.templating import templates
from app.db import firebase

router = APIRouter(prefix="/admin", include_in_schema=False)


class SessionRequest(BaseModel):
    id_token: str


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "admin/pages/login.html", {})


@router.post("/session")
def create_session(payload: SessionRequest, request: Request, response: Response) -> dict:
    """Called by the login page after Firebase sign-in. JSON only, so a cross-site form
    cannot trigger it."""
    if not firebase.is_configured():
        raise HTTPException(status_code=503, detail="The database is not connected.")
    try:
        cookie = auth.create_session(payload.id_token)
    except auth.AUTH_ERRORS:
        raise HTTPException(status_code=401, detail="Sign-in could not be verified. Try again.") from None
    if cookie is None:
        raise HTTPException(
            status_code=403,
            detail="This account is not allowed to use the admin. It must be on the admin list and have a verified email.",
        )
    response.set_cookie(
        auth.COOKIE_NAME, cookie, max_age=int(auth.SESSION_LENGTH.total_seconds()),
        httponly=True, secure=request.url.scheme == "https", samesite="lax", path=auth.COOKIE_PATH,
    )
    return {"ok": True}


@router.post("/logout")
async def logout() -> RedirectResponse:
    response = RedirectResponse("/admin/login", status_code=303)
    response.delete_cookie(auth.COOKIE_NAME, path=auth.COOKIE_PATH)
    return response
