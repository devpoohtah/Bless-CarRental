"""Car rental prices: days at the car's daily rate plus the extension rates for the leftover hours. The rates are
saved in the database and edited on the Pricing page, so they can change without a code change."""

from datetime import date, time
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.ratelimit import RateLimiter
from app.db import repositories as repo
from app.main import app
from app.schemas.catalog import Availability  # noqa: F401
from app.schemas.pricing import CarPricing, SeatRates
from app.services import notify, pricing
from tests.test_public_booking import PHOTO, book, car_request, catalog, fresh_limiter, saved_bookings, when  # noqa: F401
from app.schemas.catalog import Vehicle

client = TestClient(app)
pytestmark = pytest.mark.usefixtures("simulated_otp")

DAY1, DAY4 = date(2030, 1, 1), date(2030, 1, 4)
FIVE = SimpleNamespace(daily_rate_php=1500, seats=5)
SEVEN = SimpleNamespace(daily_rate_php=2500, seats=7)


def total(car, extra_hours=0, days=3, extra_minutes=0, **kw):
    """The total for a pick-up at 8:00 and a return `days` days, `extra_hours` hours and some minutes later."""
    end_minutes = 8 * 60 + extra_hours * 60 + extra_minutes
    end = date(2030, 1, 1 + days + end_minutes // 1440)
    leftover = end_minutes % 1440
    price = pricing.quote(car, DAY1, time(8, 0), end, time(leftover // 60, leftover % 60), **kw)
    return price.total_php if price else None


# ---- the sum ----
@pytest.mark.parametrize("extra, expected", [
    (0, 4500),        # exactly 3 days
    (1, 4500 + 200),  # up to 3 hours: per hour
    (3, 4500 + 600),
    (4, 4500 + 1000),  # 4 to 12 hours: one flat price
    (12, 4500 + 1000),
    (13, 4500 + 1500),  # 13 to 24 hours: one more day
    (23, 4500 + 1500),
])
def test_a_five_seater(extra, expected):
    assert total(FIVE, extra) == expected


@pytest.mark.parametrize("extra, expected", [
    (0, 7500),
    (1, 7500 + 250),
    (4, 7500 + 1000),  # up to 4 hours: per hour
    (5, 7500 + 1500),  # 5 to 12 hours: flat
    (12, 7500 + 1500),
    (13, 7500 + 2500),  # 13 to 24 hours: one more day
])
def test_a_seven_seater(extra, expected):
    assert total(SEVEN, extra) == expected


def test_24_extra_hours_is_simply_one_more_day():
    price = pricing.quote(FIVE, DAY1, time(8, 0), date(2030, 1, 5), time(8, 0))
    assert price.total_php == 6000 and price.days == 4 and price.extra_hours == 0
    assert [line.label for line in price.lines] == ["4 days × ₱1,500"]


def test_a_rental_under_24_hours_uses_the_extension_rates():
    short = lambda car, hours: pricing.quote(car, DAY1, time(8, 0), DAY1, time(8 + hours, 0)).total_php
    assert short(FIVE, 2) == 400 and short(FIVE, 6) == 1000 and short(FIVE, 15) == 1500
    assert short(SEVEN, 3) == 750 and short(SEVEN, 6) == 1500


def test_part_of_an_hour_counts_as_a_full_hour():
    assert total(FIVE, 1, extra_minutes=1) == 4500 + 400  # 1h01 -> 2 hours
    assert total(FIVE, 0, extra_minutes=1) == 4500 + 200  # 1 minute -> 1 hour


def test_the_lines_explain_the_total():
    price = pricing.quote(FIVE, DAY1, time(8, 0), DAY4, time(14, 0))
    assert [(line.label, line.amount_php) for line in price.lines] == [
        ("3 days × ₱1,500", 4500), ("6 extra hours (flat rate)", 1000)]
    one = pricing.quote(FIVE, DAY1, time(8, 0), date(2030, 1, 2), time(9, 0))
    assert [(line.label, line.amount_php) for line in one.lines] == [("1 day × ₱1,500", 1500), ("1 extra hour × ₱200", 200)]


@pytest.mark.parametrize("seats", [1, 4, 5, 6, 7])
def test_seat_size_picks_the_extension_rates(seats):
    car = SimpleNamespace(daily_rate_php=1500, seats=seats)
    assert total(car, 5) == 3 * 1500 + (1000 if seats <= 5 else 1500)  # 5 extra hours: flat 1000 or 1500


@pytest.mark.parametrize("car", [
    SimpleNamespace(daily_rate_php=None, seats=5), SimpleNamespace(daily_rate_php=0, seats=5),
    SimpleNamespace(daily_rate_php=1500, seats=None), SimpleNamespace(daily_rate_php=1500, seats=12),
])
def test_no_price_when_it_cannot_be_worked_out(car):
    assert pricing.quote(car, DAY1, time(8, 0), DAY4, time(8, 0)) is None


@pytest.mark.parametrize("args", [
    (DAY1, None, DAY4, time(8, 0)), (DAY1, time(8, 0), DAY4, None),
    (DAY1, time(8, 0), DAY1, time(8, 0)),  # returns the moment it leaves
    (DAY4, time(8, 0), DAY1, time(8, 0)),  # returns before it leaves
])
def test_no_price_without_usable_times(args):
    assert pricing.quote(FIVE, args[0], args[1], args[2], args[3]) is None


# ---- the rules come from the database ----
CHEAPER = CarPricing(flat_until_hours=10, five_seater=SeatRates(hourly_rate_php=300, hourly_hours=2, flat_php=900),
                     seven_seater=SeatRates(hourly_rate_php=400, hourly_hours=1, flat_php=1200))


def test_the_rules_passed_in_decide_the_price():
    assert total(FIVE, 2, rules=CHEAPER) == 4500 + 600      # 2 hours x 300
    assert total(FIVE, 6, rules=CHEAPER) == 4500 + 900      # flat 900
    assert total(FIVE, 11, rules=CHEAPER) == 4500 + 1500    # past 10 hours: one more day
    assert total(SEVEN, 1, rules=CHEAPER) == 7500 + 400


def test_built_in_rates_are_used_until_something_is_saved(fake_db):
    rules = pricing.load_rules()
    assert rules.five_seater.hourly_rate_php == 200 and rules.seven_seater.flat_php == 1500 and rules.flat_until_hours == 12


def test_saved_rules_are_loaded_and_used(fake_db):
    pricing.save_rules(CHEAPER)
    assert pricing.load_rules() == CHEAPER
    assert total(FIVE, 6, rules=None) == 4500 + 900  # quote() reads the saved rules itself


def test_a_damaged_saved_document_falls_back_to_the_built_in_rates(fake_db):
    fake_db.data["settings"] = {"car_pricing": {"flat_until_hours": "lots"}}
    assert pricing.load_rules() == CarPricing()


def test_saving_clears_the_cache(fake_db):
    assert pricing.load_rules().five_seater.hourly_rate_php == 200
    pricing.save_rules(CHEAPER)
    assert pricing.load_rules().five_seater.hourly_rate_php == 300


def test_the_hourly_hours_must_be_fewer_than_the_flat_hours():
    with pytest.raises(ValidationError):
        CarPricing(flat_until_hours=3, five_seater=SeatRates(hourly_rate_php=1, hourly_hours=3, flat_php=1),
                   seven_seater=SeatRates(hourly_rate_php=1, hourly_hours=1, flat_php=1))


# ---- a booking is priced on the server ----
def add_car(db, car_id="priced-suv", seats=7, rate=2500):
    repo.save(repo.CARS, Vehicle(id="", name=car_id.replace("-", " ").title(), vehicle_type="SUV", seats=seats,
                                 daily_rate_php=rate, availability="available", photo=PHOTO, is_sample=False), car_id)


def priced_request(**changes):
    return car_request(car="priced-suv", start_date=when(5), start_time="08:00", end_date=when(8), end_time="14:00",
                       passengers="4") | changes


def test_a_booking_keeps_its_total_and_how_it_was_worked_out(catalog):
    add_car(catalog)
    assert book("/book/car", priced_request()).status_code == 201  # 3 days + 6 hours on a 7-seater
    [saved] = saved_bookings(catalog)
    assert saved["total_php"] == 3 * 2500 + 1500
    assert [(line["label"], line["amount_php"]) for line in saved["price_lines"]] == [
        ("3 days × ₱2,500", 7500), ("6 extra hours (flat rate)", 1500)]


def test_later_price_changes_do_not_touch_bookings_already_received(catalog):
    add_car(catalog)
    book("/book/car", priced_request())
    pricing.save_rules(CHEAPER)
    book("/book/car", priced_request())  # pending bookings do not block the dates
    first, second = [doc["total_php"] for doc in saved_bookings(catalog)]
    assert first == 9000 and second == 7500 + 1200  # 6 hours: flat 1200 under the new rates


@pytest.mark.parametrize("seats, rate", [(7, None), (12, 3000)])
def test_a_request_with_no_possible_price_is_still_saved_without_a_total(catalog, seats, rate):
    add_car(catalog, "odd-car", seats, rate)
    assert book("/book/car", priced_request(car="odd-car")).status_code == 201
    [saved] = saved_bookings(catalog)
    assert saved["total_php"] is None and saved["price_lines"] == []


def test_the_customer_cannot_set_the_price(catalog):
    add_car(catalog)
    book("/book/car", priced_request(total_php="1", price_lines="x", daily_rate_php="1"))
    assert saved_bookings(catalog)[0]["total_php"] == 9000


def test_the_alert_to_the_owner_shows_the_estimate(catalog):
    add_car(catalog)
    book("/book/car", priced_request())
    from app.schemas.booking import Booking
    [saved] = saved_bookings(catalog)
    text = notify.booking_alert_text(Booking(**{**saved, "id": "x"}))
    assert "Estimated total: ₱9,000" in text


# ---- the live estimate on the form ----
def quote_url(**changes):
    query = dict(car="priced-suv", start_date=when(5), start_time="08:00", end_date=when(8), end_time="14:00") | changes
    return "/book/car/quote?" + "&".join(f"{k}={v}" for k, v in query.items())


def test_the_estimate_endpoint_matches_the_saved_total(catalog):
    add_car(catalog)
    body = client.get(quote_url()).json()
    assert body == {"ok": True, "total": "₱9,000", "lines": [
        {"label": "3 days × ₱2,500", "amount": "₱7,500"}, {"label": "6 extra hours (flat rate)", "amount": "₱1,500"}]}
    assert client.get(quote_url()).headers["cache-control"] == "no-store"


@pytest.mark.parametrize("changes", [
    dict(car="no-such-car"), dict(start_date="not-a-date"), dict(start_time="25:99"), dict(end_time=""),
    dict(end_date=when(1)),  # returns before it leaves
])
def test_the_estimate_says_no_for_anything_it_cannot_price(catalog, changes):
    add_car(catalog)
    assert client.get(quote_url(**changes)).json() == {"ok": False}


def test_the_estimate_endpoint_is_rate_limited(catalog, monkeypatch):
    from app.api.routes import bookings
    add_car(catalog)
    monkeypatch.setattr(bookings, "quote_limiter", RateLimiter(max_hits=2, window_seconds=60))
    assert [client.get(quote_url()).status_code for _ in range(3)] == [200, 200, 429]


def test_the_car_form_requires_both_times_and_has_an_estimate_panel(catalog):
    page = client.get("/book/car").text
    assert 'name="start_time" type="time" required' in page and 'name="end_time" type="time" required' in page
    assert page.count("data-quote") == 2
    assert "data-quote" not in client.get("/book/tour").text


# ---- the Pricing page ----
def post_admin(url, data):
    client.get("/")
    return client.post(url, data=data, headers={"X-CSRF-Token": client.cookies.get("csrf_token", "")}, follow_redirects=False)


NEW_RATES = dict(flat_until_hours="10", five_hourly_rate_php="300", five_hourly_hours="2", five_flat_php="900",
                 seven_hourly_rate_php="400", seven_hourly_hours="1", seven_flat_php="1200")


def test_the_pricing_page_shows_the_saved_rates_and_examples(fake_db):
    page = client.get("/admin/pricing").text
    assert 'name="five_hourly_rate_php" type="number" value="200"' in page
    assert "5-seater at ₱1,500 a day, 3 days + 6 hrs: <strong>₱5,500</strong>" in page
    assert "7-seater at ₱2,500 a day, 3 days + 15 hrs: <strong>₱10,000</strong>" in page
    assert 'href="/admin/pricing"' in page


def test_saving_new_rates_changes_new_prices_at_once(fake_db):
    response = post_admin("/admin/pricing", NEW_RATES)
    assert response.status_code == 303 and "notice=saved" in response.headers["location"]
    assert fake_db.data["settings"]["car_pricing"]["five_seater"] == {"hourly_rate_php": 300, "hourly_hours": 2, "flat_php": 900}
    assert pricing.load_rules().flat_until_hours == 10
    assert "5-seater at ₱1,500 a day, 3 days + 6 hrs: <strong>₱5,400</strong>" in client.get("/admin/pricing").text


@pytest.mark.parametrize("bad, message", [
    (dict(five_hourly_hours="10"), "fewer than the hours of the flat rate"),
    (dict(flat_until_hours="0"), "Flat rate hours"),
    (dict(five_flat_php="-5"), "5-seater flat price"),
    (dict(seven_hourly_rate_php="cheap"), "7-seater price per hour"),
    (dict(five_hourly_rate_php=""), "5-seater price per hour"),
])
def test_bad_rates_are_refused_and_nothing_is_saved(fake_db, bad, message):
    response = post_admin("/admin/pricing", NEW_RATES | bad)
    assert response.status_code == 422 and message in response.text
    assert "settings" not in fake_db.data or not fake_db.data["settings"]


def test_the_pricing_page_needs_an_admin_sign_in(fake_db, real_auth):
    response = TestClient(app).get("/admin/pricing", follow_redirects=False)
    assert response.status_code in (303, 401)


def test_pages_can_show_the_live_rates():
    from app.core.templating import templates
    assert templates.env.globals["car_pricing"]().five_seater.hourly_rate_php == 200


# ---- the admin sees the estimate on the booking ----
def test_the_booking_page_shows_the_estimate_and_its_lines(catalog):
    add_car(catalog)
    book("/book/car", priced_request())
    [booking_id] = list(catalog.data["bookings"])
    page = client.get(f"/admin/bookings/{booking_id}").text
    assert "Estimated total" in page and "₱9,000" in page
    assert "3 days × ₱2,500: ₱7,500" in page and "6 extra hours (flat rate): ₱1,500" in page
