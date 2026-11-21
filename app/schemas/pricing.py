"""Car rental price rules.

The daily rate belongs to each car (set in the admin). These rules cover the hours beyond whole days, and the
admin edits them on the Pricing page, so a price change never needs a code change. They live in Firestore
(settings/car_pricing); the numbers below are only what is used until someone saves their own.
"""

from pydantic import BaseModel, Field, model_validator

FIVE_SEATER_MAX_SEATS = 5  # cars with up to 5 seats follow the five_seater rates
SEVEN_SEATER_MAX_SEATS = 7  # 6 and 7 seats follow the seven_seater rates; larger cars get no automatic price


class SeatRates(BaseModel):
    """Extra hours beyond whole days: the first hourly_hours are charged per hour, the rest (up to the flat
    limit) cost one flat price, and anything longer is charged as one more day at the car's daily rate."""

    hourly_rate_php: int = Field(ge=0, le=1_000_000)
    hourly_hours: int = Field(ge=0, le=23)
    flat_php: int = Field(ge=0, le=1_000_000)


class CarPricing(BaseModel):
    flat_until_hours: int = Field(default=12, ge=1, le=23)
    five_seater: SeatRates = Field(default_factory=lambda: SeatRates(hourly_rate_php=200, hourly_hours=3, flat_php=1000))
    seven_seater: SeatRates = Field(default_factory=lambda: SeatRates(hourly_rate_php=250, hourly_hours=4, flat_php=1500))

    @model_validator(mode="after")
    def _hourly_hours_come_first(self):
        for rates in (self.five_seater, self.seven_seater):
            if rates.hourly_hours >= self.flat_until_hours:
                raise ValueError("the hours charged per hour must be fewer than the hours of the flat rate")
        return self


class QuoteLine(BaseModel):
    label: str
    amount_php: int


class Quote(BaseModel):
    total_php: int
    days: int
    extra_hours: int
    lines: list[QuoteLine]
