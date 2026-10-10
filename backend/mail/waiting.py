"""Waiting for a reply: sent emails that ask for something, followed until the answer comes.

For each mailbox that has this switched on, Enveliq looks at the Sent folder at each sync. A new email it has
not judged yet is shown once to the AI model, which says whether the person is waiting for an answer. Only then is a small
note kept: who it went to, the subject, the date, one line saying what is being waited for, and the email's Message-ID (so
a reply can be recognised by the thread). The text of the email is never kept.

A reply in the inbox that points back at that Message-ID (In-Reply-To or References) closes the note by itself. After a
number of days (3 by default, 1 to 14) with no reply the note shows on Home as an amber "Waiting on others" card.

Only mail sent after the switch was turned on is read: the first look at a mailbox treats what is already in Sent as old. Any
older email can be followed by hand from the Sent page.

Each person has one encrypted record (`wait:<user id>`). Everything in it came out of an email and a model, so each value
is cut short, stripped of control characters and shown only as plain text.
"""
from __future__ import annotations

import hashlib
import re
import secrets
import threading
import time
from typing import Any, Callable

RECORD_PREFIX = "wait:"
DEFAULT_DAYS = 3
MIN_DAYS, MAX_DAYS = 1, 14
KEEP_WAITING = 30 * 86400            # a note nobody answered or closed is forgotten after 30 days
KEEP_CLOSED = 7 * 86400              # an answered or dismissed note is listed for 7 days, then forgotten
KEEP_SEEN = 30 * 86400
RESTART_AFTER = 7 * 86400            # a mailbox not watched for this long starts again from "now": mail sent in the gap is not read
MAX_NOTES = 200
MAX_RECIPIENTS = 3
ACTIONS = ("got_reply", "later", "not_needed", "undo")

_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_ID = re.compile(r"<[^<>\s]{1,300}>")


def clean(value: Any, limit: int) -> str:
    if not isinstance(value, str):
        return ""
    return re.sub(r"\s+", " ", _CONTROL.sub("", value)).strip()[:limit]


def message_ids(*headers: Any) -> set[str]:
    """Every <message-id> named in In-Reply-To / References headers."""
    out: set[str] = set()
    for h in headers:
        for found in _ID.findall(str(h or "")):
            out.add(found.lower())
    return out


def mark_of(account_id: str, msgid: str) -> str:
    return hashlib.sha256(f"{account_id}|{msgid.lower()}".encode()).hexdigest()[:16]


class WaitBook:
    def __init__(self, vault: Any, clock: Callable[[], float] = time.time):
        self.vault = vault
        self.clock = clock
        self._lock = threading.RLock()

    # ---------- storage ----------

    def _load(self, user_id: str) -> dict[str, Any]:
        raw = self.vault.get_global(RECORD_PREFIX + user_id) or {}
        notes = raw.get("notes") if isinstance(raw.get("notes"), dict) else {}
        seen = raw.get("seen") if isinstance(raw.get("seen"), dict) else {}
        days = raw.get("days") if isinstance(raw.get("days"), int) and MIN_DAYS <= raw["days"] <= MAX_DAYS else DEFAULT_DAYS
        scans = raw.get("scans") if isinstance(raw.get("scans"), dict) else {}
        return {"notes": notes, "seen": seen, "days": days, "scans": scans}

    def _save(self, user_id: str, book: dict[str, Any]) -> None:
        self.vault.set_global(RECORD_PREFIX + user_id, book)

    def _purge(self, book: dict[str, Any], now: float) -> bool:
        changed = False
        for nid, n in list(book["notes"].items()):
            closed = n.get("closed_at")
            if (closed and now - closed > KEEP_CLOSED) or (not closed and now - float(n.get("sent_at") or 0) > KEEP_WAITING):
                del book["notes"][nid]
                changed = True
        for key, at in list(book["seen"].items()):
            if now - float(at or 0) > KEEP_SEEN:
                del book["seen"][key]
                changed = True
        if len(book["notes"]) > MAX_NOTES:
            for nid, _ in sorted(book["notes"].items(), key=lambda kv: float(kv[1].get("sent_at") or 0))[: len(book["notes"]) - MAX_NOTES]:
                del book["notes"][nid]
            changed = True
        return changed

    def enabled(self, user_id: str | None) -> bool:
        if not user_id:
            return False
        from . import features
        return bool(features.effective(self.vault, user_id).get("waiting"))

    # ---------- learning from the Sent folder ----------

    def judged(self, user_id: str, mark: str) -> bool:
        with self._lock:
            return mark in self._load(user_id)["seen"]

    def remember_judged(self, user_id: str, marks: list[str]) -> None:
        if not marks:
            return
        with self._lock:
            book = self._load(user_id)
            now = self.clock()
            for m in marks:
                book["seen"][m] = now
            self._purge(book, now)
            self._save(user_id, book)

    def scanned_at(self, user_id: str, account_id: str) -> float | None:
        with self._lock:
            at = self._load(user_id)["scans"].get(account_id)
        return float(at) if isinstance(at, (int, float)) else None

    def mark_scanned(self, user_id: str, account_id: str) -> None:
        with self._lock:
            book = self._load(user_id)
            book["scans"][account_id] = self.clock()
            self._save(user_id, book)

    def starting_fresh(self, user_id: str, account_id: str) -> bool:
        """True when this mailbox has just been switched on (or was left unwatched for a week): what is already in its Sent
        folder is taken as old and is not read."""
        at = self.scanned_at(user_id, account_id)
        return at is None or self.clock() - at > RESTART_AFTER

    def note_for(self, user_id: str, account_id: str, msgid: str) -> dict[str, Any] | None:
        mid = clean(msgid, 320).lower()
        with self._lock:
            for n in self._load(user_id)["notes"].values():
                if n.get("account_id") == account_id and n.get("msgid") == mid:
                    return n
        return None

    def states_for(self, user_id: str, account_id: str, msgids: list[str]) -> dict[str, str]:
        wanted = {clean(m, 320).lower(): m for m in msgids}
        with self._lock:
            return {wanted[n["msgid"]]: n.get("state") or "waiting" for n in self._load(user_id)["notes"].values()
                    if n.get("account_id") == account_id and n.get("msgid") in wanted}

    def add(self, user_id: str | None, account_id: str, msgid: str, to: list[str], subject: str, sent_at: float | None, ask: str) -> bool:
        """File a note for a sent email the model says is waiting on an answer. Returns True when a note was added."""
        if not user_id or not self.enabled(user_id):
            return False
        mid = clean(msgid, 320).lower()
        ask = clean(ask, 160)
        if not mid or not ask:
            return False
        now = self.clock()
        at = float(sent_at) if sent_at and 0 < sent_at <= now + 86400 else now
        recipients = [clean(t, 120) for t in to if clean(t, 120)][:MAX_RECIPIENTS]
        if not recipients:
            return False
        with self._lock:
            book = self._load(user_id)
            self._purge(book, now)
            if any(n.get("msgid") == mid for n in book["notes"].values()) or len(book["notes"]) >= MAX_NOTES + 20:
                return False
            nid = "w" + secrets.token_hex(12)[:23]
            book["notes"][nid] = {"id": nid, "account_id": account_id, "msgid": mid, "to": recipients, "subject": clean(subject, 200) or "(no subject)",
                                  "sent_at": at, "ask": ask, "state": "waiting", "snooze_until": 0, "closed_at": None, "reason": None}
            self._save(user_id, book)
            return True

    def waiting_ids(self, user_id: str, account_id: str) -> set[str]:
        with self._lock:
            return {n["msgid"] for n in self._load(user_id)["notes"].values() if n.get("account_id") == account_id and n.get("state") == "waiting"}

    def replies(self, user_id: str, account_id: str, seen_ids: set[str]) -> int:
        """Close every waiting note of this mailbox whose Message-ID a reply pointed back at."""
        if not seen_ids:
            return 0
        now = self.clock()
        count = 0
        with self._lock:
            book = self._load(user_id)
            for n in book["notes"].values():
                if n.get("account_id") == account_id and n.get("state") == "waiting" and n.get("msgid") in seen_ids:
                    n["state"], n["closed_at"], n["reason"] = "replied", now, "reply"
                    count += 1
            if count:
                self._save(user_id, book)
        return count

    # ---------- what the person sees ----------

    def _row(self, n: dict[str, Any], days: int, now: float) -> dict[str, Any]:
        waiting = n.get("state") == "waiting"
        age = max(0, int((now - float(n.get("sent_at") or now)) // 86400))
        due = waiting and now >= float(n.get("sent_at") or 0) + days * 86400 and now >= float(n.get("snooze_until") or 0)
        return {"id": n["id"], "account_id": n.get("account_id"), "to": n.get("to") or [], "subject": n.get("subject"), "sent_at": n.get("sent_at"),
                "ask": n.get("ask"), "state": n.get("state"), "due": due, "age_days": age, "snooze_until": n.get("snooze_until") or 0,
                "closed_at": n.get("closed_at"), "reason": n.get("reason")}

    def view(self, user_id: str) -> dict[str, Any]:
        if not self.enabled(user_id):
            return {"enabled": False, "days": DEFAULT_DAYS, "notes": [], "now": self.clock()}
        now = self.clock()
        with self._lock:
            book = self._load(user_id)
            if self._purge(book, now):
                self._save(user_id, book)
        days = book["days"]
        rows = [self._row(n, days, now) for n in book["notes"].values()]

        def order(r: dict[str, Any]) -> tuple[Any, ...]:
            group = 0 if r["due"] else 1 if r["state"] == "waiting" else 2
            return (group, float(r["sent_at"] or 0) if group < 2 else -float(r["closed_at"] or 0))

        rows.sort(key=order)
        return {"enabled": True, "days": days, "notes": rows, "now": now}

    # ---------- what the person can do ----------

    def act(self, user_id: str, nid: str, action: str) -> dict[str, Any]:
        if action not in ACTIONS:
            raise ValueError("unknown action")
        now = self.clock()
        with self._lock:
            book = self._load(user_id)
            note = book["notes"].get(nid)
            if note is None:
                raise KeyError(nid)
            if action == "got_reply":
                note["state"], note["closed_at"], note["reason"] = "replied", now, "you"
            elif action == "not_needed":
                note["state"], note["closed_at"], note["reason"] = "done", now, "not_needed"
            elif action == "later":
                if note.get("state") != "waiting":
                    raise ValueError("not waiting")
                note["snooze_until"] = now + book["days"] * 86400
            elif action == "undo":
                note["state"], note["closed_at"], note["reason"], note["snooze_until"] = "waiting", None, None, 0
            self._save(user_id, book)
        return self.view(user_id)

    def set_days(self, user_id: str, days: int) -> dict[str, Any]:
        if not isinstance(days, int) or isinstance(days, bool) or not MIN_DAYS <= days <= MAX_DAYS:
            raise ValueError("days")
        with self._lock:
            book = self._load(user_id)
            book["days"] = days
            self._save(user_id, book)
        return self.view(user_id)
