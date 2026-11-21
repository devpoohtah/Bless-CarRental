"""The price of a car rental from its pick-up and return times.

Whole 24-hour blocks cost the car's daily rate each. The hours left over use the extension rates from the
Pricing page. Partial hours count as a full hour. The server does this sum for every booking; the form only
shows an estimate it asks for here, so the browser can never set the price.
"""

import logging
import math
import time
from datetime import date, datetime, time as clock

from app.db import firebase
from app.db import repositories as repo
from app.schemas.pricing import (FIVE_SEATER_MAX_SEATS, SEVEN_SEATER_MAX_SEATS, CarPricing, Quote, QuoteLine,
                                 SeatRates)

log = logging.getLogger(__name__)

SETTINGS_DOC = "car_pricing"
_CACHE_SECONDS = 60
_cache: tuple[float, CarPricing] | None = None


def load_rules() -> CarPricing:
    """The saved rules, or the built-in ones when nothing is saved (or the database cannot be read). Cached for
    a minute so the live estimate does not read the database on every change; saving clears the cache."""
    global _cache
    now = time.monotonic()
    if _cache is not None and now - _cache[0] < _CACHE_SECONDS:
        return _cache[1]
    rules = CarPricing()
    if firebase.is_configured():
        try:
            doc = firebase.get_db().collection(repo.SETTINGS).document(SETTINGS_DOC).get()
            if doc.exists:
                rules = CarPricing(**doc.to_dict())
        except Exception:
            log.exception("Could not read the car pricing, so the built-in rates are used")
            return rules  # not cached: the next request tries the database again
    _cache = (now, rules)
    return rules


def save_rules(rules: CarPricing) -> None:
    global _cache
    firebase.get_db().collection(repo.SETTINGS).document(SETTINGS_DOC).set(rules.model_dump())
    _cache = None


def rates_for(seats: int | None, rules: CarPricing) -> SeatRates | None:
    if not seats:
        return None
    if seats <= FIVE_SEATER_MAX_SEATS:
        return rules.five_seater
    if seats <= SEVEN_SEATER_MAX_SEATS:
        return rules.seven_seater
    return None


def php(amount: int) -> str:
    return f"₱{amount:,}"


def _count(number: int, word: str) -> str:
    return f"{number} {word}" + ("" if number == 1 else "s")


def quote(car, start_date: date, start_time: clock | None, end_date: date, end_time: clock | None,
          rules: CarPricing | None = None) -> Quote | None:
    """None when no price can be worked out (no daily rate, no times, a car size without extension rates, or a
    return that is not after the pick-up): the booking then simply has no total and the owner quotes it."""
    daily = getattr(car, "daily_rate_php", None)
    if not daily or start_time is None or end_time is None:
        return None
    rules = rules or load_rules()
    seat_rates = rates_for(getattr(car, "seats", None), rules)
    if seat_rates is None:
        return None
    minutes = int((datetime.combine(end_date, end_time) - datetime.combine(start_date, start_time)).total_seconds() // 60)
    if minutes <= 0:
        return None
    days, extra = divmod(math.ceil(minutes / 60), 24)

    lines: list[QuoteLine] = []
    if days:
        lines.append(QuoteLine(label=f"{_count(days, 'day')} × {php(daily)}", amount_php=days * daily))
    if extra:
        hours = _count(extra, "extra hour" if days else "hour")
        if extra <= seat_rates.hourly_hours:
            lines.append(QuoteLine(label=f"{hours} × {php(seat_rates.hourly_rate_php)}",
                                   amount_php=extra * seat_rates.hourly_rate_php))
        elif extra <= rules.flat_until_hours:
            lines.append(QuoteLine(label=f"{hours} (flat rate)", amount_php=seat_rates.flat_php))
        else:
            lines.append(QuoteLine(label=f"{hours} (charged as one more day)", amount_php=daily))
    return Quote(total_php=sum(line.amount_php for line in lines), days=days, extra_hours=extra, lines=lines)
