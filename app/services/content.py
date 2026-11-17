"""Content for the landing page.

Tours and vehicles are read from Firestore when it is connected. Destinations, testimonials,
gallery and FAQs are still static sample data.

Everything marked is_sample / is_placeholder is NOT confirmed business information.
Edit it here, or set the flag to False once the real details are in.
"""

from app.db import firebase, repositories
from app.schemas.catalog import (
    Destination,
    FaqItem,
    GalleryImage,
    NavLink,
    Photo,
    TourPackage,
    Testimonial,
    Vehicle,
)

NAV_LINKS = [
    NavLink(label="Home", href="#home", section_id="home"),
    NavLink(label="About", href="#about", section_id="about"),
    NavLink(label="Tours", href="#tours", section_id="tours"),
    NavLink(label="Destinations", href="#destinations", section_id="destinations"),
    NavLink(label="Car Rental", href="#car-rental", section_id="car-rental"),
    NavLink(label="Gallery", href="#gallery", section_id="gallery"),
    NavLink(label="FAQ", href="#faq", section_id="faq"),
    NavLink(label="Contact", href="#contact", section_id="contact"),
]


def _photo(src: str, alt: str) -> Photo:
    return Photo(src=src, alt=alt)


def _sample_tours() -> list[TourPackage]:
    return [
        TourPackage(
            id="island-day-tour",
            name="Island Day Tour",
            destination="Guimaras",
            summary="A relaxed day of island scenery, local food stops and beach time.",
            description=(
                "Sample package. A day trip built around island scenery and local food. "
                "Itinerary, inclusions, pick-up points and rates will be confirmed by BLESS."
            ),
            duration="1 day",
            photo=_photo("customer/img/tours/tour-island-day-placeholder.svg",
                         "Placeholder image of an island coastline under a clear sky"),
            vehicle_name="Passenger Van",
            vehicle_seats=12,
            vehicle_photo=_photo("customer/img/vehicles/vehicle-passenger-van-placeholder.svg",
                                 "Placeholder illustration of a passenger van"),
        ),
        TourPackage(
            id="heritage-church-tour",
            name="Heritage and Church Tour",
            destination="Iloilo Province",
            summary="Historic churches and heritage sites, with time for photos and local stops.",
            description=(
                "Sample package. A culture-focused day visiting historic churches and heritage "
                "sites. Itinerary, inclusions and rates will be confirmed by BLESS."
            ),
            duration="1 day",
            photo=_photo("customer/img/tours/tour-heritage-day-placeholder.svg",
                         "Placeholder image of a stone church at dusk"),
            vehicle_name="Passenger Van",
            vehicle_seats=12,
            vehicle_photo=_photo("customer/img/vehicles/vehicle-passenger-van-placeholder.svg",
                                 "Placeholder illustration of a passenger van"),
        ),
        TourPackage(
            id="beach-getaway",
            name="Beach Getaway Package",
            destination="Boracay Island",
            summary="Beach days and island activities, with free time to explore at your own pace.",
            description=(
                "Sample package. A multi-day beach trip. Length of stay, inclusions and rates "
                "will be confirmed by BLESS."
            ),
            duration="3 days, 2 nights",
            photo=_photo("customer/img/tours/tour-beach-getaway-placeholder.svg",
                         "Placeholder image of a white sand beach and turquoise sea"),
            vehicle_name="Passenger Van",
            vehicle_seats=12,
            vehicle_photo=_photo("customer/img/vehicles/vehicle-passenger-van-placeholder.svg",
                                 "Placeholder illustration of a passenger van"),
        ),
    ]


# Tours and vehicles come from Firestore once it is connected (Admin > Service Management);
# without credentials the sample listings below keep the site and the tests working.
def list_tours() -> list[TourPackage]:
    if firebase.is_configured():
        return sorted(repositories.list_all(repositories.TOURS, TourPackage), key=lambda t: t.name.lower())
    return _sample_tours()


def list_vehicles() -> list[Vehicle]:
    if firebase.is_configured():
        return sorted(repositories.list_all(repositories.CARS, Vehicle), key=lambda v: v.name.lower())
    return _sample_vehicles()


def list_destinations() -> list[Destination]:
    return [
        Destination(
            id="boracay",
            name="Boracay Island",
            region="Aklan",
            summary="White sand beaches and island activities.",
            description="Sample destination. Details will be confirmed by BLESS.",
            photo=_photo("customer/img/destinations/destination-boracay-placeholder.svg",
                         "Placeholder image of a beach and turquoise sea"),
        ),
        Destination(
            id="guimaras",
            name="Guimaras",
            region="Western Visayas",
            summary="Island scenery within reach of Iloilo City.",
            description="Sample destination. Details will be confirmed by BLESS.",
            photo=_photo("customer/img/destinations/destination-guimaras-placeholder.svg",
                         "Placeholder image of an island coastline"),
        ),
        Destination(
            id="gigantes",
            name="Gigantes Islands",
            region="Carles, Iloilo",
            summary="Island hopping and coastal views.",
            description="Sample destination. Details will be confirmed by BLESS.",
            photo=_photo("customer/img/destinations/destination-gigantes-placeholder.svg",
                         "Placeholder image of islands at sunset"),
        ),
        Destination(
            id="miagao",
            name="Miagao",
            region="Iloilo",
            summary="Historic church and heritage town.",
            description="Sample destination. Details will be confirmed by BLESS.",
            photo=_photo("customer/img/destinations/destination-miagao-placeholder.svg",
                         "Placeholder image of a stone church facade"),
        ),
        Destination(
            id="iloilo-city",
            name="Iloilo City",
            region="Western Visayas",
            summary="Food, heritage and the riverfront.",
            description="Sample destination. Details will be confirmed by BLESS.",
            photo=_photo("customer/img/destinations/destination-iloilo-city-placeholder.svg",
                         "Placeholder image of a city skyline at dusk"),
        ),
    ]


def _sample_vehicles() -> list[Vehicle]:
    return [
        Vehicle(
            id="compact-sedan",
            name="Compact Sedan",
            vehicle_type="Sedan",
            seats=5,
            transmission="Automatic",
            photo=_photo("customer/img/vehicles/vehicle-compact-sedan-placeholder.svg",
                         "Placeholder illustration of a sedan"),
        ),
        Vehicle(
            id="family-suv",
            name="Family SUV",
            vehicle_type="SUV",
            seats=7,
            transmission="Automatic",
            photo=_photo("customer/img/vehicles/vehicle-family-suv-placeholder.svg",
                         "Placeholder illustration of an SUV"),
        ),
    ]


def list_testimonials() -> list[Testimonial]:
    quote = "Customer feedback goes here. Replace this placeholder with a verified review."
    return [
        Testimonial(id="placeholder-1", quote=quote, author="Customer name", service="Tour package"),
        Testimonial(id="placeholder-2", quote=quote, author="Customer name", service="Car rental"),
        Testimonial(id="placeholder-3", quote=quote, author="Customer name", service="Tour package"),
    ]


def list_gallery() -> list[GalleryImage]:
    def item(id_: str, category: str, file: str) -> GalleryImage:
        return GalleryImage(
            id=id_, category=category,
            photo=_photo(f"customer/img/gallery/{file}", f"Placeholder image: {category.lower()}"),
        )

    return [
        item("g1", "Travel destinations", "gallery-destination-placeholder.svg"),
        item("g2", "Group tours", "gallery-group-tour-placeholder.svg"),
        item("g3", "Customer travel experiences", "gallery-customer-experience-placeholder.svg"),
        item("g4", "Vehicles", "gallery-vehicle-placeholder.svg"),
        item("g5", "Business activities", "gallery-business-activity-placeholder.svg"),
        item("g6", "Travel destinations", "gallery-sunset-placeholder.svg"),
    ]


def list_faqs() -> list[FaqItem]:
    return [
        FaqItem(
            question="How can I book a tour?",
            answer=(
                "For now, tour bookings are arranged through our Facebook page and Messenger, or by "
                "phone. Tell us which tour or destination you are interested in and BLESS will "
                "confirm the next steps with you. An online booking system is planned for later."
            ),
        ),
        FaqItem(
            question="How can I rent a vehicle?",
            answer=(
                "Send us a message on Messenger or call us with the vehicle type you need and your "
                "travel dates. Rental terms, requirements and rates are confirmed by BLESS when you inquire."
            ),
        ),
        FaqItem(
            question="What information is needed for a booking?",
            answer=(
                "BLESS confirms the exact requirements when you inquire. It helps to have your "
                "preferred dates, the number of travelers, the tour or vehicle you are interested in, "
                "and your contact details ready."
            ),
        ),
        FaqItem(
            question="How can I inquire about available packages?",
            answer=(
                "Message us on Messenger or call to ask about current tour packages and vehicles. "
                "The packages and vehicles shown on this page are sample listings until the business "
                "confirms its offerings."
            ),
        ),
        FaqItem(
            question="How can I contact BLESS?",
            answer=(
                "Call 0966 053 4280, message the BLESS Facebook page on Messenger, or visit the page "
                "on Facebook. Contact details are also listed in the Contact section below."
            ),
        ),
    ]


def get_home_context() -> dict:
    return {
        "nav_links": NAV_LINKS,
        "tours": list_tours(),
        "destinations": list_destinations(),
        "vehicles": list_vehicles(),
        "testimonials": list_testimonials(),
        "gallery": list_gallery(),
        "faqs": list_faqs(),
    }
