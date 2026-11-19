"""Cloudflare Turnstile check. The secret key stays on the server."""

import json
import logging
import urllib.parse
import urllib.request

from app.core import config

log = logging.getLogger(__name__)
VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
TIMEOUT_SECONDS = 5

# Cloudflare dummy test keys (dev only). When both are set, they must be used together.
# Site key: 1x00000000000000000000AA
# Secret key: 1x0000000000000000000000000000000AA
TEST_SITE_KEY = "1x00000000000000000000AA"
TEST_SECRET_KEY = "1x0000000000000000000000000000000AA"


def passed(token: str, remote_ip: str = "") -> bool:
    """True when Cloudflare accepts the token. If Turnstile is not set up the check is skipped (True).
    Once it is set up, a missing token, a rejected token or an unreachable Cloudflare all fail closed."""
    cfg = config.integrations
    if not cfg.turnstile_ready:
        return True
    if not token:
        return False

    # Use test keys if both are explicitly set in env (dev only)
    secret = cfg.turnstile_secret_key
    if cfg.turnstile_site_key == TEST_SITE_KEY and cfg.turnstile_secret_key == TEST_SECRET_KEY:
        secret = TEST_SECRET_KEY

    fields = {"secret": secret, "response": token}
    if remote_ip:
        fields["remoteip"] = remote_ip
    request = urllib.request.Request(VERIFY_URL, data=urllib.parse.urlencode(fields).encode(), method="POST")
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            result = json.loads(response.read())
            success = bool(result.get("success"))
            if not success:
                error_codes = result.get("error-codes", [])
                log.warning("Turnstile verification failed: %s", error_codes)
            return success
    except Exception as exc:
        log.warning("Could not verify a Turnstile token (%s)", type(exc).__name__)
        return False
