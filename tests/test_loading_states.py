"""Loading states (button busy labels, page skeletons) and empty states in the admin."""

import re

from fastapi.testclient import TestClient

from app.core.templating import templates
from app.db import repositories as repo
from app.main import app
from app.schemas.booking import Booking, StatusChange
from app.core.clock import today_ph

client = TestClient(app)


def test_loading_stylesheet_is_linked_on_every_page_that_shows_loading_states():
    pages = {"/": client.get("/").text, "/admin/dashboard": client.get("/admin/dashboard").text}
    pages["/admin/login"] = client.get("/admin/login").text
    for url, html in pages.items():
        assert "shared/css/loading.css" in html, url
    assert client.get("/static/shared/css/loading.css").status_code == 200


def test_admin_pages_carry_a_placeholder_for_each_kind_of_page():
    html = client.get("/admin/bookings").text
    for kind in ("table", "dashboard", "calendar", "form"):
        assert f'<template id="skeleton-{kind}">' in html
    # Screen reader users are told the page is loading; the grey bars themselves are hidden from them.
    assert html.count('role="status">Loading the page.') == 4
    assert html.count('<div class="page" aria-hidden="true">') == 4  # the grey bars are hidden from screen readers


def test_every_submit_button_that_saves_has_a_busy_label():
    for url in ("/admin/services/cars/new", "/admin/services/tours/new", "/admin/bookings/new"):
        html = client.get(url).text
        assert re.search(r'<button type="submit" class="btn btn--action" data-busy-label="Saving…"', html), url


def test_booking_action_buttons_have_busy_labels(fake_db):
    today = today_ph()
    booking_id = repo.save(repo.BOOKINGS, Booking(
        id="", booking_type="car", customer_name="Ana", customer_phone="09171234567", item_name="Vios",
        start_date=today, end_date=today, requested_on=today, status="pending", payment_status="unpaid",
        history=[StatusChange(status="pending", changed_on=today)], is_sample=False, total_php=8000))
    html = client.get(f"/admin/bookings/{booking_id}").text
    # Downpayment form has "Recording…", remaining payment form has "Recording…",
    # additional payment form has "Recording…", status form has "Saving…",
    # manual payment status form has "Saving…"
    assert html.count('data-busy-label="Recording…"') == 3
    assert html.count('data-busy-label="Saving…"') == 2


def test_login_buttons_show_a_loading_label_and_there_is_a_live_status(monkeypatch):
    monkeypatch.setitem(templates.env.globals, "firebase_config", {"apiKey": "x", "authDomain": "x", "projectId": "x"})
    html = client.get("/admin/login").text
    assert html.count('data-busy-label="Signing in…"') == 2
    assert 'id="login-status"' in html and 'role="status"' in html


# ---- empty states ----
def test_empty_car_and_tour_lists_offer_the_add_action(fake_db):
    cars = client.get("/admin/services/cars").text
    assert "No cars yet" in cars and 'class="empty-state"' in cars
    assert re.search(r'href="/admin/services/cars/new"[^>]*>(<svg.*?</svg>)?Add car', cars, re.S)
    tours = client.get("/admin/services/tours").text
    assert "No tour packages yet" in tours and 'href="/admin/services/tours/new"' in tours


def test_empty_bookings_tell_no_bookings_yet_apart_from_an_empty_filter(fake_db):
    everything = client.get("/admin/bookings").text
    assert "No bookings yet" in everything and "Show all bookings" not in everything
    filtered = client.get("/admin/bookings?type=car").text
    assert "No car rentals yet" in filtered and "Show all bookings" in filtered
    assert "No tour bookings yet" in client.get("/admin/bookings?type=tour").text


def test_lists_with_data_show_no_empty_state():
    for url in ("/admin/services/cars", "/admin/services/tours", "/admin/bookings", "/admin/dashboard"):
        assert 'class="empty-state"' not in client.get(url).text, url
