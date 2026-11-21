"""Booking management and the booking calendar."""

import logging
from datetime import date

from fastapi import APIRouter, BackgroundTasks, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response

from app.core.auth import require_admin
from app.core.templating import notice_for, templates
from app.db.firebase import require_configured
from app.schemas.forms import BookingInput, validate
from app.services import bookings as service
from app.services import licenses, mailer
from app.services.errors import FormError

log = logging.getLogger(__name__)
router = APIRouter(prefix="/admin", include_in_schema=False, dependencies=[Depends(require_admin)])

LABELS = {
    "status_labels": service.STATUS_LABELS,
    "payment_labels": service.PAYMENT_LABELS,
    "type_labels": service.TYPE_LABELS,
    "driver_labels": service.DRIVER_LABELS,
}


def render(request: Request, template: str, active_nav: str, status_code: int = 200, **context) -> HTMLResponse:
    context |= LABELS | {"active_nav": active_nav, "notice": notice_for(request), "errors": context.get("errors", [])}
    return templates.TemplateResponse(request, f"admin/pages/{template}", context, status_code=status_code)


def _booking_or_404(booking_id: str):
    booking = service.get_booking(booking_id)
    if booking is None:
        raise HTTPException(status_code=404, detail="Booking not found")
    return booking


def _detail(request: Request, booking, status_code: int = 200, errors: list[str] | None = None) -> HTMLResponse:
    return render(request, "booking_detail.html", "bookings", status_code, booking=booking, errors=errors or [],
                  next_options=[(s, service.STATUS_LABELS[s]) for s in service.NEXT_STATUSES[booking.status]],
                  history=list(reversed(booking.history)))


@router.get("/bookings", response_class=HTMLResponse)
def bookings(request: Request, type: str | None = None) -> HTMLResponse:
    service.purge_expired_licenses_if_due()  # photos past their day are deleted here and when the app starts
    booking_type = type if type in ("car", "tour") else None
    return render(request, "bookings.html", "bookings",
                  bookings=service.list_bookings(booking_type), active_type=booking_type)


# /bookings/new must be declared before /bookings/{booking_id}.
@router.get("/bookings/new", response_class=HTMLResponse)
def booking_new(request: Request) -> HTMLResponse:
    return render(request, "booking_form.html", "bookings", form={}, item_choices=service.item_choices())


@router.post("/bookings/new")
def booking_create(
    request: Request, item: str = Form(""), customer_name: str = Form(""), customer_phone: str = Form(""),
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
    return render(request, "booking_form.html", "bookings", 422, form=raw, errors=errors,
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
def booking_detail(request: Request, booking_id: str) -> HTMLResponse:
    return _detail(request, _booking_or_404(booking_id))


@router.get("/bookings/{booking_id}/license")
def booking_license(booking_id: str) -> Response:
    """The customer's license photo, for signed-in admins only (the router requires it). Never cached."""
    booking = _booking_or_404(booking_id)
    image = licenses.load(booking_id) if booking.license_on_file else None
    if image is None:
        raise HTTPException(status_code=404, detail="No license photo for this booking")
    return Response(image, media_type=licenses.CONTENT_TYPE, headers={
        "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
        "Content-Disposition": 'inline; filename="license.webp"'})


@router.post("/bookings/{booking_id}/license/delete")
def booking_license_delete(request: Request, booking_id: str):
    """Deletes the photo now, for example when the customer asks for it."""
    require_configured()
    booking = _booking_or_404(booking_id)
    try:
        service.delete_license(booking)
    except FormError as exc:
        return _detail(request, booking, 422, [str(exc)])
    return RedirectResponse(f"/admin/bookings/{booking_id}?notice=license", status_code=303)


@router.post("/bookings/{booking_id}/status")
def booking_status(request: Request, background: BackgroundTasks, booking_id: str, status: str = Form("")):
    require_configured()
    booking = _booking_or_404(booking_id)
    try:
        updated = service.change_status(booking, status)
    except FormError as exc:
        return _detail(request, booking, 422, [str(exc)])
    if updated.status == "approved":
        background.add_task(mailer.notify_booking_approved, updated)  # after the response; a failed email never blocks this
    return RedirectResponse(f"/admin/bookings/{booking_id}?notice=status", status_code=303)


@router.post("/bookings/{booking_id}/payment")
def booking_payment(request: Request, booking_id: str, payment_status: str = Form(""), payment_type: str = Form("")):
    require_configured()
    booking = _booking_or_404(booking_id)
    try:
        service.change_payment(booking, payment_status, payment_type or None)
    except FormError as exc:
        return _detail(request, booking, 422, [str(exc)])
    return RedirectResponse(f"/admin/bookings/{booking_id}?notice=payment", status_code=303)


@router.get("/calendar", response_class=HTMLResponse)
def booking_calendar(request: Request, month: str | None = None) -> HTMLResponse:
    today = date.today()
    view = service.month_view(service.parse_month(month, today), today)
    return render(request, "calendar.html", "calendar", **view)
