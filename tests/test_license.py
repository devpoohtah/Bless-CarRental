"""Driver's license photos for self-drive rentals: checked and shrunk on upload, kept private, shown only to
admins, and deleted when the booking ends. Nothing is stored before the customer confirms their email."""

import io
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.core.clock import today_ph
from app.db import repositories as repo
from app.main import app
from app.schemas.booking import Booking, StatusChange
from app.services import bookings as service
from app.services import licenses
from tests.test_public_booking import book, car_request, catalog, client, fresh_limiter, saved_bookings  # noqa: F401

pytestmark = pytest.mark.usefixtures("simulated_otp")


def photo(fmt="PNG", size=(3000, 2000), color=(90, 30, 60)) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", size, color).save(out, fmt)
    return out.getvalue()


def with_license(content=None, name="license.png", mime="image/png") -> dict:
    return {"license_file": (name, content if content is not None else photo(), mime)}


def post_car(files=None, **changes):
    csrf = client.get("/") and client.cookies.get("csrf_token", "")
    headers = {"X-CSRF-Token": csrf}
    response = client.post("/book/car", data=car_request(**changes), files=files, headers=headers)
    if response.status_code != 202:
        return response
    return client.post("/book/verify", data={"challenge": response.json()["challenge"], "code": "123456"},
                       headers=headers)


def stored_licenses(db) -> dict:
    return db.data.get("booking_licenses", {})


# ---- preparing the photo ----
class FakeUpload:
    def __init__(self, content: bytes, filename="x.jpg"):
        self.file = io.BytesIO(content)
        self.filename = filename


def test_a_photo_becomes_a_small_webp():
    out = licenses.prepare(FakeUpload(photo("JPEG", (4000, 3000))))
    image = Image.open(io.BytesIO(out))
    assert image.format == "WEBP" and max(image.size) <= 1600 and len(out) <= licenses.MAX_STORED_BYTES


def test_exif_data_is_dropped():
    source = Image.new("RGB", (800, 600), (10, 20, 30))
    exif = Image.Exif()
    exif[0x010F] = "SecretCameraMaker"
    buf = io.BytesIO()
    source.save(buf, "JPEG", exif=exif)
    assert b"SecretCameraMaker" in buf.getvalue()  # the test photo really carries it
    out = licenses.prepare(FakeUpload(buf.getvalue()))
    assert b"SecretCameraMaker" not in out and not Image.open(io.BytesIO(out)).getexif()


@pytest.mark.parametrize("content, message", [
    (b"just some text pretending to be a photo", "JPEG, PNG or WebP"),
    (b"%PDF-1.7 not an image", "JPEG, PNG or WebP"),
    (b"\xff\xd8\xff" + b"garbage" * 50, "could not be read"),  # right first bytes, not a real image
    (b"\x89PNG\r\n\x1a\n" + b"junk" * 50, "could not be read"),
])
def test_files_that_are_not_photos_are_refused(content, message):
    with pytest.raises(licenses.LicenseError, match=message):
        licenses.prepare(FakeUpload(content))


def test_a_photo_over_5_mb_is_refused():
    with pytest.raises(licenses.LicenseError, match="5 MB"):
        licenses.prepare(FakeUpload(b"\xff\xd8\xff" + b"0" * (5 * 1024 * 1024)))


def test_a_huge_picture_is_refused_before_it_is_decoded(monkeypatch):
    monkeypatch.setattr(licenses, "MAX_PIXELS", 1_000)
    with pytest.raises(licenses.LicenseError, match="too large"):
        licenses.prepare(FakeUpload(photo("PNG", (100, 100))))


# ---- the booking flow ----
def test_a_self_drive_request_keeps_the_license_privately(catalog):
    response = post_car(files=with_license(), driver_option="self_drive")
    assert response.status_code == 201
    [booking] = saved_bookings(catalog)
    assert booking["license_on_file"] is True
    assert booking["license_delete_on"] == (date.fromisoformat(booking["end_date"]) + timedelta(days=30)).isoformat()
    [(booking_id, stored)] = stored_licenses(catalog).items()
    assert booking_id in catalog.data["bookings"]  # keyed by the booking id
    assert Image.open(io.BytesIO(stored["data"])).format == "WEBP"
    # The photo is not in the bookings document, which the admin browser reads live.
    assert not any(isinstance(v, (bytes, bytearray)) for v in booking.values())
    assert "license_file" not in str(booking)


def test_a_self_drive_request_without_a_photo_is_refused(catalog):
    response = post_car(driver_option="self_drive")
    assert response.status_code == 422 and "driver's license" in response.json()["errors"][0]
    assert saved_bookings(catalog) == [] and stored_licenses(catalog) == {}


def test_a_bad_photo_is_refused_before_any_code_is_sent(catalog):
    response = post_car(files=with_license(b"not a photo", "a.png"), driver_option="self_drive")
    assert response.status_code == 422 and "JPEG, PNG or WebP" in response.json()["errors"][0]
    assert saved_bookings(catalog) == [] and stored_licenses(catalog) == {}


@pytest.mark.parametrize("option", ["with_driver", ""])
def test_no_photo_is_needed_or_kept_without_self_drive(catalog, option):
    response = post_car(files=with_license(), driver_option=option)  # a file sent anyway is dropped unread
    assert response.status_code == 201
    [booking] = saved_bookings(catalog)
    assert booking["license_on_file"] is False and stored_licenses(catalog) == {}


def test_nothing_is_stored_until_the_email_code_is_right(catalog):
    csrf = client.get("/") and client.cookies.get("csrf_token", "")
    response = client.post("/book/car", data=car_request(driver_option="self_drive"), files=with_license(),
                           headers={"X-CSRF-Token": csrf})
    assert response.status_code == 202  # the code step: the photo waits in memory only
    assert saved_bookings(catalog) == [] and stored_licenses(catalog) == {}


def test_a_failed_booking_save_leaves_no_photo_behind(catalog, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("database down")
    monkeypatch.setattr(repo, "save", boom)
    response = post_car(files=with_license(), driver_option="self_drive")
    assert response.status_code == 503
    assert stored_licenses(catalog) == {}


def test_tour_bookings_never_take_a_license(catalog):
    page = client.get("/book/tour").text
    assert "license_file" not in page
    assert 'name="license_file"' in client.get("/book/car").text


# ---- the admin ----
def add_car_booking(db, status="pending", with_photo=True) -> str:
    today = today_ph()
    booking = Booking(id="", booking_type="car", customer_name="Ana Reyes", customer_phone="09171234567",
                      item_name="Family SUV", start_date=today, end_date=today, requested_on=today, status=status,
                      payment_status="unpaid", history=[StatusChange(status=status, changed_on=today)],
                      driver_option="self_drive", license_on_file=with_photo, is_sample=False)
    booking_id = repo.save(repo.BOOKINGS, booking)
    if with_photo:
        licenses.save(booking_id, licenses.prepare(FakeUpload(photo())))
    return booking_id


def test_an_admin_sees_the_photo_and_it_is_never_cached(fake_db):
    booking_id = add_car_booking(fake_db)
    response = client.get(f"/admin/bookings/{booking_id}/license")
    assert response.status_code == 200 and response.headers["content-type"] == "image/webp"
    assert "no-store" in response.headers["cache-control"]
    assert response.headers["x-content-type-options"] == "nosniff"
    assert Image.open(io.BytesIO(response.content)).format == "WEBP"
    page = client.get(f"/admin/bookings/{booking_id}").text
    assert f"/admin/bookings/{booking_id}/license" in page


def test_the_photo_needs_an_admin_sign_in(fake_db, real_auth):
    booking_id = add_car_booking(fake_db)
    response = TestClient(app).get(f"/admin/bookings/{booking_id}/license", follow_redirects=False)
    assert response.status_code in (303, 401) and response.headers.get("content-type") != "image/webp"


def test_there_is_no_photo_for_a_booking_without_one(fake_db):
    booking_id = add_car_booking(fake_db, with_photo=False)
    assert client.get(f"/admin/bookings/{booking_id}/license").status_code == 404
    assert client.get("/admin/bookings/missing/license").status_code == 404
    assert "No license photo is on file" in client.get(f"/admin/bookings/{booking_id}").text


@pytest.mark.parametrize("final", ["rejected", "cancelled"])
def test_the_photo_is_deleted_when_a_pending_booking_ends(fake_db, final):
    booking_id = add_car_booking(fake_db)
    service.change_status(service.get_booking(booking_id), final)
    assert stored_licenses(fake_db) == {}
    assert service.get_booking(booking_id).license_on_file is False
    assert client.get(f"/admin/bookings/{booking_id}/license").status_code == 404


def test_a_completed_booking_keeps_the_photo_for_15_more_days(fake_db):
    booking_id = add_car_booking(fake_db, status="ongoing")
    service.change_status(service.get_booking(booking_id), "completed")
    booking = service.get_booking(booking_id)
    assert booking_id in stored_licenses(fake_db) and booking.license_on_file is True
    assert booking.license_delete_on == today_ph() + timedelta(days=15)


def test_completing_never_extends_a_day_that_is_already_sooner(fake_db):
    booking_id = add_car_booking(fake_db, status="ongoing")
    sooner = today_ph() + timedelta(days=3)
    repo.save(repo.BOOKINGS, service.get_booking(booking_id).model_copy(update={"license_delete_on": sooner}), booking_id)
    service.change_status(service.get_booking(booking_id), "completed")
    assert service.get_booking(booking_id).license_delete_on == sooner


def test_the_photo_stays_while_the_booking_is_live(fake_db):
    booking_id = add_car_booking(fake_db, status="approved")
    service.change_status(service.get_booking(booking_id), "ongoing")
    assert booking_id in stored_licenses(fake_db) and service.get_booking(booking_id).license_on_file is True


def test_a_status_does_not_change_if_the_photo_cannot_be_deleted(fake_db, monkeypatch):
    booking_id = add_car_booking(fake_db)
    monkeypatch.setattr(licenses, "delete", lambda _id: (_ for _ in ()).throw(RuntimeError("down")))
    with pytest.raises(service.FormError, match="could not be deleted"):
        service.change_status(service.get_booking(booking_id), "rejected")
    booking = service.get_booking(booking_id)
    assert booking.status == "pending" and booking.license_on_file is True


# ---- request size ----
def test_an_oversized_booking_body_is_refused():
    response = client.post("/book/car", content=b"x" * (7 * 1024 * 1024),
                           headers={"content-type": "application/octet-stream"})
    assert response.status_code == 413


def test_an_oversized_body_without_a_declared_length_is_refused_too():
    def chunks():
        for _ in range(8):
            yield b"x" * (1024 * 1024)
    response = client.post("/book/car", content=chunks(), headers={"content-type": "application/octet-stream"})
    assert response.status_code == 413


def test_a_browser_style_post_works(catalog):
    """The page sends the CSRF token as a form field, not a header, so the middleware reads the multipart body
    (photo included) before the route does. The route must still receive the photo."""
    client.get("/")
    data = car_request(driver_option="self_drive") | {"csrf_token": client.cookies.get("csrf_token", "")}
    response = client.post("/book/car", data=data, files=with_license())
    assert response.status_code == 202
    done = client.post("/book/verify", data={"challenge": response.json()["challenge"], "code": "123456",
                                             "csrf_token": client.cookies.get("csrf_token", "")})
    assert done.status_code == 201 and len(stored_licenses(catalog)) == 1


# ---- retention: deleting on request and the daily sweep ----
def post_admin(url):
    client.get("/")
    return client.post(url, headers={"X-CSRF-Token": client.cookies.get("csrf_token", "")}, follow_redirects=False)


def test_an_admin_can_delete_the_photo_on_request(fake_db):
    booking_id = add_car_booking(fake_db, status="completed")
    response = post_admin(f"/admin/bookings/{booking_id}/license/delete")
    assert response.status_code == 303 and "notice=license" in response.headers["location"]
    assert stored_licenses(fake_db) == {}
    booking = service.get_booking(booking_id)
    assert booking.license_on_file is False and booking.license_delete_on is None
    assert client.get(f"/admin/bookings/{booking_id}/license").status_code == 404


def test_deleting_a_photo_that_is_not_there_is_refused(fake_db):
    booking_id = add_car_booking(fake_db, with_photo=False)
    response = post_admin(f"/admin/bookings/{booking_id}/license/delete")
    assert response.status_code == 422 and "no license photo" in response.text.lower()


def test_the_delete_button_and_the_planned_day_show_on_the_booking(fake_db):
    booking_id = add_car_booking(fake_db, status="completed")
    page = client.get(f"/admin/bookings/{booking_id}").text
    assert f"/admin/bookings/{booking_id}/license/delete" in page and "Delete photo now" in page


def set_delete_day(booking_id, day):
    repo.save(repo.BOOKINGS, service.get_booking(booking_id).model_copy(update={"license_delete_on": day}), booking_id)


def test_the_sweep_deletes_only_photos_whose_day_has_come(fake_db):
    today = today_ph()
    due, today_due, later = add_car_booking(fake_db), add_car_booking(fake_db), add_car_booking(fake_db)
    set_delete_day(due, today - timedelta(days=1))
    set_delete_day(today_due, today)
    set_delete_day(later, today + timedelta(days=1))
    no_photo = add_car_booking(fake_db, with_photo=False)
    assert service.purge_expired_licenses() == 2
    assert set(stored_licenses(fake_db)) == {later}
    assert service.get_booking(due).license_on_file is False and service.get_booking(later).license_on_file is True
    assert service.get_booking(no_photo).license_on_file is False


def test_a_booking_without_a_planned_day_falls_back_to_30_days_after_its_end(fake_db):
    old, recent = add_car_booking(fake_db), add_car_booking(fake_db)
    for booking_id, ended in ((old, today_ph() - timedelta(days=31)), (recent, today_ph() - timedelta(days=5))):
        booking = service.get_booking(booking_id)
        repo.save(repo.BOOKINGS, booking.model_copy(update={"start_date": ended, "end_date": ended}), booking_id)
    assert service.purge_expired_licenses() == 1
    assert set(stored_licenses(fake_db)) == {recent}


def test_one_failing_photo_does_not_stop_the_sweep(fake_db, monkeypatch):
    first, second = add_car_booking(fake_db), add_car_booking(fake_db)
    for booking_id in (first, second):
        set_delete_day(booking_id, today_ph() - timedelta(days=1))
    real_delete = licenses.delete

    def flaky(booking_id):
        if booking_id == first:
            raise RuntimeError("down")
        real_delete(booking_id)
    monkeypatch.setattr(licenses, "delete", flaky)
    assert service.purge_expired_licenses() == 1
    assert set(stored_licenses(fake_db)) == {first}
    assert service.get_booking(first).license_on_file is True  # still flagged, so the next sweep tries again


def test_the_sweep_runs_at_most_once_an_hour_and_never_raises(fake_db, monkeypatch):
    calls = []
    monkeypatch.setattr(service, "_last_purge", None)
    monkeypatch.setattr(service, "purge_expired_licenses", lambda: calls.append(1) or 0)
    service.purge_expired_licenses_if_due()
    service.purge_expired_licenses_if_due()
    assert calls == [1]
    monkeypatch.setattr(service, "_last_purge", None)
    monkeypatch.setattr(service, "purge_expired_licenses", lambda: (_ for _ in ()).throw(RuntimeError("down")))
    service.purge_expired_licenses_if_due()  # swallowed and logged


def test_opening_the_bookings_and_starting_the_app_both_run_the_sweep(fake_db, monkeypatch):
    calls = []
    monkeypatch.setattr(service, "purge_expired_licenses_if_due", lambda: calls.append("run"))
    client.get("/admin/bookings")
    with TestClient(app):
        pass
    assert calls == ["run", "run"]


# ---- what the customer is told ----
def test_the_car_form_states_the_retention_and_the_consent(catalog):
    car, tour = client.get("/book/car").text, client.get("/book/tour").text
    assert "15 days after your booking is completed" in car
    assert "including the use of my driver" in car and "including the use of my driver" not in tour


def test_the_privacy_page_states_the_retention():
    page = client.get("/privacy").text
    assert "15 days after your booking is completed" in page and "30 days after its end date" in page
