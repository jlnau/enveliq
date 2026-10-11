"""Trips: flights, stays and hire cars, followed from the emails about them.

When the AI summary of an incoming email says it is a booking, a change or a cancellation for a flight, a hotel or other
stay, or a hire car, each leg is filed as one booking. The AI reads the email once and only copies what it says. Everything
that is a date, a time, a night count or the grouping of bookings into trips is worked out here, in plain code.

Each person has one encrypted record (`trips:<user id>`). It holds only: the kind, the provider, the booking reference, a
flight number or property name, the places, the start and end date and time, and a mark for each email already filed.
No email text, no subject, no sender address and no link is stored. Every value came out of an email written by a stranger,
so it is cut to a short length, stripped of control characters and shown only as plain text. An email with a "Be careful"
flag is never filed. Enveliq never contacts an airline, a hotel or a rental company.

The bookings can also appear in the person's own calendar (the private feed, CalDAV or Google Calendar, whichever they set up
for tasks), when they leave that switched on. Times are the clock times written in the email, for the place they are for.
"""
from __future__ import annotations

import hashlib
import re
import secrets
import threading
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable

from .subscriptions import clean
from .tasks import parse_due, zone

RECORD_PREFIX = "trips:"
KINDS = ("flight", "stay", "car")
STATUSES = ("booked", "changed", "cancelled")
MAX_BOOKINGS = 120
MAX_EVENTS = 20
GAP_DAYS = 2                          # bookings closer together than this belong to the same trip
RETURN_DAYS = 45                      # a flight back from where an earlier flight went joins its trip when it is this close
KEEP_AFTER_END = 3 * 86400            # a trip is forgotten three days after it ends
KEEP_CANCELLED = 7 * 86400
KEEP_DISMISSED = 400 * 86400
HORIZON_BEFORE, HORIZON_AFTER = 30, 800

_TIME_CLOCK = re.compile(r"(?<![\d:.])([01]?\d|2[0-3])[:.]([0-5]\d)\s*([ap]\.?m\.?)?(?!\d)", re.I)
_TIME_HOUR = re.compile(r"(?<![\d:.])(1[0-2]|0?[1-9])\s*([ap]\.?m\.?)(?![a-z])", re.I)


def key_of(value: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", clean(value, 80).lower())


def parse_clock(text: Any) -> str | None:
    """A time of day as HH:MM from words such as '10:45', '2.35 pm' or '9am'. None when there is none. Never guessed."""
    t = clean(text, 80)
    m = _TIME_CLOCK.search(t)
    if m:
        hour, minute, half = int(m[1]), int(m[2]), (m[3] or "").lower()
        if half:
            if not 1 <= hour <= 12:
                return None
            hour = hour % 12 + (12 if half.startswith("p") else 0)
        return f"{hour:02d}:{minute:02d}"
    m = _TIME_HOUR.search(t)
    if m:
        hour, half = int(m[1]), m[2].lower()
        return f"{hour % 12 + (12 if half.startswith('p') else 0):02d}:00"
    return None


def _day(text: Any) -> date | None:
    try:
        return date.fromisoformat(text) if isinstance(text, str) else None
    except ValueError:
        return None


def nights(start: date, end: date | None) -> int | None:
    return (end - start).days if end and end > start else None


class TripBook:
    def __init__(self, vault: Any, tz_of: Callable[[str], str | None] | None = None, clock: Callable[[], float] = time.time):
        self.vault = vault
        self.tz_of = tz_of or (lambda user_id: None)
        self.clock = clock
        self._lock = threading.RLock()
        self.changed: Callable[[str], None] | None = None      # set by the application: tells the calendar mirror to catch up

    # ---------- storage ----------

    def _load(self, user_id: str) -> dict[str, Any]:
        raw = self.vault.get_global(RECORD_PREFIX + user_id) or {}
        items = raw.get("items") if isinstance(raw.get("items"), dict) else {}
        dismissed = raw.get("dismissed") if isinstance(raw.get("dismissed"), dict) else {}
        return {"items": items, "dismissed": dismissed, "calendar": raw.get("calendar") is not False}

    def _save(self, user_id: str, book: dict[str, Any]) -> None:
        self.vault.set_global(RECORD_PREFIX + user_id, book)

    def _tell(self, user_id: str) -> None:
        if self.changed is not None:
            try:
                self.changed(user_id)
            except Exception:
                pass

    def _today(self, user_id: str, now: float | None = None) -> date:
        return datetime.fromtimestamp(self.clock() if now is None else now, zone(self.tz_of(user_id))).date()

    def enabled(self, user_id: str | None) -> bool:
        if not user_id:
            return False
        from . import features
        return bool(features.effective(self.vault, user_id).get("travel"))

    def _purge(self, book: dict[str, Any], now: float, today: date) -> bool:
        changed = False
        for bid, b in list(book["items"].items()):
            last = _day(b.get("end")) or _day(b.get("start"))
            gone = last is not None and (today - last).days * 86400 > KEEP_AFTER_END
            if b.get("status") == "cancelled" and now - float(b.get("cancelled_at") or b.get("updated") or 0) > KEEP_CANCELLED:
                gone = True
            if gone or last is None:
                del book["items"][bid]
                changed = True
        for key, at in list(book["dismissed"].items()):
            if now - float(at or 0) > KEEP_DISMISSED:
                del book["dismissed"][key]
                changed = True
        if len(book["items"]) > MAX_BOOKINGS:
            for bid, _ in sorted(book["items"].items(), key=lambda kv: float(kv[1].get("updated") or 0))[: len(book["items"]) - MAX_BOOKINGS]:
                del book["items"][bid]
            changed = True
        return changed

    # ---------- learning from an email ----------

    @staticmethod
    def _clean(raw: Any) -> dict[str, Any] | None:
        if not isinstance(raw, dict) or raw.get("kind") not in KINDS or raw.get("status", "booked") not in STATUSES:
            return None
        out = {"kind": raw["kind"], "status": raw.get("status") or "booked", "start_text": clean(raw.get("start"), 60)}
        if not out["start_text"]:
            return None
        for key, limit in (("provider", 60), ("reference", 30), ("detail", 60), ("from", 60), ("to", 60)):
            out[key] = clean(raw.get(key), limit) or None
        out["end_text"] = clean(raw.get("end"), 60) or None
        return out

    @staticmethod
    def _match_key(info: dict[str, Any], start: date) -> str:
        """What makes two emails about the same booking. A changed date does not make a new one."""
        ref = key_of(info["reference"])
        if info["kind"] == "flight":
            return f"flight|{ref}|{key_of(info['from'])}|{key_of(info['to'])}" if ref else f"flight|{key_of(info['provider'])}|{key_of(info['detail'])}|{start.isoformat()}"
        if info["kind"] == "stay":
            return f"stay|{ref}|{key_of(info['provider'])}" if ref else f"stay|{key_of(info['provider'])}|{start.isoformat()}"
        return f"car|{ref}|{key_of(info['provider'])}" if ref else f"car|{key_of(info['provider'])}|{start.isoformat()}"

    def observe(self, user_id: str | None, account_id: str, message_id: str, received_at: float | None, raws: Any) -> bool:
        """File what an email says about bookings. Returns True when anything was added or changed."""
        if not user_id or not self.enabled(user_id) or not isinstance(raws, list):
            return False
        now = self.clock()
        at = float(received_at) if received_at and 0 < received_at <= now + 86400 else now
        sent_on = datetime.fromtimestamp(at, timezone.utc).date()
        today = self._today(user_id, now)
        mark = hashlib.sha256(f"{account_id}|{message_id}".encode()).hexdigest()[:16]
        touched = False
        with self._lock:
            book = self._load(user_id)
            self._purge(book, now, today)
            if any(e.get("m") == mark for b in book["items"].values() for e in b["events"]):
                return False                                                            # this very email was already filed
            for raw in raws[:6]:
                info = self._clean(raw)
                if info is None:
                    continue
                start = parse_due(info["start_text"], sent_on, sent_on)
                if start is None or not sent_on - timedelta(days=HORIZON_BEFORE) <= start <= sent_on + timedelta(days=HORIZON_AFTER):
                    continue
                end = parse_due(info["end_text"], start, start) if info["end_text"] else None
                end = end if end and end >= start and (end - start).days <= 120 else None
                mkey = self._match_key(info, start)
                if f"k:{mkey}" in book["dismissed"]:
                    continue
                item = next((b for b in book["items"].values() if b.get("match") == mkey), None)
                if item is None:
                    if info["status"] == "cancelled" or len(book["items"]) >= MAX_BOOKINGS + 10:
                        continue                                                        # nothing to cancel, or too many
                    bid = "v" + secrets.token_hex(12)[:23]
                    item = {"id": bid, "match": mkey, "kind": info["kind"], "status": "booked", "first_seen": at, "updated": at, "events": []}
                    book["items"][bid] = item
                self._apply(item, info, start, end, at, mark)
                touched = True
            if touched:
                self._save(user_id, book)
        if touched:
            self._tell(user_id)
        return touched

    @staticmethod
    def _apply(item: dict[str, Any], info: dict[str, Any], start: date, end: date | None, at: float, mark: str) -> None:
        newest = at >= float(item.get("facts_at") or 0)                                  # an older email never overwrites newer facts
        if newest:
            if info["status"] == "cancelled":
                item["status"], item["cancelled_at"] = "cancelled", at
            else:
                item["status"], item["cancelled_at"] = "booked", None
                item["start"], item["end"] = start.isoformat(), end.isoformat() if end else None
                item["start_time"] = parse_clock(info["start_text"])
                item["end_time"] = parse_clock(info["end_text"]) if info["end_text"] else None
            for key in ("provider", "reference", "detail", "from", "to"):
                if info[key]:
                    item[key] = info[key]
            item["facts_at"] = at
        else:
            for key in ("provider", "reference", "detail", "from", "to"):
                if info[key] and not item.get(key):
                    item[key] = info[key]
            if not item.get("start") and info["status"] != "cancelled":
                item["start"], item["end"] = start.isoformat(), end.isoformat() if end else None
                item["start_time"], item["end_time"] = parse_clock(info["start_text"]), parse_clock(info["end_text"]) if info["end_text"] else None
        item["updated"] = max(float(item.get("updated") or 0), at)
        item["events"].append({"at": at, "status": info["status"], "m": mark})
        item["events"].sort(key=lambda e: e["at"])
        del item["events"][:-MAX_EVENTS]

    # ---------- grouping into trips, worked out here ----------

    @staticmethod
    def _title(rows: list[dict[str, Any]]) -> str:
        for r in rows:
            if r["status"] == "cancelled":
                continue
            place = (r["to"] if r["kind"] == "flight" else r["to"] or r["provider"] if r["kind"] == "stay" else r["from"] or r["to"])
            if place:
                return f"Trip to {place}"
        return "Trip"

    def _rows(self, book: dict[str, Any], today: date) -> list[dict[str, Any]]:
        rows = []
        for b in book["items"].values():
            start = _day(b.get("start"))
            if start is None:
                continue
            end = _day(b.get("end"))
            rows.append({
                "id": b["id"], "kind": b["kind"], "status": b.get("status") or "booked", "provider": b.get("provider"), "reference": b.get("reference"),
                "detail": b.get("detail"), "from": b.get("from"), "to": b.get("to"), "start": start.isoformat(), "end": end.isoformat() if end else None,
                "start_time": b.get("start_time"), "end_time": b.get("end_time"), "nights": nights(start, end) if b["kind"] == "stay" else None,
                "days_to_start": (start - today).days,
            })
        rows.sort(key=lambda r: (r["start"], r["start_time"] or "", r["kind"]))
        return rows

    def _trips(self, rows: list[dict[str, Any]], today: date) -> list[dict[str, Any]]:
        groups: list[list[dict[str, Any]]] = []
        last_end: date | None = None
        for r in rows:
            s, e = _day(r["start"]), _day(r["end"]) or _day(r["start"])
            if groups and last_end is not None and (s - last_end).days <= GAP_DAYS:
                groups[-1].append(r)
                last_end = max(last_end, e)
            else:
                groups.append([r])
                last_end = e
        merged: list[list[dict[str, Any]]] = []
        for g in groups:
            if merged:
                # A flight home from where an earlier flight went belongs to that trip, even when nothing else bridges the days between.
                prev = merged[-1]
                out = next((r for r in reversed(prev) if r["kind"] == "flight" and r["status"] != "cancelled"), None)
                back = next((r for r in g if r["kind"] == "flight" and r["status"] != "cancelled"), None)
                gap = (min(_day(r["start"]) for r in g) - max((_day(r["end"]) or _day(r["start"])) for r in prev)).days
                if out and back and key_of(out["to"]) and key_of(out["to"]) == key_of(back["from"]) and gap <= RETURN_DAYS:
                    prev.extend(g)
                    prev.sort(key=lambda r: (r["start"], r["start_time"] or "", r["kind"]))
                    continue
            merged.append(g)
        groups = merged
        trips = []
        for g in groups:
            live = [r for r in g if r["status"] != "cancelled"] or g
            start = min(_day(r["start"]) for r in live)
            end = max((_day(r["end"]) or _day(r["start"])) for r in live)
            state = "past" if end < today else "now" if start <= today else "soon"
            trips.append({"id": g[0]["id"], "title": self._title(g), "start": start.isoformat(), "end": end.isoformat(), "days_to_start": (start - today).days,
                          "state": state, "cancelled": all(r["status"] == "cancelled" for r in g), "bookings": g})
        trips.sort(key=lambda t: t["start"])
        return trips

    def view(self, user_id: str) -> dict[str, Any]:
        if not self.enabled(user_id):
            return {"enabled": False, "trips": [], "calendar": True, "today": None}
        now = self.clock()
        today = self._today(user_id, now)
        with self._lock:
            book = self._load(user_id)
            if self._purge(book, now, today):
                self._save(user_id, book)
        return {"enabled": True, "trips": self._trips(self._rows(book, today), today), "calendar": book["calendar"], "today": today.isoformat()}

    # ---------- the calendar ----------

    def calendar_items(self, user_id: str) -> list[dict[str, Any]]:
        """What the calendar mirror should hold for this person: nothing when the feature or the switch is off, never a cancelled booking."""
        if not self.enabled(user_id):
            return []
        book = self._load(user_id)
        if not book["calendar"]:
            return []
        today = self._today(user_id)
        out = []
        for r in self._rows(book, today):
            if r["status"] == "cancelled":
                continue
            end = _day(r["end"]) or _day(r["start"])
            if (today - end).days > 1:
                continue
            out.append({**r, "summary": self.summary(r), "description": self.description(r)})
        return out

    @staticmethod
    def summary(r: dict[str, Any]) -> str:
        who = r.get("provider") or ""
        if r["kind"] == "flight":
            route = f"{r['from']} to {r['to']}" if r.get("from") and r.get("to") else (r.get("to") or "")
            return clean("Flight " + route + (f" ({r['detail']})" if r.get("detail") else "") if route else "Flight" + (f" {r['detail']}" if r.get("detail") else ""), 120)
        if r["kind"] == "stay":
            return clean("Stay: " + (who or r.get("to") or "booked"), 120)
        return clean("Hire car" + (f": {who}" if who else "") + (f", {r['from']}" if r.get("from") else ""), 120)

    @staticmethod
    def description(r: dict[str, Any]) -> str:
        parts = []
        if r.get("provider") and r["kind"] == "flight":
            parts.append(r["provider"])
        if r.get("reference"):
            parts.append("Booking reference " + r["reference"])
        parts.append("Times are as written in the email, for the place they are for.")
        return clean(". ".join(parts), 400)

    # ---------- what the person can do ----------

    def set_calendar(self, user_id: str, on: bool) -> dict[str, Any]:
        if not isinstance(on, bool):
            raise ValueError("calendar")
        with self._lock:
            book = self._load(user_id)
            book["calendar"] = on
            self._save(user_id, book)
        self._tell(user_id)
        return self.view(user_id)

    def remove(self, user_id: str, bid: str) -> dict[str, Any]:
        """The person says this is not a booking of theirs. It is forgotten and later emails for it are ignored."""
        now = self.clock()
        with self._lock:
            book = self._load(user_id)
            item = book["items"].get(bid)
            if item is None:
                raise KeyError(bid)
            if item.get("match"):
                book["dismissed"][f"k:{item['match']}"] = now
            del book["items"][bid]
            self._save(user_id, book)
        self._tell(user_id)
        return self.view(user_id)
