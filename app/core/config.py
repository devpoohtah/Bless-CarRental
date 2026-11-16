"""Site-wide settings for the BLESS landing page.

Everything in Settings is public business information, so it is safe to keep in code.
Integrations reads secrets and service settings from environment variables (.env); no
secret value ever lives in this file.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

APP_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = APP_DIR.parent
load_dotenv(PROJECT_ROOT / ".env")
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


def _env(name: str) -> str:
    return os.environ.get(name, "").strip()


def _admin_emails() -> frozenset[str]:
    return frozenset(e.strip().lower() for e in _env("ADMIN_EMAILS").split(",") if e.strip())


@dataclass(frozen=True)
class Integrations:
    """Firebase, Cloudinary and admin access, read from the environment once at start-up."""

    # Backend only. Path to the service account JSON. Unset means "no database": the app
    # then shows sample data and refuses writes, so it still runs without credentials.
    google_credentials: str = field(default_factory=lambda: _env("GOOGLE_APPLICATION_CREDENTIALS"))
    firebase_api_key: str = field(default_factory=lambda: _env("FIREBASE_API_KEY"))
    firebase_auth_domain: str = field(default_factory=lambda: _env("FIREBASE_AUTH_DOMAIN"))
    firebase_project_id: str = field(default_factory=lambda: _env("FIREBASE_PROJECT_ID"))
    firebase_sender_id: str = field(default_factory=lambda: _env("FIREBASE_MESSAGING_SENDER_ID"))
    firebase_app_id: str = field(default_factory=lambda: _env("FIREBASE_APP_ID"))
    # Backend only. The API secret never reaches a template or the browser.
    cloudinary_cloud_name: str = field(default_factory=lambda: _env("CLOUDINARY_CLOUD_NAME"))
    cloudinary_api_key: str = field(default_factory=lambda: _env("CLOUDINARY_API_KEY"))
    cloudinary_api_secret: str = field(default_factory=lambda: _env("CLOUDINARY_API_SECRET"))
    # Lower-case emails allowed into /admin. Empty means nobody can sign in.
    admin_emails: frozenset[str] = field(default_factory=_admin_emails)

    @property
    def firebase_web_config(self) -> dict[str, str] | None:
        """The public web SDK config for the login page, or None if any value is missing."""
        config = {
            "apiKey": self.firebase_api_key,
            "authDomain": self.firebase_auth_domain,
            "projectId": self.firebase_project_id,
            "messagingSenderId": self.firebase_sender_id,
            "appId": self.firebase_app_id,
        }
        return config if all(config.values()) else None

    @property
    def cloudinary_ready(self) -> bool:
        return all((self.cloudinary_cloud_name, self.cloudinary_api_key, self.cloudinary_api_secret))


settings = Settings()
integrations = Integrations()
