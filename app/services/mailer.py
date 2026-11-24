"""Emails to customers: the booking verification code (Gmail REST API or Resend) and the "booking approved" notice (Resend).

Plain text + HTML. Sending is best effort for the approval notice: a failure is logged and never blocks the admin's
status change, so nothing there raises. The verification code reports success or failure to the caller, because
the customer cannot continue without it. Secrets are never logged.
"""

import base64
import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from email.message import EmailMessage

from app.core import config
from app.core.config import settings
from app.schemas.booking import Booking

log = logging.getLogger(__name__)
TIMEOUT_SECONDS = 10
RESEND_URL = "https://api.resend.com/emails"
GMAIL_TOKEN_URL = "https://oauth2.googleapis.com/token"
GMAIL_SEND_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"
OTP_MINUTES = 10  # keep in step with app.services.otp.TTL_SECONDS

# Brand colors (match tokens.css)
ROYAL = "#162660"
POWDER = "#D0E6FD"
BONE = "#F1E4D1"
ROYAL_MUTED = "rgba(22, 38, 96, 0.8)"
POWDER_MUTED = "#3a4a7a"


def _html_wrapper(preheader: str, body_html: str) -> str:
    """Full HTML email wrapper with brand styling."""
    return f"""<!DOCTYPE html>
<html>
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <meta name="color-scheme" content="light only">
    <title>{preheader}</title>
  </head>
  <body style="margin:0;padding:0;background:{POWDER};font-family:'Figtree','Segoe UI',system-ui,sans-serif;line-height:1.5;color:{ROYAL};">
    <div style="display:none;max-height:0;overflow:hidden;color:transparent;">{preheader}</div>
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{POWDER};padding:40px 20px;">
      <tr>
        <td align="center">
          <table role="presentation" width="100%" style="max-width:560px;background:#FFFFFF;border-radius:16px;overflow:hidden;box-shadow:0 4px 24px rgba(22,38,96,0.12);">
            <!-- Header bar -->
            <tr>
              <td style="background:{ROYAL};padding:24px 32px;">
                <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
                  <tr>
                    <td style="color:#FFFFFF;font-family:'Bricolage Grotesque','Segoe UI',system-ui,sans-serif;font-size:20px;font-weight:800;letter-spacing:-0.5px;">
                      BLESS Travel & Tours
                    </td>
                    <td align="right" style="color:rgba(255,255,255,0.7);font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:0.5px;">
                      Your Journey, Our Priority
                    </td>
                  </tr>
                </table>
              </td>
            </tr>
            <!-- Body -->
            <tr>
              <td style="padding:32px;">
                {body_html}
              </td>
            </tr>
            <!-- Footer -->
            <tr>
              <td style="background:{POWDER};padding:24px 32px;border-top:1px solid rgba(22,38,96,0.1);">
                <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="font-size:13px;color:{POWDER_MUTED};">
                  <tr>
                    <td style="padding-bottom:12px;font-weight:600;color:{ROYAL};">
                      BLESS Travel and Tours & Car Rental Services
                    </td>
                  </tr>
                  <tr>
                    <td style="padding-bottom:4px;">Iloilo City, Philippines</td>
                  </tr>
                  <tr>
                    <td style="padding-top:16px;border-top:1px solid rgba(22,38,96,0.1);">
                      Questions? Call <a href="tel:+639660534280" style="color:{ROYAL};text-decoration:none;">0966 053 4280</a>
                      or message us on <a href="{settings.messenger_url}" style="color:{ROYAL};text-decoration:none;">Messenger</a>
                    </td>
                  </tr>
                </table>
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
  </body>
</html>"""


def _button(label: str, url: str = "#", primary: bool = True) -> str:
    """CTA button HTML."""
    bg = BONE if primary else ROYAL
    color = ROYAL if primary else "#FFFFFF"
    border = f"1px solid {ROYAL}" if not primary else "none"
    return f"""<table role="presentation" cellpadding="0" cellspacing="0" style="margin:24px 0;">
  <tr>
    <td style="border-radius:999px;{border};" bgcolor="{bg}">
      <a href="{url}" style="display:inline-block;padding:14px 28px;font-family:'Figtree','Segoe UI',system-ui,sans-serif;font-size:15px;font-weight:700;color:{color};text-decoration:none;border-radius:999px;line-height:1;">
        {label}
      </a>
    </td>
  </tr>
</table>"""


def _card_row(label: str, value: str, icon: str = "") -> str:
    """Key-value row inside the detail card."""
    return f"""<tr>
  <td style="padding:10px 0;border-bottom:1px solid rgba(22,38,96,0.08);">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
      <tr>
        <td style="width:28px;vertical-align:top;color:{ROYAL_MUTED};">{icon}</td>
        <td style="vertical-align:top;">
          <div style="font-size:13px;color:{POWDER_MUTED};font-weight:500;">{label}</div>
          <div style="margin-top:2px;font-size:15px;font-weight:600;color:{ROYAL};">{value}</div>
        </td>
      </tr>
    </table>
  </td>
</tr>"""


def send_gmail(to: str, subject: str, text_body: str, html_body: str | None = None) -> bool:
    """Sends through Gmail REST API (OAuth2). True only if Gmail accepted the message."""
    cfg = config.integrations
    if not cfg.gmail_ready:
        return False
    message = EmailMessage()
    message["From"] = f"{settings.short_name} <{cfg.gmail_user}>"
    message["To"] = to
    message["Subject"] = subject
    message.set_content(text_body)
    if html_body:
        message.add_alternative(html_body, subtype="html")

    # 1) Obtain access token via refresh token
    token_data = {
        "client_id": cfg.gmail_client_id,
        "client_secret": cfg.gmail_client_secret,
        "refresh_token": cfg.gmail_refresh_token,
        "grant_type": "refresh_token",
    }
    token_request = urllib.request.Request(
        GMAIL_TOKEN_URL,
        data=urllib.parse.urlencode(token_data).encode(),
        headers={"Content-Type": "application/x-www-form-urlencoded", "User-Agent": "bless-booking/1.0"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(token_request, timeout=TIMEOUT_SECONDS) as token_response:
            token_json = json.loads(token_response.read())
            access_token = token_json.get("access_token")
            if not access_token:
                log.warning("Gmail token response missing access_token: %s", token_json)
                return False
    except urllib.error.HTTPError as exc:
        try:
            reason = exc.read().decode()
        except Exception:
            reason = ""
        log.warning("Gmail token request failed (HTTP %s): %s", exc.code, reason)
        return False
    except Exception as exc:
        log.warning("Gmail token request error (%s): %s", type(exc).__name__, exc)
        return False

    # 2) Send message via Gmail API
    raw_bytes = message.as_bytes()
    raw_b64 = base64.urlsafe_b64encode(raw_bytes).decode()
    send_payload = {"raw": raw_b64}
    send_request = urllib.request.Request(
        GMAIL_SEND_URL,
        data=json.dumps(send_payload).encode(),
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "User-Agent": "bless-booking/1.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(send_request, timeout=TIMEOUT_SECONDS) as send_response:
            return 200 <= send_response.status < 300
    except urllib.error.HTTPError as exc:
        try:
            reason = exc.read().decode()
        except Exception:
            reason = ""
        log.warning("Gmail send failed (HTTP %s): %s", exc.code, reason)
    except Exception as exc:
        log.warning("Gmail send error (%s): %s", type(exc).__name__, exc)
    return False


def send_resend(to: str, subject: str, text_body: str, html_body: str | None = None) -> bool:
    """Sends through the Resend API. True only if Resend accepted the message."""
    cfg = config.integrations
    if not cfg.resend_ready:
        return False
    payload = {"from": f"{settings.short_name} <{cfg.resend_from_email}>", "to": [to], "subject": subject, "text": text_body}
    if html_body:
        payload["html"] = html_body
    request = urllib.request.Request(
        RESEND_URL,
        data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {cfg.resend_api_key}", "Content-Type": "application/json", "User-Agent": "bless-booking/1.0"},
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
    text_body = (f"Your {settings.short_name} verification code is {code}.\n\n"
                 f"It expires in {OTP_MINUTES} minutes. If you did not request it, you can ignore this email.")
    html_body = _html_wrapper(
        f"Your {settings.short_name} verification code",
        f"""<div style="text-align:center;">
  <h1 style="margin:0 0 8px;font-size:28px;font-weight:800;color:{ROYAL};">Verify your email</h1>
  <p style="margin:0 0 24px;color:{POWDER_MUTED};">Hi there,</p>
  <p style="margin:0 0 16px;color:{ROYAL};">Your verification code is:</p>
  <div style="display:inline-block;background:{BONE};border-radius:12px;padding:20px 32px;margin-bottom:24px;letter-spacing:8px;font-family:'Bricolage Grotesque','Segoe UI',system-ui,sans-serif;font-size:32px;font-weight:800;color:{ROYAL};">
    {code}
  </div>
  <p style="margin:0;color:{POWDER_MUTED};font-size:14px;">This code expires in {OTP_MINUTES} minutes.<br>If you didn't request this, you can ignore this email.</p>
</div>"""
    )
    if mode == "gmail":
        return send_gmail(to, subject, text_body, html_body)
    if mode == "resend":
        return send_resend(to, subject, text_body, html_body)
    return False


def _when(day) -> str:
    return f"{day:%b} {day.day}, {day.year}"


def _time_of_day(t) -> str:
    if t is None:
        return ""
    return f" {t:%I:%M %p}".lstrip("0")


def _driver_message(booking: Booking) -> str:
    """Returns the appropriate instruction message based on driver option."""
    is_self = booking.driver_option == "self_drive"
    has_pickup = bool(booking.pickup_location and booking.pickup_location.strip())
    if is_self:
        if has_pickup:
            return ("Please proceed to the pick-up location at your scheduled time. "
                    "Bring your driver's license and valid ID for verification.")
        return ("Please visit our office at your scheduled time to collect the vehicle. "
                "Bring your driver's license and valid ID.")
    if has_pickup:
        return ("Your driver will contact you 30 minutes before pick-up. "
                "Please have your valid ID ready.")
    return "Your driver will contact you to confirm pick-up details. Please have your valid ID ready."


def booking_approved(booking: Booking) -> tuple[str, str, str]:
    """Subject, plain text body, and HTML body for the approval email."""
    is_car = booking.booking_type == "car"
    ref = booking.reference

    # Plain text
    lines = [f"Hello {booking.customer_name},", "",
             f"Thank you for choosing {settings.business_name}!",
             f"We appreciate your trust in us for your journey.", "",
             "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
             f"Reference: {ref}",
             "Status: APPROVED",
             "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"]
    if is_car:
        lines += [f"Car: {booking.item_name}",
                  f"Pick-up: {_when(booking.start_date)}{_time_of_day(booking.start_time)}",
                  f"Return: {_when(booking.end_date)}{_time_of_day(booking.end_time)}"]
        if booking.pickup_location:
            lines.append(f"Pick-up location: {booking.pickup_location}")
        if booking.dropoff_location:
            lines.append(f"Drop-off location: {booking.dropoff_location}")
        if booking.passengers:
            lines.append(f"Passengers: {booking.passengers}")
        if booking.driver_option:
            lines.append(f"Driver: {'With driver' if booking.driver_option == 'with_driver' else 'Self-drive'}")
    else:
        when = _when(booking.start_date)
        if booking.end_date != booking.start_date:
            when += f" to {_when(booking.end_date)}"
        lines += [f"Tour: {booking.item_name}",
                  f"Date: {when}"]
        if booking.pickup_location:
            lines.append(f"Meet-up: {booking.pickup_location}")
        if booking.passengers:
            lines.append(f"Guests: {booking.passengers}")
    lines += ["━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", ""]
    if is_car:
        lines.append(_driver_message(booking))
    else:
        lines.append("Your tour coordinator will message you on Messenger the day before with final details.")
    lines += ["",
              f"Questions? Call {settings.phone_display} or message us on Messenger: {settings.messenger_url}", "",
              settings.business_name]
    text_body = "\n".join(lines)

    # HTML body
    if is_car:
        detail_rows = [
            _card_row("Reference", ref, "📋"),
            _card_row("Status", "APPROVED", "✓"),
            _card_row("Car", booking.item_name, "🚗"),
            _card_row("Pick-up", f"{_when(booking.start_date)}{_time_of_day(booking.start_time)}", "📅"),
            _card_row("Return", f"{_when(booking.end_date)}{_time_of_day(booking.end_time)}", "📅"),
        ]
        if booking.pickup_location:
            detail_rows.append(_card_row("Pick-up location", booking.pickup_location, "📍"))
        if booking.dropoff_location:
            detail_rows.append(_card_row("Drop-off location", booking.dropoff_location, "📍"))
        if booking.passengers:
            detail_rows.append(_card_row("Passengers", str(booking.passengers), "👥"))
        if booking.driver_option:
            detail_rows.append(_card_row("Driver", "With driver" if booking.driver_option == "with_driver" else "Self-drive", "👤"))
    else:
        when = _when(booking.start_date)
        if booking.end_date != booking.start_date:
            when += f" to {_when(booking.end_date)}"
        detail_rows = [
            _card_row("Reference", ref, "📋"),
            _card_row("Status", "APPROVED", "✓"),
            _card_row("Tour", booking.item_name, "🏝️"),
            _card_row("Date", when, "📅"),
        ]
        if booking.pickup_location:
            detail_rows.append(_card_row("Meet-up", booking.pickup_location, "📍"))
        if booking.passengers:
            detail_rows.append(_card_row("Guests", str(booking.passengers), "👥"))

    detail_html = "\n".join(detail_rows)
    dynamic_msg = _driver_message(booking) if is_car else "Your tour coordinator will message you on Messenger the day before with final details."

    html_body = _html_wrapper(
        f"Your {settings.short_name} {'car rental' if is_car else 'tour'} {ref} is approved",
        f"""<div>
  <h1 style="margin:0 0 8px;font-size:24px;font-weight:800;color:{ROYAL};">{'Your car rental is approved' if is_car else 'Your tour is approved'} ✓</h1>
  <p style="margin:0 0 8px;color:{ROYAL};">Hi {booking.customer_name},</p>
  <p style="margin:0 0 24px;color:{POWDER_MUTED};">
    Thank you for choosing {settings.business_name}!<br>
    We appreciate your trust in us for your journey.
  </p>
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{POWDER};border-radius:12px;overflow:hidden;">
    {detail_html}
  </table>
  <p style="margin:24px 0 0;padding:16px;background:{BONE};border-radius:12px;font-size:14px;color:{ROYAL};font-weight:500;line-height:1.6;">
    {dynamic_msg}
  </p>
</div>"""
    )

    subject = f"Your {settings.short_name} {'car rental' if is_car else 'tour'} {ref} is approved"
    return subject, text_body, html_body


def notify_booking_approved(booking: Booking) -> None:
    """Emails the customer when the admin approves their booking. Uses APPROVAL_EMAIL_MODE (falls back to OTP_DELIVERY). Never raises."""
    if not booking.customer_email:
        return
    try:
        subject, text_body, html_body = booking_approved(booking)
        mode = config.integrations.approval_email_mode
        sent = False
        if mode == "gmail":
            sent = send_gmail(booking.customer_email, subject, text_body, html_body)
        elif mode == "resend":
            sent = send_resend(booking.customer_email, subject, text_body, html_body)
        elif mode == "simulated":
            sent = send_resend(booking.customer_email, subject, text_body, html_body)  # tests mock this
        if not sent:
            log.warning("Approval email for %s was not sent (mode=%s)", booking.reference, mode)
    except Exception:
        log.exception("Approval email failed")