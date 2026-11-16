"""Data shapes for booking management. Plain Pydantic models so they can later be filled
from Firestore without changing the templates."""

from datetime import date
from typing import Literal

from pydantic import BaseModel

BookingType = Literal["car", "tour"]
BookingStatus = Literal["pending", "approved", "rejected", "ongoing", "completed", "cancelled"]
PaymentStatus = Literal["unpaid", "partial", "paid"]


class StatusChange(BaseModel):
    status: BookingStatus
    changed_on: date


class Booking(BaseModel):
    id: str
    booking_type: BookingType
    customer_name: str
    customer_phone: str
    customer_email: str
    item_name: str  # the car or tour package that was selected
    start_date: date  # pick-up date for a car, tour date for a tour package
    end_date: date  # return date for a car, last day of the tour
    details: str = ""
    requested_on: date
    status: BookingStatus
    payment_status: PaymentStatus
    history: list[StatusChange]  # oldest first
    is_sample: bool = True  # placeholder row, not a real booking
