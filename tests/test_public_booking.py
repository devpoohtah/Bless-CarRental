"""The website booking pages: /book/car and /book/tour, their forms, the blocked dates, and the buttons that lead there."""

import json
import re
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app.api.routes import bookings as bookings_route
from app.core.clock import today_ph
from app.core.ratelimit import RateLimiter
from app.db import repositories as repo
from app.main import app
from app.schemas.booking import Booking, StatusChange
from app.schemas.catalog import Photo, TourPackage, Vehicle
from app.services import bookings as service

client = TestClient(app)
pytestmark = pytest.mark.usefixtures("simulated_otp")
PHOTO = Photo(src="customer/img/vehicles/vehicle-compact-sedan-placeholder.svg", alt="A car")
VAN_PHOTO = Photo(src="customer/img/vehicles/vehicle-passenger-van-placeholder.svg", alt="A van")


@pytest.fixture(autouse=True)
def fresh_limiter(monkeypatch):
    monkeypatch.setattr(bookings_route, "limiter", RateLimiter(max_hits=50, window_seconds=600))


@pytest.fixture
def catalog(fake_db):
    """Cars: Family SUV (7 seats), City Car, and one unavailable. Tours: Island Day Tour (its van seats 10),
    Plain Tour (no vehicle details) and one unavailable."""
    for doc_id, name, seats, availability in (("family-suv", "Family SUV", 7, "available"), ("city-car", "City Car", 4, "inquire"),
                                              ("old-car", "Old Car", 5, "unavailable")):
        repo.save(repo.CARS, Vehicle(id="", name=name, vehicle_type="SUV", seats=seats, availability=availability,
                                     photo=PHOTO, is_sample=False), doc_id)
    tours = (("island-day-tour", "Island Day Tour", "inquire", True), ("plain-tour", "Plain Tour", "inquire", False),
             ("closed-tour", "Closed Tour", "unavailable", False))
    for doc_id, name, availability, has_van in tours:
        van = dict(vehicle_name="Toyota Hiace", vehicle_seats=10, vehicle_photo=VAN_PHOTO) if has_van else {}
        repo.save(repo.TOURS, TourPackage(id="", name=name, destination="Guimaras", summary="Summary.", description="Full.",
                                          availability=availability, photo=PHOTO, is_sample=False, **van), doc_id)
    return fake_db


def _get_csrf_token():
    """Get a fresh CSRF token from the cookie."""
    client.get("/")  # sets the cookie
    return client.cookies.get("csrf_token", "")


def book(url: str, data: dict):
    """A customer's whole journey: send the form, then enter the code. Returns the last response."""
    csrf_token = _get_csrf_token()
    headers = {"X-CSRF-Token": csrf_token}
    response = client.post(url, data=data, headers=headers)
    if response.status_code != 202:
        return response  # refused, or a bot: there is no code step
    return client.post("/book/verify", data={"challenge": response.json()["challenge"], "code": "123456"}, headers=headers)


def when(days: int) -> str:
    return (today_ph() + timedelta(days=days)).isoformat()


def car_request(**changes) -> dict:
    data = dict(car="family-suv", start_date=when(5), start_time="09:00", end_date=when(7), end_time="17:30",
                pickup_location="Hotel in Iloilo City", dropoff_location="Iloilo Airport", destination="Guimaras",
                passengers="4", driver_option="with_driver", details="Child seat please.",
                customer_name="Ana Reyes", customer_phone="0917 123 4567", customer_email="ana@example.com", agree="yes")
    return data | changes


def tour_request(**changes) -> dict:
    data = dict(tour="island-day-tour", start_date=when(10), end_date="", guests="6",
                customer_name="Ben Cruz", customer_phone="+63 917 765 4321", customer_email="Ben@Example.com", agree="yes")
    return data | changes


def saved_bookings(db) -> list[dict]:
    return list(db.data.get("bookings", {}).values())


def add_booking(status="approved", start=5, end=7, kind="car", item="Family SUV") -> None:
    """A booking BLESS already has, written straight to the database."""
    today = today_ph()
    repo.save(repo.BOOKINGS, Booking(
        id="", booking_type=kind, customer_name="Earlier Customer", customer_phone="09170000000", item_name=item,
        start_date=today + timedelta(days=start), end_date=today + timedelta(days=end), requested_on=today,
        status=status, payment_status="unpaid", history=[StatusChange(status=status, changed_on=today)], is_sample=False))


# ---- car rental: success ----
def test_a_car_request_is_saved_as_a_pending_unpaid_booking(catalog):
    response = book("/book/car", car_request())
    assert response.status_code == 201
    assert re.fullmatch(r"BLESS-[A-Z0-9]{4,6}", response.json()["reference"])
    (saved,) = saved_bookings(catalog)
    assert saved["status"] == "pending" and saved["payment_status"] == "unpaid" and saved["is_sample"] is False
    assert saved["email_verified"] is True and saved["customer_phone"] == "+639171234567"
    assert saved["booking_type"] == "car" and saved["item_name"] == "Family SUV"
    assert saved["passengers"] == 4 and saved["driver_option"] == "with_driver" and saved["details"] == "Child seat please."
    assert saved["pickup_location"] == "Hotel in Iloilo City" and saved["dropoff_location"] == "Iloilo Airport"
    assert saved["destination"] == "Guimaras"
    assert saved["start_date"] == when(5) and saved["end_date"] == when(7)
    assert saved["start_time"] == "09:00:00" and saved["end_time"] == "17:30:00"
    assert [h["status"] for h in saved["history"]] == ["pending"]


def test_the_driver_is_optional_for_a_car(catalog):
    data = car_request(driver_option="", details="")
    assert book("/book/car", data).status_code == 201
    (saved,) = saved_bookings(catalog)
    assert saved["driver_option"] is None


@pytest.mark.parametrize("missing", ["start_time", "end_time"])
def test_a_car_request_needs_both_times(catalog, missing):
    response = book("/book/car", car_request(**{missing: ""}))
    assert response.status_code == 422 and saved_bookings(catalog) == []


def test_a_one_day_rental_can_return_later_the_same_day(catalog):
    data = car_request(start_date=when(5), end_date=when(5), start_time="08:00", end_time="18:00")
    assert book("/book/car", data).status_code == 201


# ---- tours: success ----
def test_a_one_day_tour_needs_no_end_date_and_no_pickup(catalog):
    response = book("/book/tour", tour_request())
    assert response.status_code == 201
    (saved,) = saved_bookings(catalog)
    assert saved["booking_type"] == "tour" and saved["item_name"] == "Island Day Tour"
    assert saved["end_date"] == saved["start_date"] == when(10)
    assert saved["passengers"] == 6 and saved["pickup_location"] == ""
    assert saved["driver_option"] is None and saved["customer_email"] == "ben@example.com" and saved["status"] == "pending"
    assert saved["customer_phone"] == "+639177654321" and saved["email_verified"] is True


def test_a_multi_day_tour_keeps_its_end_date_and_meeting_point(catalog):
    data = tour_request(end_date=when(12), pickup_location="Hotel in Iloilo City")
    assert book("/book/tour", data).status_code == 201
    (saved,) = saved_bookings(catalog)
    assert saved["end_date"] == when(12) and saved["pickup_location"] == "Hotel in Iloilo City"


# ---- what the admin sees ----
def test_a_car_request_shows_up_for_the_admin_with_every_detail(catalog):
    book("/book/car", car_request())
    assert "Ana Reyes" in client.get("/admin/bookings").text
    booking_id = next(iter(catalog.data["bookings"]))
    detail = client.get(f"/admin/bookings/{booking_id}").text
    for expected in ("BLESS-", "Hotel in Iloilo City", "Iloilo Airport", "Drop-off location", "Destination", "Guimaras",
                     "With a driver", "Passengers", "Pick-up time", "9:00 AM", "Return time", "5:30 PM", "Child seat please."):
        assert expected in detail, expected
    assert "Ana Reyes" in client.get("/admin/dashboard").text


def test_a_tour_request_shows_guests_to_the_admin(catalog):
    book("/book/tour", tour_request())
    detail = client.get(f"/admin/bookings/{next(iter(catalog.data['bookings']))}").text
    assert "Island Day Tour" in detail and "Guests" in detail and "Drop-off" not in detail and "Pick-up time" not in detail


def test_customers_cannot_choose_status_or_payment(catalog):
    extra = {"status": "approved", "payment_status": "paid", "is_sample": "true"}
    book("/book/car", car_request() | extra)
    book("/book/tour", tour_request() | extra)
    for saved in saved_bookings(catalog):
        assert saved["status"] == "pending" and saved["payment_status"] == "unpaid" and saved["is_sample"] is False


# ---- validation: nothing is saved ----
@pytest.mark.parametrize("changes, message", [
    ({"customer_name": ""}, "Customer name is required"),
    ({"customer_phone": "call me"}, "Philippine mobile number"),
    ({"customer_phone": "12345"}, "Philippine mobile number"),
    ({"customer_phone": "(02) 8123 4567"}, "Philippine mobile number"),
    ({"customer_phone": "+1 415 555 0100"}, "Philippine mobile number"),
    ({"customer_email": ""}, "Customer email is required"),
    ({"customer_email": "not-an-email"}, "valid email address"),
    ({"start_date": ""}, "Start date is required"),
    ({"start_date": "soon"}, "must be a valid date"),
    ({"start_date": when(-1)}, "cannot be in the past"),
    ({"start_date": when(800), "end_date": when(801)}, "within the next two years"),
    ({"end_date": ""}, "End date is required"),
    ({"end_date": when(2)}, "return date cannot be before the pick-up date"),
    ({"start_date": when(5), "end_date": when(5), "start_time": "10:00", "end_time": "09:00"}, "return time must be after"),
    ({"start_time": "9 o'clock"}, "Pick-up time must be a valid time"),
    ({"pickup_location": ""}, "Pick-up location is required"),
    ({"dropoff_location": ""}, "Drop-off location is required"),
    ({"destination": ""}, "Destination is required"),
    ({"passengers": ""}, "Number of people is required"),
    ({"passengers": "0"}, "Number of people is outside the allowed range"),
    ({"passengers": "many"}, "must be a whole number"),
    ({"passengers": "8"}, "seats up to 7"),
    ({"driver_option": "chauffeur"}, "Driver option is not valid"),
    ({"car": ""}, "Type of car is required"),
    ({"car": "does-not-exist"}, "Choose a car from the list"),
    ({"car": "old-car", "passengers": "2"}, "currently unavailable"),
])
def test_invalid_car_requests_are_refused_with_a_message_and_nothing_is_saved(catalog, changes, message):
    response = book("/book/car", car_request(**changes))
    assert response.status_code == 422, response.text
    assert any(message in text for text in response.json()["errors"]), response.json()
    assert saved_bookings(catalog) == []


@pytest.mark.parametrize("changes, message", [
    ({"customer_name": ""}, "Customer name is required"),
    ({"customer_phone": "call me"}, "Philippine mobile number"),
    ({"customer_email": ""}, "Customer email is required"),
    ({"start_date": ""}, "Start date is required"),
    ({"start_date": when(-1)}, "cannot be in the past"),
    ({"end_date": when(2)}, "end date cannot be before the start date"),
    ({"guests": ""}, "Number of guests is required"),
    ({"guests": "0"}, "Number of guests is outside the allowed range"),
    ({"guests": "11"}, "seats up to 10 guests"),
    ({"tour": ""}, "Tour package is required"),
    ({"tour": "does-not-exist"}, "Choose a tour package from the list"),
    ({"tour": "closed-tour", "guests": "2"}, "currently unavailable"),
])
def test_invalid_tour_requests_are_refused_with_a_message_and_nothing_is_saved(catalog, changes, message):
    response = book("/book/tour", tour_request(**changes))
    assert response.status_code == 422, response.text
    assert any(message in text for text in response.json()["errors"]), response.json()
    assert saved_bookings(catalog) == []


def test_a_tour_without_vehicle_details_has_no_guest_limit(catalog):
    assert book("/book/tour", tour_request(tour="plain-tour", guests="30")).status_code == 201


def test_a_form_cannot_book_the_other_kind_of_item(catalog):
    assert book("/book/car", car_request(car="island-day-tour")).status_code == 422
    assert book("/book/tour", tour_request(tour="family-suv")).status_code == 422
    assert saved_bookings(catalog) == []


# ---- dates that are already taken ----
def test_an_approved_booking_blocks_overlapping_dates_for_that_car(catalog):
    add_booking("approved", 5, 7)
    for start, end in ((4, 5), (6, 6), (7, 9), (3, 10)):
        response = book("/book/car", car_request(start_date=when(start), end_date=when(end)))
        assert response.status_code == 422, (start, end)
        assert "already booked" in response.json()["errors"][0]
    assert len(saved_bookings(catalog)) == 1  # only the one added directly


def test_the_days_just_before_and_after_an_approved_booking_are_free(catalog):
    add_booking("approved", 5, 7)
    assert book("/book/car", car_request(start_date=when(2), end_date=when(4))).status_code == 201
    assert book("/book/car", car_request(start_date=when(8), end_date=when(9))).status_code == 201


def test_an_ongoing_booking_still_blocks_its_dates(catalog):
    add_booking("ongoing", 5, 7)
    assert book("/book/car", car_request()).status_code == 422


@pytest.mark.parametrize("status", ["pending", "rejected", "cancelled", "completed"])
def test_only_approved_and_ongoing_bookings_block_dates(catalog, status):
    add_booking(status, 5, 7)
    assert book("/book/car", car_request()).status_code == 201


def test_a_booking_for_another_car_does_not_block(catalog):
    add_booking("approved", 5, 7, item="City Car")
    assert book("/book/car", car_request()).status_code == 201


def test_a_car_booking_does_not_block_a_tour_with_the_same_name(catalog):
    add_booking("approved", 10, 10, kind="car", item="Island Day Tour")
    assert book("/book/tour", tour_request()).status_code == 201


def test_an_approved_tour_blocks_that_tour_only(catalog):
    add_booking("approved", 10, 10, kind="tour", item="Island Day Tour")
    assert book("/book/tour", tour_request()).status_code == 422
    assert book("/book/tour", tour_request(tour="plain-tour")).status_code == 201


def test_blocked_dates_are_on_the_page_without_any_customer_details(catalog):
    add_booking("approved", 5, 7)
    add_booking("pending", 20, 21)
    html = client.get("/book/car").text
    data = json.loads(re.search(r'<script type="application/json" id="blocked-dates">(.*?)</script>', html, re.S).group(1))
    assert data["Family SUV"] == [[when(5), when(7)]] and data["City Car"] == []
    assert "Earlier Customer" not in html and "09170000000" not in html


def test_without_a_database_nothing_is_blocked():
    assert service.blocked_ranges("car", "Family SUV") == []


# ---- abuse and failure ----
def test_the_hidden_field_makes_a_bot_look_successful_but_saves_nothing(catalog):
    for url, data in (("/book/car", car_request()), ("/book/tour", tour_request())):
        csrf_token = _get_csrf_token()
        response = client.post(url, data=data | {"website": "http://spam.example"}, headers={"X-CSRF-Token": csrf_token})
        assert response.status_code == 201 and response.json()["reference"] == ""
    assert saved_bookings(catalog) == []


def test_too_many_requests_from_one_address_are_refused(catalog, monkeypatch):
    monkeypatch.setattr(bookings_route, "limiter", RateLimiter(max_hits=2, window_seconds=600))
    codes = [book("/book/car", car_request(start_date=when(20 + 3 * i), end_date=when(21 + 3 * i))).status_code
             for i in range(3)]
    assert codes == [201, 201, 429]
    assert len(saved_bookings(catalog)) == 2


def test_without_a_database_the_request_is_refused_politely():
    for url, data in (("/book/car", car_request()), ("/book/tour", tour_request())):
        csrf_token = _get_csrf_token()
        response = client.post(url, data=data, headers={"X-CSRF-Token": csrf_token})
        assert response.status_code == 503 and "Messenger" in response.json()["errors"][0]


def test_a_storage_failure_gives_a_generic_message_and_no_internals(catalog, monkeypatch):
    def broken(data, email_verified=False):
        raise RuntimeError("secret firestore detail")
    monkeypatch.setattr(service, "create_car_booking", broken)
    response = book("/book/car", car_request())
    assert response.status_code == 503
    assert "secret" not in response.text and "try again" in response.json()["errors"][0]


def test_the_rate_limiter_forgets_old_attempts():
    now = [0.0]
    limiter = RateLimiter(max_hits=2, window_seconds=60, clock=lambda: now[0])
    assert [limiter.allow("a"), limiter.allow("a"), limiter.allow("a")] == [True, True, False]
    assert limiter.allow("b")  # another visitor is unaffected
    now[0] = 61
    assert limiter.allow("a")


# ---- the pages ----
def field_names(html: str) -> set[str]:
    form = html.split('id="booking-form"')[1].split("</form>")[0]
    return set(re.findall(r'<(?:input|select|textarea)[^>]* name="([a-z_]+)"', form))


def test_the_car_page_has_every_field_the_server_expects():
    html = client.get("/book/car").text
    assert field_names(html) >= {"car", "start_date", "start_time", "end_date", "end_time", "pickup_location",
                                 "dropoff_location", "destination", "passengers", "driver_option", "details",
                                 "customer_name", "customer_phone", "customer_email", "website"}
    assert 'action="/book/car"' in html and 'method="post"' in html and f'min="{today_ph().isoformat()}"' in html
    assert re.search(r'<input id="bk-email"[^>]* required', html) and 'id="booking-view-code"' in html
    form_html = html.split('id="booking-form"')[1].split("</form>")[0]
    ids = re.findall(r'<(?:input|select|textarea) id="(bk-[a-z-]+)"', form_html)
    assert ids and all(re.search(rf'id="{i}"[^>]*>.*?<label[^>]*for="{i}"', form_html, re.DOTALL) for i in ids)


def test_the_tour_page_has_every_field_the_server_expects():
    html = client.get("/book/tour").text
    assert field_names(html) >= {"tour", "start_date", "end_date", "guests", "pickup_location", "details",
                                 "customer_name", "customer_phone", "customer_email", "website"}
    assert field_names(html).isdisjoint({"dropoff_location", "destination", "driver_option", "start_time", "end_time"})
    assert 'action="/book/tour"' in html
    form_html = html.split('id="booking-form"')[1].split("</form>")[0]
    ids = re.findall(r'<(?:input|select|textarea) id="(bk-[a-z-]+)"', form_html)
    assert ids and all(re.search(rf'id="{i}"[^>]*>.*?<label[^>]*for="{i}"', form_html, re.DOTALL) for i in ids)


def test_each_page_loads_the_calendar_from_a_pinned_cdn_version_with_an_integrity_check():
    for url in ("/book/car", "/book/tour"):
        html = client.get(url).text
        assert re.search(r'<script src="https://cdn\.jsdelivr\.net/npm/flatpickr@4\.6\.13/dist/flatpickr\.min\.js" integrity="sha384-', html)
        assert re.search(r'<link rel="stylesheet" href="https://cdn\.jsdelivr\.net/npm/flatpickr@4\.6\.13/dist/flatpickr\.min\.css" integrity="sha384-', html)
        assert 'id="bk-calendar"' in html


def test_the_chosen_item_is_preselected_and_unavailable_ones_are_not_offered(catalog):
    html = client.get("/book/car?car=city-car").text
    assert re.search(r'<option value="city-car" selected', html)
    options = html.split('id="bk-item"')[1].split("</select>")[0]
    assert "Family SUV" in options and "City Car" in options and "Old Car" not in options
    tours = client.get("/book/tour?tour=plain-tour").text
    assert re.search(r'<option value="plain-tour" selected', tours) and "Closed Tour" not in tours


def test_an_unknown_choice_falls_back_to_the_first_item(catalog):
    assert re.search(r'<option value="city-car" selected', client.get("/book/car?car=nope").text)


def test_the_tour_page_shows_the_tours_own_vehicle(catalog):
    html = client.get("/book/tour?tour=island-day-tour").text
    assert "Vehicle for this tour" in html and "Toyota Hiace" in html and 'data-vehicle-seats="10"' in html
    plain = client.get("/book/tour?tour=plain-tour").text
    assert re.search(r'<div class="book__vehicle"[^>]* hidden>', plain)


def test_vans_belong_to_tours_not_to_car_rental():
    assert "Passenger Van" in client.get("/book/tour").text  # the sample tours carry a van
    assert "Passenger Van" not in client.get("/book/car").text
    home = client.get("/").text
    assert "Passenger Van" not in home.split('id="car-rental"')[1].split("</section>")[0]


def test_a_page_with_nothing_to_book_says_so_and_offers_messenger(fake_db):
    for url in ("/book/car", "/book/tour"):
        html = client.get(url).text
        assert "open for booking right now" in html and "m.me/" in html and 'id="booking-form"' not in html


def test_the_booking_pages_link_back_to_the_landing_page_sections():
    html = client.get("/book/car").text
    assert 'href="/#tours"' in html and 'href="/#home"' in html and 'href="/#services"' in html
    assert 'href="/"' in html  # breadcrumb


def test_messenger_stays_available_as_a_secondary_way_to_ask():
    for url in ("/book/car", "/book/tour"):
        assert "Message us on Messenger" in client.get(url).text


# ---- landing page ----
def test_the_landing_page_buttons_lead_to_the_booking_pages(catalog):
    html = client.get("/").text
    assert 'href="/book/car?car=family-suv"' in html and 'href="/book/tour?tour=island-day-tour"' in html
    assert "booking-dialog" not in html and "data-book" not in html
    assert html.count('class="btn btn--action btn--sm site-header__cta" href="#services"') == 1
    assert 'class="btn btn--action btn--block" href="#services"' in html


def test_unavailable_items_cannot_be_booked_from_the_site(catalog):
    html = client.get("/").text
    assert "/book/car?car=old-car" not in html and "/book/tour?tour=closed-tour" not in html
    assert "Currently unavailable</button>" in html


def test_the_tour_details_dialog_links_to_the_tour_booking_page(catalog):
    html = client.get("/").text
    dialog = html.split('id="tour-island-day-tour"')[1].split("</dialog>")[0]
    assert 'href="/book/tour?tour=island-day-tour"' in dialog and "Toyota Hiace (10 seats)" in dialog


def test_the_form_has_a_required_agree_checkbox_for_the_terms_and_privacy_policy():
    html = client.get("/book/car").text
    assert 'name="agree"' in html and 'type="checkbox"' in html and "required" in html.split('name="agree"')[1][:60]
    assert 'href="/terms"' in html and 'href="/privacy"' in html


def test_a_request_without_the_agree_box_is_refused_and_sends_no_code(fake_db):
    for path, data in (("/book/car", car_request()), ("/book/tour", tour_request())):
        for missing in ({"agree": ""}, {"agree": "no"}):
            csrf_token = _get_csrf_token()
            response = client.post(path, data=data | missing, headers={"X-CSRF-Token": csrf_token})
            assert response.status_code == 422 and "Terms and Conditions" in response.json()["errors"][0]
    assert saved_bookings(fake_db) == []


# ---- privacy policy, form alerts, CSRF from script ----
def test_the_privacy_policy_is_general_and_says_nothing_about_the_admin_side():
    html = client.get("/privacy").text.lower()
    for internal in ("admin", "sign in", "sign-in", "signed-in", "firebase", "gmail", "resend", "turnstile",
                     "payment status", "reference number", "6-digit", "approved"):
        assert internal not in html, internal
    assert "data privacy act" in html and "your rights" in html  # the notice itself is still complete


def test_the_booking_form_shows_problems_in_sweetalert_with_inline_boxes_as_the_fallback():
    html = client.get("/book/car").text
    assert "sweetalert2@11.26.25" in html and 'integrity="sha384-' in html  # pinned and integrity-checked
    assert html.index("sweetalert2") < html.index("booking.js")  # loaded first
    assert 'id="booking-errors"' in html and 'id="code-errors"' in html  # used only if the CDN fails
    js = client.get("/static/customer/js/booking.js").text
    assert "Swal.fire" in js and "window.Swal" in js and "textContent" in js  # customer text is never set as HTML
    assert "html: list" in js and ".innerHTML" not in js


def test_booking_js_sends_the_csrf_token_with_the_code_and_resend_requests():
    js = client.get("/static/customer/js/booking.js").text
    assert js.count("...csrfHeaders") == 2 and '"X-CSRF-Token"' in js
