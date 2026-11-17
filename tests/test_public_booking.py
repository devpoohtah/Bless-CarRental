"""The website booking form: POST /bookings, plus the buttons and dialog on the landing page."""

import re
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app.api.routes import bookings as bookings_route
from app.core.clock import today_ph
from app.core.ratelimit import RateLimiter
from app.db import repositories as repo
from app.main import app
from app.schemas.catalog import Photo, TourPackage, Vehicle
from app.services import bookings as service

client = TestClient(app)
PHOTO = Photo(src="customer/img/vehicles/vehicle-compact-sedan-placeholder.svg", alt="A car")


@pytest.fixture(autouse=True)
def fresh_limiter(monkeypatch):
    monkeypatch.setattr(bookings_route, "limiter", RateLimiter(max_hits=50, window_seconds=600))


@pytest.fixture
def catalog(fake_db):
    """A car that seats 7, an unavailable car, a tour package and an unavailable tour."""
    for name, seats, availability in (("Family SUV", 7, "available"), ("Old Van", 12, "unavailable")):
        repo.save(repo.CARS, Vehicle(id="", name=name, vehicle_type="SUV", seats=seats, availability=availability,
                                     photo=PHOTO, is_sample=False))
    for name, availability in (("Island Day Tour", "inquire"), ("Closed Tour", "unavailable")):
        repo.save(repo.TOURS, TourPackage(id="", name=name, destination="Guimaras", summary="Summary.", description="Full.",
                                          availability=availability, photo=PHOTO, is_sample=False))
    return fake_db


def when(days: int) -> str:
    return (today_ph() + timedelta(days=days)).isoformat()


def car_request(**changes) -> dict:
    data = dict(item="car:Family SUV", start_date=when(5), end_date=when(7), passengers="4",
                pickup_location="Hotel in Iloilo City", driver_option="with_driver", details="Child seat please.",
                customer_name="Ana Reyes", customer_phone="0917 123 4567", customer_email="ana@example.com")
    return data | changes


def tour_request(**changes) -> dict:
    data = dict(item="tour:Island Day Tour", start_date=when(10), end_date="", passengers="6",
                customer_name="Ben Cruz", customer_phone="+63 917 765 4321")
    return data | changes


def saved_bookings(db) -> list[dict]:
    return list(db.data.get("bookings", {}).values())


# ---- success ----
def test_a_car_request_is_saved_as_a_pending_unpaid_booking(catalog):
    response = client.post("/bookings", data=car_request())
    assert response.status_code == 201
    reference = response.json()["reference"]
    assert re.fullmatch(r"BLESS-[A-Z0-9]{4,6}", reference)
    (saved,) = saved_bookings(catalog)
    assert saved["status"] == "pending" and saved["payment_status"] == "unpaid" and saved["is_sample"] is False
    assert saved["booking_type"] == "car" and saved["item_name"] == "Family SUV"
    assert saved["passengers"] == 4 and saved["driver_option"] == "with_driver"
    assert saved["pickup_location"] == "Hotel in Iloilo City" and saved["details"] == "Child seat please."
    assert saved["start_date"] == when(5) and saved["end_date"] == when(7)
    assert [h["status"] for h in saved["history"]] == ["pending"]


def test_a_one_day_tour_needs_no_end_date_and_has_no_driver(catalog):
    response = client.post("/bookings", data=tour_request(driver_option="with_driver"))
    assert response.status_code == 201
    (saved,) = saved_bookings(catalog)
    assert saved["booking_type"] == "tour" and saved["end_date"] == saved["start_date"] == when(10)
    assert saved["driver_option"] is None and saved["customer_email"] == ""


def test_a_website_request_shows_up_for_the_admin_with_its_details(catalog):
    client.post("/bookings", data=car_request())
    listing = client.get("/admin/bookings").text
    assert "Ana Reyes" in listing and "Pending" in listing
    booking_id = next(iter(catalog.data["bookings"]))
    detail = client.get(f"/admin/bookings/{booking_id}").text
    for expected in ("BLESS-", "Hotel in Iloilo City", "With a driver", "Passengers", "Child seat please."):
        assert expected in detail
    assert "Ana Reyes" in client.get("/admin/dashboard").text


def test_customers_cannot_choose_status_or_payment(catalog):
    client.post("/bookings", data=car_request() | {"status": "approved", "payment_status": "paid", "is_sample": "true"})
    (saved,) = saved_bookings(catalog)
    assert saved["status"] == "pending" and saved["payment_status"] == "unpaid" and saved["is_sample"] is False


# ---- validation: nothing is saved ----
@pytest.mark.parametrize("changes, message", [
    ({"customer_name": ""}, "Customer name is required"),
    ({"customer_phone": "call me"}, "valid phone number"),
    ({"customer_phone": "12345"}, "valid phone number"),
    ({"customer_email": "not-an-email"}, "valid email address"),
    ({"start_date": ""}, "Start date is required"),
    ({"start_date": "soon"}, "must be a valid date"),
    ({"start_date": when(-1)}, "cannot be in the past"),
    ({"start_date": when(800), "end_date": when(801)}, "within the next two years"),
    ({"end_date": when(2)}, "end date cannot be before the start date"),
    ({"passengers": ""}, "Number of people is required"),
    ({"passengers": "0"}, "Number of people is outside the allowed range"),
    ({"passengers": "many"}, "must be a whole number"),
    ({"passengers": "8"}, "seats up to 7"),
    ({"driver_option": "chauffeur"}, "Driver option is not valid"),
    ({"item": ""}, "Car or tour is required"),
    ({"item": "car:Does Not Exist"}, "Choose a car or tour package"),
    ({"item": "boat:Family SUV"}, "Choose a car or tour package"),
    ({"item": "car:Old Van", "passengers": "2"}, "currently unavailable"),
    ({"item": "tour:Closed Tour", "passengers": "2"}, "currently unavailable"),
])
def test_invalid_requests_are_refused_with_a_message_and_nothing_is_saved(catalog, changes, message):
    response = client.post("/bookings", data=car_request(**changes))
    assert response.status_code == 422, response.text
    assert any(message in text for text in response.json()["errors"]), response.json()
    assert saved_bookings(catalog) == []


def test_a_tour_does_not_check_seats(catalog):
    assert client.post("/bookings", data=tour_request(passengers="30")).status_code == 201


# ---- abuse and failure ----
def test_the_hidden_field_makes_a_bot_look_successful_but_saves_nothing(catalog):
    response = client.post("/bookings", data=car_request(website="http://spam.example"))
    assert response.status_code == 201 and response.json()["reference"] == ""
    assert saved_bookings(catalog) == []


def test_too_many_requests_from_one_address_are_refused(catalog, monkeypatch):
    monkeypatch.setattr(bookings_route, "limiter", RateLimiter(max_hits=2, window_seconds=600))
    codes = [client.post("/bookings", data=car_request()).status_code for _ in range(3)]
    assert codes == [201, 201, 429]
    assert len(saved_bookings(catalog)) == 2


def test_without_a_database_the_request_is_refused_politely():
    response = client.post("/bookings", data=car_request())
    assert response.status_code == 503 and "Messenger" in response.json()["errors"][0]


def test_a_storage_failure_gives_a_generic_message_and_no_internals(catalog, monkeypatch):
    def broken(data):
        raise RuntimeError("secret firestore detail")
    monkeypatch.setattr(service, "create_public_booking", broken)
    response = client.post("/bookings", data=car_request())
    assert response.status_code == 503
    assert "secret" not in response.text and "try again" in response.json()["errors"][0]


def test_the_rate_limiter_forgets_old_attempts():
    now = [0.0]
    limiter = RateLimiter(max_hits=2, window_seconds=60, clock=lambda: now[0])
    assert [limiter.allow("a"), limiter.allow("a"), limiter.allow("a")] == [True, True, False]
    assert limiter.allow("b")  # another visitor is unaffected
    now[0] = 61
    assert limiter.allow("a")


# ---- landing page ----
def test_book_now_buttons_open_the_form_instead_of_messenger():
    html = client.get("/").text
    assert html.count('<button type="button" class="btn btn--action btn--sm site-header__cta" data-book>Book Now</button>') == 1
    assert '<button type="button" class="btn btn--action btn--block" data-book>Book Now</button>' in html
    assert "(opens Messenger in a new tab)</span></a>" not in html.split('id="main"')[0]  # none left in the header
    # one booking button per sample vehicle and tour card, each naming what it books
    assert html.count('data-book="car:') == len(service.content.list_vehicles())
    assert html.count('data-book="tour:') >= len(service.content.list_tours())


def test_the_booking_dialog_is_on_the_page_once_with_every_field_the_server_expects():
    html = client.get("/").text
    assert html.count('id="booking-dialog"') == 1
    form = html.split('id="booking-form"')[1].split("</form>")[0]
    for name in ("item", "start_date", "end_date", "passengers", "driver_option", "pickup_location", "details",
                 "customer_name", "customer_phone", "customer_email", "website"):
        assert f'name="{name}"' in form, name
    assert f'min="{today_ph().isoformat()}"' in form
    assert 'action="/bookings"' in html and 'method="post"' in html
    assert all(re.search(rf'<label[^>]*for="{i}"', html) for i in re.findall(r'<(?:input|select|textarea) id="(bk-[a-z]+)"', html))


def test_unavailable_items_cannot_be_booked_from_the_site(catalog):
    html = client.get("/").text
    assert 'data-book="car:Family SUV"' in html and 'data-book="tour:Island Day Tour"' in html
    assert 'data-book="car:Old Van"' not in html and 'data-book="tour:Closed Tour"' not in html
    assert "Currently unavailable</button>" in html
    options = html.split('id="bk-item"')[1].split("</select>")[0]
    assert "Family SUV" in options and "Island Day Tour" in options
    assert "Old Van" not in options and "Closed Tour" not in options


def test_messenger_stays_available_as_a_secondary_way_to_ask():
    html = client.get("/").text
    dialog = html.split('id="booking-dialog"')[1]
    assert "Message us on Messenger" in dialog
    assert html.count("https://m.me/") >= 3  # footer, contact and the dialogs still link to Messenger
