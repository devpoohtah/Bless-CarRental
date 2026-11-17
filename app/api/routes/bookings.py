"""Booking pages and requests from the website: one page and one form for car rental, another for tours.

Public: no sign-in, so every value is validated here and the customer can only create a Pending,
unpaid request. Telegram and web push alerts run after the response, so a slow alert never delays
the customer.
"""

import logging
from datetime import date

from fastapi import APIRouter, BackgroundTasks, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse

from app.core.clock import today_ph
from app.core.ratelimit import RateLimiter
from app.core.templating import templates
from app.db import firebase
from app.schemas.forms import PublicCarBookingInput, PublicTourBookingInput, validate
from app.services import bookings as service
from app.services import content, notify
from app.services.errors import FormError

log = logging.getLogger(__name__)
router = APIRouter(include_in_schema=False)

# Per visitor address. Behind a proxy every visitor shares the proxy's address unless uvicorn
# runs with --proxy-headers and --forwarded-allow-ips set to that proxy.
limiter = RateLimiter(max_hits=10, window_seconds=600)

MESSENGER_HINT = "message us on Messenger"


def _errors(status_code: int, *messages: str) -> JSONResponse:
    return JSONResponse({"errors": list(messages)}, status_code=status_code)


def _page(request: Request, template: str, **context) -> HTMLResponse:
    context |= {"nav_links": content.NAV_LINKS, "nav_base": "/", "current_year": date.today().year,
                "today_iso": today_ph().isoformat()}
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


def _submit(request: Request, background: BackgroundTasks, model, raw: dict, honeypot: str, create):
    client = request.client.host if request.client else "unknown"
    if not limiter.allow(client):
        return _errors(429, f"Too many requests. Please wait a few minutes, or {MESSENGER_HINT}.")
    if honeypot.strip():
        # The hidden "website" field is for bots. Pretend it worked and save nothing.
        return JSONResponse({"ok": True, "reference": ""}, status_code=201)
    if not firebase.is_configured():
        return _errors(503, f"Online booking is not available right now. Please {MESSENGER_HINT}.")
    data, errors = validate(model, raw)
    if data is None:
        return _errors(422, *errors)
    try:
        booking = create(data)
    except FormError as exc:
        return _errors(422, str(exc))
    except Exception:
        log.exception("Could not save a website booking request")
        return _errors(503, f"We could not save your request. Please try again in a moment, or {MESSENGER_HINT}.")
    background.add_task(notify.notify_new_booking, booking)
    return JSONResponse({"ok": True, "reference": booking.reference}, status_code=201)


@router.post("/book/car")
def submit_car(
    request: Request, background: BackgroundTasks, car: str = Form(""), start_date: str = Form(""),
    start_time: str = Form(""), end_date: str = Form(""), end_time: str = Form(""),
    pickup_location: str = Form(""), dropoff_location: str = Form(""), destination: str = Form(""),
    passengers: str = Form(""), driver_option: str = Form(""), details: str = Form(""),
    customer_name: str = Form(""), customer_phone: str = Form(""), customer_email: str = Form(""),
    website: str = Form(""),
):
    raw = dict(car=car, start_date=start_date, start_time=start_time, end_date=end_date, end_time=end_time,
               pickup_location=pickup_location, dropoff_location=dropoff_location, destination=destination,
               passengers=passengers, driver_option=driver_option, details=details, customer_name=customer_name,
               customer_phone=customer_phone, customer_email=customer_email)
    return _submit(request, background, PublicCarBookingInput, raw, website, service.create_car_booking)


@router.post("/book/tour")
def submit_tour(
    request: Request, background: BackgroundTasks, tour: str = Form(""), start_date: str = Form(""),
    end_date: str = Form(""), guests: str = Form(""), pickup_location: str = Form(""), details: str = Form(""),
    customer_name: str = Form(""), customer_phone: str = Form(""), customer_email: str = Form(""),
    website: str = Form(""),
):
    raw = dict(tour=tour, start_date=start_date, end_date=end_date, guests=guests, pickup_location=pickup_location,
               details=details, customer_name=customer_name, customer_phone=customer_phone,
               customer_email=customer_email)
    return _submit(request, background, PublicTourBookingInput, raw, website, service.create_tour_booking)
