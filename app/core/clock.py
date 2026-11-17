"""The business's calendar day. BLESS is in Iloilo and the Philippines has no daylight saving,
so a fixed UTC+8 offset is enough (and avoids needing a time zone database on Windows)."""

from datetime import date, datetime, timedelta, timezone

PHILIPPINES = timezone(timedelta(hours=8))


def today_ph() -> date:
    return datetime.now(PHILIPPINES).date()
