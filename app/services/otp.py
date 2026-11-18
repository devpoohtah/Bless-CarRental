"""One-time email codes that confirm a customer's address before a booking request is saved.

The validated request waits here under a challenge ID until the right code arrives. Only delivery is
swappable (OTP_DELIVERY); generation, hashing, expiry, the attempt limit, single use and the resend
cooldown are the same in every mode. In "simulated" mode the code is always 123456 and no email is sent.

State is in this process's memory, like the rate limiter: it is lost on restart and not shared between
workers. That is fine for one worker; move it to Firestore or Redis before running several.
"""

import hashlib
import hmac
import logging
import math
import secrets
import threading
import time
from dataclasses import dataclass
from typing import Any

from app.core import config
from app.services import mailer

log = logging.getLogger(__name__)

TTL_SECONDS = 600
MAX_ATTEMPTS = 5
RESEND_COOLDOWN_SECONDS = 60
SIMULATED_CODE = "123456"


class OtpError(Exception):
    """A problem the customer can be told about. code is one of: wrong_code, expired, locked, cooldown, send_failed."""

    def __init__(self, code: str, message: str, attempts_left: int | None = None, retry_after: int | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.attempts_left = attempts_left
        self.retry_after = retry_after


@dataclass
class _Challenge:
    kind: str
    data: Any  # the validated booking request, kept until the code is right
    email: str
    salt: bytes
    code_hash: bytes
    expires_at: float
    attempts_left: int
    resend_at: float


def mask_email(email: str) -> str:
    local, _, domain = email.partition("@")
    return f"{local[:1]}***@{domain}"


def _hash(salt: bytes, code: str) -> bytes:
    return hmac.new(salt, code.encode(), hashlib.sha256).digest()


class OtpStore:
    def __init__(self, clock=time.monotonic):
        self._clock = clock
        self._items: dict[str, _Challenge] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _send_new_code(email: str) -> tuple[str, bool]:
        """Makes a code and delivers it. Returns (code, simulated). Called without the lock: sending can be slow."""
        simulated = config.integrations.otp_mode == "simulated"
        code = SIMULATED_CODE if simulated else f"{secrets.randbelow(1_000_000):06d}"
        if not simulated and not mailer.send_otp_email(email, code):
            raise OtpError("send_failed", "We could not send the code. Please try again in a moment.")
        return code, simulated

    def _arm(self, challenge: _Challenge, code: str) -> None:
        """Makes this the only valid code for the challenge. Call with the lock held."""
        now = self._clock()
        challenge.salt = secrets.token_bytes(16)
        challenge.code_hash = _hash(challenge.salt, code)
        challenge.expires_at = now + TTL_SECONDS
        challenge.attempts_left = MAX_ATTEMPTS
        challenge.resend_at = now + RESEND_COOLDOWN_SECONDS

    def start(self, kind: str, data: Any, email: str) -> tuple[str, str | None]:
        """Sends a code for this request. Returns (challenge ID, test code or None)."""
        code, simulated = self._send_new_code(email)
        challenge = _Challenge(kind, data, email, b"", b"", 0.0, 0, 0.0)
        challenge_id = secrets.token_urlsafe(24)
        with self._lock:
            self._arm(challenge, code)
            now = self._clock()
            self._items = {k: v for k, v in self._items.items() if v.expires_at > now}  # forget expired ones
            self._items[challenge_id] = challenge
        return challenge_id, code if simulated else None

    def resend(self, challenge_id: str) -> str | None:
        """Sends a new code (the old one stops working). Returns the test code in simulated mode."""
        with self._lock:
            challenge = self._items.get(challenge_id)
            now = self._clock()
            if challenge is None or challenge.expires_at <= now:
                self._items.pop(challenge_id, None)
                raise OtpError("expired", "This code has expired. Please start again.")
            if now < challenge.resend_at:
                wait = math.ceil(challenge.resend_at - now)
                raise OtpError("cooldown", f"Please wait {wait} seconds before asking for another code.", retry_after=wait)
            challenge.resend_at = now + RESEND_COOLDOWN_SECONDS  # reserve, so two clicks cannot send two emails
            email = challenge.email
        try:
            code, simulated = self._send_new_code(email)
        except OtpError:
            with self._lock:
                challenge.resend_at = 0.0  # nothing went out: let the customer try again straight away
            raise
        with self._lock:
            if self._items.get(challenge_id) is not challenge:  # used up or locked while the email was being sent
                raise OtpError("expired", "This code has expired. Please start again.")
            self._arm(challenge, code)
        return code if simulated else None

    def verify(self, challenge_id: str, code: str) -> tuple[str, Any]:
        """Checks the code. On success the challenge is used up and (kind, request) is returned."""
        with self._lock:
            challenge = self._items.get(challenge_id)
            if challenge is None or challenge.expires_at <= self._clock():
                self._items.pop(challenge_id, None)
                raise OtpError("expired", "This code has expired. Please start again.")
            if not hmac.compare_digest(_hash(challenge.salt, code.strip()), challenge.code_hash):
                challenge.attempts_left -= 1
                if challenge.attempts_left <= 0:
                    del self._items[challenge_id]
                    raise OtpError("locked", "Too many wrong codes. Please start again.")
                left = challenge.attempts_left
                raise OtpError("wrong_code", f"That code is not right. {left} {'try' if left == 1 else 'tries'} left.",
                               attempts_left=left)
            del self._items[challenge_id]  # single use
            return challenge.kind, challenge.data

    def discard(self, challenge_id: str) -> None:
        with self._lock:
            self._items.pop(challenge_id, None)


store = OtpStore()
