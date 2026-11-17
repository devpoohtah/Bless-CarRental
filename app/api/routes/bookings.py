"""Booking requests sent from the website. Public: no sign-in, so every value is validated here
and the customer can only create a Pending, unpaid request."""

import logging

from fastapi import APIRouter, Form, Request
from fastapi.responses import JSONResponse

from app.core.ratelimit import RateLimiter
from app.db import firebase
from app.schemas.forms import PublicBookingInput, validate
from app.services import bookings as service
from app.services.errors import FormError

log = logging.getLogger(__name__)
router = APIRouter(include_in_schema=False)

# Per visitor address. Behind a proxy every visitor shares the proxy's address unless uvicorn
# runs with --proxy-headers and --forwarded-allow-ips set to that proxy.
limiter = RateLimiter(max_hits=10, window_seconds=600)

MESSENGER_HINT = "message us on Messenger"


def _errors(status_code: int, *messages: str) -> JSONResponse:
    return JSONResponse({"errors": list(messages)}, status_code=status_code)


@router.post("/bookings")
def submit_booking(
    request: Request, item: str = Form(""), start_date: str = Form(""), end_date: str = Form(""),
    passengers: str = Form(""), pickup_location: str = Form(""), driver_option: str = Form(""),
    details: str = Form(""), customer_name: str = Form(""), customer_phone: str = Form(""),
    customer_email: str = Form(""), website: str = Form(""),
):
    client = request.client.host if request.client else "unknown"
    if not limiter.allow(client):
        return _errors(429, f"Too many requests. Please wait a few minutes, or {MESSENGER_HINT}.")
    if website.strip():
        # The hidden "website" field is for bots. Pretend it worked and save nothing.
        return JSONResponse({"ok": True, "reference": ""}, status_code=201)
    if not firebase.is_configured():
        return _errors(503, f"Online booking is not available right now. Please {MESSENGER_HINT}.")

    raw = dict(item=item, start_date=start_date, end_date=end_date, passengers=passengers,
               pickup_location=pickup_location, driver_option=driver_option, details=details,
               customer_name=customer_name, customer_phone=customer_phone, customer_email=customer_email)
    data, errors = validate(PublicBookingInput, raw)
    if data is None:
        return _errors(422, *errors)
    try:
        booking = service.create_public_booking(data)
    except FormError as exc:
        return _errors(422, str(exc))
    except Exception:
        log.exception("Could not save a website booking request")
        return _errors(503, f"We could not save your request. Please try again in a moment, or {MESSENGER_HINT}.")
    return JSONResponse({"ok": True, "reference": booking.reference}, status_code=201)
