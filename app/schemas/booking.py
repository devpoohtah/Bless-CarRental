"""Data shapes for booking management. Plain Pydantic models so they can later be filled
from Firestore without changing the templates."""

from datetime import date, datetime, time
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.schemas.pricing import QuoteLine

BookingType = Literal["car", "tour"]
BookingStatus = Literal["pending", "approved", "rejected", "ongoing", "completed", "cancelled"]
PaymentStatus = Literal["unpaid", "partial", "paid"]
PaymentType = Literal["gcash", "bank_transfer", "cash"]
DownpaymentType = Literal["gcash", "bank_transfer"]
DriverOption = Literal["with_driver", "self_drive"]


class StatusChange(BaseModel):
    status: BookingStatus
    changed_on: date


class AdditionalPayment(BaseModel):
    """An extra charge recorded by admin (e.g., delivery fee, hotel pickup fee)."""
    amount_php: int = Field(ge=1)
    payment_type: PaymentType
    description: str = Field(min_length=1, max_length=200)
    date: date


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
    requested_at: datetime | None = None
    status: BookingStatus
    payment_status: PaymentStatus
    # Downpayment (for booking confirmation) - GCash or Bank Transfer only
    downpayment_amount: int = 0
    downpayment_type: DownpaymentType | None = None
    # Remaining balance payments - GCash, Bank Transfer, or Cash
    amount_paid: int = 0  # additional payments toward remaining balance
    payment_type: PaymentType | None = None  # last payment method for remaining balance
    history: list[StatusChange]  # oldest first
    email_verified: bool = False  # the customer entered the code we emailed (website requests only)
    license_front_on_file: bool = False  # front of driver's license stored (self-drive requests)
    license_back_on_file: bool = False  # back of driver's license stored (self-drive requests)
    total_php: int | None = None  # estimated total when the request came in (website car requests); None = not priced
    price_lines: list[QuoteLine] = []  # how that total was worked out, kept as it was then
    license_delete_on: date | None = None  # the day the stored photos are deleted automatically
    is_sample: bool = True  # placeholder row, not a real booking; saved bookings set this to False
    # Additional payments recorded by admin (delivery fees, hotel pickup fees, etc.)
    additional_payments: list[AdditionalPayment] = []

    # Backward compat: map old Firestore field "license_on_file" -> "license_front_on_file"
    @model_validator(mode="before")
    @classmethod
    def _map_old_license_field(cls, data: dict) -> dict:
        if isinstance(data, dict):
            if data.get("license_on_file") is True and not data.get("license_front_on_file"):
                data["license_front_on_file"] = True
        return data

    # Backward compat: license_on_file property maps to license_front_on_file
    @property
    def license_on_file(self) -> bool:
        return self.license_front_on_file

    @property
    def total_paid(self) -> int:
        """Downpayment + remaining balance payments."""
        return self.downpayment_amount + self.amount_paid

    @property
    def remaining_balance(self) -> int | None:
        """Total owed minus all payments. None if total not priced."""
        if self.total_php is None:
            return None
        return max(0, self.total_php - self.total_paid)

    @property
    def additional_total(self) -> int:
        """Sum of all additional payments recorded by admin."""
        return sum(p.amount_php for p in self.additional_payments)

    @property
    def reference(self) -> str:
        """Short code the customer is given, so a message about a booking can be matched to it."""
        return f"BLESS-{self.id[:6].upper()}"
