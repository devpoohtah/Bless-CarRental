"""Service management: cars and tour packages (create, edit, delete, image upload)."""

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse

from app.core.auth import require_admin
from app.core.templating import notice_for, templates
from app.db.firebase import require_configured
from app.schemas.forms import CarInput, TourInput, validate
from app.services import admin as service
from app.services.errors import FormError

router = APIRouter(prefix="/admin/services", include_in_schema=False, dependencies=[Depends(require_admin)])

CAR_FIELDS = ("name", "vehicle_type", "seats", "transmission", "daily_rate_php", "availability")
TOUR_FIELDS = ("name", "destination", "duration", "summary", "description", "price_php", "availability",
               "vehicle_name", "vehicle_seats")


def render(request: Request, template: str, active_nav: str, status_code: int = 200, **context) -> HTMLResponse:
    context |= {"active_nav": active_nav, "availability_labels": service.AVAILABILITY_LABELS,
                "notice": notice_for(request), "errors": context.get("errors", [])}
    return templates.TemplateResponse(request, f"admin/pages/{template}", context, status_code=status_code)


def _values(item, fields) -> dict:
    return {name: getattr(item, name) for name in fields}


def _run(model, raw: dict, action) -> list[str]:
    """Validate the raw form, then run the save. Returns the messages to show, empty on success."""
    data, errors = validate(model, raw)
    if data is None:
        return errors
    try:
        action(data)
    except FormError as exc:
        return [str(exc)]
    return []


def _done(url: str, notice: str) -> RedirectResponse:
    return RedirectResponse(f"{url}?notice={notice}", status_code=303)


def _car_or_404(car_id: str):
    car = service.get_car(car_id)
    if car is None:
        raise HTTPException(status_code=404, detail="Car not found")
    return car


def _tour_or_404(tour_id: str):
    tour = service.get_tour_package(tour_id)
    if tour is None:
        raise HTTPException(status_code=404, detail="Tour package not found")
    return tour


@router.get("")
async def services_home() -> RedirectResponse:
    return RedirectResponse("/admin/services/cars")


# ---- cars ----
@router.get("/cars", response_class=HTMLResponse)
def cars(request: Request) -> HTMLResponse:
    return render(request, "cars.html", "cars", cars=service.list_cars())


@router.get("/cars/new", response_class=HTMLResponse)
def car_new(request: Request) -> HTMLResponse:
    return render(request, "car_form.html", "cars", car=None, form={})


@router.post("/cars/new")
def car_create(
    request: Request, name: str = Form(""), vehicle_type: str = Form(""), seats: str = Form(""),
    transmission: str = Form(""), daily_rate_php: str = Form(""), availability: str = Form("inquire"),
    image: UploadFile | None = File(None),
):
    require_configured()
    raw = dict(name=name, vehicle_type=vehicle_type, seats=seats, transmission=transmission,
               daily_rate_php=daily_rate_php, availability=availability)
    errors = _run(CarInput, raw, lambda data: service.create_car(data, image))
    if not errors:
        return _done("/admin/services/cars", "saved")
    return render(request, "car_form.html", "cars", 422, car=None, form=raw, errors=errors)


@router.get("/cars/{car_id}/edit", response_class=HTMLResponse)
def car_edit(request: Request, car_id: str) -> HTMLResponse:
    car = _car_or_404(car_id)
    return render(request, "car_form.html", "cars", car=car, form=_values(car, CAR_FIELDS))


@router.post("/cars/{car_id}/edit")
def car_update(
    request: Request, car_id: str, name: str = Form(""), vehicle_type: str = Form(""), seats: str = Form(""),
    transmission: str = Form(""), daily_rate_php: str = Form(""), availability: str = Form("inquire"),
    image: UploadFile | None = File(None), remove_image: str = Form(""),
):
    require_configured()
    car = _car_or_404(car_id)
    raw = dict(name=name, vehicle_type=vehicle_type, seats=seats, transmission=transmission,
               daily_rate_php=daily_rate_php, availability=availability)
    errors = _run(CarInput, raw, lambda data: service.update_car(car, data, image, bool(remove_image)))
    if not errors:
        return _done("/admin/services/cars", "saved")
    return render(request, "car_form.html", "cars", 422, car=car, form=raw, errors=errors)


@router.post("/cars/{car_id}/delete")
def car_delete(car_id: str) -> RedirectResponse:
    require_configured()
    service.delete_car(_car_or_404(car_id))
    return _done("/admin/services/cars", "deleted")


# ---- tour packages ----
@router.get("/tours", response_class=HTMLResponse)
def tours(request: Request) -> HTMLResponse:
    return render(request, "tours.html", "tours", tours=service.list_tour_packages())


@router.get("/tours/new", response_class=HTMLResponse)
def tour_new(request: Request) -> HTMLResponse:
    return render(request, "tour_form.html", "tours", tour=None, form={})


@router.post("/tours/new")
def tour_create(
    request: Request, name: str = Form(""), destination: str = Form(""), duration: str = Form(""),
    summary: str = Form(""), description: str = Form(""), price_php: str = Form(""),
    availability: str = Form("inquire"), vehicle_name: str = Form(""), vehicle_seats: str = Form(""),
    image: UploadFile | None = File(None), vehicle_image: UploadFile | None = File(None),
):
    require_configured()
    raw = dict(name=name, destination=destination, duration=duration, summary=summary,
               description=description, price_php=price_php, availability=availability,
               vehicle_name=vehicle_name, vehicle_seats=vehicle_seats)
    errors = _run(TourInput, raw, lambda data: service.create_tour_package(data, image, vehicle_image))
    if not errors:
        return _done("/admin/services/tours", "saved")
    return render(request, "tour_form.html", "tours", 422, tour=None, form=raw, errors=errors)


@router.get("/tours/{tour_id}/edit", response_class=HTMLResponse)
def tour_edit(request: Request, tour_id: str) -> HTMLResponse:
    tour = _tour_or_404(tour_id)
    return render(request, "tour_form.html", "tours", tour=tour, form=_values(tour, TOUR_FIELDS))


@router.post("/tours/{tour_id}/edit")
def tour_update(
    request: Request, tour_id: str, name: str = Form(""), destination: str = Form(""), duration: str = Form(""),
    summary: str = Form(""), description: str = Form(""), price_php: str = Form(""),
    availability: str = Form("inquire"), vehicle_name: str = Form(""), vehicle_seats: str = Form(""),
    image: UploadFile | None = File(None), vehicle_image: UploadFile | None = File(None),
    remove_image: str = Form(""), remove_vehicle_image: str = Form(""),
):
    require_configured()
    tour = _tour_or_404(tour_id)
    raw = dict(name=name, destination=destination, duration=duration, summary=summary,
               description=description, price_php=price_php, availability=availability,
               vehicle_name=vehicle_name, vehicle_seats=vehicle_seats)
    errors = _run(TourInput, raw, lambda data: service.update_tour_package(
        tour, data, image, vehicle_image, bool(remove_image), bool(remove_vehicle_image)))
    if not errors:
        return _done("/admin/services/tours", "saved")
    return render(request, "tour_form.html", "tours", 422, tour=tour, form=raw, errors=errors)


@router.post("/tours/{tour_id}/delete")
def tour_delete(tour_id: str) -> RedirectResponse:
    require_configured()
    service.delete_tour_package(_tour_or_404(tour_id))
    return _done("/admin/services/tours", "deleted")
