"""Emails to customers: the booking verification code (Gmail SMTP or Resend) and the "booking approved" notice (Resend).

Plain text only. Sending is best effort for the approval notice: a failure is logged and never blocks the admin's
status change, so nothing there raises. The verification code reports success or failure to the caller, because
the customer cannot continue without it. Secrets are never logged.
"""

import json
import logging
import smtplib
import urllib.error
import urllib.request
from email.message import EmailMessage

from app.core import config
from app.core.config import settings
from app.schemas.booking import Booking

log = logging.getLogger(__name__)
TIMEOUT_SECONDS = 10
RESEND_URL = "https://api.resend.com/emails"
OTP_MINUTES = 10  # keep in step with app.services.otp.TTL_SECONDS


def send_gmail(to: str, subject: str, body: str) -> bool:
    """Sends through Gmail SMTP with an app password. True only if Gmail accepted the message."""
    cfg = config.integrations
    if not cfg.gmail_ready:
        return False
    message = EmailMessage()
    message["From"] = f"{settings.short_name} <{cfg.gmail_user}>"
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=TIMEOUT_SECONDS) as smtp:
            smtp.login(cfg.gmail_user, cfg.gmail_app_password)
            smtp.send_message(message)
        return True
    except Exception as exc:  # the message may quote the address or credentials: log the type only
        log.warning("Gmail could not send an email (%s)", type(exc).__name__)
        return False


def send_resend(to: str, subject: str, body: str) -> bool:
    """Sends through the Resend API. True only if Resend accepted the message."""
    cfg = config.integrations
    if not cfg.resend_ready:
        return False
    request = urllib.request.Request(
        RESEND_URL,
        data=json.dumps({"from": f"{settings.short_name} <{cfg.resend_from_email}>", "to": [to],
                         "subject": subject, "text": body}).encode(),
        # Resend sits behind Cloudflare, which rejects the default Python user agent.
        headers={"Authorization": f"Bearer {cfg.resend_api_key}", "Content-Type": "application/json",
                 "User-Agent": "bless-booking/1.0"},
        method="POST")
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            return 200 <= response.status < 300
    except urllib.error.HTTPError as exc:
        try:
            reason = json.loads(exc.read()).get("message", "")
        except Exception:
            reason = ""
        log.warning("Resend refused an email (HTTP %s) %s", exc.code, reason)
    except Exception as exc:
        log.warning("Could not reach Resend (%s)", type(exc).__name__)
    return False


def send_otp_email(to: str, code: str) -> bool:
    """Delivers the verification code the way OTP_DELIVERY says. False if it could not be sent."""
    mode = config.integrations.otp_mode
    subject = f"Your {settings.short_name} verification code: {code}"
    body = (f"Your {settings.short_name} verification code is {code}.\n\n"
            f"It expires in {OTP_MINUTES} minutes. If you did not request it, you can ignore this email.")
    if mode == "gmail":
        return send_gmail(to, subject, body)
    if mode == "resend":
        return send_resend(to, subject, body)
    return False


def _when(day) -> str:
    return f"{day:%b} {day.day}, {day.year}"


def booking_approved_text(booking: Booking) -> tuple[str, str]:
    """Subject and body of the approval email. Only stored booking data and the public BLESS contact details."""
    is_car = booking.booking_type == "car"
    lines = [f"Hello {booking.customer_name},", "",
             f"Your {'car rental' if is_car else 'tour'} request {booking.reference} has been approved by "
             f"{settings.business_name}.", "",
             f"{'Car' if is_car else 'Tour package'}: {booking.item_name}"]
    if is_car:
        lines += [f"Pick-up: {_when(booking.start_date)}", f"Return: {_when(booking.end_date)}"]
    else:
        when = _when(booking.start_date)
        if booking.end_date != booking.start_date:
            when += f" to {_when(booking.end_date)}"
        lines.append(f"Date: {when}")
    if booking.pickup_location:
        lines.append(f"{'Pick-up location' if is_car else 'Meet-up'}: {booking.pickup_location}")
    lines += ["", f"Questions? Call {settings.phone_display} or message us on Messenger: {settings.messenger_url}", "",
              settings.business_name]
    return f"Your {settings.short_name} booking {booking.reference} is approved", "\n".join(lines)


def notify_booking_approved(booking: Booking) -> None:
    """Emails the customer when the admin approves their booking. Skipped without an address or Resend settings. Never raises."""
    if not booking.customer_email:
        return
    try:
        subject, body = booking_approved_text(booking)
        if not send_resend(booking.customer_email, subject, body):
            log.warning("Approval email for %s was not sent", booking.reference)
    except Exception:
        log.exception("Approval email failed")
