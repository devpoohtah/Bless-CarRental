"""Booking management and the booking calendar.

These pages only display data for now. Approving, rejecting, cancelling and status updates
are shown but disabled until the database is connected.
"""

from datetime import date

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from app.core.templating import templates
from app.services import bookings as service

router = APIRouter(prefix="/admin", include_in_schema=False)

LABELS = {
    "status_labels": service.STATUS_LABELS,
    "payment_labels": service.PAYMENT_LABELS,
    "type_labels": service.TYPE_LABELS,
}


def render(request: Request, template: str, active_nav: str, **context) -> HTMLResponse:
    context |= LABELS | {"active_nav": active_nav}
    return templates.TemplateResponse(request, f"admin/pages/{template}", context)


@router.get("/bookings", response_class=HTMLResponse)
async def bookings(request: Request, type: str | None = None) -> HTMLResponse:
    booking_type = type if type in ("car", "tour") else None
    return render(request, "bookings.html", "bookings",
                  bookings=service.list_bookings(booking_type), active_type=booking_type)


@router.get("/bookings/{booking_id}", response_class=HTMLResponse)
async def booking_detail(request: Request, booking_id: str) -> HTMLResponse:
    booking = service.get_booking(booking_id)
    if booking is None:
        raise HTTPException(status_code=404, detail="Booking not found")
    return render(request, "booking_detail.html", "bookings", booking=booking,
                  next_options=[(s, service.STATUS_LABELS[s]) for s in service.NEXT_STATUSES[booking.status]],
                  history=list(reversed(booking.history)))


@router.get("/calendar", response_class=HTMLResponse)
async def booking_calendar(request: Request, month: str | None = None) -> HTMLResponse:
    today = date.today()
    view = service.month_view(service.parse_month(month, today), today)
    return render(request, "calendar.html", "calendar", **view)
