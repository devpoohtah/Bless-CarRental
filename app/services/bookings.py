"""Data for booking management and the booking calendar.

Bookings are read from and written to Firestore when it is connected. Without credentials
this returns placeholder bookings whose dates are relative to today, so the calendar and
tests always have something to show.
"""

import calendar
from datetime import date, timedelta

from app.db import firebase
from app.db import repositories as repo
from app.schemas.booking import Booking, BookingStatus, BookingType, StatusChange
from app.core.clock import today_ph
from app.schemas.forms import BookingInput, PublicCarBookingInput, PublicTourBookingInput
from app.services import content
from app.services.errors import FormError

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
DRIVER_LABELS = {"with_driver": "With a driver", "self_drive": "Self-drive"}

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
        booking(5, "car", "Family SUV", -2, 2, "ongoing", "paid", -9,
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
    rows = repo.list_all(repo.BOOKINGS, Booking) if firebase.is_configured() else _sample_bookings(date.today())
    rows = sorted(rows, key=lambda b: (b.requested_on, b.start_date), reverse=True)
    return [b for b in rows if booking_type in (None, b.booking_type)]


def pending_count() -> int:
    """Real bookings waiting for a decision. Sample rows are not real requests, so without a database: 0."""
    if not firebase.is_configured():
        return 0
    return repo.count_where(repo.BOOKINGS, status="pending", is_sample=False)


def get_booking(booking_id: str) -> Booking | None:
    if firebase.is_configured():
        return repo.get_one(repo.BOOKINGS, booking_id, Booking)
    return next((b for b in list_bookings() if b.id == booking_id), None)


def item_choices() -> dict[str, list[tuple[str, str]]]:
    """Cars and tour packages for the booking form, as (value, label) pairs per group."""
    return {
        "Cars": [(f"car:{v.name}", v.name) for v in content.list_vehicles()],
        "Tour packages": [(f"tour:{t.name}", t.name) for t in content.list_tours()],
    }


def create_booking(data: BookingInput) -> str:
    choices = {value for group in item_choices().values() for value, _ in group}
    if data.item not in choices:
        raise FormError("Choose a car or tour package from the list.")
    today = date.today()
    booking = Booking(
        id="",
        booking_type=data.booking_type,
        customer_name=data.customer_name,
        customer_phone=data.customer_phone,
        customer_email=data.customer_email or "",
        item_name=data.item_name,
        start_date=data.start_date,
        end_date=data.end_date,
        details=data.details or "",
        requested_on=today,
        status="pending",
        payment_status=data.payment_status,
        history=[StatusChange(status="pending", changed_on=today)],
        is_sample=False,
    )
    return repo.save(repo.BOOKINGS, booking)


# A date is taken once BLESS has approved a booking for it, and stays taken while the trip is under way.
BLOCKING_STATUSES: tuple[BookingStatus, ...] = ("approved", "ongoing")
MAX_DAYS_AHEAD = 730  # website requests may be made up to two years ahead


def blocked_ranges(booking_type: BookingType, item_name: str) -> list[tuple[date, date]]:
    """(first day, last day) of every approved or ongoing booking for this car or tour package.

    Pending requests do not block a date, because BLESS has not accepted them yet. Sample rows never block.
    """
    if not firebase.is_configured():
        return []
    rows = repo.list_where(repo.BOOKINGS, Booking, booking_type=booking_type, item_name=item_name)
    return sorted((b.start_date, b.end_date) for b in rows if b.status in BLOCKING_STATUSES and not b.is_sample)


def all_blocked_ranges(booking_type: BookingType, names: list[str]) -> dict[str, list[list[str]]]:
    """Blocked ranges for several items at once, as ISO strings the booking page can hand to its calendar."""
    return {name: [[a.isoformat(), b.isoformat()] for a, b in blocked_ranges(booking_type, name)] for name in names}


def _check_dates_free(booking_type: BookingType, item_name: str, start: date, end: date) -> None:
    if any(first <= end and start <= last for first, last in blocked_ranges(booking_type, item_name)):
        raise FormError(f"{item_name} is already booked on some of those dates. "
                        "Choose different dates, or message us on Messenger.")


def _check_start_date(start: date) -> date:
    today = today_ph()
    if start < today:
        raise FormError("The start date cannot be in the past.")
    if start > today + timedelta(days=MAX_DAYS_AHEAD):
        raise FormError("Choose a start date within the next two years.")
    return today


def _find(items, item_id: str, what: str):
    chosen = next((entry for entry in items if entry.id == item_id), None)
    if chosen is None:
        raise FormError(f"Choose a {what} from the list.")
    if chosen.availability == "unavailable":
        raise FormError(f"{chosen.name} is currently unavailable. Choose another, or message us on Messenger.")
    return chosen


def build_car_booking(data: PublicCarBookingInput, email_verified: bool = False) -> Booking:
    """Runs every check for a website car rental request and returns the Pending booking without saving it.
    Status and payment are decided here, never by the customer."""
    car = _find(content.list_vehicles(), data.car, "car")
    today = _check_start_date(data.start_date)
    if car.seats and data.passengers > car.seats:
        raise FormError(f"The {car.name} seats up to {car.seats} passengers.")
    _check_dates_free("car", car.name, data.start_date, data.end_date)
    return Booking(
        id="", booking_type="car", customer_name=data.customer_name, customer_phone=data.customer_phone,
        customer_email=data.customer_email, item_name=car.name,
        start_date=data.start_date, end_date=data.end_date, start_time=data.start_time, end_time=data.end_time,
        details=data.details or "", passengers=data.passengers, pickup_location=data.pickup_location,
        dropoff_location=data.dropoff_location, destination=data.destination, driver_option=data.driver_option,
        requested_on=today, status="pending", payment_status="unpaid",
        history=[StatusChange(status="pending", changed_on=today)], email_verified=email_verified, is_sample=False,
    )


def create_car_booking(data: PublicCarBookingInput, email_verified: bool = False) -> Booking:
    """Saves a website car rental request as a Pending booking."""
    booking = build_car_booking(data, email_verified)
    return booking.model_copy(update={"id": repo.save(repo.BOOKINGS, booking)})


def build_tour_booking(data: PublicTourBookingInput, email_verified: bool = False) -> Booking:
    """Runs every check for a website tour request and returns the Pending booking without saving it."""
    tour = _find(content.list_tours(), data.tour, "tour package")
    today = _check_start_date(data.start_date)
    if tour.vehicle_seats and data.guests > tour.vehicle_seats:
        raise FormError(f"The vehicle for {tour.name} seats up to {tour.vehicle_seats} guests. "
                        "For a bigger group, message us on Messenger.")
    _check_dates_free("tour", tour.name, data.start_date, data.end_date)
    return Booking(
        id="", booking_type="tour", customer_name=data.customer_name, customer_phone=data.customer_phone,
        customer_email=data.customer_email, item_name=tour.name,
        start_date=data.start_date, end_date=data.end_date, details=data.details or "",
        passengers=data.guests, pickup_location=data.pickup_location or "",
        requested_on=today, status="pending", payment_status="unpaid",
        history=[StatusChange(status="pending", changed_on=today)], email_verified=email_verified, is_sample=False,
    )


def create_tour_booking(data: PublicTourBookingInput, email_verified: bool = False) -> Booking:
    """Saves a website tour request as a Pending booking."""
    booking = build_tour_booking(data, email_verified)
    return booking.model_copy(update={"id": repo.save(repo.BOOKINGS, booking)})


def change_status(booking: Booking, new_status: str) -> Booking:
    """Moves the booking to new_status, saves it and returns the updated booking."""
    if new_status not in NEXT_STATUSES[booking.status]:
        raise FormError("That status change is not allowed for this booking.")
    history = [*booking.history, StatusChange(status=new_status, changed_on=date.today())]
    updated = booking.model_copy(update={"status": new_status, "history": history})
    repo.save(repo.BOOKINGS, updated, booking.id)
    return updated


def change_payment(booking: Booking, new_status: str) -> None:
    if new_status not in PAYMENT_LABELS:
        raise FormError("Choose a payment status from the list.")
    repo.save(repo.BOOKINGS, booking.model_copy(update={"payment_status": new_status}), booking.id)


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
