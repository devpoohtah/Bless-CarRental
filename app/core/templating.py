"""Shared Jinja2 environment so every route renders with the same helpers."""

from datetime import date, time
from pathlib import Path

from fastapi.templating import Jinja2Templates

from app.core import config
from app.core.clock import now_ph
from app.core.config import STATIC_DIR, TEMPLATES_DIR, settings
from app.core.csrf import csrf_token
from app.core.icons import icon
from app.db import firebase
from app.services import pricing

def _csp_nonce(request) -> dict:
    """Makes {{ csp_nonce }} available in every template. The value is set per request in security.py."""
    return {"csp_nonce": getattr(request.state, "csp_nonce", "")}


templates = Jinja2Templates(directory=str(TEMPLATES_DIR), context_processors=[_csp_nonce])
templates.env.trim_blocks = True
templates.env.lstrip_blocks = True


def static_url(path: str) -> str:
    """URL for a file under app/static, with a modified-time query so edits bypass browser caches.

    Images uploaded to Cloudinary are full https URLs and are returned unchanged.
    """
    if path.startswith("https://"):
        return path
    url = f"/static/{path}"
    try:
        return f"{url}?v={int((Path(STATIC_DIR) / path).stat().st_mtime)}"
    except OSError:
        return url


def absolute_url(request, path: str = "/") -> str:
    """Full https URL for a path. Social sites and search engines need absolute links."""
    base = settings.public_base_url or str(request.base_url).rstrip("/")
    return f"{base}{path}"


def php(amount: int | None, fallback: str = "Contact for rates") -> str:
    """Format a peso amount, or return a neutral fallback when no price is set."""
    return f"PHP {amount:,}" if amount is not None else fallback


# firebase_config is the PUBLIC web SDK config (never secrets); only the login page reads it.
templates.env.globals.update(
    icon=icon, static_url=static_url, absolute_url=absolute_url, site=settings, firebase_config=config.integrations.firebase_web_config,
    database_ready=lambda: firebase.is_configured(), push_config=lambda: config.integrations.push_web_config,
    csrf_token=csrf_token,
    car_pricing=lambda: pricing.load_rules(),  # the saved extra-hour rates, for pages that show them
    turnstile_site_key=config.integrations.turnstile_site_key if config.integrations.turnstile_ready else "",
)

# Short confirmations shown after a redirect (?notice=key). Only these keys are ever shown.
NOTICES = {
    "saved": "Saved.",
    "deleted": "Deleted.",
    "created": "Booking added.",
    "status": "Booking status updated.",
    "payment": "Payment status updated.",
    "license": "License photo deleted.",
}


def notice_for(request) -> str | None:
    return NOTICES.get(request.query_params.get("notice", ""))

def short_date(day: date) -> str:
    return f"{day:%b} {day.day}"


def long_date(day: date) -> str:
    return f"{day:%a}, {day:%b} {day.day}, {day.year}"


def date_range(start: date, end: date) -> str:
    """'Nov 10, 2026' for a single day, 'Nov 3 – Nov 5, 2026' for a range."""
    if start == end:
        return f"{short_date(start)}, {start.year}"
    return f"{short_date(start)} \u2013 {short_date(end)}, {end.year}"


def date_time(day: date, at: time | None = None) -> str:
    """'Nov 18, 2026 - 9:00 AM', or just 'Nov 18, 2026' when there is no time."""
    text = f"{short_date(day)}, {day.year}"
    return f"{text} - {clock(at)}" if at else text


def now_label() -> str:
    """The current Philippine date and time, written the same way. The sidebar clock keeps it fresh."""
    now = now_ph()
    return date_time(now.date(), now.time())


def clock(value: time) -> str:
    """'9:30 AM'."""
    return f"{value:%I:%M %p}".lstrip("0")


templates.env.filters.update(php=php, short_date=short_date, long_date=long_date, date_range=date_range, clock=clock,
                             date_time=date_time)
templates.env.globals["now_label"] = now_label
