"""Shared Jinja2 environment so every route renders with the same helpers."""

from pathlib import Path

from fastapi.templating import Jinja2Templates

from app.core.config import STATIC_DIR, TEMPLATES_DIR, settings
from app.core.icons import icon

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
templates.env.trim_blocks = True
templates.env.lstrip_blocks = True


def static_url(path: str) -> str:
    """URL for a file under app/static, with a modified-time query so edits bypass browser caches."""
    url = f"/static/{path}"
    try:
        return f"{url}?v={int((Path(STATIC_DIR) / path).stat().st_mtime)}"
    except OSError:
        return url


def php(amount: int | None, fallback: str = "Contact for rates") -> str:
    """Format a peso amount, or return a neutral fallback when no price is set."""
    return f"PHP {amount:,}" if amount is not None else fallback


templates.env.globals.update(icon=icon, static_url=static_url, site=settings)
templates.env.filters["php"] = php
