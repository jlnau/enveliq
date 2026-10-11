"""Subscriptions and free trials, followed from the emails about them.

When the AI summary of an incoming email says it is about a paid subscription or a free trial (started, trial started,
renewal notice, receipt, cancelled), the facts are filed under one subscription. The AI reads the email once and only
copies what it says. Everything that is a date or a count is worked out here, in plain code: when a free trial ends
(from a date, or from "30 days" counted from the email's date), the next renewal (rolled forward by the billing period when
the date has passed), and how many days are left. Nothing here is decided by a model.

Each person has one encrypted record (`subs:<user id>`). It holds only: the service, the amount as written, the billing
period, the renewal and trial dates, whether it was cancelled, one web address and a mark for each email already
filed. No email text, no subject and no address of the sender are stored.

Everything came out of an email written by a stranger and read by a model, so every value is cut to a short length,
stripped of control characters and shown only as plain text. An email that carries a "Be careful" warning is never
filed, so a fake renewal notice cannot put a card on Home. The only link offered is the home page of the sender's own
domain, and only when it passes the same public-address rule as unsubscribe links; the page shows the name of that
website before it opens. Enveliq never contacts the company: the person's own browser does.
"""
from __future__ import annotations

import calendar
import hashlib
import re
import secrets
import threading
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable

from . import scamcheck
from .tasks import parse_due, zone
from .unsub import safe_url

RECORD_PREFIX = "subs:"
KINDS = ("started", "trial_started", "renewal_notice", "receipt", "cancelled")
PERIODS = ("weekly", "fortnightly", "monthly", "quarterly", "yearly")
ACTIONS = ("not_subscription", "cancelled", "keep")
MAX_ITEMS = 80
MAX_EVENTS = 30
KEEP_STALE = 400 * 86400             # nothing heard for 400 days (a yearly bill is heard from once a year)
KEEP_CANCELLED = 30 * 86400
KEEP_ENDED_TRIAL = 14 * 86400
KEEP_DISMISSED = 400 * 86400
NUDGE_DEFAULT = 3
NUDGE_MIN, NUDGE_MAX = 1, 14

_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
# Senders that deliver mail or take payments for other companies. Their home page is not the company's.
NOT_COMPANY = {
    "gmail.com", "googlemail.com", "outlook.com", "hotmail.com", "live.com", "msn.com", "yahoo.com", "icloud.com", "me.com", "aol.com",
    "proton.me", "protonmail.com", "sendgrid.net", "sendgrid.com", "amazonses.com", "mailchimp.com", "mcsv.net", "rsgsv.net", "mandrillapp.com",
    "mailgun.org", "mailgun.com", "postmarkapp.com", "sparkpostmail.com", "constantcontact.com", "klaviyo.com", "hubspot.com", "customer.io",
    "stripe.com", "paddle.com", "paypal.com", "fastspring.com", "chargebee.com", "recurly.com",
}


def clean(value: Any, limit: int) -> str:
    if not isinstance(value, str):
        return ""
    return re.sub(r"\s+", " ", _CONTROL.sub("", value)).strip()[:limit]


def service_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", clean(value, 80).lower())


def company_link(sender_address: Any) -> str | None:
    """The home page of the domain the email came from, or None. Only a plain public web address; never a number, never a mail service."""
    text = clean(sender_address, 200).lower()
    host = text.rsplit("@", 1)[-1].strip(" <>.") if "@" in text else ""
    if not host or "." not in host or not re.fullmatch(r"[a-z0-9.\-]+", host) or not re.fullmatch(r"[a-z]{2,24}", host.rsplit(".", 1)[-1]):
        return None                                   # a bare number, or no real ending, is never a company
    domain = scamcheck.registrable(host)
    if not domain or domain in NOT_COMPANY or "." not in domain:
        return None
    url = f"https://{domain}/"
    return url if safe_url(url) else None


def add_months(day: date, months: int, anchor_day: int | None = None) -> date:
    index = day.year * 12 + (day.month - 1) + months
    year, month = divmod(index, 12)
    month += 1
    want = anchor_day or day.day
    return date(year, month, min(want, calendar.monthrange(year, month)[1]))


def step(day: date, period: str, times: int, anchor_day: int | None = None) -> date:
    """`day` moved forward by `times` billing periods."""
    if period == "weekly":
        return day + timedelta(days=7 * times)
    if period == "fortnightly":
        return day + timedelta(days=14 * times)
    if period == "monthly":
        return add_months(day, times, anchor_day)
    if period == "quarterly":
        return add_months(day, 3 * times, anchor_day)
    return add_months(day, 12 * times, anchor_day)


def roll_forward(anchor: date, period: str | None, today: date) -> date | None:
    """The first renewal on or after `today`, counted from a known one. None when it has passed and the period is unknown."""
    if anchor >= today:
        return anchor
    if period not in PERIODS:
        return None
    n = 1
    while step(anchor, period, n, anchor.day) < today:
        n += 1
        if n > 4000:
            return None
    return step(anchor, period, n, anchor.day)


def _iso(day: date | None) -> str | None:
    return day.isoformat() if day else None


def _day(text: Any) -> date | None:
    try:
        return date.fromisoformat(text) if isinstance(text, str) else None
    except ValueError:
        return None


class SubBook:
    def __init__(self, vault: Any, tz_of: Callable[[str], str | None] | None = None, clock: Callable[[], float] = time.time):
        self.vault = vault
        self.tz_of = tz_of or (lambda user_id: None)
        self.clock = clock
        self._lock = threading.RLock()

    # ---------- storage ----------

    def _load(self, user_id: str) -> dict[str, Any]:
        raw = self.vault.get_global(RECORD_PREFIX + user_id) or {}
        items = raw.get("items") if isinstance(raw.get("items"), dict) else {}
        dismissed = raw.get("dismissed") if isinstance(raw.get("dismissed"), dict) else {}
        days = raw.get("nudge_days")
        days = days if isinstance(days, int) and not isinstance(days, bool) and NUDGE_MIN <= days <= NUDGE_MAX else NUDGE_DEFAULT
        return {"items": items, "dismissed": dismissed, "nudge_days": days}

    def _save(self, user_id: str, book: dict[str, Any]) -> None:
        self.vault.set_global(RECORD_PREFIX + user_id, book)

    def _today(self, user_id: str, now: float | None = None) -> date:
        return datetime.fromtimestamp(self.clock() if now is None else now, zone(self.tz_of(user_id))).date()

    def enabled(self, user_id: str | None) -> bool:
        if not user_id:
            return False
        from . import features
        return bool(features.effective(self.vault, user_id).get("subscriptions"))

    def _purge(self, book: dict[str, Any], now: float, today: date) -> bool:
        changed = False
        for sid, s in list(book["items"].items()):
            nxt = self.next_date(s, today)
            ended = s.get("status") == "trial" and _day(s.get("trial_ends")) is not None and _day(s["trial_ends"]) < today
            old = (
                now - float(s.get("updated") or 0) > KEEP_STALE
                or (s.get("status") == "cancelled" and now - float(s.get("cancelled_at") or s.get("updated") or 0) > KEEP_CANCELLED)
                or (ended and not nxt and now - float(s.get("updated") or 0) > KEEP_ENDED_TRIAL)
            )
            if old:
                del book["items"][sid]
                changed = True
        for key, at in list(book["dismissed"].items()):
            if now - float(at or 0) > KEEP_DISMISSED:
                del book["dismissed"][key]
                changed = True
        if len(book["items"]) > MAX_ITEMS:
            for sid, _ in sorted(book["items"].items(), key=lambda kv: float(kv[1].get("updated") or 0))[: len(book["items"]) - MAX_ITEMS]:
                del book["items"][sid]
            changed = True
        return changed

    # ---------- dates, worked out in code ----------

    @staticmethod
    def next_date(item: dict[str, Any], today: date) -> dict[str, Any] | None:
        """What happens next: a free trial ending, or a renewal. None when nothing is coming (cancelled, trial over, no date)."""
        if item.get("status") == "cancelled":
            return None
        if item.get("status") == "trial":
            end = _day(item.get("trial_ends"))
            if end is not None and end >= today:
                return {"kind": "trial_ends", "on": end.isoformat(), "days": (end - today).days}
            return None
        anchor = _day(item.get("renews"))
        if anchor is None:
            return None
        when = roll_forward(anchor, item.get("period"), today)
        if when is None:
            return None
        return {"kind": "renews", "on": when.isoformat(), "days": (when - today).days}

    # ---------- learning from an email ----------

    @staticmethod
    def _clean(raw: Any) -> dict[str, Any] | None:
        if not isinstance(raw, dict) or raw.get("kind") not in KINDS:
            return None
        service = clean(raw.get("service"), 60)
        if not service_key(service):
            return None
        days = raw.get("trial_days")
        return {
            "kind": raw["kind"], "service": service, "amount": clean(raw.get("amount"), 30) or None,
            "period": raw.get("period") if raw.get("period") in PERIODS else None,
            "renews_text": clean(raw.get("renews_on"), 60) or None, "trial_text": clean(raw.get("trial_ends_on"), 60) or None,
            "trial_days": days if isinstance(days, int) and not isinstance(days, bool) and 1 <= days <= 400 else None,
        }

    def observe(self, user_id: str | None, account_id: str, message_id: str, received_at: float | None, raw: Any, link: str | None = None) -> bool:
        """File what an email says about a subscription. Returns True when one was added or changed."""
        if not user_id or not self.enabled(user_id):
            return False
        info = self._clean(raw)
        if info is None:
            return False
        now = self.clock()
        at = float(received_at) if received_at and 0 < received_at <= now + 86400 else now
        sent_on = datetime.fromtimestamp(at, timezone.utc).date()

        def sane(day: date | None) -> date | None:
            return day if day and sent_on - timedelta(days=400) <= day <= sent_on + timedelta(days=800) else None

        renews = sane(parse_due(info["renews_text"], sent_on, sent_on))
        trial_end = sane(parse_due(info["trial_text"], sent_on, sent_on))
        if trial_end is None and info["trial_days"] and info["kind"] in ("started", "trial_started"):
            trial_end = sent_on + timedelta(days=info["trial_days"])                  # counted here, from the email's own date
        key = service_key(info["service"])
        mark = hashlib.sha256(f"{account_id}|{message_id}".encode()).hexdigest()[:16]
        link = link if link and safe_url(link) else None
        today = self._today(user_id, now)
        with self._lock:
            book = self._load(user_id)
            self._purge(book, now, today)
            if any(e.get("m") == mark for s in book["items"].values() for e in s["events"]):
                return False                                                        # this very email was already filed
            if f"s:{key}" in book["dismissed"]:
                return False
            item = next((s for s in book["items"].values() if s.get("key") == key), None)
            if item is None:
                if len(book["items"]) >= MAX_ITEMS + 10:
                    return False
                sid = "b" + secrets.token_hex(12)[:23]
                item = {"id": sid, "service": info["service"], "key": key, "amount": None, "period": None, "status": "active", "renews": None,
                        "estimated": False, "trial_ends": None, "link": None, "first_seen": at, "updated": at, "events": []}
                book["items"][sid] = item
            self._apply(item, info, renews, trial_end, sent_on, at, mark, link)
            item["updated"] = max(float(item.get("updated") or 0), at)
            self._save(user_id, book)
            return True

    @staticmethod
    def _apply(item: dict[str, Any], info: dict[str, Any], renews: date | None, trial_end: date | None, sent_on: date, at: float, mark: str, link: str | None) -> None:
        kind = info["kind"]
        newest = at >= float(item.get("facts_at") or 0)                             # an older email never overwrites newer facts
        if link and not item.get("link"):
            item["link"] = link
        if newest:
            if info["amount"]:
                item["amount"] = info["amount"]
            if info["period"]:
                item["period"] = info["period"]
        if kind == "cancelled":
            if newest:
                item["status"], item["cancelled_at"] = "cancelled", at
        elif kind in ("started", "trial_started") and trial_end is not None:
            if newest:
                item["status"], item["trial_ends"], item["cancelled_at"] = "trial", trial_end.isoformat(), None
        elif kind in ("started", "trial_started"):
            if newest:
                item["status"], item["cancelled_at"] = "active", None               # a (re)start without a trial
        elif item.get("status") == "trial" and newest:
            end = _day(item.get("trial_ends"))
            if kind == "receipt" or (end is not None and end < sent_on):
                item["status"] = "active"                                           # the first real charge ends the trial
        if kind != "cancelled" and item.get("status") in ("active", "trial") and newest:
            if renews is not None:
                item["renews"], item["estimated"] = renews.isoformat(), False
            elif kind in ("started", "receipt") and item.get("period") in PERIODS and item.get("status") == "active":
                item["renews"], item["estimated"] = step(sent_on, item["period"], 1).isoformat(), True      # worked out here, and shown as "about"
        if newest:
            item["facts_at"] = at
        item["events"].append({"at": at, "kind": kind, "m": mark})
        item["events"].sort(key=lambda e: e["at"])
        del item["events"][:-MAX_EVENTS]

    # ---------- showing it ----------

    @staticmethod
    def _row(s: dict[str, Any], today: date, soon: int) -> dict[str, Any]:
        nxt = SubBook.next_date(s, today)
        url = s.get("link") if s.get("link") and safe_url(s["link"]) else None
        host = re.sub(r"^https?://", "", url or "").split("/")[0] if url else None
        end = _day(s.get("trial_ends"))
        return {
            "id": s["id"], "service": s.get("service"), "amount": s.get("amount"), "period": s.get("period"), "status": s.get("status"),
            "next": nxt, "estimated": bool(s.get("estimated")) and bool(nxt and nxt["kind"] == "renews"),
            "trial_over": bool(s.get("status") == "trial" and end is not None and end < today),
            "soon": bool(nxt and nxt["days"] <= soon), "link": {"url": url, "host": host} if url else None, "updated": s.get("updated"),
        }

    def view(self, user_id: str) -> dict[str, Any]:
        if not self.enabled(user_id):
            return {"enabled": False, "items": [], "nudge_days": NUDGE_DEFAULT, "today": None}
        now = self.clock()
        today = self._today(user_id, now)
        with self._lock:
            book = self._load(user_id)
            if self._purge(book, now, today):
                self._save(user_id, book)
        rows = [self._row(s, today, book["nudge_days"]) for s in book["items"].values()]

        def order(r: dict[str, Any]) -> tuple[Any, ...]:
            group = 0 if r["next"] else 1 if r["status"] != "cancelled" else 2
            return (group, r["next"]["on"] if r["next"] else "9999", -(r["updated"] or 0))

        rows.sort(key=order)
        return {"enabled": True, "items": rows, "nudge_days": book["nudge_days"], "today": today.isoformat()}

    def due_nudges(self, user_id: str, now: float | None = None) -> list[dict[str, Any]]:
        """Subscriptions coming up within the person's number of days. Each has a `key` that is the same for the same coming date."""
        if not self.enabled(user_id):
            return []
        now = self.clock() if now is None else now
        today = self._today(user_id, now)
        book = self._load(user_id)
        out = []
        for s in book["items"].values():
            nxt = self.next_date(s, today)
            if nxt and nxt["days"] <= book["nudge_days"]:
                out.append({"key": f"{s['id']}|{nxt['on']}", "service": s.get("service"), "amount": s.get("amount"), "kind": nxt["kind"], "days": nxt["days"], "on": nxt["on"]})
        out.sort(key=lambda n: (n["days"], n["service"] or ""))
        return out

    # ---------- what the person can do ----------

    def set_nudge_days(self, user_id: str, days: int) -> dict[str, Any]:
        if isinstance(days, bool) or not isinstance(days, int) or not NUDGE_MIN <= days <= NUDGE_MAX:
            raise ValueError("days")
        with self._lock:
            book = self._load(user_id)
            book["nudge_days"] = days
            self._save(user_id, book)
        return self.view(user_id)

    def act(self, user_id: str, sid: str, action: str) -> dict[str, Any]:
        if action not in ACTIONS:
            raise ValueError("unknown action")
        now = self.clock()
        with self._lock:
            book = self._load(user_id)
            item = book["items"].get(sid)
            if item is None:
                raise KeyError(sid)
            if action == "cancelled":
                item["status"], item["cancelled_at"] = "cancelled", now
            elif action == "keep":
                if item.get("status") != "cancelled":
                    raise ValueError("not cancelled")
                item["status"], item["cancelled_at"] = "active", None
            elif action == "not_subscription":
                if item.get("key"):
                    book["dismissed"][f"s:{item['key']}"] = now
                del book["items"][sid]
            self._save(user_id, book)
        return self.view(user_id)
