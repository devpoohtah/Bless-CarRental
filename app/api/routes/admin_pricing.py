"""The Pricing page: the owner's extra-hour rates for cars. Saved in the database, so a price change is an
edit here and never a code change."""

from datetime import date, time
from types import SimpleNamespace

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.core.auth import require_admin
from app.core.templating import notice_for, templates
from app.db.firebase import require_configured
from app.schemas.forms import PricingInput, validate
from app.schemas.pricing import CarPricing
from app.services import pricing

router = APIRouter(prefix="/admin/pricing", include_in_schema=False, dependencies=[Depends(require_admin)])

FIELDS = ("flat_until_hours", "five_hourly_rate_php", "five_hourly_hours", "five_flat_php",
          "seven_hourly_rate_php", "seven_hourly_hours", "seven_flat_php")


def _values(rules: CarPricing) -> dict:
    return {"flat_until_hours": rules.flat_until_hours,
            "five_hourly_rate_php": rules.five_seater.hourly_rate_php, "five_hourly_hours": rules.five_seater.hourly_hours,
            "five_flat_php": rules.five_seater.flat_php,
            "seven_hourly_rate_php": rules.seven_seater.hourly_rate_php, "seven_hourly_hours": rules.seven_seater.hourly_hours,
            "seven_flat_php": rules.seven_seater.flat_php}


def _examples(rules: CarPricing) -> list[dict]:
    """Worked examples with the rates as saved, so the owner can see what a customer would be charged."""
    day = date(2030, 1, 1)
    cars = [("5-seater at ₱1,500 a day", SimpleNamespace(daily_rate_php=1500, seats=5)),
            ("7-seater at ₱2,500 a day", SimpleNamespace(daily_rate_php=2500, seats=7))]
    rows = []
    for title, car in cars:
        for extra in (0, 2, 6, 15):
            price = pricing.quote(car, day, time(8, 0), date(2030, 1, 4), time(8 + extra, 0) if extra else time(8, 0), rules)
            if price:
                rows.append({"car": title, "trip": "3 days" + (f" + {extra} hrs" if extra else ""),
                             "total": pricing.php(price.total_php)})
    return rows


def _render(request: Request, status_code: int = 200, **context) -> HTMLResponse:
    context |= {"active_nav": "cars", "notice": notice_for(request), "errors": context.get("errors", [])}
    return templates.TemplateResponse(request, "admin/pages/pricing.html", context, status_code=status_code)


@router.get("", response_class=HTMLResponse)
def pricing_page(request: Request) -> HTMLResponse:
    rules = pricing.load_rules()
    return _render(request, form=_values(rules), examples=_examples(rules))


@router.post("")
def pricing_save(
    request: Request, flat_until_hours: str = Form(""), five_hourly_rate_php: str = Form(""),
    five_hourly_hours: str = Form(""), five_flat_php: str = Form(""), seven_hourly_rate_php: str = Form(""),
    seven_hourly_hours: str = Form(""), seven_flat_php: str = Form(""),
):
    require_configured()
    raw = dict(flat_until_hours=flat_until_hours, five_hourly_rate_php=five_hourly_rate_php,
               five_hourly_hours=five_hourly_hours, five_flat_php=five_flat_php,
               seven_hourly_rate_php=seven_hourly_rate_php, seven_hourly_hours=seven_hourly_hours,
               seven_flat_php=seven_flat_php)
    data, errors = validate(PricingInput, raw)
    if data is None:
        return _render(request, 422, form=raw, errors=errors, examples=_examples(pricing.load_rules()))
    pricing.save_rules(data.to_rules())
    return RedirectResponse("/admin/pricing?notice=saved", status_code=303)
