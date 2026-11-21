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
from app.services.errors import FormError

# Same wording the landing page uses for each availability value.
AVAILABILITY_LABELS = {
    "inquire": "Ask for availability",
    "available": "Available",
    "unavailable": "Currently unavailable",
}

# Shown until a real photo is uploaded.
CAR_PLACEHOLDER = "customer/img/services/service-car-rental-placeholder.svg"
TOUR_PLACEHOLDER = "customer/img/services/service-tours-placeholder.svg"
VAN_PLACEHOLDER = "customer/img/vehicles/vehicle-passenger-van-placeholder.svg"


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


def _update(collection, folder, placeholder, item, data, image, remove_image=False):
    uploaded = _upload(image, folder)
    removed = remove_image and not uploaded and bool(item.photo.public_id)  # a new file wins over "remove"
    if uploaded:
        photo = Photo(src=uploaded.url, alt=data.name, public_id=uploaded.public_id)
    elif removed:
        photo = Photo(src=placeholder, alt=data.name)
    else:
        photo = item.photo.model_copy(update={"alt": data.name})
    updated = item.model_copy(update={**data.model_dump(), "photo": photo, "is_sample": False})
    try:
        repo.save(collection, updated, item.id)
    except Exception:
        if uploaded:
            images.delete(uploaded.public_id)
        raise
    if uploaded or removed:
        images.delete(item.photo.public_id)  # the replaced or removed image


def _remove(collection, item):
    repo.delete(collection, item.id)
    images.delete(item.photo.public_id)


def create_car(data: CarInput, image: UploadFile | None) -> str:
    if not _has_file(image):
        # No image: use placeholder
        photo = Photo(src=CAR_PLACEHOLDER, alt=data.name)
    else:
        # Upload single image (full res, WebP, quality 90)
        uploaded = images.upload(image, "cars")
        photo = Photo(src=uploaded.url, alt=data.name, public_id=uploaded.public_id)
    item = Vehicle(id="", photo=photo, is_sample=False, **data.model_dump())
    try:
        return repo.save(repo.CARS, item)
    except Exception:
        if _has_file(image) and photo.public_id:
            images.delete(photo.public_id)
        raise


def update_car(car: Vehicle, data: CarInput, image: UploadFile | None, remove_image: bool = False) -> None:
    if _has_file(image):
        # New image uploaded
        uploaded = images.upload(image, "cars")
        photo = Photo(src=uploaded.url, alt=data.name, public_id=uploaded.public_id)
    elif remove_image and car.photo.public_id:
        # Remove requested, no new image: revert to placeholder
        photo = Photo(src=CAR_PLACEHOLDER, alt=data.name)
    else:
        # Keep existing
        photo = car.photo.model_copy(update={"alt": data.name})

    updated = car.model_copy(update={**data.model_dump(), "photo": photo, "is_sample": False})
    try:
        repo.save(repo.CARS, updated, car.id)
    except Exception:
        if _has_file(image) and photo.public_id:
            images.delete(photo.public_id)
        raise
    # Clean up old image if replaced or removed
    if _has_file(image) or remove_image:
        if car.photo.public_id and (not _has_file(image) or car.photo.public_id != photo.public_id):
            images.delete(car.photo.public_id)


def delete_car(car: Vehicle) -> None:
    _remove(repo.CARS, car)


def _save_tour(item: TourPackage | None, data: TourInput, image: UploadFile | None,
               vehicle_image: UploadFile | None, remove_image: bool = False,
               remove_vehicle_image: bool = False) -> str:
    """Create (item is None) or update a tour package, with its package photo and its own vehicle photo.

    The vehicle belongs to the package, so vans stay out of the car rental list.
    """
    if _has_file(vehicle_image) and not data.vehicle_name:
        raise FormError("Enter the vehicle name before adding a vehicle image.")
    uploads: list[images.UploadedImage] = []  # made now; removed again if the save fails

    def upload(file, folder):
        done = _upload(file, folder)
        if done:
            uploads.append(done)
        return done

    try:
        new_photo = upload(image, "tours")
        new_vehicle = upload(vehicle_image, "tour-vehicles")
    except Exception:
        for done in uploads:
            images.delete(done.public_id)
        raise

    old_photo = item.photo if item else None
    old_vehicle = item.vehicle_photo if item else None
    if new_photo:
        photo = Photo(src=new_photo.url, alt=data.name, public_id=new_photo.public_id)
    elif old_photo and not (remove_image and old_photo.public_id):
        photo = old_photo.model_copy(update={"alt": data.name})
    else:
        photo = Photo(src=TOUR_PLACEHOLDER, alt=data.name)  # new package, or its image was removed
    if not data.vehicle_name:
        vehicle_photo = None
    elif new_vehicle:
        vehicle_photo = Photo(src=new_vehicle.url, alt=data.vehicle_name, public_id=new_vehicle.public_id)
    elif old_vehicle and not (remove_vehicle_image and old_vehicle.public_id):
        vehicle_photo = old_vehicle.model_copy(update={"alt": data.vehicle_name})
    else:
        vehicle_photo = Photo(src=VAN_PLACEHOLDER, alt=data.vehicle_name)

    fields = {**data.model_dump(), "photo": photo, "vehicle_photo": vehicle_photo, "is_sample": False}
    saved = item.model_copy(update=fields) if item else TourPackage(id="", **fields)
    try:
        doc_id = repo.save(repo.TOURS, saved, item.id if item else None)
    except Exception:
        for done in uploads:
            images.delete(done.public_id)
        raise
    if old_photo and old_photo.public_id and photo.public_id != old_photo.public_id:
        images.delete(old_photo.public_id)  # replaced or removed
    if old_vehicle and old_vehicle.public_id and (vehicle_photo is None or vehicle_photo.public_id != old_vehicle.public_id):
        images.delete(old_vehicle.public_id)  # replaced or removed, or the vehicle itself was removed
    return doc_id


def create_tour_package(data: TourInput, image: UploadFile | None, vehicle_image: UploadFile | None = None) -> str:
    return _save_tour(None, data, image, vehicle_image)


def update_tour_package(tour: TourPackage, data: TourInput, image: UploadFile | None,
                        vehicle_image: UploadFile | None = None, remove_image: bool = False,
                        remove_vehicle_image: bool = False) -> None:
    _save_tour(tour, data, image, vehicle_image, remove_image, remove_vehicle_image)


def delete_tour_package(tour: TourPackage) -> None:
    _remove(repo.TOURS, tour)
    if tour.vehicle_photo:
        images.delete(tour.vehicle_photo.public_id)
