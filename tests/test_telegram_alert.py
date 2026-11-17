"""Telegram alerts for new website booking requests."""

import io
import json
import logging
import urllib.error
from dataclasses import replace
from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.api.routes import bookings as bookings_route
from app.core import config
from app.core.ratelimit import RateLimiter
from app.core.clock import today_ph
from app.db import repositories as repo
from app.main import app
from app.schemas.booking import Booking, StatusChange
from app.schemas.catalog import Photo, TourPackage, Vehicle
from app.services import notify
from tests.test_public_booking import car_request, tour_request, when

client = TestClient(app)
TOKEN = "123456:SECRET-TOKEN-VALUE"
CHAT = "-5579257273"
PHOTO = Photo(src="customer/img/vehicles/vehicle-compact-sedan-placeholder.svg", alt="A car")


def car_booking(**changes) -> Booking:
    fields = dict(
        id="abc123", booking_type="car", customer_name="Ana Reyes", customer_phone="0917 123 4567",
        item_name="Toyota Vios", start_date=date(2027, 3, 4), end_date=date(2027, 3, 6),
        pickup_location="Hotel in Iloilo City", passengers=4, driver_option="with_driver", details="Child seat please.",
        requested_on=today_ph(), status="pending", payment_status="unpaid", is_sample=False,
        history=[StatusChange(status="pending", changed_on=today_ph())])
    return Booking(**(fields | changes))


@pytest.fixture(autouse=True)
def fresh_limiter(monkeypatch):
    monkeypatch.setattr(bookings_route, "limiter", RateLimiter(max_hits=50, window_seconds=600))


@pytest.fixture
def telegram_on(monkeypatch):
    monkeypatch.setattr(config, "integrations", replace(
        config.integrations, telegram_bot_token=TOKEN, telegram_chat_id=CHAT, admin_base_url="https://bless.example"))


@pytest.fixture
def alerts(monkeypatch) -> list[str]:
    sent: list[str] = []
    monkeypatch.setattr(notify, "send_telegram", lambda text: sent.append(text) or True)
    return sent


@pytest.fixture
def catalog(fake_db):
    repo.save(repo.CARS, Vehicle(id="", name="Family SUV", vehicle_type="SUV", seats=7, availability="available",
                                 photo=PHOTO, is_sample=False))
    repo.save(repo.TOURS, TourPackage(id="", name="Island Day Tour", destination="Guimaras", summary="S", description="D",
                                      availability="inquire", photo=PHOTO, is_sample=False))
    return fake_db


# ---- the message ----
def test_a_car_alert_has_everything_the_caller_needs():
    text = notify.booking_alert_text(car_booking(), "https://bless.example")
    for expected in ("New car rental request BLESS-ABC123", "Customer: Ana Reyes", "Phone: 0917 123 4567",
                     "Car: Toyota Vios", "Pick-up: Mar 4, 2027", "Return: Mar 6, 2027",
                     "Trip: 4 passengers, with a driver", "Meet-up: Hotel in Iloilo City", "Notes: Child seat please.",
                     "Open: https://bless.example/admin/bookings/abc123", 'Reply "Calling now"'):
        assert expected in text, expected


def test_a_tour_alert_shows_the_dates_and_guests():
    tour = car_booking(booking_type="tour", item_name="Island Day Tour", pickup_location="",
                       driver_option=None, end_date=date(2027, 3, 4), details="")
    text = notify.booking_alert_text(tour)
    assert "New tour request" in text and "Tour package: Island Day Tour" in text
    assert "Date: Mar 4, 2027\n" in text and "Guests: 4" in text
    assert "Meet-up" not in text and "Notes" not in text and "Open:" not in text  # nothing to show, no site address set
    assert "Date: Mar 4, 2027 to Mar 6, 2027" in notify.booking_alert_text(replace_tour(tour, end=date(2027, 3, 6)))


def replace_tour(booking: Booking, end: date) -> Booking:
    return booking.model_copy(update={"end_date": end})


def test_long_notes_are_cut_and_customer_text_is_never_treated_as_formatting():
    text = notify.booking_alert_text(car_booking(details="x" * 500, customer_name="<b>Ana</b> _x_"))
    assert "Notes: " + "x" * 200 + "..." in text and "x" * 201 not in text
    assert "Customer: <b>Ana</b> _x_" in text


# ---- sending ----
class FakeResponse:
    def __init__(self, status=200): self.status = status
    def __enter__(self): return self
    def __exit__(self, *exc): return False


def test_nothing_is_sent_when_telegram_is_not_set_up(monkeypatch):
    monkeypatch.setattr(notify.urllib.request, "urlopen", lambda *a, **k: pytest.fail("must not call Telegram"))
    assert notify.send_telegram("hello") is False


def test_the_message_is_posted_to_the_group_as_plain_text(telegram_on, monkeypatch):
    seen = {}
    def fake_urlopen(request, timeout):
        seen.update(url=request.full_url, body=json.loads(request.data), timeout=timeout, method=request.get_method())
        return FakeResponse()
    monkeypatch.setattr(notify.urllib.request, "urlopen", fake_urlopen)
    assert notify.send_telegram("hello") is True
    assert seen["url"] == f"https://api.telegram.org/bot{TOKEN}/sendMessage" and seen["method"] == "POST"
    assert seen["body"] == {"chat_id": CHAT, "text": "hello", "disable_web_page_preview": True}
    assert "parse_mode" not in seen["body"] and seen["timeout"] == notify.TIMEOUT_SECONDS


def test_a_telegram_error_is_logged_without_the_token_and_does_not_raise(telegram_on, monkeypatch, caplog):
    def refuse(request, timeout):
        raise urllib.error.HTTPError(request.full_url, 400, "Bad Request", {}, io.BytesIO(b'{"description": "chat not found"}'))
    monkeypatch.setattr(notify.urllib.request, "urlopen", refuse)
    with caplog.at_level(logging.WARNING):
        assert notify.send_telegram("hello") is False
    assert "chat not found" in caplog.text and "400" in caplog.text
    assert TOKEN not in caplog.text and "SECRET" not in caplog.text


def test_a_network_failure_is_logged_without_the_token_and_does_not_raise(telegram_on, monkeypatch, caplog):
    def down(request, timeout):
        raise urllib.error.URLError("no route to " + request.full_url)
    monkeypatch.setattr(notify.urllib.request, "urlopen", down)
    with caplog.at_level(logging.WARNING):
        assert notify.send_telegram("hello") is False
    assert TOKEN not in caplog.text


# ---- when alerts go out ----
def test_a_car_request_sends_one_alert_with_its_reference(catalog, alerts):
    response = client.post("/bookings", data=car_request())
    assert response.status_code == 201
    (text,) = alerts
    assert response.json()["reference"] in text and "Ana Reyes" in text and "Family SUV" in text


def test_a_tour_request_sends_one_alert(catalog, alerts):
    assert client.post("/bookings", data=tour_request()).status_code == 201
    (text,) = alerts
    assert "New tour request" in text and "Ben Cruz" in text


def test_the_alert_links_to_the_booking_when_the_site_address_is_set(catalog, telegram_on, monkeypatch):
    sent = []
    monkeypatch.setattr(notify.urllib.request, "urlopen", lambda request, timeout: sent.append(json.loads(request.data)) or FakeResponse())
    client.post("/bookings", data=car_request())
    booking_id = next(iter(catalog.data["bookings"]))
    assert f"Open: https://bless.example/admin/bookings/{booking_id}" in sent[0]["text"]


def test_no_alert_for_requests_that_were_not_saved(catalog, alerts):
    client.post("/bookings", data=car_request(customer_name=""))                  # invalid
    client.post("/bookings", data=car_request(website="http://spam.example"))      # bot
    client.post("/bookings", data=car_request(item="car:Nope"))                         # unknown car
    assert alerts == []


def test_no_alert_when_the_request_is_rejected_by_the_business_rules(catalog, alerts):
    assert client.post("/bookings", data=car_request(passengers="9")).status_code == 422   # Family SUV seats 7
    assert client.post("/bookings", data=car_request(start_date=when(-2), end_date=when(1))).status_code == 422
    assert alerts == []


def test_no_alert_without_a_database(alerts):
    assert client.post("/bookings", data=car_request()).status_code == 503
    assert alerts == []


def test_the_booking_is_saved_and_the_customer_told_even_if_the_alert_blows_up(catalog, monkeypatch):
    def explode(text):
        raise RuntimeError("telegram is down")
    monkeypatch.setattr(notify, "send_telegram", explode)
    response = client.post("/bookings", data=car_request())
    assert response.status_code == 201 and response.json()["reference"].startswith("BLESS-")
    assert len(catalog.data["bookings"]) == 1


def test_admin_added_bookings_do_not_alert(catalog, alerts):
    client.post("/admin/bookings/new", data={"item": "car:Family SUV", "customer_name": "Walk In", "customer_phone": "09171234567",
                                             "start_date": when(3), "end_date": when(4)})
    assert len(catalog.data["bookings"]) == 1 and alerts == []
