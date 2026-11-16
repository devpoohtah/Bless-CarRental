"""Data for booking management and the booking calendar.

Until Firestore is connected this returns placeholder bookings. Their dates are relative
to today so the calendar always has something to show. Replace the bodies of
list_bookings() and get_booking() with Firestore reads; the routes and templates will not
need to change.
"""

import calendar
from datetime import date, timedelta

from app.schemas.booking import Booking, BookingStatus, BookingType, StatusChange

STATUS_LABELS = {
    "pending": "Pending",
    "approved": "Approved",
    "rejected": "Rejected",
    "ongoing": "Ongoing",
    "completed": "Completed",
    "cancelled": "Cancelled",
}
PAYMENT_LABELS = {"unpaid": "Unpaid", "partial": "Partially paid", "paid": "Paid"}
TYPE_LABELS = {"car": "Car rental", "tour": "Tour booking"}

# Which statuses a booking can move to from its current one. Rejected, completed and
# cancelled are final.
NEXT_STATUSES: dict[BookingStatus, list[BookingStatus]] = {
    "pending": ["approved", "rejected", "cancelled"],
    "approved": ["ongoing", "cancelled"],
    "ongoing": ["completed"],
    "rejected": [],
    "completed": [],
    "cancelled": [],
}

# The calendar shows bookings that are still scheduled or under way.
CALENDAR_STATUSES: tuple[BookingStatus, ...] = ("pending", "approved", "ongoing")


def _sample_bookings(today: date) -> list[Booking]:
    def d(days: int) -> date:
        return today + timedelta(days=days)

    def booking(n, kind, item, start, end, status, payment, requested, path):
        return Booking(
            id=f"sample-{n}",
            booking_type=kind,
            customer_name=f"Customer {n}",
            customer_phone="Placeholder phone number",
            customer_email="Placeholder email",
            item_name=item,
            start_date=d(start),
            end_date=d(end),
            details="Placeholder booking details.",
            requested_on=d(requested),
            status=status,
            payment_status=payment,
            history=[StatusChange(status=s, changed_on=d(day)) for s, day in path],
        )

    return [
        booking(1, "car", "Compact Sedan", 3, 5, "pending", "unpaid", -1, [("pending", -1)]),
        booking(2, "tour", "Island Day Tour", 10, 10, "pending", "unpaid", 0, [("pending", 0)]),
        booking(3, "car", "Family SUV", 1, 4, "approved", "partial", -4,
                [("pending", -4), ("approved", -3)]),
        booking(4, "tour", "Beach Getaway Package", 7, 9, "approved", "paid", -6,
                [("pending", -6), ("approved", -5)]),
        booking(5, "car", "Passenger Van", -2, 2, "ongoing", "paid", -9,
                [("pending", -9), ("approved", -8), ("ongoing", -2)]),
        booking(6, "tour", "Heritage and Church Tour", -12, -12, "completed", "paid", -20,
                [("pending", -20), ("approved", -19), ("ongoing", -12), ("completed", -12)]),
        booking(7, "car", "Compact Sedan", 5, 6, "rejected", "unpaid", -3,
                [("pending", -3), ("rejected", -2)]),
        booking(8, "tour", "Island Day Tour", 14, 14, "cancelled", "unpaid", -7,
                [("pending", -7), ("approved", -6), ("cancelled", -1)]),
        booking(9, "car", "Compact Sedan", 2, 3, "approved", "unpaid", -2,
                [("pending", -2), ("approved", -1)]),
    ]


def list_bookings(booking_type: BookingType | None = None) -> list[Booking]:
    rows = sorted(_sample_bookings(date.today()), key=lambda b: b.requested_on, reverse=True)
    return [b for b in rows if booking_type in (None, b.booking_type)]


def get_booking(booking_id: str) -> Booking | None:
    return next((b for b in list_bookings() if b.id == booking_id), None)


def recent_bookings(limit: int = 5) -> list[Booking]:
    return list_bookings()[:limit]


def parse_month(value: str | None, today: date) -> date:
    """First day of the month in 'YYYY-MM' form; falls back to the current month."""
    try:
        year, month = (int(part) for part in (value or "").split("-"))
        if not 2000 <= year <= 2100:
            raise ValueError("year out of range")
        return date(year, month, 1)
    except ValueError:
        return today.replace(day=1)


def month_view(first_day: date, today: date) -> dict:
    """Everything the calendar page needs for one month."""
    bookings = [b for b in list_bookings() if b.status in CALENDAR_STATUSES]

    def on(day: date) -> list[Booking]:
        return [b for b in bookings if b.start_date <= day <= b.end_date]

    weeks = [
        [{"date": day, "in_month": day.month == first_day.month, "is_today": day == today,
          "bookings": on(day)} for day in week]
        for week in calendar.Calendar(firstweekday=6).monthdatescalendar(first_day.year, first_day.month)
    ]
    agenda = [(cell["date"], cell["bookings"]) for week in weeks for cell in week
              if cell["in_month"] and cell["bookings"]]
    previous = (first_day - timedelta(days=1)).replace(day=1)
    following = (first_day + timedelta(days=31)).replace(day=1)
    return {
        "month_label": first_day.strftime("%B %Y"),
        "weeks": weeks,
        "agenda": agenda,
        "previous_month": previous.strftime("%Y-%m"),
        "next_month": following.strftime("%Y-%m"),
        "is_current_month": first_day == today.replace(day=1),
        "weekdays": [calendar.day_abbr[i] for i in (6, 0, 1, 2, 3, 4, 5)],
    }
