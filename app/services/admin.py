"""Data for the admin dashboard and service management (cars and tour packages).

Reads come from Firestore when it is connected, otherwise from the landing page samples.
Writes always need Firestore (see firebase.require_configured).
"""

from fastapi import UploadFile

from app.db import firebase
from app.db import repositories as repo
from app.schemas.admin import DashboardStats
from app.schemas.catalog import Photo, TourPackage, Vehicle
from app.schemas.forms import CarInput, TourInput
from app.services import bookings, content, images

# Same wording the landing page uses for each availability value.
AVAILABILITY_LABELS = {
    "inquire": "Ask for availability",
    "available": "Available",
    "unavailable": "Currently unavailable",
}

# Shown until a real photo is uploaded.
CAR_PLACEHOLDER = "customer/img/services/service-car-rental-placeholder.svg"
TOUR_PLACEHOLDER = "customer/img/services/service-tours-placeholder.svg"


# ---- dashboard ----
def get_dashboard_context() -> dict:
    rows = bookings.list_bookings()
    if firebase.is_configured():
        stats = DashboardStats(
            total_cars=len(list_cars()),
            total_tour_packages=len(list_tour_packages()),
            total_bookings=len(rows),
            pending_bookings=sum(b.status == "pending" for b in rows),
            approved_bookings=sum(b.status == "approved" for b in rows),
        )
    else:
        stats = DashboardStats()  # no database: every count stays unavailable, never made up
    return {"stats": stats, "recent_bookings": rows[:5]}


# ---- reads ----
def list_cars() -> list[Vehicle]:
    return content.list_vehicles()


def get_car(car_id: str) -> Vehicle | None:
    if firebase.is_configured():
        return repo.get_one(repo.CARS, car_id, Vehicle)
    return next((car for car in list_cars() if car.id == car_id), None)


def list_tour_packages() -> list[TourPackage]:
    return content.list_tours()


def get_tour_package(tour_id: str) -> TourPackage | None:
    if firebase.is_configured():
        return repo.get_one(repo.TOURS, tour_id, TourPackage)
    return next((tour for tour in list_tour_packages() if tour.id == tour_id), None)


# ---- writes (shared by cars and tours) ----
def _has_file(image: UploadFile | None) -> bool:
    return image is not None and bool(image.filename)


def _upload(image: UploadFile | None, folder: str) -> images.UploadedImage | None:
    return images.upload(image, folder) if _has_file(image) else None


def _create(collection, model, folder, placeholder, data, image):
    uploaded = _upload(image, folder)
    photo = (Photo(src=uploaded.url, alt=data.name, public_id=uploaded.public_id) if uploaded
             else Photo(src=placeholder, alt=data.name))
    item = model(id="", photo=photo, is_sample=False, **data.model_dump())
    try:
        return repo.save(collection, item)
    except Exception:
        if uploaded:
            images.delete(uploaded.public_id)  # do not leave an image nothing points to
        raise


def _update(collection, folder, item, data, image):
    uploaded = _upload(image, folder)
    if uploaded:
        photo = Photo(src=uploaded.url, alt=data.name, public_id=uploaded.public_id)
    else:
        photo = item.photo.model_copy(update={"alt": data.name})
    updated = item.model_copy(update={**data.model_dump(), "photo": photo, "is_sample": False})
    try:
        repo.save(collection, updated, item.id)
    except Exception:
        if uploaded:
            images.delete(uploaded.public_id)
        raise
    if uploaded:
        images.delete(item.photo.public_id)  # the replaced image


def _remove(collection, item):
    repo.delete(collection, item.id)
    images.delete(item.photo.public_id)


def create_car(data: CarInput, image: UploadFile | None) -> str:
    return _create(repo.CARS, Vehicle, "cars", CAR_PLACEHOLDER, data, image)


def update_car(car: Vehicle, data: CarInput, image: UploadFile | None) -> None:
    _update(repo.CARS, "cars", car, data, image)


def delete_car(car: Vehicle) -> None:
    _remove(repo.CARS, car)


def create_tour_package(data: TourInput, image: UploadFile | None) -> str:
    return _create(repo.TOURS, TourPackage, "tours", TOUR_PLACEHOLDER, data, image)


def update_tour_package(tour: TourPackage, data: TourInput, image: UploadFile | None) -> None:
    _update(repo.TOURS, "tours", tour, data, image)


def delete_tour_package(tour: TourPackage) -> None:
    _remove(repo.TOURS, tour)
