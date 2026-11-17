"""Desktop alerts (Firebase Cloud Messaging web push) for new bookings.

A browser that allowed alerts sends its token to /admin/push/register; it is stored in the
push_tokens collection, written and read only by the server. Sending is best effort: a failure
here must never stop a booking from being saved, so callers catch everything.
"""

import hashlib
import logging
from datetime import date

from firebase_admin import messaging
from pydantic import BaseModel

from app.core import config
from app.core.clock import today_ph
from app.db import firebase
from app.db import repositories as repo

log = logging.getLogger(__name__)
CHUNK = 500  # FCM accepts at most 500 tokens per multicast
# Tokens FCM reports as gone for good. Anything else (a timeout, a quota error) may pass, so it is kept.
DEAD_TOKEN_ERRORS = (messaging.UnregisteredError, messaging.SenderIdMismatchError)


class PushToken(BaseModel):
    id: str
    token: str
    admin_email: str
    registered_on: date


def _doc_id(token: str) -> str:
    """Same token, same document: registering twice never creates a duplicate."""
    return hashlib.sha256(token.encode()).hexdigest()


def register_token(token: str, admin_email: str) -> None:
    repo.save(repo.PUSH_TOKENS, PushToken(id="", token=token, admin_email=admin_email.lower(),
                                          registered_on=today_ph()), _doc_id(token))


def admin_tokens() -> list[PushToken]:
    """Only browsers of people still on ADMIN_EMAILS, so removing an admin also stops their alerts."""
    allowed = config.integrations.admin_emails
    return [t for t in repo.list_all(repo.PUSH_TOKENS, PushToken) if t.admin_email in allowed]


def _send_multicast(tokens: list[str], data: dict[str, str]) -> list[Exception | None]:
    """One entry per token: None when FCM accepted it, otherwise the error."""
    message = messaging.MulticastMessage(
        data=data, tokens=tokens,
        webpush=messaging.WebpushConfig(headers={"Urgency": "high", "TTL": "3600"}))
    response = messaging.send_each_for_multicast(message, app=firebase.init_app())
    return [None if r.success else r.exception for r in response.responses]


def send_to_admins(title: str, body: str, url: str, tag: str) -> int:
    """Pushes one alert to every admin browser. Returns how many accepted it. Data-only message: the
    service worker builds the notification, so no Firebase code has to run in it."""
    if not firebase.is_configured():
        return 0
    tokens = admin_tokens()
    data = {"title": title, "body": body, "url": url, "tag": tag}
    delivered = 0
    for start in range(0, len(tokens), CHUNK):
        chunk = tokens[start:start + CHUNK]
        for entry, error in zip(chunk, _send_multicast([t.token for t in chunk], data)):
            if error is None:
                delivered += 1
            elif isinstance(error, DEAD_TOKEN_ERRORS):
                repo.delete(repo.PUSH_TOKENS, _doc_id(entry.token))  # that browser is gone: stop sending to it
            else:
                log.warning("Push to one admin browser failed (%s)", type(error).__name__)
    return delivered
