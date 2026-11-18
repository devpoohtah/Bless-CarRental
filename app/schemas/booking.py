"""Data shapes for booking management. Plain Pydantic models so they can later be filled
from Firestore without changing the templates."""

from datetime import date, time
from typing import Literal

from pydantic import BaseModel

BookingType = Literal["car", "tour"]
BookingStatus = Literal["pending", "approved", "rejected", "ongoing", "completed", "cancelled"]
PaymentStatus = Literal["unpaid", "partial", "paid"]
DriverOption = Literal["with_driver", "self_drive"]


class StatusChange(BaseModel):
    status: BookingStatus
    changed_on: date


class Booking(BaseModel):
    id: str
    booking_type: BookingType
    customer_name: str
    customer_phone: str
    customer_email: str = ""
    item_name: str  # the car or tour package that was selected
    start_date: date  # pick-up date for a car, tour date for a tour package
    end_date: date  # return date for a car, last day of the tour
    details: str = ""
    # Filled in by the website booking form. Older and hand-added bookings leave them empty.
    passengers: int | None = None  # people travelling (guests for a tour)
    pickup_location: str = ""  # hotel, address or landmark
    dropoff_location: str = ""  # cars only
    destination: str = ""  # cars only
    start_time: time | None = None  # pick-up time; optional
    end_time: time | None = None  # return time; optional
    driver_option: DriverOption | None = None  # cars only
    requested_on: date
    status: BookingStatus
    payment_status: PaymentStatus
    history: list[StatusChange]  # oldest first
    email_verified: bool = False  # the customer entered the code we emailed (website requests only)
    is_sample: bool = True  # placeholder row, not a real booking; saved bookings set this to False

    @property
    def reference(self) -> str:
        """Short code the customer is given, so a message about a booking can be matched to it."""
        return f"BLESS-{self.id[:6].upper()}"
