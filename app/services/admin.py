"""Data for the admin dashboard.

Today this returns placeholders. When Firebase is added, replace the bodies of
get_dashboard_stats() and list_recent_bookings() with Firestore reads and keep returning
the same schemas; the route and template will not need to change.
"""

from app.schemas.admin import DashboardStats
from app.schemas.catalog import TourPackage, Vehicle
from app.services import bookings, content

# Same wording the landing page uses for each availability value.
AVAILABILITY_LABELS = {
    "inquire": "Ask for availability",
    "available": "Available",
    "unavailable": "Currently unavailable",
}


def get_dashboard_stats() -> DashboardStats:
    # No database yet, so every count is unavailable rather than made up.
    return DashboardStats()


def get_dashboard_context() -> dict:
    return {"stats": get_dashboard_stats(), "recent_bookings": bookings.recent_bookings()}


# Service management. Until Firestore is connected these return the landing page sample
# data, so the admin and the public site agree. Replace the bodies with Firestore reads;
# the routes and templates will not need to change.
def list_cars() -> list[Vehicle]:
    return content.list_vehicles()


def get_car(car_id: str) -> Vehicle | None:
    return next((car for car in list_cars() if car.id == car_id), None)


def list_tour_packages() -> list[TourPackage]:
    return content.list_tours()


def get_tour_package(tour_id: str) -> TourPackage | None:
    return next((tour for tour in list_tour_packages() if tour.id == tour_id), None)
