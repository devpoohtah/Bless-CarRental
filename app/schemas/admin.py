"""Data shapes for the admin dashboard.

Plain Pydantic models, like app/schemas/catalog.py, so they can later be filled from
Firestore without changing the template. A count of None means "not available yet"; the
dashboard shows a dash for it instead of inventing a number.
"""

from typing import Literal

from pydantic import BaseModel


class DashboardStats(BaseModel):
    total_cars: int | None = None
    total_tour_packages: int | None = None
    total_bookings: int | None = None
    pending_bookings: int | None = None
    approved_bookings: int | None = None


class BookingRequest(BaseModel):
    id: str
    customer_name: str
    item: str  # the car or tour package that was requested
    requested_date: str
    status: Literal["pending", "approved"]
    is_sample: bool = True  # placeholder row, not a real booking
