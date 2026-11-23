"""Booking management and the booking calendar."""

import logging
from datetime import date

from fastapi import APIRouter, BackgroundTasks, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response

from app.core.auth import AdminUser, require_admin, require_staff
from app.core.templating import notice_for, templates
from app.db.firebase import require_configured
from app.schemas.forms import BookingInput, validate
from app.services import bookings as service
from app.services import licenses, mailer
from app.services.errors import FormError

log = logging.getLogger(__name__)
router = APIRouter(prefix="/admin", include_in_schema=False, dependencies=[Depends(require_staff)])

LABELS = {
    "status_labels": service.STATUS_LABELS,
    "payment_labels": service.PAYMENT_LABELS,
    "type_labels": service.TYPE_LABELS,
}


def render(request: Request, template: str, active_nav: str, admin: AdminUser, status_code: int = 200, **context) -> HTMLResponse:
    context |= LABELS | {"active_nav": active_nav, "notice": notice_for(request), "errors": context.get("errors", []), "admin_role": admin.role.value}
    return templates.TemplateResponse(request, f"admin/pages/{template}", context, status_code=status_code)


def _booking_or_404(booking_id: str):
    booking = service.get_booking(booking_id)
    if booking is None:
        raise HTTPException(status_code=404, detail="Booking not found")
    return booking


def _detail(request: Request, admin: AdminUser, booking, status_code: int = 200, errors: list[str] | None = None) -> HTMLResponse:
    return render(request, "booking_detail.html", "bookings", admin, status_code, booking=booking, errors=errors or [],
                  next_options=[(s, service.STATUS_LABELS[s]) for s in service.NEXT_STATUSES[booking.status]],
                  history=list(reversed(booking.history)))


@router.get("/bookings", response_class=HTMLResponse)
def bookings(request: Request, admin: AdminUser = Depends(require_staff), type: str | None = None, search: str | None = None) -> HTMLResponse:
    service.purge_expired_licenses_if_due()
    booking_type = type if type in ("car", "tour") else None
    return render(request, "bookings.html", "bookings", admin,
                  bookings=service.list_bookings(booking_type, search), active_type=booking_type, search=search)


# /bookings/new must be declared before /bookings/{booking_id}.
@router.get("/bookings/new", response_class=HTMLResponse)
def booking_new(request: Request, admin: AdminUser = Depends(require_staff)) -> HTMLResponse:
    return render(request, "booking_form.html", "bookings", admin, form={}, item_choices=service.item_choices())


@router.post("/bookings/new")
def booking_create(
    request: Request, admin: AdminUser = Depends(require_staff), item: str = Form(""), customer_name: str = Form(""), customer_phone: str = Form(""),
    customer_email: str = Form(""), start_date: str = Form(""), end_date: str = Form(""),
    details: str = Form(""), payment_status: str = Form("unpaid"),
):
    require_configured()
    raw = dict(item=item, customer_name=customer_name, customer_phone=customer_phone,
               customer_email=customer_email, start_date=start_date, end_date=end_date,
               details=details, payment_status=payment_status)
    data, errors = validate(BookingInput, raw)
    if data is not None:
        try:
            booking_id = service.create_booking(data)
            return RedirectResponse(f"/admin/bookings/{booking_id}?notice=created", status_code=303)
        except FormError as exc:
            errors = [str(exc)]
    return render(request, "booking_form.html", "bookings", admin, 422, form=raw, errors=errors,
                  item_choices=service.item_choices())


@router.get("/pending-count")
def pending_count() -> JSONResponse:
    """Polled by the sidebar badge. Behind the same admin sign-in as every /admin page."""
    try:
        return JSONResponse({"pending": service.pending_count()})
    except Exception:
        log.exception("Could not count pending bookings")
        return JSONResponse({"pending": None}, status_code=503)


@router.get("/bookings/{booking_id}", response_class=HTMLResponse)
def booking_detail(request: Request, booking_id: str, admin: AdminUser = Depends(require_staff)) -> HTMLResponse:
    return _detail(request, admin, _booking_or_404(booking_id))


@router.get("/bookings/{booking_id}/license/front")
def booking_license_front(booking_id: str) -> Response:
    """The customer's license front photo, for signed-in admins only. Never cached."""
    booking = _booking_or_404(booking_id)
    image = licenses.load_front(booking_id) if booking.license_on_file else None
    if image is None:
        raise HTTPException(status_code=404, detail="No license front photo for this booking")
    return Response(image, media_type=licenses.CONTENT_TYPE, headers={
        "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
        "Content-Disposition": 'inline; filename="license-front.webp"'})

@router.get("/bookings/{booking_id}/license/back")
def booking_license_back(booking_id: str) -> Response:
    """The customer's license back photo, for signed-in admins only. Never cached."""
    booking = _booking_or_404(booking_id)
    image = licenses.load_back(booking_id) if booking.license_back_on_file else None
    if image is None:
        raise HTTPException(status_code=404, detail="No license back photo for this booking")
    return Response(image, media_type=licenses.CONTENT_TYPE, headers={
        "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
        "Content-Disposition": 'inline; filename="license-back.webp"'})

@router.get("/bookings/{booking_id}/license")
def booking_license(booking_id: str) -> Response:
    """Backward compat: returns front photo."""
    return booking_license_front(booking_id)


@router.post("/bookings/{booking_id}/license/delete", dependencies=[Depends(require_admin)])
def booking_license_delete(request: Request, booking_id: str, admin: AdminUser = Depends(require_admin)):
    """Deletes the photo now, for example when the customer asks for it. Admin only."""
    require_configured()
    booking = _booking_or_404(booking_id)
    try:
        service.delete_license(booking)
    except FormError as exc:
        return _detail(request, admin, booking, 422, [str(exc)])
    return RedirectResponse(f"/admin/bookings/{booking_id}?notice=license", status_code=303)


@router.post("/bookings/{booking_id}/status")
def booking_status(request: Request, background: BackgroundTasks, booking_id: str, status: str = Form(""), admin: AdminUser = Depends(require_staff)):
    require_configured()
    booking = _booking_or_404(booking_id)
    try:
        updated = service.change_status(booking, status)
    except FormError as exc:
        return _detail(request, admin, booking, 422, [str(exc)])
    if updated.status == "approved":
        background.add_task(mailer.notify_booking_approved, updated)  # after the response; a failed email never blocks this
    return RedirectResponse(f"/admin/bookings/{booking_id}?notice=status", status_code=303)


@router.post("/bookings/{booking_id}/payment")
def booking_payment(request: Request, booking_id: str, payment_status: str = Form(""), payment_type: str = Form(""), admin: AdminUser = Depends(require_staff)):
    require_configured()
    booking = _booking_or_404(booking_id)
    try:
        service.change_payment(booking, payment_status, payment_type or None)
    except FormError as exc:
        return _detail(request, admin, booking, 422, [str(exc)])
    return RedirectResponse(f"/admin/bookings/{booking_id}?notice=payment", status_code=303)


@router.post("/bookings/{booking_id}/downpayment")
def booking_downpayment(request: Request, booking_id: str, amount: int = Form(...), payment_type: str = Form(...), admin: AdminUser = Depends(require_staff)):
    require_configured()
    booking = _booking_or_404(booking_id)
    try:
        service.record_downpayment(booking, amount, payment_type)
    except FormError as exc:
        return _detail(request, admin, booking, 422, [str(exc)])
    return RedirectResponse(f"/admin/bookings/{booking_id}?notice=downpayment", status_code=303)


@router.post("/bookings/{booking_id}/payment/record")
def booking_record_remaining_payment(request: Request, booking_id: str, amount: int = Form(...), payment_type: str = Form(""), admin: AdminUser = Depends(require_staff)):
    require_configured()
    booking = _booking_or_404(booking_id)
    try:
        service.record_remaining_payment(booking, amount, payment_type or None)
    except FormError as exc:
        return _detail(request, admin, booking, 422, [str(exc)])
    return RedirectResponse(f"/admin/bookings/{booking_id}?notice=payment_recorded", status_code=303)


@router.post("/bookings/{booking_id}/additional-payment")
def booking_additional_payment(request: Request, booking_id: str, amount: int = Form(...), payment_type: str = Form(...), description: str = Form(...), admin: AdminUser = Depends(require_staff)):
    require_configured()
    booking = _booking_or_404(booking_id)
    try:
        service.record_additional_payment(booking, amount, payment_type, description)
    except FormError as exc:
        return _detail(request, admin, booking, 422, [str(exc)])
    return RedirectResponse(f"/admin/bookings/{booking_id}?notice=additional_payment", status_code=303)


@router.get("/calendar", response_class=HTMLResponse)
def booking_calendar(request: Request, admin: AdminUser = Depends(require_staff), month: str | None = None) -> HTMLResponse:
    today = date.today()
    view = service.month_view(service.parse_month(month, today), today)
    return render(request, "calendar.html", "calendar", admin, **view)