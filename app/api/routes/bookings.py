"""Booking pages and requests from the website: one page and one form for car rental, another for tours.

Public: no sign-in, so every value is validated here and the customer can only create a Pending,
unpaid request. Nothing is saved until the customer enters the code emailed to them (see
app.services.otp): the form post only checks the request and sends the code. Telegram and web push
alerts run after the response, so a slow alert never delays the customer.
"""

import logging
from datetime import date

from fastapi import APIRouter, BackgroundTasks, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse

from app.core import config
from app.core.clock import today_ph
from app.core.ratelimit import RateLimiter
from app.core.templating import templates
from app.db import firebase
from app.schemas.forms import PublicCarBookingInput, PublicTourBookingInput, validate
from app.services import bookings as service
from app.services import content, notify, otp, turnstile
from app.services.errors import FormError

log = logging.getLogger(__name__)
router = APIRouter(include_in_schema=False)

# Per visitor address. Behind a proxy every visitor shares the proxy's address unless uvicorn
# runs with --proxy-headers and --forwarded-allow-ips set to that proxy.
limiter = RateLimiter(max_hits=10, window_seconds=600)
# Every code is an email, so each address is limited too: this stops one person's inbox being flooded.
email_limiter = RateLimiter(max_hits=5, window_seconds=3600)

# What each form creates once its code is right: the validation model, the check-only step, and the save step.
FORMS = {
    "car": (PublicCarBookingInput, lambda data: service.build_car_booking(data),
            lambda data, **kw: service.create_car_booking(data, **kw)),
    "tour": (PublicTourBookingInput, lambda data: service.build_tour_booking(data),
             lambda data, **kw: service.create_tour_booking(data, **kw)),
}

MESSENGER_HINT = "message us on Messenger"


def _errors(status_code: int, *messages: str, **extra) -> JSONResponse:
    return JSONResponse({"errors": list(messages)} | extra, status_code=status_code)


def _client(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _otp_failure(exc: otp.OtpError) -> JSONResponse:
    status = {"wrong_code": 400, "expired": 410, "locked": 429, "cooldown": 429, "send_failed": 503}[exc.code]
    return _errors(status, exc.message, code=exc.code, attempts_left=exc.attempts_left, retry_after=exc.retry_after)


def _challenge_body(challenge: str, email: str, test_code: str | None) -> dict:
    body = {"challenge": challenge, "email": otp.mask_email(email), "resend_in": otp.RESEND_COOLDOWN_SECONDS}
    if test_code:  # only ever set in simulated mode (OTP_DELIVERY=simulated)
        body["test_code"] = test_code
    return body


def _page(request: Request, template: str, **context) -> HTMLResponse:
    context |= {"nav_links": content.NAV_LINKS, "nav_base": "/", "current_year": date.today().year,
                "today_iso": today_ph().isoformat(),
                "turnstile_site_key": config.integrations.turnstile_site_key if config.integrations.turnstile_ready else ""}
    return templates.TemplateResponse(request, f"customer/pages/{template}", context)


def _bookable(items) -> list:
    return [item for item in items if item.availability != "unavailable"]


@router.get("/book/car", response_class=HTMLResponse)
def car_page(request: Request, car: str = "") -> HTMLResponse:
    cars = _bookable(content.list_vehicles())
    selected = next((c for c in cars if c.id == car), cars[0] if cars else None)
    return _page(request, "book_car.html", cars=cars, selected=selected,
                 blocked=service.all_blocked_ranges("car", [c.name for c in cars]))


@router.get("/book/tour", response_class=HTMLResponse)
def tour_page(request: Request, tour: str = "") -> HTMLResponse:
    tours = _bookable(content.list_tours())
    selected = next((t for t in tours if t.id == tour), tours[0] if tours else None)
    return _page(request, "book_tour.html", tours=tours, selected=selected,
                 blocked=service.all_blocked_ranges("tour", [t.name for t in tours]))


def _submit(request: Request, kind: str, raw: dict, honeypot: str, token: str, agree: str = ""):
    """Checks a request and emails a code. Saves nothing: /book/verify does that once the code is right."""
    client = _client(request)
    if not limiter.allow(client):
        return _errors(429, f"Too many requests. Please wait a few minutes, or {MESSENGER_HINT}.")
    if honeypot.strip():
        # The hidden "website" field is for bots. Pretend it worked and save nothing.
        return JSONResponse({"ok": True, "reference": ""}, status_code=201)
    if not firebase.is_configured() or not config.integrations.otp_mode:
        return _errors(503, f"Online booking is not available right now. Please {MESSENGER_HINT}.")
    if agree != "yes":
        return _errors(422, "Please tick the box to agree to the Terms and Conditions and the Privacy Policy.")
    model, build, _create = FORMS[kind]
    data, errors = validate(model, raw)
    if data is None:
        return _errors(422, *errors)
    if not turnstile.passed(token, client):
        return _errors(422, "We could not confirm you are human. Please try again.", code="turnstile")
    try:
        build(data)  # the same checks as the final save, so mistakes show up before an email is sent
    except FormError as exc:
        return _errors(422, str(exc))
    except Exception:
        log.exception("Could not check a website booking request")
        return _errors(503, f"We could not check your request. Please try again in a moment, or {MESSENGER_HINT}.")
    if not email_limiter.allow(data.customer_email):
        return _errors(429, "Too many codes were sent to this email address. Please try again later.")
    try:
        challenge, test_code = otp.store.start(kind, data, data.customer_email)
    except otp.OtpError as exc:
        return _otp_failure(exc)
    return JSONResponse(_challenge_body(challenge, data.customer_email, test_code), status_code=202)


@router.post("/book/verify")
def verify_code(background: BackgroundTasks, challenge: str = Form(""), code: str = Form("")):
    """The customer's code. Right: save the booking. Wrong, expired or locked: say which."""
    try:
        kind, data = otp.store.verify(challenge, code)
    except otp.OtpError as exc:
        return _otp_failure(exc)
    # The code is used up now. Dates can have been taken since the form was sent, so the save checks them again.
    try:
        booking = FORMS[kind][2](data, email_verified=True)
    except FormError as exc:
        return _errors(422, str(exc), code="rejected")
    except Exception:
        log.exception("Could not save a website booking request")
        return _errors(503, f"We could not save your request. Please try again in a moment, or {MESSENGER_HINT}.",
                       code="rejected")
    background.add_task(notify.notify_new_booking, booking)
    return JSONResponse({"ok": True, "reference": booking.reference}, status_code=201)


@router.post("/book/resend")
def resend_code(request: Request, challenge: str = Form("")):
    if not limiter.allow(_client(request)):
        return _errors(429, "Too many requests. Please wait a few minutes.", code="cooldown")
    try:
        test_code = otp.store.resend(challenge)
    except otp.OtpError as exc:
        return _otp_failure(exc)
    body = {"resend_in": otp.RESEND_COOLDOWN_SECONDS}
    if test_code:
        body["test_code"] = test_code
    return JSONResponse(body)


@router.post("/book/car")
def submit_car(
    request: Request, car: str = Form(""), start_date: str = Form(""),
    start_time: str = Form(""), end_date: str = Form(""), end_time: str = Form(""),
    pickup_location: str = Form(""), dropoff_location: str = Form(""), destination: str = Form(""),
    passengers: str = Form(""), driver_option: str = Form(""), details: str = Form(""),
    customer_name: str = Form(""), customer_phone: str = Form(""), customer_email: str = Form(""),
    website: str = Form(""), agree: str = Form(""), cf_turnstile_response: str = Form("", alias="cf-turnstile-response"),
):
    raw = dict(car=car, start_date=start_date, start_time=start_time, end_date=end_date, end_time=end_time,
               pickup_location=pickup_location, dropoff_location=dropoff_location, destination=destination,
               passengers=passengers, driver_option=driver_option, details=details, customer_name=customer_name,
               customer_phone=customer_phone, customer_email=customer_email)
    return _submit(request, "car", raw, website, cf_turnstile_response, agree)


@router.post("/book/tour")
def submit_tour(
    request: Request, tour: str = Form(""), start_date: str = Form(""),
    end_date: str = Form(""), guests: str = Form(""), pickup_location: str = Form(""), details: str = Form(""),
    customer_name: str = Form(""), customer_phone: str = Form(""), customer_email: str = Form(""),
    website: str = Form(""), agree: str = Form(""), cf_turnstile_response: str = Form("", alias="cf-turnstile-response"),
):
    raw = dict(tour=tour, start_date=start_date, end_date=end_date, guests=guests, pickup_location=pickup_location,
               details=details, customer_name=customer_name, customer_phone=customer_phone,
               customer_email=customer_email)
    return _submit(request, "tour", raw, website, cf_turnstile_response, agree)
