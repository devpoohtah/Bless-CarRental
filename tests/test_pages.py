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
    assert html.count('fetchpriority="high"') == 1  # first slide only
    assert html.count("data-src=") == 7 and 'src="/static/customer/img/hero/slide-1.webp' in html
    for n in range(1, 9):
        assert f"hero/slide-{n}.webp" in html


def test_hero_controls_exist_and_are_labelled():
    html = client.get("/").text
    for label in ("Previous photo", "Next photo", "Pause slideshow"):
        assert f'aria-label="{label}"' in html
    assert html.count("data-hero-dot") == 8 and 'aria-roledescription="carousel"' in html


def test_the_hero_has_the_headline_and_no_car():
    html = client.get("/").text
    assert "Drive with BLESS." in html and "hero__car" not in html and "hero-car.webp" not in html


def _vehicles(*specs):
    from app.schemas.catalog import Photo, Vehicle
    photo = Photo(src="customer/img/vehicles/vehicle-family-suv-placeholder.svg", alt="A car")
    return [Vehicle(id=i, name=name, vehicle_type="SUV", seats=seats, transmission="A/T", daily_rate_php=rate,
                    availability=availability, photo=photo, is_sample=False)
            for i, name, seats, rate, availability in specs]


def _car_rental_section(html: str) -> str:
    return html[html.index('id="car-rental"'):].split("</section>")[0]


def test_car_rental_is_a_carousel_with_seats_rate_and_a_link_to_all_cars(monkeypatch):
    from app.services import content
    monkeypatch.setattr(content, "list_vehicles", lambda: _vehicles(("ertiga", "Ertiga", 7, 1500, "available"),
                                                                    ("vios", "Toyota Vios", 4, 1800, "inquire")))
    section = _car_rental_section(client.get("/").text)
    assert section.count("data-vslide") == 2 and "Ertiga" in section and "Toyota Vios" in section
    assert "PHP 1,500" in section and "PHP 1,800" in section and "<dd>7</dd>" in section and "<dd>4</dd>" in section
    assert 'href="/book/car?car=ertiga"' in section and 'href="/cars"' in section
    assert "data-vcar-prev" in section and "data-vcar-next" in section and "1 of 2" in section
    assert "stack-grid" not in section  # the card grid lives on /cars now


def test_a_single_vehicle_has_no_carousel_buttons_and_an_unavailable_one_cannot_be_booked(monkeypatch):
    from app.services import content
    monkeypatch.setattr(content, "list_vehicles", lambda: _vehicles(("old-car", "Old Car", 5, 1000, "unavailable")))
    section = _car_rental_section(client.get("/").text)
    assert "data-vcar-prev" not in section and 'href="/cars"' in section
    assert "/book/car?car=old-car" not in section and "Currently unavailable</button>" in section


def test_car_rental_without_vehicles_says_so(monkeypatch):
    from app.services import content
    monkeypatch.setattr(content, "list_vehicles", lambda: [])
    section = _car_rental_section(client.get("/").text)
    assert "No vehicles are listed" in section and "data-vcar-track" not in section


def test_cars_page_lists_every_vehicle_with_its_booking_button(monkeypatch):
    from app.services import content
    monkeypatch.setattr(content, "list_vehicles", lambda: _vehicles(("ertiga", "Ertiga", 7, 1500, "available"),
                                                                    ("vios", "Toyota Vios", 4, 1800, "inquire"),
                                                                    ("old-car", "Old Car", 5, 1000, "unavailable")))
    response = client.get("/cars")
    html = response.text
    assert response.status_code == 200 and "<h1>Car rental</h1>" in html and 'aria-label="Breadcrumb"' in html
    assert html.count('class="card__media card__media--vehicle"') == 3  # whole-car image style, vehicles only
    assert 'href="/book/car?car=ertiga"' in html and 'href="/book/car?car=vios"' in html
    assert "/book/car?car=old-car" not in html and "Currently unavailable</button>" in html
    assert 'href="/#car-rental"' in html and 'href="/#home"' in html  # navbar links lead back to the landing page


def test_cars_page_without_vehicles_says_so(monkeypatch):
    from app.services import content
    monkeypatch.setattr(content, "list_vehicles", lambda: [])
    assert "No vehicles are listed" in client.get("/cars").text


def _tours(count):
    from app.schemas.catalog import Photo, TourPackage
    photo = Photo(src="customer/img/tours/tour-island-day-placeholder.svg", alt="A tour")
    return [TourPackage(id=f"tour-{n}", name=f"Tour {n}", destination="Guimaras", summary="Summary.", description="Full.",
                        photo=photo, is_sample=False) for n in range(1, count + 1)]


def test_landing_shows_the_first_three_tours_and_links_to_all(monkeypatch):
    from app.services import content
    monkeypatch.setattr(content, "list_tours", lambda: _tours(5))
    html = client.get("/").text
    assert html.count('data-open-dialog="tour-tour-') == 3 and 'id="tour-tour-3"' in html and 'id="tour-tour-4"' not in html
    assert 'href="/tours"' in html


def test_tours_page_lists_every_tour_with_its_details_dialog(monkeypatch):
    from app.services import content
    monkeypatch.setattr(content, "list_tours", lambda: _tours(5))
    response = client.get("/tours")
    html = response.text
    assert response.status_code == 200 and "<h1>Travel tour packages</h1>" in html
    assert html.count('data-open-dialog="tour-tour-') == 5 and 'id="tour-tour-5"' in html
    assert 'href="/book/tour?tour=tour-5"' in html and 'href="/#tours"' in html


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
