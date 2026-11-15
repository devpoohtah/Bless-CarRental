"""Service management: cars and tour packages.

These pages only display data for now. Saving, deleting and image upload are shown but
disabled until the database and image storage are connected.
"""

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.core.templating import templates
from app.services.admin import (
    AVAILABILITY_LABELS,
    get_car,
    get_tour_package,
    list_cars,
    list_tour_packages,
)

router = APIRouter(prefix="/admin/services", include_in_schema=False)


def render(request: Request, template: str, active_nav: str, **context) -> HTMLResponse:
    context |= {"active_nav": active_nav, "availability_labels": AVAILABILITY_LABELS}
    return templates.TemplateResponse(request, f"admin/pages/{template}", context)


@router.get("")
async def services_home() -> RedirectResponse:
    return RedirectResponse("/admin/services/cars")


@router.get("/cars", response_class=HTMLResponse)
async def cars(request: Request) -> HTMLResponse:
    return render(request, "cars.html", "cars", cars=list_cars())


@router.get("/cars/new", response_class=HTMLResponse)
async def car_new(request: Request) -> HTMLResponse:
    return render(request, "car_form.html", "cars", car=None)


@router.get("/cars/{car_id}/edit", response_class=HTMLResponse)
async def car_edit(request: Request, car_id: str) -> HTMLResponse:
    car = get_car(car_id)
    if car is None:
        raise HTTPException(status_code=404, detail="Car not found")
    return render(request, "car_form.html", "cars", car=car)


@router.get("/tours", response_class=HTMLResponse)
async def tours(request: Request) -> HTMLResponse:
    return render(request, "tours.html", "tours", tours=list_tour_packages())


@router.get("/tours/new", response_class=HTMLResponse)
async def tour_new(request: Request) -> HTMLResponse:
    return render(request, "tour_form.html", "tours", tour=None)


@router.get("/tours/{tour_id}/edit", response_class=HTMLResponse)
async def tour_edit(request: Request, tour_id: str) -> HTMLResponse:
    tour = get_tour_package(tour_id)
    if tour is None:
        raise HTTPException(status_code=404, detail="Tour package not found")
    return render(request, "tour_form.html", "tours", tour=tour)
