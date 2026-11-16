import re

from fastapi.testclient import TestClient

from app.core.templating import templates
from app.main import app
from app.schemas.admin import DashboardStats

client = TestClient(app)


def test_dashboard_has_all_sections():
    html = client.get("/admin/dashboard").text
    for heading in ("Dashboard Overview", "Total Cars", "Total Tour Packages", "Total Bookings",
                    "Pending and Approved Bookings", "Recent Booking Requests"):
        assert heading in html, heading


def test_dashboard_shows_placeholders_not_invented_numbers():
    html = client.get("/admin/dashboard").text
    assert "No data yet" in html
    assert "sample data, not real bookings" in html


def test_dashboard_is_not_indexed_or_linked_from_landing_page():
    assert 'name="robots" content="noindex, nofollow"' in client.get("/admin/dashboard").text
    assert "/admin" not in client.get("/").text


def test_dashboard_assets_load():
    html = client.get("/admin/dashboard").text
    paths = set(re.findall(r'(?:src|href)="(/static/[^"?]+)', html))
    assert "/static/admin/css/admin.css" in paths and "/static/shared/css/tokens.css" in paths
    for path in paths:
        assert client.get(path).status_code == 200, path


def render(**context):
    return templates.env.get_template("admin/pages/dashboard.html").render(**context)


def test_dashboard_empty_state():
    html = render(stats=DashboardStats(), recent_bookings=[])
    assert "No booking requests yet." in html
    assert "<table" not in html


def test_dashboard_shows_real_counts_when_available():
    html = render(stats=DashboardStats(total_cars=7), recent_bookings=[])
    assert re.search(r"Total Cars</dt>\s*<dd>\s*7\s*</dd>", html)


def test_admin_root_redirects_to_dashboard():
    response = client.get("/admin", follow_redirects=False)
    assert response.status_code in (302, 307)
    assert response.headers["location"] == "/admin/dashboard"


def test_sidebar_links_and_current_page():
    html = client.get("/admin/dashboard").text
    for href in ("/admin/dashboard", "/admin/services/cars", "/admin/services/tours"):
        assert f'href="{href}"' in html, href
    assert re.search(r'href="/admin/dashboard"[^>]*aria-current="page"', html)
    assert not re.search(r'href="/admin/services/cars"[^>]*aria-current', html)
    for href in ("/admin/bookings", "/admin/calendar"):
        assert f'href="{href}"' in html, href


def test_admin_uses_shared_logo_and_favicon():
    html = client.get("/admin/dashboard").text
    assert html.count("/static/shared/img/bless-logo.webp") >= 2  # favicon link + sidebar logo
    assert client.get("/static/shared/img/bless-logo.webp").status_code == 200
    assert client.get("/static/customer/img/bless-logo.webp").status_code == 404


def test_sidebar_has_collapse_and_sign_out():
    html = client.get("/admin/dashboard").text
    assert "data-admin-collapse" in html and 'aria-expanded="true"' in html
    assert re.search(r'<form method="post" action="/admin/logout">', html)
    assert "Sign out" in html


def test_logout_is_post_only_clears_the_cookie_and_returns_to_login():
    assert client.get("/admin/logout").status_code == 405
    response = client.post("/admin/logout", follow_redirects=False)
    assert response.status_code == 303 and response.headers["location"] == "/admin/login"
    assert "bless_admin_session" in response.headers["set-cookie"]


def test_dashboard_recent_requests_come_from_bookings():
    html = client.get("/admin/dashboard").text
    assert "Customer 1" in html
    assert 'href="/admin/bookings/sample-' in html
