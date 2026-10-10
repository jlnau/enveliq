from __future__ import annotations

import threading
import time
from collections import deque


class SlidingWindowLimiter:
    """At most `max_events` per key in any `window` seconds."""

    def __init__(self, max_events: int, window: float, max_keys: int = 4096):
        self.max_events = max_events
        self.window = window
        self.max_keys = max_keys
        self._events: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            if len(self._events) >= self.max_keys and key not in self._events:
                self._events.pop(next(iter(self._events)))
            q = self._events.setdefault(key, deque())
            while q and now - q[0] > self.window:
                q.popleft()
            if len(q) >= self.max_events:
                return False
            q.append(now)
            return True
