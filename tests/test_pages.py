import re

from fastapi.testclient import TestClient

from app.core.config import STATIC_DIR
from app.main import app

client = TestClient(app)


def test_home_renders_all_sections():
    html = client.get("/").text
    for section_id in ("home", "about", "tours", "destinations", "car-rental",
                       "why-us", "testimonials", "gallery", "faq", "contact"):
        assert f'id="{section_id}"' in html


def test_nav_anchors_point_to_existing_sections():
    html = client.get("/").text
    ids = set(re.findall(r'\sid="([^"]+)"', html))
    anchors = set(re.findall(r'href="#([^"]+)"', html))
    assert anchors <= ids, f"Broken anchors: {anchors - ids}"


def test_contact_details_and_logo_comment():
    html = client.get("/").text
    assert "0966 053 4280" in html
    assert "tel:+639660534280" in html
    assert "https://www.facebook.com/profile.php?id=61572490139656" in html
    assert "your brand logo will go here" in html


def test_every_referenced_static_file_exists():
    html = re.sub(r"<!--.*?-->", "", client.get("/").text, flags=re.S)  # ignore commented-out logo example
    paths = set(re.findall(r'(?:src|href)="(/static/[^"?]+)', html))
    assert paths
    for path in paths:
        assert client.get(path).status_code == 200, path


def test_no_emoji_in_markup():
    html = client.get("/").text
    assert not re.search("[\U0001F300-\U0001FAFF\u2600-\u27BF]", html)


def test_favicon_routes():
    assert client.get("/favicon.ico").status_code == 200
    assert (STATIC_DIR / "shared" / "img" / "favicon.svg").exists()
