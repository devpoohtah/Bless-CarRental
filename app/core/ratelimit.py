"""A small in-memory rate limiter for the public booking endpoint.

State lives in this process only: it resets when the server restarts, and each worker process
counts separately. That is enough to stop a script flooding Firestore with fake requests; it is
not a replacement for a firewall or CAPTCHA if the site is attacked seriously.
"""

import threading
import time
from collections import deque


class RateLimiter:
    def __init__(self, max_hits: int, window_seconds: float, clock=time.monotonic):
        self._max = max_hits
        self._window = window_seconds
        self._clock = clock
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        """Records one attempt for key; False when key has used up its attempts in the window."""
        now = self._clock()
        with self._lock:
            hits = self._hits.setdefault(key, deque())
            while hits and now - hits[0] >= self._window:
                hits.popleft()
            if len(hits) >= self._max:
                return False
            hits.append(now)
            if len(self._hits) > 5000:  # keep memory bounded: forget keys with nothing recent
                for stale in [k for k, v in self._hits.items() if not v or now - v[-1] >= self._window]:
                    del self._hits[stale]
            return True
