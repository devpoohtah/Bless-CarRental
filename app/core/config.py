"""Site-wide settings for the BLESS landing page.

Everything here is public business information, so it is safe to keep in code.
Secrets (for example Firebase service credentials) must NOT go in this file; load them
from environment variables when the Firebase integration is added.
"""

from dataclasses import dataclass
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = APP_DIR / "templates"
STATIC_DIR = APP_DIR / "static"


@dataclass(frozen=True)
class Settings:
    business_name: str = "BLESS Travel and Tours & Car Rental Services"
    short_name: str = "BLESS"
    tagline: str = "Your Journey, Our Priority."
    site_description: str = (
        "Travel tours, tour packages and car rental services in Iloilo City, Philippines. "
        "Discover the world, one mile at a time."
    )
    location: str = "Iloilo City, Philippines"

    phone_display: str = "0966 053 4280"
    phone_href: str = "tel:+639660534280"

    facebook_url: str = "https://www.facebook.com/profile.php?id=61572490139656"
    # Messenger deep link for the same Facebook page (page ID taken from the URL above).
    messenger_url: str = "https://m.me/61572490139656"

    # Leave as None until the business confirms its email address. The contact section
    # shows a "not yet available" line while this is empty and links it once it is set.
    email: str | None = None


settings = Settings()
