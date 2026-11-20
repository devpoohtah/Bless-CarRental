import re

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_services_root_redirects_to_cars():
    response = client.get("/admin/services", follow_redirects=False)
    assert response.status_code in (302, 307)
    assert response.headers["location"] == "/admin/services/cars"


def test_car_list_shows_cars_and_add_link():
    html = client.get("/admin/services/cars").text
    assert "Car Management" in html
    for name in ("Compact Sedan", "Family SUV"):
        assert name in html
    assert "Passenger Van" not in html  # vans belong to tour packages, not car rental
    assert 'href="/admin/services/cars/new"' in html
    assert 'href="/admin/services/cars/family-suv/edit"' in html
    assert "sample data" in html
    assert re.search(r'href="/admin/services/cars"[^>]*aria-current="page"', html)


def test_tour_list_shows_packages_and_add_link():
    html = client.get("/admin/services/tours").text
    assert "Tour Package Management" in html
    assert "Island Day Tour" in html
    assert 'href="/admin/services/tours/new"' in html
    assert re.search(r'href="/admin/services/tours"[^>]*aria-current="page"', html)


def test_car_form_new_is_blank_and_edit_is_prefilled():
    new = client.get("/admin/services/cars/new").text
    assert "Add car" in new and "Delete car" not in new
    edit = client.get("/admin/services/cars/family-suv/edit").text
    assert "Edit car" in edit and "Delete car" in edit
    assert 'value="Family SUV"' in edit
    assert 'name="seats" type="number" value="7"' in edit


def test_tour_form_edit_is_prefilled():
    html = client.get("/admin/services/tours/island-day-tour/edit").text
    assert 'value="Island Day Tour"' in html
    assert 'value="Guimaras"' in html
    assert "Delete tour package" in html


def test_unknown_ids_return_404():
    assert client.get("/admin/services/cars/nope/edit").status_code == 404
    assert client.get("/admin/services/tours/nope/edit").status_code == 404


def _post_with_csrf(url: str, data: dict):
    """Helper to POST with CSRF token from the cookie."""
    # Get the page first to set the CSRF cookie
    client.get(url.replace("/edit", "").replace("/delete", ""))
    csrf_token = client.cookies.get("csrf_token", "")
    headers = {"X-CSRF-Token": csrf_token}
    return client.post(url, data=data, headers=headers)


def test_without_a_database_saving_is_disabled_and_posts_are_refused():
    for url in ("/admin/services/cars/family-suv/edit", "/admin/services/tours/island-day-tour/edit"):
        html = client.get(url).text
        assert re.search(r'<button type="submit" class="btn btn--action"[^>]* disabled>', html), url
        assert "database is not connected" in html
    assert _post_with_csrf("/admin/services/cars/new", {"name": "X"}).status_code == 503
    assert _post_with_csrf("/admin/services/cars/family-suv/delete", {}).status_code == 503


def test_every_field_has_a_label():
    for url in ("/admin/services/cars/new", "/admin/services/tours/new"):
        html = client.get(url).text
        ids = re.findall(r'<(?:input|select|textarea) id="([^"]+)"', html)
        assert ids
        for field_id in ids:
            assert f'for="{field_id}"' in html, (url, field_id)


def test_service_pages_assets_load():
    for url in ("/admin/services/cars", "/admin/services/tours", "/admin/services/cars/new"):
        html = client.get(url).text
        paths = set(re.findall(r'(?:src|href)="(/static/[^"?]+)', html))
        assert "/static/admin/js/admin.js" in paths and "/static/shared/css/buttons.css" in paths
        for path in paths:
            assert client.get(path).status_code == 200, (url, path)


def test_landing_page_still_has_no_admin_links():
    assert "/admin" not in client.get("/").text
