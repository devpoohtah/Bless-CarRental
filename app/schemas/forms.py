"""Validation for the admin forms. Raw form strings go in; clean values or messages come out."""

import re
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

from app.schemas.booking import DriverOption, PaymentStatus
from app.schemas.catalog import Availability


def _blank_to_none(raw: dict) -> dict:
    return {k: (v.strip() or None) if isinstance(v, str) else v for k, v in raw.items()}


class CarInput(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    vehicle_type: str = Field(min_length=1, max_length=60)
    seats: int | None = Field(default=None, ge=1, le=60)
    transmission: str | None = Field(default=None, max_length=40)
    daily_rate_php: int | None = Field(default=None, ge=0, le=10_000_000)
    availability: Availability = "inquire"


class TourInput(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    destination: str = Field(min_length=1, max_length=120)
    duration: str | None = Field(default=None, max_length=60)
    summary: str = Field(min_length=1, max_length=300)
    description: str = Field(min_length=1, max_length=4000)
    price_php: int | None = Field(default=None, ge=0, le=10_000_000)
    availability: Availability = "inquire"


class _ItemInput(BaseModel):
    # "car:<name>" or "tour:<name>": the type comes from the choice, so they cannot disagree.
    item: str = Field(min_length=3, max_length=200)

    @property
    def booking_type(self) -> Literal["car", "tour"] | None:
        kind = self.item.split(":", 1)[0]
        return kind if kind in ("car", "tour") else None

    @property
    def item_name(self) -> str:
        return self.item.split(":", 1)[1]


class BookingInput(_ItemInput):
    customer_name: str = Field(min_length=1, max_length=120)
    customer_phone: str = Field(min_length=1, max_length=40)
    customer_email: str | None = Field(default=None, max_length=120)
    start_date: date
    end_date: date
    details: str | None = Field(default=None, max_length=2000)
    payment_status: PaymentStatus = "unpaid"

    @model_validator(mode="after")
    def _dates_in_order(self):
        if self.end_date < self.start_date:
            raise ValueError("the end date cannot be before the start date")
        return self


_PHONE_CHARACTERS = re.compile(r"^[0-9+()\-.\s]+$")
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class PublicBookingInput(_ItemInput):
    """A booking request from the website. The customer cannot set status or payment."""

    customer_name: str = Field(min_length=1, max_length=120)
    customer_phone: str = Field(min_length=1, max_length=40)
    customer_email: str | None = Field(default=None, max_length=120)
    start_date: date
    end_date: date | None = None  # left blank for a one-day tour: it then equals the start date
    passengers: int = Field(ge=1, le=60)
    pickup_location: str | None = Field(default=None, max_length=200)
    driver_option: DriverOption | None = None
    details: str | None = Field(default=None, max_length=2000)

    @field_validator("customer_phone")
    @classmethod
    def _phone(cls, value: str) -> str:
        digits = sum(ch.isdigit() for ch in value)
        if not _PHONE_CHARACTERS.match(value) or not 7 <= digits <= 15:
            raise ValueError("must be a valid phone number")
        return value

    @field_validator("customer_email")
    @classmethod
    def _email_shape(cls, value: str | None) -> str | None:
        if value is not None and not _EMAIL.match(value):
            raise ValueError("must be a valid email address")
        return value

    @model_validator(mode="after")
    def _dates_in_order(self):
        if self.end_date is None:
            self.end_date = self.start_date
        elif self.end_date < self.start_date:
            raise ValueError("the end date cannot be before the start date")
        return self


LABELS = {
    "name": "Name", "vehicle_type": "Vehicle type", "seats": "Seats", "transmission": "Transmission",
    "daily_rate_php": "Daily rate", "availability": "Availability", "destination": "Destination",
    "duration": "Duration", "summary": "Short summary", "description": "Full description",
    "price_php": "Price", "item": "Car or tour", "customer_name": "Customer name",
    "customer_phone": "Customer phone", "customer_email": "Customer email",
    "start_date": "Start date", "end_date": "End date", "details": "Details",
    "payment_status": "Payment status", "passengers": "Number of people",
    "pickup_location": "Pick-up location", "driver_option": "Driver option",
}


def _message(error: dict) -> str:
    kind = error["type"]
    # A blank field is turned into None before validation, so None means "left empty".
    if kind in ("missing", "string_too_short") or error.get("input") is None:
        return "is required"
    if kind in ("int_parsing", "int_from_float"):
        return "must be a whole number"
    if kind in ("greater_than_equal", "less_than_equal"):
        return "is outside the allowed range"
    if kind == "string_too_long":
        return "is too long"
    if kind in ("date_parsing", "date_from_datetime_parsing", "date_type"):
        return "must be a valid date"
    if kind == "value_error":
        return str(error["ctx"]["error"])
    return "is not valid"


def validate(model: type[BaseModel], raw: dict) -> tuple[BaseModel | None, list[str]]:
    """Returns (values, []) on success or (None, messages) on failure."""
    try:
        return model(**_blank_to_none(raw)), []
    except ValidationError as exc:
        messages = []
        for error in exc.errors():
            field = str(error["loc"][0]) if error["loc"] else ""
            label = LABELS.get(field)
            text = _message(error)
            messages.append(f"{label} {text}." if label else f"{text[:1].upper()}{text[1:]}.")
        return None, messages
