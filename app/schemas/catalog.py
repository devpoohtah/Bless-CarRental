"""Data shapes for everything the landing page lists.

These are plain Pydantic models so they can later be read from, and written to, Firestore
(`model.model_dump()` / `Model(**document)`) without changing the templates.
`is_sample=True` marks placeholder content that the business has not confirmed.
"""

from typing import Literal

from pydantic import BaseModel, Field


class Photo(BaseModel):
    src: str = Field(description="Path under app/static, or a full https URL for an uploaded image")
    alt: str
    public_id: str | None = Field(default=None, description="Cloudinary id, needed to delete the upload")


Availability = Literal["inquire", "available", "unavailable"]


class TourPackage(BaseModel):
    id: str
    name: str
    destination: str
    summary: str
    description: str
    duration: str | None = None
    price_php: int | None = None
    availability: Availability = "inquire"
    photo: Photo
    # The vehicle that takes guests on this tour (usually a van). It lives on the package, not in the
    # car rental list, so vans never show up for car rental.
    vehicle_name: str | None = None
    vehicle_seats: int | None = None
    vehicle_photo: Photo | None = None
    is_sample: bool = True


class Destination(BaseModel):
    id: str
    name: str
    region: str
    summary: str
    description: str
    photo: Photo
    is_sample: bool = True



class Vehicle(BaseModel):
    id: str
    name: str
    vehicle_type: str
    seats: int | None = None
    transmission: str | None = None
    daily_rate_php: int | None = None
    availability: Availability = "inquire"
    photo: Photo
    description: str | None = None
    is_sample: bool = True


class Testimonial(BaseModel):
    id: str
    quote: str
    author: str
    service: str
    rating: int | None = Field(default=None, ge=1, le=5)
    photo: Photo | None = None
    translation: str | None = None  # English version of a quote written in Tagalog or Taglish
    source: str | None = None  # where the customer wrote it, e.g. a Facebook message
    tag: str | None = None  # short label such as "Returning customer"
    is_placeholder: bool = True


class FaqItem(BaseModel):
    question: str
    answer: str


class GalleryImage(BaseModel):
    id: str
    category: str
    photo: Photo


class HeroSlide(BaseModel):
    file: str = Field(description="File name under HERO_IMAGE_BASE")
    alt: str = Field(default="", description="Describe the photo; leave empty and it is treated as decoration")
    caption: str | None = Field(default=None, description="Short text shown in the hero's control strip, if any")


class NavLink(BaseModel):
    label: str
    href: str
    section_id: str
