"""Email verification of website bookings: the code rules, the three delivery modes, Turnstile, and the approval email."""

import io
import json
import logging
import urllib.error
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from app.api.routes import bookings as bookings_route
from app.core import config
from app.core.ratelimit import RateLimiter
from app.main import app
from app.services import mailer, otp, turnstile
from tests.test_public_booking import add_booking, car_request, catalog, saved_bookings, tour_request, when  # noqa: F401

client = TestClient(app)
pytestmark = pytest.mark.usefixtures("simulated_otp")  # tests below switch the mode themselves where they need to


def _get_csrf_token():
    """Get a fresh CSRF token from the cookie."""
    client.get("/")  # sets the cookie
    return client.cookies.get("csrf_token", "")


def _headers():
    return {"X-CSRF-Token": _get_csrf_token()}


def _admin_post(url: str, data: dict, **kwargs):
    """POST to an admin endpoint with CSRF token."""
    client.get("/admin/dashboard")  # sets the cookie
    csrf_token = client.cookies.get("csrf_token", "")
    headers = {"X-CSRF-Token": csrf_token, **kwargs.get("headers", {})}
    return client.post(url, data=data, headers=headers, **{k: v for k, v in kwargs.items() if k != "headers"})


def set_integrations(monkeypatch, **changes):
    monkeypatch.setattr(config, "integrations", replace(config.integrations, **changes))


def start(data=None, url="/book/car"):
    return client.post(url, data=data or car_request(), headers=_headers())


def verify(challenge, code="123456"):
    return client.post("/book/verify", data={"challenge": challenge, "code": code}, headers=_headers())


# ---- the store, on its own ----
class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


@pytest.fixture
def store(simulated_otp):
    clock = Clock()
    return otp.OtpStore(clock=clock), clock


def test_the_right_code_returns_the_request_once(store):
    s, _ = store
    challenge, _code = s.start("car", {"a": 1}, "ana@example.com")
    assert s.verify(challenge, "123456") == ("car", {"a": 1})
    with pytest.raises(otp.OtpError) as exc:  # single use
        s.verify(challenge, "123456")
    assert exc.value.code == "expired"


def test_the_code_is_never_kept_in_the_clear(store):
    s, _ = store
    challenge, _ = s.start("car", {}, "ana@example.com")
    item = s._items[challenge]
    assert "123456" not in repr(item) and item.code_hash != b"123456" and len(item.code_hash) == 32


def test_wrong_codes_count_down_then_lock_even_for_the_right_code(store):
    s, _ = store
    challenge, _ = s.start("car", {}, "ana@example.com")
    lefts = []
    for _ in range(otp.MAX_ATTEMPTS - 1):
        with pytest.raises(otp.OtpError) as exc:
            s.verify(challenge, "000000")
        assert exc.value.code == "wrong_code"
        lefts.append(exc.value.attempts_left)
    assert lefts == [4, 3, 2, 1]
    with pytest.raises(otp.OtpError) as exc:
        s.verify(challenge, "000000")
    assert exc.value.code == "locked"
    with pytest.raises(otp.OtpError):  # the right code no longer works
        s.verify(challenge, "123456")


def test_a_code_expires_after_ten_minutes(store):
    s, clock = store
    challenge, _ = s.start("car", {}, "ana@example.com")
    clock.now += otp.TTL_SECONDS - 1
    assert s.verify(challenge, "123456")[0] == "car"
    challenge, _ = s.start("car", {}, "ana@example.com")
    clock.now += otp.TTL_SECONDS + 1
    with pytest.raises(otp.OtpError) as exc:
        s.verify(challenge, "123456")
    assert exc.value.code == "expired"


def test_resend_has_a_cooldown_and_resets_the_attempts(store):
    s, clock = store
    challenge, _ = s.start("car", {}, "ana@example.com")
    with pytest.raises(otp.OtpError) as exc:
        s.resend(challenge)
    assert exc.value.code == "cooldown" and 0 < exc.value.retry_after <= otp.RESEND_COOLDOWN_SECONDS
    with pytest.raises(otp.OtpError):
        s.verify(challenge, "111111")
    clock.now += otp.RESEND_COOLDOWN_SECONDS + 1
    assert s.resend(challenge) == "123456"
    assert s._items[challenge].attempts_left == otp.MAX_ATTEMPTS


def test_unknown_and_empty_challenges_are_just_expired(store):
    s, _ = store
    for challenge in ("", "nope"):
        with pytest.raises(otp.OtpError) as exc:
            s.verify(challenge, "123456")
        assert exc.value.code == "expired"


def test_expired_challenges_are_forgotten_when_a_new_one_starts(store):
    s, clock = store
    s.start("car", {}, "a@example.com")
    clock.now += otp.TTL_SECONDS + 1
    s.start("car", {}, "b@example.com")
    assert len(s._items) == 1


def test_a_failed_resend_send_frees_the_button_and_keeps_the_old_code(store, monkeypatch):
    s, clock = store
    set_integrations(monkeypatch, otp_delivery="gmail", gmail_user="x@gmail.com", gmail_app_password="p")
    monkeypatch.setattr(mailer, "send_gmail", lambda *a: True)
    challenge, _ = s.start("car", {}, "ana@example.com")
    monkeypatch.setattr(mailer, "send_gmail", lambda *a: False)
    clock.now += otp.RESEND_COOLDOWN_SECONDS + 1
    with pytest.raises(otp.OtpError) as exc:
        s.resend(challenge)
    assert exc.value.code == "send_failed"
    assert s._items[challenge].resend_at == 0.0  # can try again at once


def test_mask_email():
    assert otp.mask_email("ana@example.com") == "a***@example.com"


# ---- delivery modes ----
@pytest.mark.parametrize("value", ["", "console", "brevo", "123456"])
def test_nothing_is_delivered_when_otp_delivery_is_unset_or_unknown(catalog, monkeypatch, value):
    # Not even the fixed code: production must never fall back to it by accident.
    set_integrations(monkeypatch, otp_delivery=value)
    response = start()
    assert response.status_code == 503 and "Messenger" in response.json()["errors"][0]
    assert saved_bookings(catalog) == [] and otp.store._items == {}


def test_gmail_and_resend_modes_need_their_credentials(monkeypatch):
    set_integrations(monkeypatch, otp_delivery="gmail")
    assert config.integrations.otp_mode == ""
    set_integrations(monkeypatch, otp_delivery="resend")
    assert config.integrations.otp_mode == ""
    set_integrations(monkeypatch, otp_delivery="", gmail_user="x@gmail.com", gmail_app_password="abcd")
    assert config.integrations.otp_mode == "gmail"  # unset picks Gmail when it is set up


def test_the_app_password_may_be_pasted_with_its_spaces(monkeypatch):
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "abcd efgh ijkl mnop")
    assert config.Integrations().gmail_app_password == "abcdefghijklmnop"


def test_simulated_mode_shows_the_test_code_and_sends_no_email(catalog, monkeypatch):
    sent = []
    monkeypatch.setattr(mailer, "send_gmail", lambda *a: sent.append(a) or True)
    monkeypatch.setattr(mailer, "send_resend", lambda *a: sent.append(a) or True)
    response = start()
    assert response.status_code == 202
    body = response.json()
    assert body["test_code"] == "123456" and body["email"] == "a***@example.com" and body["resend_in"] == 60
    assert sent == []


def test_gmail_mode_sends_a_random_code_by_email_and_never_returns_it(catalog, monkeypatch):
    set_integrations(monkeypatch, otp_delivery="gmail", gmail_user="x@gmail.com", gmail_app_password="p")
    sent = []
    monkeypatch.setattr(mailer, "send_gmail", lambda to, subject, body: sent.append((to, subject, body)) or True)
    response = start()
    assert response.status_code == 202 and "test_code" not in response.json()
    ((to, subject, body),) = sent
    code = subject.rsplit(" ", 1)[1]
    assert to == "ana@example.com" and code.isdigit() and len(code) == 6 and code in body
    assert verify(response.json()["challenge"], code).status_code == 201
    assert saved_bookings(catalog)[0]["email_verified"] is True


def test_resend_mode_uses_the_resend_sender(catalog, monkeypatch):
    set_integrations(monkeypatch, otp_delivery="resend", resend_api_key="re_key")
    sent = []
    monkeypatch.setattr(mailer, "send_resend", lambda to, subject, body: sent.append(to) or True)
    assert start().status_code == 202 and sent == ["ana@example.com"]


def test_if_the_email_cannot_be_sent_nothing_is_stored_and_the_customer_is_told(catalog, monkeypatch):
    set_integrations(monkeypatch, otp_delivery="gmail", gmail_user="x@gmail.com", gmail_app_password="p")
    monkeypatch.setattr(mailer, "send_gmail", lambda *a: False)
    response = start()
    assert response.status_code == 503 and response.json()["code"] == "send_failed"
    assert otp.store._items == {} and saved_bookings(catalog) == []


# ---- the customer's journey ----
def test_nothing_is_saved_until_the_right_code_is_entered(catalog):
    challenge = start().json()["challenge"]
    assert saved_bookings(catalog) == []
    assert verify(challenge, "000000").status_code == 400
    assert saved_bookings(catalog) == []
    response = verify(challenge)
    assert response.status_code == 201 and response.json()["reference"].startswith("BLESS-")
    (saved,) = saved_bookings(catalog)
    assert saved["email_verified"] is True and saved["status"] == "pending"


def test_a_wrong_code_says_how_many_tries_are_left(catalog):
    challenge = start().json()["challenge"]
    body = verify(challenge, "111111").json()
    assert body["code"] == "wrong_code" and body["attempts_left"] == 4 and "4 tries left" in body["errors"][0]


def test_five_wrong_codes_lock_the_request(catalog):
    challenge = start().json()["challenge"]
    responses = [verify(challenge, "000000") for _ in range(5)]
    assert [r.status_code for r in responses] == [400, 400, 400, 400, 429]
    assert responses[-1].json()["code"] == "locked"
    assert verify(challenge).status_code == 410 and saved_bookings(catalog) == []


def test_a_code_is_single_use_even_with_a_double_click(catalog):
    challenge = start().json()["challenge"]
    assert verify(challenge).status_code == 201
    assert verify(challenge).status_code == 410
    assert len(saved_bookings(catalog)) == 1


def test_resend_gives_a_new_challenge_state_after_the_cooldown(catalog, monkeypatch):
    clock = Clock()
    monkeypatch.setattr(otp, "store", otp.OtpStore(clock=clock))
    challenge = start().json()["challenge"]
    early = client.post("/book/resend", data={"challenge": challenge}, headers=_headers())
    assert early.status_code == 429 and early.json()["code"] == "cooldown" and early.json()["retry_after"] > 0
    clock.now += 61
    late = client.post("/book/resend", data={"challenge": challenge}, headers=_headers())
    assert late.status_code == 200 and late.json()["resend_in"] == 60 and late.json()["test_code"] == "123456"


def test_resend_for_an_unknown_challenge_is_expired(catalog):
    response = client.post("/book/resend", data={"challenge": "nope"}, headers=_headers())
    assert response.status_code == 410 and response.json()["code"] == "expired"


def test_the_dates_are_checked_again_when_the_code_is_entered(catalog):
    challenge = start().json()["challenge"]
    add_booking("approved", 5, 7)  # BLESS approves someone else in the meantime
    response = verify(challenge)
    assert response.status_code == 422 and "already booked" in response.json()["errors"][0] and response.json()["code"] == "rejected"
    assert len(saved_bookings(catalog)) == 1  # only the one added directly


def test_dates_that_are_already_taken_are_refused_before_any_code_is_sent(catalog):
    add_booking("approved", 5, 7)
    assert start().status_code == 422
    assert otp.store._items == {}


def test_invalid_details_never_send_a_code(catalog, monkeypatch):
    sent = []
    monkeypatch.setattr(otp.mailer, "send_otp_email", lambda *a: sent.append(a) or True)
    assert start(car_request(customer_phone="123")).status_code == 422
    assert start(car_request(customer_email="nope")).status_code == 422
    assert sent == [] and otp.store._items == {}


def test_phone_numbers_are_saved_in_one_format(catalog):
    for number in ("0917 123 4567", "+63 917 123 4567", "917-123-4567", "639171234567", "(0917) 123.4567"):
        data = car_request(customer_phone=number, start_date=when(30), end_date=when(31))
        assert verify(start(data).json()["challenge"]).status_code == 201, number
    assert {b["customer_phone"] for b in saved_bookings(catalog)} == {"+639171234567"}


def test_one_email_address_cannot_be_flooded_with_codes(catalog, monkeypatch):
    monkeypatch.setattr(bookings_route, "email_limiter", RateLimiter(max_hits=2, window_seconds=3600))
    codes = [start().status_code for _ in range(3)]
    assert codes == [202, 202, 429]
    assert start(car_request(customer_email="other@example.com")).status_code == 202


def test_the_ip_limit_also_covers_resend(catalog, monkeypatch):
    challenge = start().json()["challenge"]
    monkeypatch.setattr(bookings_route, "limiter", RateLimiter(max_hits=1, window_seconds=600))
    assert client.post("/book/resend", data={"challenge": challenge}, headers=_headers()).status_code == 429


def test_the_fixed_code_never_appears_outside_simulated_mode(catalog, monkeypatch):
    set_integrations(monkeypatch, otp_delivery="gmail", gmail_user="x@gmail.com", gmail_app_password="p")
    monkeypatch.setattr(mailer, "send_gmail", lambda *a: True)
    pages = [client.get("/book/car").text, client.get("/book/tour").text,
             start().text, start(tour_request(), "/book/tour").text]
    assert all("123456" not in page for page in pages)


# ---- Turnstile ----
class FakeResponse:
    def __init__(self, body: bytes, status=200):
        self._body, self.status = body, status

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@pytest.fixture
def turnstile_on(monkeypatch):
    set_integrations(monkeypatch, turnstile_site_key="site", turnstile_secret_key="SECRET-KEY")


def test_without_turnstile_keys_the_check_is_skipped(catalog):
    assert turnstile.passed("") is True
    assert start().status_code == 202


def test_a_missing_token_is_refused_once_turnstile_is_on(catalog, turnstile_on):
    response = start()
    assert response.status_code == 422 and response.json()["code"] == "turnstile" and saved_bookings(catalog) == []


def test_cloudflare_decides(catalog, turnstile_on, monkeypatch):
    seen = []

    def fake(request, timeout):
        seen.append(request.data.decode())
        return FakeResponse(json.dumps({"success": "response=good-token" in seen[-1]}).encode())
    monkeypatch.setattr(turnstile.urllib.request, "urlopen", fake)
    assert start(car_request() | {"cf-turnstile-response": "rejected-token"}).status_code == 422
    assert start(car_request() | {"cf-turnstile-response": "good-token"}).status_code == 202
    assert "secret=SECRET-KEY" in seen[0] and "response=rejected-token" in seen[0]


def test_an_unreachable_cloudflare_fails_closed(catalog, turnstile_on, monkeypatch):
    def down(request, timeout):
        raise urllib.error.URLError("offline")
    monkeypatch.setattr(turnstile.urllib.request, "urlopen", down)
    assert start(car_request() | {"cf-turnstile-response": "t"}).status_code == 422


def test_the_widget_is_on_the_page_only_when_configured(turnstile_on, monkeypatch):
    html = client.get("/book/car").text
    assert 'class="cf-turnstile" data-sitekey="site"' in html and "challenges.cloudflare.com/turnstile/v0/api.js" in html
    assert "SECRET-KEY" not in html
    set_integrations(monkeypatch, turnstile_site_key="", turnstile_secret_key="")
    assert "cf-turnstile" not in client.get("/book/car").text


# ---- senders ----
def test_resend_request_is_one_json_post_with_the_key_in_a_header(monkeypatch):
    set_integrations(monkeypatch, resend_api_key="re_SECRET", resend_from_email="hello@example.com")
    seen = {}

    def fake(request, timeout):
        seen.update(url=request.full_url, headers=dict(request.header_items()), body=json.loads(request.data))
        return FakeResponse(b"{}")
    monkeypatch.setattr(mailer.urllib.request, "urlopen", fake)
    assert mailer.send_resend("ana@example.com", "Subject", "Body") is True
    assert seen["url"] == "https://api.resend.com/emails" and seen["headers"]["Authorization"] == "Bearer re_SECRET"
    assert seen["body"] == {"from": "BLESS <hello@example.com>", "to": ["ana@example.com"], "subject": "Subject", "text": "Body"}


def test_resend_errors_are_logged_without_the_key(monkeypatch, caplog):
    set_integrations(monkeypatch, resend_api_key="re_SECRET")

    def refuse(request, timeout):
        raise urllib.error.HTTPError(request.full_url, 403, "Forbidden", {}, io.BytesIO(b'{"message": "domain is not verified"}'))
    monkeypatch.setattr(mailer.urllib.request, "urlopen", refuse)
    with caplog.at_level(logging.WARNING):
        assert mailer.send_resend("ana@example.com", "s", "b") is False
    assert "domain is not verified" in caplog.text and "re_SECRET" not in caplog.text


def test_gmail_logs_in_over_ssl_with_the_app_password(monkeypatch):
    set_integrations(monkeypatch, gmail_user="bless@gmail.com", gmail_app_password="apppassword")
    calls = {}

    class FakeSmtp:
        def __init__(self, host, port, timeout):
            calls["server"] = (host, port)

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def login(self, user, password):
            calls["login"] = (user, password)

        def send_message(self, message):
            calls["message"] = message
    monkeypatch.setattr(mailer.smtplib, "SMTP_SSL", FakeSmtp)
    assert mailer.send_gmail("ana@example.com", "Hi", "Body") is True
    assert calls["server"] == ("smtp.gmail.com", 465) and calls["login"] == ("bless@gmail.com", "apppassword")
    assert calls["message"]["To"] == "ana@example.com" and calls["message"]["Subject"] == "Hi"


def test_a_gmail_failure_is_logged_without_the_password(monkeypatch, caplog):
    set_integrations(monkeypatch, gmail_user="bless@gmail.com", gmail_app_password="apppassword")

    def fail(*a, **k):
        raise OSError("auth failed for apppassword")
    monkeypatch.setattr(mailer.smtplib, "SMTP_SSL", fail)
    with caplog.at_level(logging.WARNING):
        assert mailer.send_gmail("ana@example.com", "s", "b") is False
    assert "apppassword" not in caplog.text


# ---- the approval email ----
@pytest.fixture
def approvals(monkeypatch):
    sent = []
    monkeypatch.setattr(mailer, "send_resend", lambda to, subject, body: sent.append((to, subject, body)) or True)
    return sent


def pending_booking(catalog) -> str:
    verify(start().json()["challenge"])
    return next(iter(catalog.data["bookings"]))


def test_approving_a_booking_emails_the_customer(catalog, approvals):
    booking_id = pending_booking(catalog)
    assert _admin_post(f"/admin/bookings/{booking_id}/status", {"status": "approved"}, follow_redirects=False).status_code == 303
    ((to, subject, body),) = approvals
    assert to == "ana@example.com" and "approved" in subject and "BLESS-" in subject
    assert "Ana Reyes" in body and "Family SUV" in body and "0966 053 4280" in body


def test_other_status_changes_send_nothing(catalog, approvals):
    booking_id = pending_booking(catalog)
    _admin_post(f"/admin/bookings/{booking_id}/status", {"status": "rejected"})
    assert approvals == []


def test_a_booking_without_an_email_is_approved_without_sending(catalog, approvals):
    add_booking("pending", 20, 21)
    booking_id = next(iter(catalog.data["bookings"]))
    assert _admin_post(f"/admin/bookings/{booking_id}/status", {"status": "approved"}, follow_redirects=False).status_code == 303
    assert approvals == [] and catalog.data["bookings"][booking_id]["status"] == "approved"


def test_a_failing_email_never_blocks_the_approval(catalog, monkeypatch):
    def explode(*a):
        raise RuntimeError("resend is down")
    monkeypatch.setattr(mailer, "send_resend", explode)
    booking_id = pending_booking(catalog)
    response = _admin_post(f"/admin/bookings/{booking_id}/status", {"status": "approved"}, follow_redirects=False)
    assert response.status_code == 303 and catalog.data["bookings"][booking_id]["status"] == "approved"


def test_the_approval_email_for_a_tour_shows_its_dates(catalog, approvals):
    verify(start(tour_request(end_date=when(12)), "/book/tour").json()["challenge"])
    booking_id = next(iter(catalog.data["bookings"]))
    _admin_post(f"/admin/bookings/{booking_id}/status", {"status": "approved"})
    (_, subject, body), = approvals
    assert "Island Day Tour" in body and " to " in body


def test_the_admin_sees_that_the_email_was_verified(catalog):
    booking_id = pending_booking(catalog)
    assert "ana@example.com (verified)" in client.get(f"/admin/bookings/{booking_id}").text
