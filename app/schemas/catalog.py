"""Data shapes for everything the landing page lists.

These are plain Pydantic models so they can later be read from, and written to, Firestore
(`model.model_dump()` / `Model(**document)`) without changing the templates.
`is_sample=True` marks placeholder content that the business has not confirmed.
"""

from typing import Literal

from pydantic import BaseModel, Field


class Photo(BaseModel):
    src: str = Field(description="Path under app/static, e.g. images/tours/example.jpg")
    alt: str


class TourPackage(BaseModel):
    id: str
    name: str
    destination: str
    summary: str
    description: str
    duration: str | None = None
    price_php: int | None = None
    photo: Photo
    is_sample: bool = True


class Destination(BaseModel):
    id: str
    name: str
    region: str
    summary: str
    description: str
    photo: Photo
    is_sample: bool = True


Availability = Literal["inquire", "available", "unavailable"]


class Vehicle(BaseModel):
    id: str
    name: str
    vehicle_type: str
    seats: int | None = None
    transmission: str | None = None
    daily_rate_php: int | None = None
    availability: Availability = "inquire"
    photo: Photo
    is_sample: bool = True


class Testimonial(BaseModel):
    id: str
    quote: str
    author: str
    service: str
    rating: int | None = Field(default=None, ge=1, le=5)
    photo: Photo | None = None
    is_placeholder: bool = True


class FaqItem(BaseModel):
    question: str
    answer: str


class GalleryImage(BaseModel):
    id: str
    category: str
    photo: Photo


class NavLink(BaseModel):
    label: str
    href: str
    section_id: str
