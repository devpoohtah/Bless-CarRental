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


# ---- hero slideshow and floating header ----
def test_hero_has_eight_slides_and_only_the_first_image_loads_with_the_page():
    html = client.get("/").text
    assert html.count("data-slide ") == 8
    assert html.count('fetchpriority="high"') == 2  # first slide + the car
    assert html.count("data-src=") == 7 and 'src="/static/customer/img/hero/slide-1.webp' in html
    for n in range(1, 9):
        assert f"hero/slide-{n}.webp" in html


def test_hero_controls_exist_and_are_labelled():
    html = client.get("/").text
    for label in ("Previous photo", "Next photo", "Pause slideshow"):
        assert f'aria-label="{label}"' in html
    assert html.count("data-hero-dot") == 8 and 'aria-roledescription="carousel"' in html


def test_the_hero_keeps_the_car_and_the_headline():
    html = client.get("/").text
    assert "hero-car.webp" in html and "Drive with BLESS." in html


def test_header_is_a_floating_island_with_the_menu_panel_outside_the_bar():
    html = client.get("/").text
    bar = html.index('class="site-header__bar"')
    assert html.index('id="mobile-menu"') > html.index("</nav>", bar) > bar
    assert 'class="container site-header__bar"' not in html


def test_slide_captions_come_only_from_the_slide_list(monkeypatch):
    from app.schemas.catalog import HeroSlide
    from app.services import content
    monkeypatch.setattr(content, "HERO_SLIDES", [HeroSlide(file="a.webp", alt="Sample alt", caption="Sample caption"), HeroSlide(file="b.webp")])
    html = client.get("/").text
    assert 'data-caption="Sample caption"' in html and 'alt="Sample alt"' in html
    assert html.count("data-caption=") == 1
