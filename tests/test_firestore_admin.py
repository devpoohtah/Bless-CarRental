"""Service management, booking management and the public site against an in-memory Firestore."""

import re
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import images

client = TestClient(app)
TODAY = date.today()


def _post_with_csrf(url: str, data: dict, files: dict | None = None, **kwargs):
    """Helper to POST with CSRF token from the cookie."""
    # GET first to set the CSRF cookie
    client.get(url.replace("/edit", "").replace("/delete", "").replace("/new", "").replace("/status", "").replace("/payment", ""))
    csrf_token = client.cookies.get("csrf_token", "")
    # Send CSRF token in header (middleware checks header first)
    headers = {"X-CSRF-Token": csrf_token}
    return client.post(url, data=data, files=files, headers=headers, **kwargs)

CAR = dict(name="Toyota Vios", vehicle_type="Sedan", seats="5", transmission="Automatic",
           daily_rate_php="2500", availability="available",
           summary="Reliable sedan for city and highway driving.",
           description="A well-maintained sedan suitable for daily commuting and weekend trips. Features air conditioning and comfortable seating for 5.")
TOUR = dict(name="Guimaras Day Trip", destination="Guimaras", duration="1 day", summary="Island day trip.",
            description="Full day on the island.", price_php="1800", availability="inquire")


@pytest.fixture
def uploads(monkeypatch):
    """Fake image storage: records uploads and deletions."""
    log = {"uploaded": [], "deleted": []}

    def fake_upload(file, folder):
        log["uploaded"].append((file.filename, folder))
        n = len(log["uploaded"])
        return images.UploadedImage(url=f"https://res.cloudinary.com/demo/{folder}/{n}.webp", public_id=f"bless/{folder}/{n}")

    monkeypatch.setattr(images, "upload", fake_upload)
    monkeypatch.setattr(images, "delete", lambda public_id: log["deleted"].append(public_id))
    return log


def only_id(db, collection):
    (doc_id,) = db.data[collection]
    return doc_id


# ---- cars ----
def test_create_car_saves_a_real_record_with_placeholder_photo(fake_db, uploads):
    response = _post_with_csrf("/admin/services/cars/new", CAR, follow_redirects=False)
    assert response.status_code == 303 and response.headers["location"] == "/admin/services/cars?notice=saved"
    doc = fake_db.data["cars"][only_id(fake_db, "cars")]
    assert doc["name"] == "Toyota Vios" and doc["seats"] == 5 and doc["daily_rate_php"] == 2500
    assert doc["is_sample"] is False and doc["photo"]["src"].endswith("service-car-rental-placeholder.svg")
    assert "id" not in doc and uploads["uploaded"] == []
    html = client.get("/admin/services/cars").text
    assert "Toyota Vios" in html and "Saved." not in html  # notice only with ?notice=
    assert "Saved." in client.get("/admin/services/cars?notice=saved").text
    assert "sample data" not in html


def test_create_car_with_image_stores_the_cloudinary_url_and_id(fake_db, uploads):
    _post_with_csrf("/admin/services/cars/new", CAR, files={"image": ("vios.jpg", b"x", "image/jpeg")})
    photo = fake_db.data["cars"][only_id(fake_db, "cars")]["photo"]
    assert photo["src"] == "https://res.cloudinary.com/demo/cars/1.webp" and photo["public_id"] == "bless/cars/1"
    assert 'src="https://res.cloudinary.com/demo/cars/1.webp"' in client.get("/").text  # public site, unchanged URL


def test_invalid_car_shows_messages_and_keeps_what_was_typed(fake_db, uploads):
    response = _post_with_csrf("/admin/services/cars/new", {**CAR, "name": "", "seats": "abc", "daily_rate_php": "-5"})
    assert response.status_code == 422
    html = response.text
    assert "Name is required." in html and "Seats must be a whole number." in html
    assert "Daily rate is outside the allowed range." in html
    assert 'value="Sedan"' in html  # the valid fields are still filled in
    assert fake_db.data.get("cars", {}) == {}


def test_image_problem_is_shown_on_the_form_and_nothing_is_saved(fake_db, monkeypatch):
    def refuse(file, folder):
        raise images.ImageError("The file must be a JPEG, PNG or WebP image.")
    monkeypatch.setattr(images, "upload", refuse)
    response = _post_with_csrf("/admin/services/cars/new", CAR, files={"image": ("a.txt", b"x", "text/plain")})
    assert response.status_code == 422 and "JPEG, PNG or WebP" in response.text
    assert fake_db.data.get("cars", {}) == {}


def test_edit_car_updates_fields_and_replacing_the_image_deletes_the_old_one(fake_db, uploads):
    _post_with_csrf("/admin/services/cars/new", CAR, files={"image": ("a.jpg", b"x", "image/jpeg")})
    car_id = only_id(fake_db, "cars")
    assert 'value="Toyota Vios"' in client.get(f"/admin/services/cars/{car_id}/edit").text
    _post_with_csrf(f"/admin/services/cars/{car_id}/edit", {**CAR, "daily_rate_php": "3000"},
                files={"image": ("b.jpg", b"y", "image/jpeg")})
    doc = fake_db.data["cars"][car_id]
    assert doc["daily_rate_php"] == 3000 and doc["photo"]["public_id"] == "bless/cars/2"
    assert uploads["deleted"] == ["bless/cars/1"]


def test_edit_without_a_new_file_keeps_the_existing_image(fake_db, uploads):
    _post_with_csrf("/admin/services/cars/new", CAR, files={"image": ("a.jpg", b"x", "image/jpeg")})
    car_id = only_id(fake_db, "cars")
    _post_with_csrf(f"/admin/services/cars/{car_id}/edit", {**CAR, "name": "Vios G"})
    doc = fake_db.data["cars"][car_id]
    assert doc["name"] == "Vios G" and doc["photo"]["public_id"] == "bless/cars/1"
    assert uploads["deleted"] == [] and len(uploads["uploaded"]) == 1


def test_delete_car_removes_the_record_and_its_image(fake_db, uploads):
    _post_with_csrf("/admin/services/cars/new", CAR, files={"image": ("a.jpg", b"x", "image/jpeg")})
    car_id = only_id(fake_db, "cars")
    response = _post_with_csrf(f"/admin/services/cars/{car_id}/delete", {}, follow_redirects=False)
    assert response.headers["location"].endswith("notice=deleted")
    assert fake_db.data["cars"] == {} and uploads["deleted"] == ["bless/cars/1"]
    assert _post_with_csrf(f"/admin/services/cars/{car_id}/delete", {}).status_code == 404


def test_unknown_car_is_404_when_connected(fake_db):
    assert client.get("/admin/services/cars/nope/edit").status_code == 404
    assert _post_with_csrf("/admin/services/cars/nope/edit", CAR).status_code == 404


def test_car_form_enables_save_delete_and_upload_when_connected(fake_db, uploads):
    _post_with_csrf("/admin/services/cars/new", CAR)
    html = client.get(f"/admin/services/cars/{only_id(fake_db, 'cars')}/edit").text
    assert not re.search(r"<button[^>]*disabled", html)
    assert 'type="file"' in html and "license plate" in html and "data-confirm" in html


# ---- tours ----
def test_tour_create_edit_delete(fake_db, uploads):
    _post_with_csrf("/admin/services/tours/new", TOUR)
    tour_id = only_id(fake_db, "tours")
    assert fake_db.data["tours"][tour_id]["price_php"] == 1800
    bad = _post_with_csrf("/admin/services/tours/new", {**TOUR, "summary": "", "description": ""})
    assert bad.status_code == 422 and "Short summary is required." in bad.text
    _post_with_csrf(f"/admin/services/tours/{tour_id}/edit", {**TOUR, "duration": "2 days"})
    assert fake_db.data["tours"][tour_id]["duration"] == "2 days"
    _post_with_csrf(f"/admin/services/tours/{tour_id}/delete", {})
    assert fake_db.data["tours"] == {}


def test_a_tour_package_keeps_its_own_vehicle_and_never_adds_it_to_car_rental(fake_db, uploads):
    van = {"vehicle_name": "Toyota Hiace", "vehicle_seats": "12"}
    _post_with_csrf("/admin/services/tours/new", TOUR | van, files={"vehicle_image": ("van.png", b"x", "image/png")})
    tour_id = only_id(fake_db, "tours")
    saved = fake_db.data["tours"][tour_id]
    assert saved["vehicle_name"] == "Toyota Hiace" and saved["vehicle_seats"] == 12
    assert saved["vehicle_photo"]["src"].startswith("https://res.cloudinary.com/demo/tour-vehicles/")
    assert uploads["uploaded"] == [("van.png", "tour-vehicles")]
    assert "cars" not in fake_db.data or fake_db.data["cars"] == {}
    assert "Toyota Hiace (12 seats)" in client.get("/admin/services/tours").text
    assert 'value="Toyota Hiace"' in client.get(f"/admin/services/tours/{tour_id}/edit").text


def test_a_vehicle_without_a_new_photo_gets_the_placeholder_and_keeps_it_on_edit(fake_db, uploads):
    _post_with_csrf("/admin/services/tours/new", TOUR | {"vehicle_name": "Toyota Hiace"})
    tour_id = only_id(fake_db, "tours")
    assert fake_db.data["tours"][tour_id]["vehicle_photo"]["src"].endswith("vehicle-passenger-van-placeholder.svg")
    _post_with_csrf(f"/admin/services/tours/{tour_id}/edit", TOUR | {"vehicle_name": "Toyota Hiace", "vehicle_seats": "9"},
                files={"vehicle_image": ("van.png", b"x", "image/png")})
    first = fake_db.data["tours"][tour_id]["vehicle_photo"]
    assert first["public_id"] == "bless/tour-vehicles/1"
    _post_with_csrf(f"/admin/services/tours/{tour_id}/edit", TOUR | {"vehicle_name": "Toyota Hiace", "vehicle_seats": "9"})
    assert fake_db.data["tours"][tour_id]["vehicle_photo"]["public_id"] == "bless/tour-vehicles/1"  # kept
    assert uploads["deleted"] == []


def test_replacing_or_removing_the_vehicle_deletes_its_old_image(fake_db, uploads):
    _post_with_csrf("/admin/services/tours/new", TOUR | {"vehicle_name": "Hiace"}, files={"vehicle_image": ("a.png", b"x", "image/png")})
    tour_id = only_id(fake_db, "tours")
    _post_with_csrf(f"/admin/services/tours/{tour_id}/edit", TOUR | {"vehicle_name": "Hiace"}, files={"vehicle_image": ("b.png", b"x", "image/png")})
    assert uploads["deleted"] == ["bless/tour-vehicles/1"]
    _post_with_csrf(f"/admin/services/tours/{tour_id}/edit", TOUR)  # vehicle name cleared
    saved = fake_db.data["tours"][tour_id]
    assert saved["vehicle_name"] is None and saved["vehicle_photo"] is None
    assert uploads["deleted"] == ["bless/tour-vehicles/1", "bless/tour-vehicles/2"]


def test_deleting_a_tour_also_deletes_its_vehicle_image(fake_db, uploads):
    _post_with_csrf("/admin/services/tours/new", TOUR | {"vehicle_name": "Hiace"}, files={"vehicle_image": ("a.png", b"x", "image/png")})
    _post_with_csrf(f"/admin/services/tours/{only_id(fake_db, 'tours')}/delete", {})
    assert fake_db.data["tours"] == {} and "bless/tour-vehicles/1" in uploads["deleted"]


def test_a_vehicle_image_needs_a_vehicle_name_and_nothing_is_uploaded_or_saved(fake_db, uploads):
    response = _post_with_csrf("/admin/services/tours/new", TOUR, files={"vehicle_image": ("van.png", b"x", "image/png")})
    assert response.status_code == 422 and "Enter the vehicle name" in response.text
    assert fake_db.data.get("tours", {}) == {} and uploads["uploaded"] == []


def test_the_vehicle_seats_must_be_a_sensible_whole_number(fake_db, uploads):
    for seats in ("0", "99", "many"):
        response = _post_with_csrf("/admin/services/tours/new", TOUR | {"vehicle_name": "Hiace", "vehicle_seats": seats})
        assert response.status_code == 422 and "Vehicle seats" in response.text, seats
    assert fake_db.data.get("tours", {}) == {}


def test_the_tour_form_has_vehicle_fields_and_its_own_image_input(fake_db):
    html = client.get("/admin/services/tours/new").text
    for expected in ('name="vehicle_name"', 'name="vehicle_seats"', 'name="vehicle_image"', 'name="image"'):
        assert expected in html
    assert re.findall(r'<input id="([^"]+)"', html).count("image") == 1  # ids stay unique


# ---- public site ----
def test_public_site_shows_firestore_items_and_drops_the_sample_notes(fake_db, uploads):
    _post_with_csrf("/admin/services/cars/new", CAR)
    _post_with_csrf("/admin/services/tours/new", TOUR)
    html = client.get("/").text
    assert "Toyota Vios" in html and "Guimaras Day Trip" in html
    assert "Compact Sedan" not in html and "Island Day Tour" not in html
    assert "Sample listings" not in html


def test_public_site_empty_state_when_connected_but_nothing_added(fake_db):
    html = client.get("/").text
    assert "No vehicles are listed right now" in html and "No tour packages are listed right now" in html
    assert "Compact Sedan" not in html


def test_one_broken_document_does_not_take_the_page_down(fake_db, uploads):
    _post_with_csrf("/admin/services/cars/new", CAR)
    fake_db.data["cars"]["broken"] = {"name": "No type or photo"}
    html = client.get("/admin/services/cars").text
    assert "Toyota Vios" in html and "No type or photo" not in html


# ---- bookings ----
def make_inventory(fake_db, uploads):
    _post_with_csrf("/admin/services/cars/new", CAR)
    _post_with_csrf("/admin/services/tours/new", TOUR)


def booking_form(**overrides):
    data = dict(item="car:Toyota Vios", customer_name="Ana Reyes", customer_phone="0917 000 0000",
                customer_email="ana@example.com", start_date=(TODAY + timedelta(days=2)).isoformat(),
                end_date=(TODAY + timedelta(days=4)).isoformat(), details="Airport pick-up",
                payment_status="unpaid")
    return data | overrides


def test_booking_form_lists_cars_and_tours_and_is_linked_from_the_list(fake_db, uploads):
    make_inventory(fake_db, uploads)
    html = client.get("/admin/bookings/new").text
    assert 'value="car:Toyota Vios"' in html and 'value="tour:Guimaras Day Trip"' in html
    assert 'href="/admin/bookings/new"' in client.get("/admin/bookings").text
    labels = re.findall(r'<(?:input|select|textarea) id="([^"]+)"', html)
    assert labels and all(f'for="{i}"' in html for i in labels)


def test_create_booking_starts_pending_with_history_and_appears_everywhere(fake_db, uploads):
    make_inventory(fake_db, uploads)
    response = _post_with_csrf("/admin/bookings/new", booking_form(), follow_redirects=False)
    booking_id = only_id(fake_db, "bookings")
    assert response.headers["location"] == f"/admin/bookings/{booking_id}?notice=created"
    doc = fake_db.data["bookings"][booking_id]
    assert doc["status"] == "pending" and doc["booking_type"] == "car" and doc["item_name"] == "Toyota Vios"
    assert doc["history"] == [{"status": "pending", "changed_on": TODAY.isoformat()}]
    assert doc["requested_on"] == TODAY.isoformat() and doc["is_sample"] is False
    detail = client.get(f"/admin/bookings/{booking_id}?notice=created").text
    assert "Ana Reyes" in detail and "Booking added." in detail and "Approve" in detail
    assert "Ana Reyes" in client.get("/admin/bookings").text
    assert "Ana Reyes" in client.get("/admin/dashboard").text
    assert "Ana Reyes" in client.get("/admin/calendar").text  # pending bookings are on the calendar


def test_tour_booking_gets_the_tour_type(fake_db, uploads):
    make_inventory(fake_db, uploads)
    _post_with_csrf("/admin/bookings/new", booking_form(item="tour:Guimaras Day Trip"))
    assert fake_db.data["bookings"][only_id(fake_db, "bookings")]["booking_type"] == "tour"


@pytest.mark.parametrize("overrides, message", [
    ({"customer_name": ""}, "Customer name is required."),
    ({"customer_phone": ""}, "Customer phone is required."),
    ({"start_date": "not-a-date"}, "Start date must be a valid date."),
    ({"end_date": (TODAY - timedelta(days=30)).isoformat()}, "The end date cannot be before the start date."),
    ({"item": ""}, "Car or tour is required."),
    ({"item": "car:Not In The List"}, "Choose a car or tour package from the list."),
    ({"item": "plane:Boeing"}, "Choose a car or tour package from the list."),
])
def test_invalid_bookings_are_refused_with_a_message(fake_db, uploads, overrides, message):
    make_inventory(fake_db, uploads)
    response = _post_with_csrf("/admin/bookings/new", booking_form(**overrides))
    assert response.status_code == 422 and message in response.text
    assert fake_db.data.get("bookings", {}) == {}


def test_email_is_optional(fake_db, uploads):
    make_inventory(fake_db, uploads)
    _post_with_csrf("/admin/bookings/new", booking_form(customer_email=""))
    booking_id = only_id(fake_db, "bookings")
    assert "Not provided" in client.get(f"/admin/bookings/{booking_id}").text


def test_status_flow_is_enforced_and_recorded_in_history(fake_db, uploads):
    make_inventory(fake_db, uploads)
    _post_with_csrf("/admin/bookings/new", booking_form())
    booking_id = only_id(fake_db, "bookings")
    url = f"/admin/bookings/{booking_id}/status"

    skip = _post_with_csrf(url, {"status": "completed"})  # pending cannot jump to completed
    assert skip.status_code == 422 and "not allowed" in skip.text
    assert fake_db.data["bookings"][booking_id]["status"] == "pending"

    ok = _post_with_csrf(url, {"status": "approved"}, follow_redirects=False)
    assert ok.headers["location"].endswith("notice=status")
    _post_with_csrf(url, {"status": "ongoing"})
    _post_with_csrf(url, {"status": "completed"})
    doc = fake_db.data["bookings"][booking_id]
    assert [h["status"] for h in doc["history"]] == ["pending", "approved", "ongoing", "completed"]
    final = client.get(f"/admin/bookings/{booking_id}").text
    assert "can no longer be changed" in final and "Save status" not in final
    assert _post_with_csrf(url, {"status": "pending"}).status_code == 422  # final states are final


def test_reject_and_cancel_buttons_post_the_expected_status(fake_db, uploads):
    make_inventory(fake_db, uploads)
    _post_with_csrf("/admin/bookings/new", booking_form())
    booking_id = only_id(fake_db, "bookings")
    html = client.get(f"/admin/bookings/{booking_id}").text
    # The select has name="status", options have value="approved"/"rejected"/"cancelled"
    assert 'name="status"' in html
    assert 'value="approved"' in html and 'value="rejected"' in html
    assert 'value="cancelled"' in html
    # The status form button has data-busy-label; data-confirm is on the license delete button (not shown here)
    _post_with_csrf(f"/admin/bookings/{booking_id}/status", {"status": "rejected"})
    assert fake_db.data["bookings"][booking_id]["status"] == "rejected"


def test_payment_status_changes_and_rejects_unknown_values(fake_db, uploads):
    make_inventory(fake_db, uploads)
    _post_with_csrf("/admin/bookings/new", booking_form())
    booking_id = only_id(fake_db, "bookings")
    url = f"/admin/bookings/{booking_id}/payment"
    assert _post_with_csrf(url, {"payment_status": "paid"}, follow_redirects=False).headers["location"].endswith("notice=payment")
    assert fake_db.data["bookings"][booking_id]["payment_status"] == "paid"
    assert _post_with_csrf(url, {"payment_status": "free"}).status_code == 422
    assert fake_db.data["bookings"][booking_id]["payment_status"] == "paid"


def test_unknown_booking_is_404_when_connected(fake_db):
    assert client.get("/admin/bookings/nope").status_code == 404
    assert _post_with_csrf("/admin/bookings/nope/status", {"status": "approved"}).status_code == 404


def test_only_pending_and_approved_show_on_the_calendar_but_all_are_listed(fake_db, uploads):
    make_inventory(fake_db, uploads)
    _post_with_csrf("/admin/bookings/new", booking_form(customer_name="Ana Reyes"))
    _post_with_csrf("/admin/bookings/new", booking_form(customer_name="Ben Cruz"))
    ben = [i for i, d in fake_db.data["bookings"].items() if d["customer_name"] == "Ben Cruz"][0]
    _post_with_csrf(f"/admin/bookings/{ben}/status", {"status": "rejected"})
    assert "Ben Cruz" in client.get("/admin/bookings").text
    calendar = client.get("/admin/calendar").text
    assert "Ana Reyes" in calendar and "Ben Cruz" not in calendar


# ---- dashboard ----
def test_dashboard_shows_real_counts(fake_db, uploads):
    make_inventory(fake_db, uploads)
    _post_with_csrf("/admin/bookings/new", booking_form(customer_name="Ana Reyes"))
    _post_with_csrf("/admin/bookings/new", booking_form(customer_name="Ben Cruz"))
    ben = [i for i, d in fake_db.data["bookings"].items() if d["customer_name"] == "Ben Cruz"][0]
    _post_with_csrf(f"/admin/bookings/{ben}/status", {"status": "approved"})
    html = client.get("/admin/dashboard").text
    stats = dict(re.findall(r"<dt>([^<]+)</dt>\s*<dd>\s*(\d+)\s*</dd>", html))
    assert stats == {"Total Cars": "1", "Total Tour Packages": "1", "Total Bookings": "2",
                     "Pending": "1", "Approved": "1"}
    assert "sample data" not in html


def test_dashboard_with_an_empty_database_shows_zeros_and_no_requests(fake_db):
    html = client.get("/admin/dashboard").text
    assert "No booking requests yet" in html
    assert dict(re.findall(r"<dt>([^<]+)</dt>\s*<dd>\s*(\d+)\s*</dd>", html))["Total Bookings"] == "0"


# ---- remove image ----
def test_remove_image_on_a_car_deletes_it_and_falls_back_to_the_placeholder(fake_db, uploads):
    _post_with_csrf("/admin/services/cars/new", CAR, files={"image": ("a.jpg", b"x", "image/jpeg")})
    car_id = only_id(fake_db, "cars")
    _post_with_csrf(f"/admin/services/cars/{car_id}/edit", {**CAR, "remove_image": "1"})
    photo = fake_db.data["cars"][car_id]["photo"]
    assert photo["src"].endswith("service-car-rental-placeholder.svg") and photo["public_id"] is None
    assert uploads["deleted"] == ["bless/cars/1"]


def test_a_new_file_wins_over_remove_image(fake_db, uploads):
    _post_with_csrf("/admin/services/cars/new", CAR, files={"image": ("a.jpg", b"x", "image/jpeg")})
    car_id = only_id(fake_db, "cars")
    _post_with_csrf(f"/admin/services/cars/{car_id}/edit", {**CAR, "remove_image": "1"},
                files={"image": ("b.jpg", b"y", "image/jpeg")})
    assert fake_db.data["cars"][car_id]["photo"]["public_id"] == "bless/cars/2"
    assert uploads["deleted"] == ["bless/cars/1"]  # deleted once, not twice


def test_remove_image_without_an_uploaded_image_changes_nothing(fake_db, uploads):
    _post_with_csrf("/admin/services/cars/new", CAR)  # placeholder photo, nothing on Cloudinary
    car_id = only_id(fake_db, "cars")
    _post_with_csrf(f"/admin/services/cars/{car_id}/edit", {**CAR, "remove_image": "1"})
    assert uploads["deleted"] == []


def test_a_failed_save_keeps_the_image_when_remove_was_requested(fake_db, uploads):
    _post_with_csrf("/admin/services/cars/new", CAR, files={"image": ("a.jpg", b"x", "image/jpeg")})
    car_id = only_id(fake_db, "cars")
    response = _post_with_csrf(f"/admin/services/cars/{car_id}/edit", {**CAR, "name": "", "remove_image": "1"})
    assert response.status_code == 422
    assert fake_db.data["cars"][car_id]["photo"]["public_id"] == "bless/cars/1" and uploads["deleted"] == []


def test_remove_package_and_vehicle_images_independently(fake_db, uploads):
    data = TOUR | {"vehicle_name": "Hiace"}
    _post_with_csrf("/admin/services/tours/new", data,
                files={"image": ("a.jpg", b"x", "image/jpeg"), "vehicle_image": ("v.png", b"x", "image/png")})
    tour_id = only_id(fake_db, "tours")
    _post_with_csrf(f"/admin/services/tours/{tour_id}/edit", data | {"remove_vehicle_image": "1"})
    doc = fake_db.data["tours"][tour_id]
    assert doc["photo"]["public_id"] == "bless/tours/1"  # package image untouched
    assert doc["vehicle_photo"]["src"].endswith("vehicle-passenger-van-placeholder.svg")
    assert doc["vehicle_name"] == "Hiace" and uploads["deleted"] == ["bless/tour-vehicles/2"]
    _post_with_csrf(f"/admin/services/tours/{tour_id}/edit", data | {"remove_image": "1"})
    assert fake_db.data["tours"][tour_id]["photo"]["src"].endswith("service-tours-placeholder.svg")
    assert uploads["deleted"] == ["bless/tour-vehicles/2", "bless/tours/1"]


def test_the_remove_checkbox_only_appears_for_an_uploaded_image(fake_db, uploads):
    _post_with_csrf("/admin/services/cars/new", CAR)
    car_id = only_id(fake_db, "cars")
    assert "data-image-remove" not in client.get(f"/admin/services/cars/{car_id}/edit").text
    assert "data-image-remove" not in client.get("/admin/services/cars/new").text
    _post_with_csrf(f"/admin/services/cars/{car_id}/edit", CAR, files={"image": ("a.jpg", b"x", "image/jpeg")})
    html = client.get(f"/admin/services/cars/{car_id}/edit").text
    assert 'name="remove_image" type="checkbox"' in html and "data-image-preview" in html


# ---- car form dropdowns ----
def _options(html: str, field: str) -> list[tuple[str, bool]]:
    """(value, selected) for every option of one <select>."""
    block = re.search(rf'<select id="{field}".*?</select>', html, re.S).group(0)
    return [(m.group(1), "selected" in m.group(0)) for m in re.finditer(r'<option value="([^"]*)"[^>]*>', block)]


def test_the_car_form_offers_dropdowns_for_type_and_transmission():
    html = client.get("/admin/services/cars/new").text
    assert _options(html, "vehicle_type") == [
        ("", True), ("Sedan", False), ("MPV", False), ("SUV", False), ("Pick up", False), ("Van", False)
    ]
    assert _options(html, "transmission") == [("", True), ("A/T", False), ("M/T", False)]
    assert re.search(r'<select id="vehicle_type"[^>]* required', html)
    assert not re.search(r'<select id="transmission"[^>]* required', html)  # optional
    assert '<input id="vehicle_type"' not in html and '<input id="transmission"' not in html


def test_editing_an_older_record_preselects_its_choices(fake_db):
    # Saved before the dropdowns existed: "Suv" and "A/T" as typed, and "Automatic" spelled out.
    fake_db.data["cars"] = {"old-1": {**CAR, "vehicle_type": "Suv", "transmission": "A/T", "seats": 5, "daily_rate_php": 1, "is_sample": False,
                                      "photo": {"src": "customer/img/vehicles/vehicle-compact-sedan-placeholder.svg", "alt": "Car"}},
                            "old-2": {**CAR, "vehicle_type": "Pickup", "transmission": "Automatic", "seats": 5, "daily_rate_php": 1, "is_sample": False,
                                      "photo": {"src": "customer/img/vehicles/vehicle-compact-sedan-placeholder.svg", "alt": "Car"}}}
    one = client.get("/admin/services/cars/old-1/edit").text
    assert ("SUV", True) in _options(one, "vehicle_type") and ("A/T", True) in _options(one, "transmission")
    two = client.get("/admin/services/cars/old-2/edit").text
    # "Pickup" (no space) canonicalizes to "Pick up" (with space), so it matches and is preselected
    assert ("Pick up", True) in _options(two, "vehicle_type")
    assert ("A/T", True) in _options(two, "transmission")


def test_only_listed_values_are_saved_and_spelling_is_normalised(fake_db, uploads):
    _post_with_csrf("/admin/services/cars/new", CAR | {"vehicle_type": "suv", "transmission": "m/t"})
    doc = fake_db.data["cars"][only_id(fake_db, "cars")]
    assert doc["vehicle_type"] == "SUV" and doc["transmission"] == "M/T"

    bad = _post_with_csrf("/admin/services/cars/new", CAR | {"vehicle_type": "Spaceship"})
    assert bad.status_code == 422 and "Vehicle type must be one of: Sedan, MPV, SUV, Pick up, Van." in bad.text
    bad = _post_with_csrf("/admin/services/cars/new", CAR | {"transmission": "CVT"})
    assert bad.status_code == 422 and "Transmission must be one of: A/T, M/T." in bad.text
    assert _post_with_csrf("/admin/services/cars/new", CAR | {"vehicle_type": ""}).status_code == 422
    assert len(fake_db.data["cars"]) == 1  # nothing else was saved

    _post_with_csrf("/admin/services/cars/new", CAR | {"name": "No gearbox", "transmission": ""})
    assert any(d["name"] == "No gearbox" and d["transmission"] is None for d in fake_db.data["cars"].values())
