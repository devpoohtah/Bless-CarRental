import re
from datetime import date

from fastapi.testclient import TestClient

from app.main import app
from app.services import bookings as service

client = TestClient(app)
TODAY = date.today()


# ---- data and status flow ----
def test_sample_data_covers_every_status_and_both_types():
    rows = service.list_bookings()
    assert {b.status for b in rows} == set(service.STATUS_LABELS)
    assert {b.booking_type for b in rows} == {"car", "tour"}
    assert all(b.is_sample for b in rows)


def test_status_flow_is_consistent():
    assert set(service.NEXT_STATUSES) == set(service.STATUS_LABELS)
    for status, targets in service.NEXT_STATUSES.items():
        assert status not in targets and set(targets) <= set(service.STATUS_LABELS)
    for final in ("rejected", "completed", "cancelled"):
        assert service.NEXT_STATUSES[final] == []


def test_history_ends_at_the_current_status():
    for b in service.list_bookings():
        assert b.history[-1].status == b.status


# ---- list and filters ----
def test_list_shows_all_bookings_with_filter_links():
    html = client.get("/admin/bookings").text
    assert "Booking Management" in html
    assert html.count('href="/admin/bookings/sample-') == len(service.list_bookings())
    for href in ("/admin/bookings", "/admin/bookings?type=car", "/admin/bookings?type=tour"):
        assert f'href="{href}"' in html
    assert re.search(r'href="/admin/bookings"[^>]*aria-current="page"', html)  # sidebar link


def test_filter_by_type():
    cars = client.get("/admin/bookings?type=car").text
    tours = client.get("/admin/bookings?type=tour").text
    n_cars = len(service.list_bookings("car"))
    assert cars.count('href="/admin/bookings/sample-') == n_cars
    assert tours.count('href="/admin/bookings/sample-') == len(service.list_bookings("tour"))
    assert "Tour booking</span>" not in cars and "Car rental</span>" not in tours
    assert re.search(r'href="/admin/bookings\?type=car" aria-current="true"', cars)


def test_unknown_filter_value_shows_everything():
    html = client.get("/admin/bookings?type=nonsense").text
    assert html.count('href="/admin/bookings/sample-') == len(service.list_bookings())


# ---- detail ----
def test_detail_shows_customer_item_dates_payment_and_history():
    b = service.get_booking("sample-3")
    html = client.get("/admin/bookings/sample-3").text
    for expected in (b.customer_name, b.customer_phone, b.customer_email, b.item_name,
                     "Pick-up date", "Return date", "Partially paid", "Booking history",
                     "Customer information"):
        assert expected in html, expected
    assert html.count('<li>') >= len(b.history)
    assert "Current" in html


def test_detail_wording_differs_for_tours():
    html = client.get("/admin/bookings/sample-2").text
    assert "Selected tour package" in html and "Start date" in html and "Pick-up date" not in html


def test_sample_bookings_have_no_working_controls():
    html = client.get("/admin/bookings/sample-1").text
    assert "sample booking" in html and "Save status" not in html and "Approve" not in html


def test_unknown_booking_is_404():
    assert client.get("/admin/bookings/nope").status_code == 404


# ---- calendar ----
def test_calendar_defaults_to_current_month_with_legend_and_nav():
    html = client.get("/admin/calendar").text
    assert "Booking Calendar" in html and TODAY.strftime("%B %Y") in html
    for word in ("Pending", "Approved", "Ongoing", "Car rental", "Tour booking"):
        assert word in html
    assert "?month=" in html and "is-today" in html
    assert re.search(r'href="/admin/calendar"[^>]*aria-current="page"', html)


def test_calendar_shows_only_scheduled_statuses():
    html = client.get("/admin/calendar").text
    shown = set(re.findall(r'href="/admin/bookings/(sample-\d)"', html))
    expected = {b.id for b in service.list_bookings() if b.status in service.CALENDAR_STATUSES}
    # bookings that fall outside the displayed weeks are fine to miss; hidden statuses never appear
    hidden = {b.id for b in service.list_bookings() if b.status not in service.CALENDAR_STATUSES}
    assert shown and shown <= expected and not (shown & hidden)


def test_calendar_marks_pending_and_approved_differently():
    html = client.get("/admin/calendar").text
    assert "chip chip--pending" in html and "chip chip--approved" in html
    assert ", Car rental, Approved" in html and ", Car rental, Pending" in html  # words for screen readers


def test_multi_day_booking_appears_on_every_day():
    view = service.month_view(TODAY.replace(day=1), TODAY)
    booking = service.get_booking("sample-3")  # approved, today+1 .. today+4
    days_with = [c["date"] for week in view["weeks"] for c in week
                 if any(b.id == booking.id for b in c["bookings"])]
    assert days_with and all(booking.start_date <= d <= booking.end_date for d in days_with)


def test_calendar_month_param_and_bad_values():
    assert "December 2030" in client.get("/admin/calendar?month=2030-12").text
    assert "No scheduled bookings this month." in client.get("/admin/calendar?month=2030-12").text
    for bad in ("garbage", "2026-13", "1999-01", "9999-12", ""):
        response = client.get(f"/admin/calendar?month={bad}")
        assert response.status_code == 200 and TODAY.strftime("%B %Y") in response.text, bad


def test_calendar_navigation_wraps_years():
    view = service.month_view(date(2026, 1, 1), TODAY)
    assert view["previous_month"] == "2025-12"
    assert service.month_view(date(2026, 12, 1), TODAY)["next_month"] == "2027-01"


def test_calendar_has_a_phone_agenda_with_links():
    html = client.get("/admin/calendar").text
    assert 'class="agenda"' in html and 'class="agenda__item" href="/admin/bookings/sample-' in html


# ---- assets ----
def test_booking_pages_assets_load():
    for url in ("/admin/bookings", "/admin/bookings/sample-1", "/admin/calendar"):
        html = client.get(url).text
        for path in set(re.findall(r'(?:src|href)="(/static/[^"?]+)', html)):
            assert client.get(path).status_code == 200, (url, path)
