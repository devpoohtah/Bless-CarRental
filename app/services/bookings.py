"""Data for booking management and the booking calendar.

Bookings are read from and written to Firestore when it is connected. Without credentials
this returns placeholder bookings whose dates are relative to today, so the calendar and
tests always have something to show.
"""

import calendar
import logging
import time
from datetime import date, datetime, timedelta

from app.db import firebase
from app.db import repositories as repo
from app.schemas.booking import AdditionalPayment, Booking, BookingStatus, BookingType, StatusChange
from app.core.clock import PHILIPPINES, today_ph
from app.schemas.forms import BookingInput, PublicCarBookingInput, PublicTourBookingInput
from app.services import content, licenses, pricing
from app.services.errors import FormError

log = logging.getLogger(__name__)

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

# License photo retention. A rejected or cancelled booking never went ahead, so its photo is deleted at once.
# A completed booking keeps it for a short while in case damage is found afterwards, then it is deleted.
# A booking nobody ever closes loses it this long after its end date, so no photo stays forever.
LICENSE_DELETED_AT_ONCE_BY: tuple[BookingStatus, ...] = ("rejected", "cancelled")
LICENSE_KEPT_DAYS_AFTER_COMPLETION = 15
LICENSE_KEPT_DAYS_AFTER_END = 30

# The calendar shows bookings that are still scheduled or under way.
CALENDAR_STATUSES: tuple[BookingStatus, ...] = ("pending", "approved", "ongoing")


def _sample_bookings(today: date) -> list[Booking]:
    def d(days: int) -> date:
        return today + timedelta(days=days)

    def dt(days: int) -> datetime:
        return datetime.combine(d(days), datetime.min.time()).replace(tzinfo=PHILIPPINES)

    def booking(n, kind, item, start, end, status, payment, requested, path,
                total_php: int | None = None, downpayment_amount: int = 0,
                downpayment_type: str | None = None, amount_paid: int = 0, payment_type: str | None = None):
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
            requested_at=dt(requested),
            status=status,
            payment_status=payment,
            downpayment_amount=downpayment_amount,
            downpayment_type=downpayment_type,
            amount_paid=amount_paid,
            payment_type=payment_type,
            total_php=total_php,
            history=[StatusChange(status=s, changed_on=d(day)) for s, day in path],
        )

    # Sample totals (in PHP) for bookings that have pricing
    CAR_TOTAL = 8000
    TOUR_TOTAL = 12000

    return [
        # No downpayment, no payments
        booking(1, "car", "Compact Sedan", 3, 5, "pending", "unpaid", -1, [("pending", -1)],
                total_php=CAR_TOTAL),
        booking(2, "tour", "Island Day Tour", 10, 10, "pending", "unpaid", 0, [("pending", 0)],
                total_php=TOUR_TOTAL),
        # Downpayment only (partial)
        booking(3, "car", "Family SUV", 1, 4, "approved", "partial", -4,
                [("pending", -4), ("approved", -3)], total_php=CAR_TOTAL,
                downpayment_amount=500, downpayment_type="gcash"),
        # Downpayment + full remaining (paid)
        booking(4, "tour", "Beach Getaway Package", 7, 9, "approved", "paid", -6,
                [("pending", -6), ("approved", -5)], total_php=TOUR_TOTAL,
                downpayment_amount=500, downpayment_type="bank_transfer", amount_paid=TOUR_TOTAL - 500, payment_type="cash"),
        # Downpayment + full remaining (paid)
        booking(5, "car", "Family SUV", -2, 2, "ongoing", "paid", -9,
                [("pending", -9), ("approved", -8), ("ongoing", -2)], total_php=CAR_TOTAL,
                downpayment_amount=500, downpayment_type="gcash", amount_paid=CAR_TOTAL - 500, payment_type="gcash"),
        # Downpayment + full remaining (paid)
        booking(6, "tour", "Heritage and Church Tour", -12, -12, "completed", "paid", -20,
                [("pending", -20), ("approved", -19), ("ongoing", -12), ("completed", -12)],
                total_php=TOUR_TOTAL, downpayment_amount=500, downpayment_type="bank_transfer",
                amount_paid=TOUR_TOTAL - 500, payment_type="bank_transfer"),
        # Rejected - no payments
        booking(7, "car", "Compact Sedan", 5, 6, "rejected", "unpaid", -3,
                [("pending", -3), ("rejected", -2)], total_php=CAR_TOTAL),
        # Cancelled - had downpayment but cancelled
        booking(8, "tour", "Island Day Tour", 14, 14, "cancelled", "unpaid", -7,
                [("pending", -7), ("approved", -6), ("cancelled", -1)], total_php=TOUR_TOTAL,
                downpayment_amount=500, downpayment_type="gcash"),
        # Approved but no downpayment yet
        booking(9, "car", "Compact Sedan", 2, 3, "approved", "unpaid", -2,
                [("pending", -2), ("approved", -1)], total_php=CAR_TOTAL),
    ]


def list_bookings(booking_type: BookingType | None = None, search: str | None = None) -> list[Booking]:
    rows = repo.list_all(repo.BOOKINGS, Booking) if firebase.is_configured() else _sample_bookings(date.today())
    def sort_key(b: Booking):
        if b.requested_at:
            dt = b.requested_at
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=PHILIPPINES)
            return dt
        return datetime.combine(b.requested_on, datetime.max.time()).replace(tzinfo=PHILIPPINES)
    rows = sorted(rows, key=lambda b: (sort_key(b), b.start_date), reverse=True)
    if booking_type is not None:
        rows = [b for b in rows if b.booking_type == booking_type]
    if search:
        s = search.strip().lower()
        rows = [b for b in rows if s in b.reference.lower() or s in b.customer_name.lower()]
    return rows


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
    _check_dates_free(data.booking_type, data.item_name, data.start_date, data.end_date)
    now_ph = datetime.now(PHILIPPINES)
    today = now_ph.date()
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
        requested_at=now_ph,
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
    return chosen


def build_car_booking(data: PublicCarBookingInput, email_verified: bool = False) -> Booking:
    """Runs every check for a website car rental request and returns the Pending booking without saving it.
    Status and payment are decided here, never by the customer. All car rentals are self-drive."""
    car = _find(content.list_vehicles(), data.car, "car")
    today = _check_start_date(data.start_date)
    now_ph = datetime.now(PHILIPPINES)
    if car.seats and data.passengers > car.seats:
        raise FormError(f"The {car.name} seats up to {car.seats} passengers.")
    _check_dates_free("car", car.name, data.start_date, data.end_date)
    # Priced here, on the server, with the rates as they are now; the booking keeps that figure and its lines.
    price = pricing.quote(car, data.start_date, data.start_time, data.end_date, data.end_time)
    return Booking(
        id="", booking_type="car", customer_name=data.customer_name, customer_phone=data.customer_phone,
        customer_email=data.customer_email, item_name=car.name,
        start_date=data.start_date, end_date=data.end_date, start_time=data.start_time, end_time=data.end_time,
        details=data.details or "", passengers=data.passengers, pickup_location=data.pickup_location,
        dropoff_location=data.dropoff_location, destination=data.destination, driver_option="self_drive",
        requested_on=today, requested_at=now_ph, status="pending", payment_status="unpaid",
        history=[StatusChange(status="pending", changed_on=today)], email_verified=email_verified, is_sample=False,
        total_php=price.total_php if price else None, price_lines=price.lines if price else [],
    )


def create_car_booking(data: PublicCarBookingInput, email_verified: bool = False,
                       license_front: bytes | None = None, license_back: bytes | None = None) -> Booking:
    """Saves a website car rental request as a Pending booking, with the license photos if there are any."""
    booking = build_car_booking(data, email_verified)
    if license_front is None:
        return booking.model_copy(update={"id": repo.save(repo.BOOKINGS, booking)})
    # The photos are keyed by the booking id, so pick the id first. Photos go in first and are removed again
    # if the booking cannot be saved, so photos never stay behind without a booking.
    booking_id = repo.new_id(repo.BOOKINGS)
    licenses.save(booking_id, license_front, license_back)
    booking = booking.model_copy(update={
        "license_front_on_file": True,
        "license_back_on_file": license_back is not None,
        "license_delete_on": booking.end_date + timedelta(days=LICENSE_KEPT_DAYS_AFTER_END)})
    try:
        repo.save(repo.BOOKINGS, booking, booking_id)
    except Exception:
        try:
            licenses.delete(booking_id)
        except Exception:
            log.exception("Could not remove the license photos of booking %s after a failed save", booking_id)
        raise
    return booking.model_copy(update={"id": booking_id})


def build_tour_booking(data: PublicTourBookingInput, email_verified: bool = False) -> Booking:
    """Runs every check for a website tour request and returns the Pending booking without saving it."""
    tour = _find(content.list_tours(), data.tour, "tour package")
    today = _check_start_date(data.start_date)
    now_ph = datetime.now(PHILIPPINES)
    if tour.vehicle_seats and data.guests > tour.vehicle_seats:
        raise FormError(f"The vehicle for {tour.name} seats up to {tour.vehicle_seats} guests. "
                        "For a bigger group, message us on Messenger.")
    _check_dates_free("tour", tour.name, data.start_date, data.end_date)
    return Booking(
        id="", booking_type="tour", customer_name=data.customer_name, customer_phone=data.customer_phone,
        customer_email=data.customer_email, item_name=tour.name,
        start_date=data.start_date, end_date=data.end_date, details=data.details or "",
        passengers=data.guests, pickup_location=data.pickup_location or "",
        requested_on=today, requested_at=now_ph, status="pending", payment_status="unpaid",
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
    if new_status in BLOCKING_STATUSES and booking.status not in BLOCKING_STATUSES:
        _check_dates_free(booking.booking_type, booking.item_name, booking.start_date, booking.end_date)
    history = [*booking.history, StatusChange(status=new_status, changed_on=date.today())]
    changes: dict = {"status": new_status, "history": history}
    if booking.license_on_file and new_status in LICENSE_DELETED_AT_ONCE_BY:
        _remove_license_photo(booking.id)  # first: if this fails the status does not change, so nothing is left behind
        changes |= {"license_front_on_file": False, "license_back_on_file": False, "license_delete_on": None}
    elif booking.license_on_file and new_status == "completed":
        soon = today_ph() + timedelta(days=LICENSE_KEPT_DAYS_AFTER_COMPLETION)
        changes["license_delete_on"] = min(soon, booking.license_delete_on or soon)
    updated = booking.model_copy(update=changes)
    repo.save(repo.BOOKINGS, updated, booking.id)
    return updated


def change_payment(booking: Booking, new_status: str, payment_type: str | None = None) -> None:
    if new_status not in PAYMENT_LABELS:
        raise FormError("Choose a payment status from the list.")
    update = {"payment_status": new_status}
    if payment_type:
        update["payment_type"] = payment_type
    repo.save(repo.BOOKINGS, booking.model_copy(update=update), booking.id)


def record_downpayment(booking: Booking, amount: int, payment_type: str) -> Booking:
    """Record the downpayment for a booking (GCash or Bank Transfer only)."""
    if amount < 0:
        raise FormError("Downpayment amount cannot be negative.")
    if payment_type not in ("gcash", "bank_transfer"):
        raise FormError("Downpayment must be GCash or Bank Transfer.")
    if booking.total_php is not None and amount > booking.total_php:
        raise FormError(f"Downpayment exceeds total amount (₱{booking.total_php:,}).")

    update = {"downpayment_amount": amount, "downpayment_type": payment_type}
    # Auto-update payment_status if this is the first payment
    if booking.payment_status == "unpaid":
        update["payment_status"] = "partial"

    updated = booking.model_copy(update=update)
    repo.save(repo.BOOKINGS, updated, booking.id)
    return updated


def record_remaining_payment(booking: Booking, amount: int, payment_type: str | None = None) -> Booking:
    """Record a payment toward the remaining balance (GCash, Bank Transfer, or Cash)."""
    if amount < 0:
        raise FormError("Payment amount cannot be negative.")
    if payment_type and payment_type not in ("gcash", "bank_transfer", "cash"):
        raise FormError("Payment type must be GCash, Bank Transfer, or Cash.")

    new_amount_paid = booking.amount_paid + amount
    if booking.total_php is not None and booking.total_paid + amount > booking.total_php:
        raise FormError(f"Total payments exceed total amount (₱{booking.total_php:,}).")

    # Determine new payment status based on total paid (downpayment + remaining)
    total_paid = booking.downpayment_amount + new_amount_paid
    if booking.total_php is None:
        new_status = "partial"
    elif total_paid >= booking.total_php:
        new_status = "paid"
    elif total_paid > 0:
        new_status = "partial"
    else:
        new_status = "unpaid"

    update = {"amount_paid": new_amount_paid, "payment_status": new_status}
    if payment_type:
        update["payment_type"] = payment_type

    updated = booking.model_copy(update=update)
    repo.save(repo.BOOKINGS, updated, booking.id)
    return updated


def record_additional_payment(booking: Booking, amount: int, payment_type: str, description: str) -> Booking:
    """Record an additional payment (e.g., delivery fee, hotel pickup fee)."""
    if amount < 1:
        raise FormError("Additional payment amount must be at least ₱1.")
    if payment_type not in ("gcash", "bank_transfer", "cash"):
        raise FormError("Payment type must be GCash, Bank Transfer, or Cash.")
    if not description or not description.strip():
        raise FormError("Description is required.")

    additional = AdditionalPayment(
        amount_php=amount,
        payment_type=payment_type,
        description=description.strip(),
        date=date.today(),
    )
    updated_payments = [*booking.additional_payments, additional]
    updated = booking.model_copy(update={"additional_payments": updated_payments})
    repo.save(repo.BOOKINGS, updated, booking.id)
    return updated


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


def _remove_license_photo(booking_id: str) -> None:
    try:
        licenses.delete(booking_id)
    except Exception:
        log.exception("Could not delete the license photo of booking %s", booking_id)
        raise FormError("The license photo could not be deleted. Nothing was changed. Try again.") from None


def delete_license(booking: Booking) -> Booking:
    """Deletes the photos now, for example because the customer asked for it."""
    if not booking.license_on_file:
        raise FormError("There is no license photo to delete.")
    _remove_license_photo(booking.id)
    updated = booking.model_copy(update={"license_front_on_file": False, "license_back_on_file": False, "license_delete_on": None})
    repo.save(repo.BOOKINGS, updated, booking.id)
    return updated


_PURGE_EVERY = timedelta(hours=1)
_last_purge = None


def purge_expired_licenses(today: date | None = None) -> int:
    """Deletes every license photo whose day has come. Only bookings that hold a photo are read, so this is
    cheap. Returns how many were deleted. A failure on one photo is logged and the rest carry on."""
    today = today or today_ph()
    deleted = 0
    for booking in repo.list_where(repo.BOOKINGS, Booking, license_front_on_file=True):
        due = booking.license_delete_on or booking.end_date + timedelta(days=LICENSE_KEPT_DAYS_AFTER_END)
        if due > today:
            continue
        try:
            delete_license(booking)
            deleted += 1
        except Exception:
            log.exception("Could not purge the license photos of booking %s", booking.id)
    return deleted


def purge_expired_licenses_if_due() -> None:
    """Runs the purge at most once an hour. Called when the app starts and when an admin opens the bookings,
    so no scheduler is needed. Never raises: it must not break the page it runs on."""
    global _last_purge
    stamp = time.monotonic()
    if _last_purge is not None and stamp - _last_purge < _PURGE_EVERY.total_seconds():
        return
    _last_purge = stamp
    try:
        if firebase.is_configured():
            purge_expired_licenses()
    except Exception:
        log.exception("License photo purge failed")