"""Away reply: an optional automatic answer for holidays and other absences.

This is the one place where Enveliq sends an email without the person pressing Send, so it is off until they turn it on, it only ever
sends the words they wrote, and it is careful:

* Only between the start and end dates they chose (their own time zone), and only for mail that arrives while it is on.
* One reply per sender per absence, however many emails they send.
* Never to mailing lists, newsletters, automatic mail, "no reply" addresses, the person's own addresses, or mail that was not addressed to
  them. Every reply says it is automatic (Auto-Submitted), so other programs do not answer it, and no more than 20 go out in an hour.
* Nothing from the email is put in the reply: no quote, no subject beyond "Automatic reply: <subject>".

One encrypted record per person (`away:<user id>`): the settings and the addresses already answered in this absence.
"""
from __future__ import annotations

import re
import threading
import time
from datetime import date, datetime
from typing import Any, Callable
from zoneinfo import ZoneInfo

RECORD_PREFIX = "away:"
MAX_BODY = 2000
MAX_DAYS = 366
MAX_PER_HOUR = 20
MAX_REPLIED = 2000
STALE_SECONDS = 3 * 86400                 # mail older than this is never answered (a mailbox that was offline for a while)
_LOCK = threading.Lock()
_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_NOREPLY = re.compile(r"^(no[-_.]?reply|do[-_.]?not[-_.]?reply|donotreply|mailer-daemon|postmaster|bounces?|notifications?|alerts?|daemon|newsletter|news|updates?|support-noreply|auto[-_.]?(reply|response|mail))([-_.+@0-9].*)?$", re.I)


class AwayError(ValueError):
    """Plain, safe-to-show reason a change was refused."""


def clean_body(value: Any) -> str:
    return _CTRL.sub("", str(value or "").replace("\r\n", "\n").replace("\r", "\n")).strip()[:MAX_BODY]


def parse_day(value: Any) -> date:
    if not isinstance(value, str) or not _DATE.match(value):
        raise AwayError("Choose a start and an end date.")
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise AwayError("That date is not valid.") from None


def automatic(address: Any) -> bool:
    """An address that is not a person: a no-reply or system address."""
    local = str(address or "").split("@", 1)[0].strip()
    return not local or bool(_NOREPLY.match(local))


class AwayBook:
    def __init__(self, vault: Any, timezone_of: Callable[[str], str], clock: Callable[[], float] = time.time) -> None:
        self.vault, self.timezone_of, self.clock = vault, timezone_of, clock

    def _load(self, user_id: str) -> dict[str, Any]:
        raw = self.vault.get_global(RECORD_PREFIX + user_id) or {}
        return {"enabled": bool(raw.get("enabled")), "start": str(raw.get("start") or ""), "end": str(raw.get("end") or ""),
                "body": str(raw.get("body") or ""), "replied": dict(raw.get("replied") or {}), "recent": [float(t) for t in raw.get("recent") or []],
                "sent": int(raw.get("sent") or 0)}

    def _save(self, user_id: str, state: dict[str, Any]) -> None:
        self.vault.set_global(RECORD_PREFIX + user_id, state)

    def today(self, user_id: str) -> date:
        try:
            zone = ZoneInfo(self.timezone_of(user_id) or "UTC")
        except Exception:
            zone = ZoneInfo("UTC")
        return datetime.fromtimestamp(self.clock(), zone).date()

    def state_of(self, user_id: str) -> str:
        """off, scheduled (on, but not started), active, or ended."""
        s = self._load(user_id)
        if not s["enabled"] or not s["start"] or not s["end"]:
            return "off"
        today, start, end = self.today(user_id), date.fromisoformat(s["start"]), date.fromisoformat(s["end"])
        return "scheduled" if today < start else "active" if today <= end else "ended"

    def view(self, user_id: str) -> dict[str, Any]:
        s = self._load(user_id)
        return {"enabled": s["enabled"], "start": s["start"], "end": s["end"], "body": s["body"], "state": self.state_of(user_id),
                "answered": len(s["replied"]), "limits": {"body": MAX_BODY, "days": MAX_DAYS}, "today": self.today(user_id).isoformat()}

    def save(self, user_id: str, enabled: bool, start: Any, end: Any, body: Any) -> dict[str, Any]:
        text = clean_body(body)
        if enabled:
            if not text:
                raise AwayError("Write the message people will get.")
            a, b = parse_day(start), parse_day(end)
            if b < a:
                raise AwayError("The end date is before the start date.")
            if (b - a).days > MAX_DAYS:
                raise AwayError("An away reply can last up to a year.")
            if b < self.today(user_id):
                raise AwayError("The end date has already passed.")
        with _LOCK:
            s = self._load(user_id)
            new_start, new_end = (str(start or ""), str(end or "")) if enabled else (s["start"], s["end"])
            if (new_start, new_end) != (s["start"], s["end"]) or (enabled and not s["enabled"]):
                s["replied"], s["recent"], s["sent"] = {}, [], 0               # a new absence starts with a clean list of who was answered
            s.update(enabled=bool(enabled), start=new_start, end=new_end, body=text)
            self._save(user_id, s)
        return self.view(user_id)

    def claim(self, user_id: str, address: str) -> bool:
        """Reserve the one reply this sender gets in this absence. False when it is off, outside the dates, already answered, or at the hourly limit."""
        key = str(address or "").strip().lower()
        if not key:
            return False
        with _LOCK:
            s = self._load(user_id)
            if not s["enabled"] or not s["start"] or not s["end"] or not s["body"]:
                return False
            today = self.today(user_id)
            if not (date.fromisoformat(s["start"]) <= today <= date.fromisoformat(s["end"])):
                return False
            now = self.clock()
            s["recent"] = [t for t in s["recent"] if now - t < 3600]
            if key in s["replied"] or len(s["recent"]) >= MAX_PER_HOUR or len(s["replied"]) >= MAX_REPLIED:
                return False
            s["replied"][key] = now
            s["recent"].append(now)
            s["sent"] += 1
            self._save(user_id, s)
        return True

    def release(self, user_id: str, address: str) -> None:
        """The reply could not be sent: let this sender be answered next time."""
        key = str(address or "").strip().lower()
        with _LOCK:
            s = self._load(user_id)
            if s["replied"].pop(key, None) is not None:
                s["sent"] = max(0, s["sent"] - 1)
                self._save(user_id, s)

    def body_of(self, user_id: str) -> str:
        return self._load(user_id)["body"]

    def forget_user(self, user_id: str) -> None:
        self.vault.set_global(RECORD_PREFIX + user_id, {})


def eligible(item: dict[str, Any], stored: dict[str, Any], own: set[str], now: float) -> str | None:
    """The address to answer, or None when this email should not get an away reply."""
    if item.get("automated"):
        return None
    ctx = stored.get("reply_context") or {}
    to = str(ctx.get("reply_to") or "").strip()
    sender = str(stored.get("sender_address") or "").strip().lower()
    if not to or not ctx.get("delivered_to"):                       # no one to answer, or it was not addressed to this person (a list, a Bcc)
        return None
    if automatic(to) or automatic(sender) or to.lower() in own or sender in own:
        return None
    received = stored.get("received_at")
    if isinstance(received, (int, float)) and now - float(received) > STALE_SECONDS:
        return None
    return to
