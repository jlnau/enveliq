"""Tasks that make themselves.

When the AI summary of an email says something needs doing, a task exists for it. Nobody presses a button.
The task follows its email: replying, Reviewed, Archive, Bin, or the email leaving the inbox ends it.

Each person has one encrypted record (`tasks:<user id>`) that holds only what the task list needs: the title and
detail the summary suggested, the sender's name, a date, and the state. No email text and no mailbox links are
stored here. A task is found again from its email by the (mailbox, message) pair, so one email never makes two tasks.

Everything is worked out in the person's own time zone (the browser tells the server which one). A task with no date
is due the day it was made, so nothing is ever left floating. A task that was missed is shown under Today, never
as an alarm: it says how long it has been waiting.
"""
from __future__ import annotations

import hashlib
import re
import secrets
import threading
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

RECORD_PREFIX = "tasks:"
CLOSED_KEEP_SECONDS = 36 * 3600
MAX_TASKS = 500
MAX_MANUAL_OPEN = 200
STATE_OPEN, STATE_DONE, STATE_REMOVED = "open", "done", "removed"
REASONS = {
    "you": "Done",
    "replied": "Done by itself · you replied",
    "handled": "Done by itself · the email was dealt with",
    "gone": "Done by itself · the email left your inbox",
}
MOVES = ("later_today", "tomorrow", "weekend", "next_week", "date")

_MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
_DAYS = {"sun": 6, "mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5}       # Python weekday numbers
_DAY_WORD = re.compile(r"\b(sun(?:day)?|mon(?:day)?|tue(?:s|sday)?|wed(?:nesday)?|thu(?:rs|rsday)?|fri(?:day)?|sat(?:urday)?)\b")
_URGENT = re.compile(r"\b(asap|a\.s\.a\.p|immediately|urgent(?:ly)?|right away|straight away|now|eod|end of (?:the )?day|within 24 hours)\b")
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def clean(value: Any, limit: int) -> str:
    return _CONTROL.sub("", str(value or "")).replace("\r", " ").replace("\n", " ").strip()[:limit]


def zone(name: str | None) -> Any:
    """The person's time zone; UTC when it is missing or unknown."""
    if name and isinstance(name, str) and len(name) <= 64 and re.fullmatch(r"[A-Za-z0-9_+\-/]+", name):
        try:
            return ZoneInfo(name)
        except (ZoneInfoNotFoundError, ValueError, OSError):
            pass
    return timezone.utc


def valid_zone(name: Any) -> bool:
    return isinstance(name, str) and zone(name) is not timezone.utc or name == "UTC"


def parse_due(text: str | None, ref: date, today: date) -> date | None:
    """A date from words like 'Friday', 'tomorrow', '12 Oct', '2026-10-12' or 'ASAP'. `ref` is the day the email was
    sent (so 'Friday' means the Friday after it), `today` is today. None when no date can be found."""
    if not text:
        return None
    t = str(text).lower()
    m = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", t)
    if m:
        try:
            return date(int(m[1]), int(m[2]), int(m[3]))
        except ValueError:
            return None
    months = "|".join(_MONTHS)
    day = mon = year = None
    m = re.search(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+({months})[a-z]*\.?(?:,?\s+(\d{{4}}))?", t)
    if m:
        day, mon, year = int(m[1]), _MONTHS.index(m[2]), int(m[3]) if m[3] else 0
    else:
        m = re.search(rf"\b({months})[a-z]*\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?(?:,?\s+(\d{{4}}))?", t)
        if m:
            mon, day, year = _MONTHS.index(m[1]), int(m[2]), int(m[3]) if m[3] else 0
    if m and day is not None and 1 <= day <= 31:
        try:
            found = date(year or ref.year, mon + 1, day)
            if not year and found < ref - timedelta(days=183):
                found = date(ref.year + 1, mon + 1, day)
            return found
        except ValueError:
            return None
    if _URGENT.search(t):
        return today
    if re.search(r"\b(today|tonight|this evening)\b", t):
        return ref
    if re.search(r"\btomorrow\b", t):
        return ref + timedelta(days=1)
    m = _DAY_WORD.search(t)
    if m:
        return ref + timedelta(days=(_DAYS[m[1][:3]] - ref.weekday()) % 7)
    return None


def task_id(account_id: str, message_id: str) -> str:
    return "t" + hashlib.sha256(f"{account_id}|{message_id}".encode()).hexdigest()[:23]


class TaskBook:
    def __init__(self, vault: Any, clock: Callable[[], float] = time.time):
        self.vault = vault
        self.clock = clock
        self._lock = threading.RLock()
        self.listeners: list[Callable[[str, dict[str, Any], str], None]] = []   # (user id, task, change) for calendar and To-do mirrors

    # ---------- storage ----------

    def _load(self, user_id: str) -> dict[str, Any]:
        raw = self.vault.get_global(RECORD_PREFIX + user_id) or {}
        items = raw.get("items") if isinstance(raw.get("items"), dict) else {}
        return {"tz": raw.get("tz") if isinstance(raw.get("tz"), str) else None, "items": items}

    def _save(self, user_id: str, book: dict[str, Any]) -> None:
        self.vault.set_global(RECORD_PREFIX + user_id, book)

    def _emit(self, user_id: str, task: dict[str, Any], change: str) -> None:
        for fn in list(self.listeners):
            try:
                fn(user_id, dict(task), change)
            except Exception:                       # a calendar or To-do that is down never breaks the list
                pass

    def timezone_of(self, user_id: str) -> str | None:
        with self._lock:
            return self._load(user_id)["tz"]

    def set_timezone(self, user_id: str, name: str | None) -> None:
        if not name or not valid_zone(name):
            return
        with self._lock:
            book = self._load(user_id)
            if book["tz"] != name:
                book["tz"] = name
                self._save(user_id, book)

    def _today(self, book: dict[str, Any], now: float) -> date:
        return datetime.fromtimestamp(now, zone(book["tz"])).date()

    # ---------- keeping the list in step with the mail ----------

    def reconcile(self, user_id: str) -> None:
        """Make a task for every email that needs one, and end the tasks whose email has been dealt with."""
        from .service import MAIL_METHODS
        now = self.clock()
        with self._lock:
            book = self._load(user_id)
            items: dict[str, dict[str, Any]] = book["items"]
            tz = zone(book["tz"])
            today = datetime.fromtimestamp(now, tz).date()
            live: dict[str, dict[str, Any]] = {}
            try:
                accounts = [a for a in self.vault.list_accounts() if a.get("owner_user_id") == user_id and a.get("auth_method") in MAIL_METHODS]
            except Exception:
                return
            changed, events = False, []
            for account in accounts:
                try:
                    messages = self.vault.list_messages(account["id"])
                except Exception:
                    continue
                for m in messages:
                    tid = task_id(account["id"], m["id"])
                    live[tid] = m
                    spec = m.get("suggested_task")
                    if tid in items or m.get("state", "unread") != "unread" or m.get("from_all_mail") or m.get("replied_at") \
                            or not isinstance(spec, dict) or not spec.get("title"):
                        continue
                    sent = datetime.fromtimestamp(m["received_at"], tz).date() if m.get("received_at") else today
                    due = parse_due(spec.get("due"), sent, today) or today
                    items[tid] = {
                        "id": tid, "account_id": account["id"], "message_id": m["id"],
                        "title": clean(spec.get("title"), 300), "detail": clean(spec.get("detail"), 2000),
                        "sender": clean(m.get("sender_display") or m.get("sender_address"), 200),
                        "priority": m.get("priority") if m.get("priority") in ("low", "normal", "high") else "normal",
                        "received": m.get("received_at") or 0,
                        "due": due.isoformat(), "remind_at": None, "state": STATE_OPEN, "reason": None,
                        "created_at": now, "closed_at": None, "moved": False, "ext": {},
                    }
                    events.append((items[tid], "added"))
                    changed = True
            known_accounts = {a["id"] for a in accounts}
            for tid, t in list(items.items()):
                if t["state"] != STATE_OPEN or t.get("manual"):        # a task the person made by hand stays until they finish it
                    continue
                m = live.get(tid)
                reason = None
                if t["account_id"] not in known_accounts or m is None:
                    reason = "gone"
                elif m.get("state", "unread") != "unread":
                    reason = "handled"
                elif m.get("replied_at"):
                    reason = "replied"
                if reason:
                    self._close(t, reason, now)
                    events.append((t, "closed"))
                    changed = True
            for tid, t in list(items.items()):          # tidy up: finished tasks are shown for a day and a half
                if t["state"] != STATE_OPEN and now - float(t.get("closed_at") or 0) > CLOSED_KEEP_SECONDS and (t["state"] == STATE_DONE or tid not in live):
                    del items[tid]
                    changed = True
            if len(items) > MAX_TASKS:
                for tid in sorted((k for k, v in items.items() if v["state"] != STATE_OPEN), key=lambda k: items[k].get("closed_at") or 0)[:len(items) - MAX_TASKS]:
                    del items[tid]
                changed = True
            if changed:
                self._save(user_id, book)
        for t, change in events:
            self._emit(user_id, t, change)

    @staticmethod
    def _close(task: dict[str, Any], reason: str, now: float) -> None:
        task.update(state=STATE_DONE, reason=reason, closed_at=now)

    def close_message(self, user_id: str, account_id: str, message_id: str, reason: str) -> None:
        """The person just dealt with this email: end its task now, saying why."""
        if reason not in REASONS:
            return
        with self._lock:
            book = self._load(user_id)
            t = book["items"].get(task_id(account_id, message_id))
            if not t or t["state"] != STATE_OPEN or t.get("manual"):
                return
            self._close(t, reason, self.clock())
            self._save(user_id, book)
        self._emit(user_id, t, "closed")

    # ---------- reading ----------

    def view(self, user_id: str, tz: str | None = None) -> dict[str, Any]:
        if tz:
            self.set_timezone(user_id, tz)
        self.reconcile(user_id)
        now = self.clock()
        with self._lock:
            book = self._load(user_id)
        today = self._today(book, now)
        rows = []
        for t in book["items"].values():
            if t["state"] == STATE_REMOVED:
                continue
            due = date.fromisoformat(t["due"])
            rows.append({
                "id": t["id"], "account_id": t["account_id"], "message_id": t["message_id"], "title": t["title"], "detail": t["detail"],
                "sender": t["sender"], "priority": t["priority"], "due": t["due"], "days": (due - today).days, "remind_at": t["remind_at"],
                "state": t["state"], "reason": t["reason"], "reason_text": REASONS.get(t["reason"] or "", ""), "closed_at": t["closed_at"],
                "moved": t["moved"], "manual": bool(t.get("manual")),
            })
        rows.sort(key=lambda r: (r["state"] != STATE_OPEN, max(r["days"], 0), 0 if r["priority"] == "high" else 1, r["days"], -self._received(book, r["id"])))
        return {"today": today.isoformat(), "tz": book["tz"], "now": now, "tasks": rows}

    @staticmethod
    def _received(book: dict[str, Any], tid: str) -> float:
        return float(book["items"][tid].get("received") or 0)

    def snapshot(self, user_id: str) -> list[dict[str, Any]]:
        """Every task the person still has (open, finished and removed ones), for calendar and To-do mirrors."""
        with self._lock:
            return [dict(t) for t in self._load(user_id)["items"].values()]

    def held(self, user_id: str | None) -> set[tuple[str, str]]:
        """(account id, message id) of every email that has an open task. Such an email is never removed from Enveliq."""
        if not user_id:
            return set()
        with self._lock:
            return {(t["account_id"], t["message_id"]) for t in self._load(user_id)["items"].values() if t["state"] == STATE_OPEN}

    def open_tasks(self, user_id: str) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(t) for t in self._load(user_id)["items"].values() if t["state"] == STATE_OPEN]

    # ---------- the person's own changes ----------

    def add(self, user_id: str, account_id: str, message_id: str, title: str, *, on: str | None = None) -> dict[str, Any]:
        """A task the person writes themselves for one of their own emails (for example "ring the plumber when I get home").
        It does not close by itself when the email is dealt with: only the person finishes it. `on` is YYYY-MM-DD, today when
        left out. Raises KeyError when the email is not one of this person's, ValueError for a bad title, date or a full list."""
        from .service import MAIL_METHODS
        title = clean(title, 300)
        if not title:
            raise ValueError("no title")
        now = self.clock()
        with self._lock:
            try:
                mine = {a["id"] for a in self.vault.list_accounts() if a.get("owner_user_id") == user_id and a.get("auth_method") in MAIL_METHODS}
            except Exception:
                raise KeyError(account_id) from None
            if account_id not in mine:
                raise KeyError(account_id)
            try:
                msg = next((m for m in self.vault.list_messages(account_id) if m["id"] == message_id), None)
            except Exception:
                msg = None
            if msg is None:
                raise KeyError(message_id)
            book = self._load(user_id)
            items: dict[str, dict[str, Any]] = book["items"]
            if sum(1 for t in items.values() if t.get("manual") and t["state"] == STATE_OPEN) >= MAX_MANUAL_OPEN:
                raise ValueError("too many")
            today = self._today(book, now)
            if on:
                try:
                    due = date.fromisoformat(on)
                except ValueError:
                    raise ValueError("bad date") from None
                if not today <= due <= today + timedelta(days=366):
                    raise ValueError("date out of range")
            else:
                due = today
            tid = "t" + secrets.token_hex(11) + "0"
            while tid in items:
                tid = "t" + secrets.token_hex(11) + "0"
            items[tid] = {
                "id": tid, "account_id": account_id, "message_id": message_id, "title": title, "detail": "",
                "sender": clean(msg.get("sender_display") or msg.get("sender_address"), 200),
                "priority": "normal", "received": msg.get("received_at") or 0,
                "due": due.isoformat(), "remind_at": None, "state": STATE_OPEN, "reason": None,
                "created_at": now, "closed_at": None, "moved": False, "ext": {}, "manual": True,
            }
            self._save(user_id, book)
            out = dict(items[tid])
        self._emit(user_id, out, "added")
        return out

    def act(self, user_id: str, tid: str, action: str, *, to: str | None = None, on: str | None = None) -> dict[str, Any]:
        """done | reopen | remove | not_today | move (to: later_today, tomorrow, weekend, next_week, date; on: YYYY-MM-DD)."""
        now = self.clock()
        with self._lock:
            book = self._load(user_id)
            t = book["items"].get(tid)
            if t is None:
                raise KeyError(tid)
            tz = zone(book["tz"])
            local = datetime.fromtimestamp(now, tz)
            today = local.date()
            change = "updated"
            if action == "done":
                if t["state"] == STATE_OPEN:
                    self._close(t, "you", now)
                change = "closed"
            elif action == "reopen":
                t.update(state=STATE_OPEN, reason=None, closed_at=None)
                change = "reopened"
            elif action == "remove":
                t.update(state=STATE_REMOVED, reason=None, closed_at=now)
                change = "closed"
            elif action in ("not_today", "move"):
                if t["state"] != STATE_OPEN:
                    raise ValueError("closed")
                target = "tomorrow" if action == "not_today" else to
                remind = None
                if target == "later_today":
                    evening = datetime.combine(today, datetime.min.time(), tz).replace(hour=18)
                    soon = local + timedelta(hours=1)
                    when = max(evening, soon)
                    if when.date() != today or when.hour >= 22:
                        new = today + timedelta(days=1)
                    else:
                        new, remind = today, when.timestamp()
                elif target == "tomorrow":
                    new = today + timedelta(days=1)
                elif target == "weekend":
                    new = today + timedelta(days=(5 - today.weekday()) % 7 or 7)
                elif target == "next_week":
                    new = today + timedelta(days=7 - today.weekday())
                elif target == "date":
                    try:
                        new = date.fromisoformat(on or "")
                    except ValueError:
                        raise ValueError("bad date") from None
                    if not today <= new <= today + timedelta(days=366):
                        raise ValueError("date out of range")
                else:
                    raise ValueError("bad move")
                t.update(due=new.isoformat(), remind_at=remind, moved=True)
                t["ext"] = dict(t.get("ext") or {}, notified=None)          # a moved task is allowed to remind again
            else:
                raise ValueError("bad action")
            self._save(user_id, book)
            out = dict(t)
        self._emit(user_id, out, change)
        return out
