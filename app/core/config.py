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

    # The public address of the site, e.g. https://blesstravel.example (no trailing slash). Used for the canonical
    # link, sitemap and share preview. Empty means "use the address the request came in on".
    public_base_url: str = field(default_factory=lambda: _env("PUBLIC_BASE_URL").rstrip("/"))


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
    # Public key (Firebase console > Project settings > Cloud Messaging > Web Push certificates).
    # Browsers need it to subscribe to desktop alerts. Unset means the alerts button is not shown.
    firebase_vapid_key: str = field(default_factory=lambda: _env("FIREBASE_VAPID_KEY"))
    # Backend only. The API secret never reaches a template or the browser.
    cloudinary_cloud_name: str = field(default_factory=lambda: _env("CLOUDINARY_CLOUD_NAME"))
    cloudinary_api_key: str = field(default_factory=lambda: _env("CLOUDINARY_API_KEY"))
    cloudinary_api_secret: str = field(default_factory=lambda: _env("CLOUDINARY_API_SECRET"))
    # Lower-case emails allowed into /admin. Empty means nobody can sign in.
    admin_emails: frozenset[str] = field(default_factory=_admin_emails)
    # Backend only. Booking alerts go to this Telegram group; unset means alerts are skipped.
    telegram_bot_token: str = field(default_factory=lambda: _env("TELEGRAM_BOT_TOKEN"))
    telegram_chat_id: str = field(default_factory=lambda: _env("TELEGRAM_CHAT_ID"))
    # Public address of this site, for the link in an alert (for example https://example.com).
    # Unset means alerts carry no link.
    admin_base_url: str = field(default_factory=lambda: _env("ADMIN_BASE_URL").rstrip("/"))
    # How the booking verification code is delivered: "gmail", "resend" or "simulated" (fixed test
    # code 123456, no email sent). Unset picks "gmail" when its credentials exist, else nothing.
    otp_delivery: str = field(default_factory=lambda: _env("OTP_DELIVERY").lower())
    # Backend only. Gmail SMTP for the verification code. Use a Google app password, never the login password.
    gmail_user: str = field(default_factory=lambda: _env("GMAIL_USER"))
    gmail_app_password: str = field(default_factory=lambda: _env("GMAIL_APP_PASSWORD").replace(" ", ""))
    # Backend only. Resend sends the customer emails (booking approved). Until a domain is verified in
    # Resend, only the account owner's address receives mail, so use onboarding@resend.dev for tests.
    resend_api_key: str = field(default_factory=lambda: _env("RESEND_API_KEY"))
    resend_from_email: str = field(default_factory=lambda: _env("RESEND_FROM_EMAIL") or "onboarding@resend.dev")
    # Cloudflare Turnstile. The site key is public; the secret key stays on the server.
    # Unset means the booking form has no challenge.
    turnstile_site_key: str = field(default_factory=lambda: _env("TURNSTILE_SITE_KEY"))
    turnstile_secret_key: str = field(default_factory=lambda: _env("TURNSTILE_SECRET_KEY"))

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
    def push_web_config(self) -> dict | None:
        """Public settings the admin pages need for desktop alerts, or None when alerts are not set up.
        The server also needs the service account to send them."""
        web = self.firebase_web_config
        if not (web and self.firebase_vapid_key and self.google_credentials):
            return None
        return {"firebase": web, "vapidKey": self.firebase_vapid_key}

    @property
    def telegram_ready(self) -> bool:
        return bool(self.telegram_bot_token and self.telegram_chat_id)

    @property
    def gmail_ready(self) -> bool:
        return bool(self.gmail_user and self.gmail_app_password)

    @property
    def resend_ready(self) -> bool:
        return bool(self.resend_api_key)

    @property
    def turnstile_ready(self) -> bool:
        return bool(self.turnstile_site_key and self.turnstile_secret_key)

    @property
    def otp_mode(self) -> str:
        """"simulated", "gmail", "resend", or "" when no code can be delivered. An unknown value or
        missing credentials give "", never the fixed test code, so production cannot fall into it by accident."""
        mode = self.otp_delivery or ("gmail" if self.gmail_ready else "")
        if mode == "simulated":
            return mode
        if mode == "gmail" and self.gmail_ready:
            return mode
        if mode == "resend" and self.resend_ready:
            return mode
        return ""

    @property
    def cloudinary_ready(self) -> bool:
        return all((self.cloudinary_cloud_name, self.cloudinary_api_key, self.cloudinary_api_secret))


settings = Settings()
integrations = Integrations()
