"""Tells an administrator when a newer Enveliq release is out.

About once a day Enveliq's server (never the person's browser) asks GitHub for the number of the newest published
release of Enveliq and compares it with its own. Nothing about the person, the install or its data is sent: it is
the same plain request anyone can make to https://api.github.com/repos/jlnau/enveliq/releases/latest.

- Only a published release counts (drafts and pre-releases are ignored).
- Only a plain version number and a link to Enveliq's own releases page on GitHub are accepted from the answer;
  anything else is thrown away, so nothing GitHub (or anyone in between) sends can put other text or links on a page.
- A failed check is quiet: the notice just doesn't show.
- Administrators can switch it off (Administration, Updates).
"""
from __future__ import annotations

import json
import re
import threading
import time
import urllib.request
from typing import Any, Callable

RELEASES_API = "https://api.github.com/repos/jlnau/enveliq/releases/latest"
RELEASE_URL_PREFIX = "https://github.com/jlnau/enveliq/releases/"
CHECK_EVERY = 24 * 3600          # a good answer is kept for a day
RETRY_AFTER = 3600               # after a failed try, wait an hour
_TAG = re.compile(r"^v?(\d{1,4}(?:\.\d{1,4}){1,3})$")


def parse_version(text: str) -> tuple[int, ...] | None:
    m = _TAG.match(str(text or "").strip())
    return tuple(int(p) for p in m.group(1).split(".")) if m else None


def accept(data: Any) -> dict[str, str] | None:
    """The version number and release link out of GitHub's answer, or None if it is not exactly what we expect."""
    if not isinstance(data, dict) or data.get("draft") or data.get("prerelease"):
        return None
    ver = parse_version(data.get("tag_name", ""))
    url = data.get("html_url")
    if ver is None or not isinstance(url, str) or len(url) > 200 or not url.startswith(RELEASE_URL_PREFIX):
        return None
    if not re.fullmatch(r"[A-Za-z0-9._/%-]+", url[len(RELEASE_URL_PREFIX):]):
        return None
    return {"version": ".".join(str(p) for p in ver), "url": url}


def fetch_latest() -> dict[str, str] | None:
    req = urllib.request.Request(RELEASES_API, headers={"User-Agent": "Enveliq-update-check", "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=8) as r:          # noqa: S310 - a fixed https address
        return accept(json.loads(r.read(200_000).decode("utf-8")))


class UpdateChecker:
    def __init__(self, current: str, fetch: Callable[[], dict[str, str] | None] | None = None, now: Callable[[], float] = time.time):
        self.current = parse_version(current) or (0,)
        self.fetch = fetch or (lambda: fetch_latest())     # looked up when it is used, so tests can replace fetch_latest
        self._now = now
        self.latest: dict[str, str] | None = None
        self.checked_at = float("-inf")   # the last time we got a proper answer
        self.tried_at = float("-inf")     # the last time we tried at all
        self._lock = threading.Lock()
        self._running = False

    def newer(self) -> dict[str, str] | None:
        """The newest release, if it is newer than the one running."""
        latest = self.latest
        v = parse_version(latest["version"]) if latest else None
        return dict(latest) if latest and v and v > self.current else None

    def due(self) -> bool:
        now = self._now()
        return now - self.checked_at >= CHECK_EVERY and now - self.tried_at >= RETRY_AFTER

    def refresh(self) -> None:
        """Ask now, on this thread. Never raises."""
        self.tried_at = self._now()
        try:
            got = self.fetch()
        except Exception:               # no internet, GitHub busy, a strange answer: the notice just doesn't show
            return
        if got is not None:
            self.latest, self.checked_at = got, self._now()

    def maybe_refresh(self) -> None:
        """Start a check in the background if one is due. Returns at once."""
        with self._lock:
            if self._running or not self.due():
                return
            self._running = True
            self.tried_at = self._now()

        def run() -> None:
            try:
                self.refresh()
            finally:
                self._running = False

        threading.Thread(target=run, name="enveliq-update-check", daemon=True).start()
