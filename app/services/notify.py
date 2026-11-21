"""Alerts to the BLESS Telegram group when a booking request comes in.

Plain text only: customer-typed words are never interpreted as formatting. Sending is best
effort. A Telegram outage, a wrong chat ID or missing settings must never stop a booking
request from being saved, so nothing here raises, and the bot token is never logged.
"""

import json
import logging
import urllib.error
import urllib.request
from datetime import datetime

from app.core import config
from app.core.clock import PHILIPPINES, now_ph
from app.core.templating import date_time
from app.schemas.booking import Booking
from app.services import mailer, push

log = logging.getLogger(__name__)
TIMEOUT_SECONDS = 5
NOTES_LIMIT = 200


def _when(day) -> str:
    return f"{day:%b} {day.day}, {day.year}"


def booking_alert_text(booking: Booking, admin_base_url: str = "", sent_at: datetime | None = None) -> str:
    """The message for a new website request: when it came in, who, what, when, and where to open it.
    sent_at is always shown in Philippine time, whatever time zone the server runs in."""
    is_car = booking.booking_type == "car"
    sent = (sent_at or now_ph()).astimezone(PHILIPPINES)
    lines = [f"New {'car rental' if is_car else 'tour'} request {booking.reference}",
             f"Sent: {date_time(sent.date(), sent.time())}", "",
             f"Customer: {booking.customer_name}", f"Phone: {booking.customer_phone}",
             f"{'Car' if is_car else 'Tour package'}: {booking.item_name}"]
    if is_car:
        # The times are shown when the customer gave them, so nobody has to open the booking to see them.
        lines.append(f"Pick-up: {date_time(booking.start_date, booking.start_time)}")
        lines.append(f"Return: {date_time(booking.end_date, booking.end_time)}")
        if booking.total_php is not None:
            lines.append(f"Estimated total: ₱{booking.total_php:,}")
        extras = [f"{booking.passengers} passengers"] if booking.passengers else []
        if booking.driver_option:
            extras.append("with a driver" if booking.driver_option == "with_driver" else "self-drive")
        if extras:
            lines.append("Trip: " + ", ".join(extras))
    else:
        when = _when(booking.start_date)
        if booking.end_date != booking.start_date:
            when += f" to {_when(booking.end_date)}"
        lines.append(f"Date: {when}")
        if booking.passengers:
            lines.append(f"Guests: {booking.passengers}")
    if booking.pickup_location:
        lines.append(f"Meet-up: {booking.pickup_location}")
    if booking.details:
        lines.append("Notes: " + booking.details[:NOTES_LIMIT] + ("..." if len(booking.details) > NOTES_LIMIT else ""))
    if admin_base_url:
        lines += ["", f"Open: {admin_base_url}/admin/bookings/{booking.id}"]
    lines += ["", 'Reply "Calling now" here before you call, so the customer is not called twice.']
    return "\n".join(lines)


def send_telegram(text: str) -> bool:
    """Posts text to the configured group. True only if Telegram accepted it."""
    settings = config.integrations
    if not settings.telegram_ready:
        return False
    request = urllib.request.Request(
        f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage",
        data=json.dumps({"chat_id": settings.telegram_chat_id, "text": text, "disable_web_page_preview": True}).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            return 200 <= response.status < 300
    except urllib.error.HTTPError as exc:
        # Telegram explains itself in the body, for example "chat not found". The URL holds the token: not logged.
        try:
            reason = json.loads(exc.read()).get("description", "")
        except Exception:
            reason = ""
        log.warning("Telegram refused the booking alert (HTTP %s) %s", exc.code, reason)
    except Exception as exc:
        log.warning("Could not reach Telegram for a booking alert (%s)", type(exc).__name__)
    return False


def _booking_confirmed_text(booking: Booking) -> tuple[str, str]:
    """Subject and body of the booking confirmation email."""
    is_car = booking.booking_type == "car"
    lines = [f"Hello {booking.customer_name},", "",
             f"Thank you for your {'car rental' if is_car else 'tour'} request {booking.reference}.", "",
             f"We've received your request for {booking.item_name}.", ""]
    if is_car:
        lines += [f"Pick-up: {_when(booking.start_date)}", f"Return: {_when(booking.end_date)}"]
    else:
        when = _when(booking.start_date)
        if booking.end_date != booking.start_date:
            when += f" to {_when(booking.end_date)}"
        lines.append(f"Date: {when}")
    if booking.pickup_location:
        lines.append(f"{'Pick-up location' if is_car else 'Meet-up'}: {booking.pickup_location}")
    lines += ["", "We'll review your request and confirm by email shortly.", "",
              f"Questions? Call {config.settings.phone_display} or message us on Messenger: {config.settings.messenger_url}", "",
              config.settings.business_name]
    return f"Your {config.settings.short_name} booking request {booking.reference} received", "\n".join(lines)


def notify_booking_confirmed(booking: Booking) -> None:
    """Emails the customer when their booking request is saved (after email verification). Never raises."""
    if not booking.customer_email:
        return
    try:
        subject, body = _booking_confirmed_text(booking)
        mode = config.integrations.approval_email_mode
        sent = False
        if mode == "gmail":
            sent = mailer.send_gmail(booking.customer_email, subject, body)
        elif mode == "resend":
            sent = mailer.send_resend(booking.customer_email, subject, body)
        elif mode == "simulated":
            sent = mailer.send_resend(booking.customer_email, subject, body)
        if not sent:
            log.warning("Confirmation email for %s was not sent (mode=%s)", booking.reference, mode)
    except Exception:
        log.exception("Confirmation email failed")


def notify_new_booking(booking: Booking) -> None:
    """Tells the Telegram group and the admins' browsers about a new website request. Never raises,
    and one channel failing never stops the other."""
    try:
        send_telegram(booking_alert_text(booking, config.integrations.admin_base_url))
    except Exception:
        log.exception("Booking alert failed")
    try:
        push.send_to_admins(
            title=f"New {'car rental' if booking.booking_type == 'car' else 'tour'} request",
            # No phone number: notifications show on lock screens.
            body=f"{booking.customer_name} - {booking.item_name}, {_when(booking.start_date)}",
            url=f"/admin/bookings/{booking.id}", tag=booking.id)
    except Exception:
        log.exception("Booking push failed")
