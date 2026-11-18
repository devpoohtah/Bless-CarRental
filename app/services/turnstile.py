"""Cloudflare Turnstile check for the booking form. The secret key stays on the server."""

import json
import logging
import urllib.parse
import urllib.request

from app.core import config

log = logging.getLogger(__name__)
VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
TIMEOUT_SECONDS = 5


def passed(token: str, remote_ip: str = "") -> bool:
    """True when Cloudflare accepts the token. If Turnstile is not set up the check is skipped (True).
    Once it is set up, a missing token, a rejected token or an unreachable Cloudflare all fail closed."""
    cfg = config.integrations
    if not cfg.turnstile_ready:
        return True
    if not token:
        return False
    fields = {"secret": cfg.turnstile_secret_key, "response": token}
    if remote_ip:
        fields["remoteip"] = remote_ip
    request = urllib.request.Request(VERIFY_URL, data=urllib.parse.urlencode(fields).encode(), method="POST")
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            return bool(json.loads(response.read()).get("success"))
    except Exception as exc:
        log.warning("Could not verify a Turnstile token (%s)", type(exc).__name__)
        return False
