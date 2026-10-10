"""Following online orders from the emails about them.

When the AI summary of an incoming email says it is about an order or a parcel (confirmed, shipped, out for delivery,
delivered, delayed), the facts are filed under one order. Each later email about the same order updates that order's
status and expected date. A "delivered" email puts a card on Home that asks the person to confirm the parcel arrived.

Each person has one encrypted record (`ship:<user id>`). It holds only: the shop, the order and tracking numbers, the
carrier, a few words about the items, the status, the expected date, and the date and subject of each email that
belonged to the order. No email text, no addresses and no mailbox links are stored.

Everything here came out of an email written by a stranger and read by a model, so every value is cut to a short length,
stripped of control characters, and shown only as plain text. A carrier's tracking page is offered only from a short
fixed list of web addresses; the tracking number is the one part that varies, and it is limited to letters and digits.
Enveliq never contacts a carrier: the person's own browser opens the page.
"""
from __future__ import annotations

import hashlib
import re
import secrets
import threading
import time
from datetime import date, datetime, timezone
from typing import Any, Callable
from urllib.parse import quote, urlsplit

from .tasks import parse_due
from .unsub import safe_url

RECORD_PREFIX = "ship:"
KEEP_DELIVERED = 14 * 86400          # an arrived order is listed for 14 days, then forgotten
KEEP_OPEN = 90 * 86400               # an order with no news for 90 days is forgotten
KEEP_DISMISSED = 90 * 86400
SNOOZE = 20 * 3600
MAX_ORDERS = 150
MAX_EVENTS = 30
KINDS = ("order_confirmed", "shipped", "out_for_delivery", "delivered", "delayed")
STATUS_OF = {"order_confirmed": "ordered", "shipped": "shipped", "out_for_delivery": "out_for_delivery", "delivered": "delivered", "delayed": "shipped"}
RANK = {"ordered": 0, "shipped": 1, "out_for_delivery": 2, "delivered": 3}
ACTIONS = ("confirm", "not_yet", "not_order", "track", "undo")

_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

# Carrier name (lower case, as it appears in the email) -> tracking page. {n} is the tracking number.
CARRIERS: list[tuple[tuple[str, ...], str]] = [
    (("australia post", "auspost"), "https://auspost.com.au/mypost/track/details/{n}"),
    (("ups", "united parcel"), "https://www.ups.com/track?tracknum={n}"),
    (("fedex", "federal express"), "https://www.fedex.com/fedextrack/?trknbr={n}"),
    (("dhl",), "https://www.dhl.com/global-en/home/tracking/tracking-express.html?submit=1&tracking-id={n}"),
    (("usps", "united states postal"), "https://tools.usps.com/go/TrackConfirmAction?tLabels={n}"),
    (("royal mail",), "https://www.royalmail.com/track-your-item#/tracking-results/{n}"),
    (("canada post",), "https://www.canadapost-postescanada.ca/track-reperage/en#/search?searchFor={n}"),
    (("aramex",), "https://www.aramex.com/track/results?ShipmentNumber={n}"),
    (("sendle",), "https://track.sendle.com/tracking?ref={n}"),
    (("couriers please", "couriersplease"), "https://www.couriersplease.com.au/tools-track/no/{n}"),
    (("tnt",), "https://www.tnt.com/express/en_au/site/shipping-tools/tracking.html?searchType=con&cons={n}"),
    (("dpd",), "https://track.dpd.co.uk/parcels/{n}"),
    (("evri", "hermes"), "https://www.evri.com/track/parcel/{n}"),
    (("yodel",), "https://www.yodel.co.uk/track/{n}"),
]
FIXED_NAMES = ["Australia Post", "UPS", "FedEx", "DHL", "USPS", "Royal Mail", "Canada Post", "Aramex", "Sendle", "Couriers Please", "TNT", "DPD", "Evri", "Yodel"]

# Carriers the household has added. One list for everybody, so a carrier one person adds is there for all.
SHARED_RECORD = "ship:carriers"
MAX_SHARED = 40
_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9 .&'\-]{1,39}")


class CarrierError(ValueError):
    """Something the person can fix; the text is safe to show them."""


def clean(value: Any, limit: int) -> str:
    if not isinstance(value, str):
        return ""
    return re.sub(r"\s+", " ", _CONTROL.sub("", value)).strip()[:limit]


def order_key(value: Any) -> str | None:
    """A comparable form of an order number, or None when it does not look like one."""
    text = clean(value, 60).lstrip("#").strip()
    key = re.sub(r"[^a-z0-9]", "", text.lower())
    return key if 3 <= len(key) <= 40 and re.search(r"\d", key) else None


def tracking_key(value: Any) -> str | None:
    key = re.sub(r"[^A-Z0-9]", "", clean(value, 60).upper())
    return key if 8 <= len(key) <= 40 and re.search(r"\d", key) else None


def shop_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", clean(value, 80).lower())


def track_url(carrier: str | None, tracking: str | None, shared: Any = ()) -> str | None:
    key = tracking_key(tracking)
    name = clean(carrier, 60).lower()
    if not key or not name:
        return None
    for names, template in CARRIERS:
        if any(re.search(rf"\b{re.escape(n)}\b", name) for n in names):
            return template.replace("{n}", quote(key, safe=""))
    for item in shared:
        if re.search(rf"(?<![a-z0-9]){re.escape(item['name'].lower())}(?![a-z0-9])", name):
            return item["url"].replace("{n}", quote(key, safe=""))
    return None


def clean_carrier_name(value: Any) -> str:
    name = clean(value, 200)
    if not _NAME.fullmatch(name):
        raise CarrierError("Give the carrier's name in a few words, for example Sendle.")
    return name


def clean_template(url: Any, example: Any = None) -> str:
    """A tracking-page address with {n} where the tracking number goes, or CarrierError. Always https, always a public name."""
    text = clean(url, 400).replace("{number}", "{n}").replace("{NUMBER}", "{n}")
    if "{n}" not in text and isinstance(example, str):
        typed = re.sub(r"\s+", "", example)
        for candidate in (typed, re.sub(r"[^A-Za-z0-9]", "", example)):         # as typed (with dashes), then letters and digits only
            if len(re.sub(r"[^A-Za-z0-9]", "", candidate)) >= 6 and len(re.findall(re.escape(candidate), text, re.I)) == 1:
                text = re.sub(re.escape(candidate), "{n}", text, count=1, flags=re.I)
                break
    if text.count("{n}") != 1:
        raise CarrierError("Put {number} in the address where the tracking number goes, for example https://track.example.com/?id={number}. Or type that parcel's tracking number in the last box and Enveliq will find it.")
    if len(text) > 300 or re.search(r"[\s\"'<>\\`]", text):
        raise CarrierError("That address does not look right. Copy it again from the tracking page.")
    if not text.lower().startswith("https://"):
        raise CarrierError("The address must start with https://")
    authority = re.split(r"[/?#]", text[8:], maxsplit=1)[0]
    probe = text.replace("{n}", "0123456789")
    try:
        port = urlsplit(probe).port
    except ValueError:
        port = 0
    if "{n}" in authority or port is not None or safe_url(probe) is None:
        raise CarrierError("That address can't be used. It must be a normal public website address, starting https://, with the tracking number after the website name.")
    return text


def _iso(day: date | None) -> str | None:
    return day.isoformat() if day else None


class ShipBook:
    def __init__(self, vault: Any, clock: Callable[[], float] = time.time):
        self.vault = vault
        self.clock = clock
        self._lock = threading.RLock()

    # ---------- storage ----------

    def _load(self, user_id: str) -> dict[str, Any]:
        raw = self.vault.get_global(RECORD_PREFIX + user_id) or {}
        orders = raw.get("orders") if isinstance(raw.get("orders"), dict) else {}
        dismissed = raw.get("dismissed") if isinstance(raw.get("dismissed"), dict) else {}
        return {"orders": orders, "dismissed": dismissed}

    def _save(self, user_id: str, book: dict[str, Any]) -> None:
        self.vault.set_global(RECORD_PREFIX + user_id, book)

    def _purge(self, book: dict[str, Any], now: float) -> bool:
        changed = False
        for oid, o in list(book["orders"].items()):
            done = o.get("delivered_at")
            if (done and now - done > KEEP_DELIVERED) or (not done and now - float(o.get("updated") or 0) > KEEP_OPEN):
                del book["orders"][oid]
                changed = True
        for key, at in list(book["dismissed"].items()):
            if now - float(at or 0) > KEEP_DISMISSED:
                del book["dismissed"][key]
                changed = True
        if len(book["orders"]) > MAX_ORDERS:
            for oid, _ in sorted(book["orders"].items(), key=lambda kv: float(kv[1].get("updated") or 0))[: len(book["orders"]) - MAX_ORDERS]:
                del book["orders"][oid]
            changed = True
        return changed

    def enabled(self, user_id: str | None) -> bool:
        if not user_id:
            return False
        from . import features
        return bool(features.effective(self.vault, user_id).get("shipping"))

    # ---------- learning from an email ----------

    @staticmethod
    def _clean_shipment(raw: Any) -> dict[str, Any] | None:
        if not isinstance(raw, dict) or raw.get("kind") not in KINDS:
            return None
        return {
            "kind": raw["kind"],
            "shop": clean(raw.get("shop"), 60),
            "order": order_key(raw.get("order_number")) and clean(raw.get("order_number"), 40).lstrip("#").strip(),
            "tracking": tracking_key(raw.get("tracking_number")),
            "carrier": clean(raw.get("carrier"), 40) or None,
            "items": clean(raw.get("items"), 200) or None,
            "total": clean(raw.get("total"), 30) or None,
            "expected_text": clean(raw.get("expected"), 60) or None,
        }

    def observe(self, user_id: str | None, account_id: str, message_id: str, subject: str, received_at: float | None, shipment: Any) -> bool:
        """File what an email says about an order. Returns True when an order was added or changed."""
        if not user_id or not self.enabled(user_id):
            return False
        info = self._clean_shipment(shipment)
        if info is None or not (info["shop"] or info["order"] or info["tracking"]):
            return False
        now = self.clock()
        at = float(received_at) if received_at and 0 < received_at <= now + 86400 else now
        okey, tkey, skey = order_key(info["order"]), info["tracking"], shop_key(info["shop"])
        mark = hashlib.sha256(f"{account_id}|{message_id}".encode()).hexdigest()[:16]
        with self._lock:
            book = self._load(user_id)
            self._purge(book, now)
            if any(e.get("m") == mark for o in book["orders"].values() for e in o["events"]):
                return False                                              # this very email was already filed (summarised twice)
            dismissed = book["dismissed"]
            if (okey and f"o:{okey}" in dismissed) or (tkey and f"t:{tkey}" in dismissed) or (not okey and not tkey and skey and f"s:{skey}" in dismissed):
                return False
            order = None
            if okey:
                order = next((o for o in book["orders"].values() if o.get("order_key") == okey), None)
            if order is None and tkey:
                order = next((o for o in book["orders"].values() if o.get("tracking_key") == tkey), None)
            if order is None and not okey and skey:
                # No order number: join the shop's one open order. When the email has a tracking number, that order must not have one yet.
                open_same = [o for o in book["orders"].values()
                             if o.get("shop_key") == skey and not o.get("delivered_at") and not (tkey and o.get("tracking_key"))]
                if len(open_same) == 1:
                    order = open_same[0]
            if order is None:
                if len(book["orders"]) >= MAX_ORDERS + 20:
                    return False
                oid = "s" + secrets.token_hex(12)[:23]
                order = {"id": oid, "shop": info["shop"] or None, "shop_key": skey, "order": None, "order_key": None, "carrier": None, "tracking": None,
                         "tracking_key": None, "items": None, "status": STATUS_OF[info["kind"]], "expected": None, "expected_text": None, "prev_expected": None,
                         "delayed": False, "delivered_at": None, "ack": None, "snooze_until": 0, "unsure": not (okey or tkey), "first_seen": at, "updated": at,
                         "events": []}
                book["orders"][oid] = order
            self._apply(order, info, okey, tkey, skey, at, mark, subject)
            order["updated"] = max(float(order.get("updated") or 0), at)
            self._save(user_id, book)
            return True

    @staticmethod
    def _apply(order: dict[str, Any], info: dict[str, Any], okey: str | None, tkey: str | None, skey: str, at: float, mark: str, subject: str) -> None:
        for field, value in (("shop", info["shop"]), ("carrier", info["carrier"]), ("total", info["total"])):
            if value and not order.get(field):
                order[field] = value
        if info["items"] and (not order.get("items") or len(info["items"]) > len(order["items"])):
            order["items"] = info["items"]                                      # a fuller description in a later email wins
        if skey and not order.get("shop_key"):
            order["shop_key"] = skey
        if okey and not order.get("order_key"):
            order["order"], order["order_key"] = info["order"], okey
        if tkey and not order.get("tracking_key"):
            order["tracking"], order["tracking_key"] = tkey, tkey
        if (okey or tkey) and order.get("unsure") is True and (order.get("order_key") or order.get("tracking_key")):
            order["unsure"] = False
        status = STATUS_OF[info["kind"]]
        if RANK[status] > RANK.get(order.get("status"), 0):
            order["status"] = status
        if order["status"] == "delivered" and not order.get("delivered_at"):
            order["delivered_at"] = at
        if info["expected_text"]:
            ref = datetime.fromtimestamp(at, timezone.utc).date()
            when = _iso(parse_due(info["expected_text"], ref, ref))
            old = order.get("expected")
            if when and when != old and at >= float(order.get("expected_at") or 0):
                order["prev_expected"] = old if old else order.get("prev_expected")
                order["expected"], order["expected_at"] = when, at
                order["delayed"] = bool(old and when > old)
            order["expected_text"] = info["expected_text"]
        if info["kind"] == "delayed":
            order["delayed"] = True
        order["events"].append({"at": at, "kind": info["kind"], "subject": clean(subject, 160) or "(no subject)", "m": mark})
        order["events"].sort(key=lambda e: e["at"])
        del order["events"][:-MAX_EVENTS]

    # ---------- carriers added by the household ----------

    def shared_carriers(self) -> list[dict[str, Any]]:
        raw = self.vault.get_global(SHARED_RECORD) or {}
        out = []
        for i in raw.get("items") if isinstance(raw.get("items"), list) else []:
            try:
                if isinstance(i, dict) and re.fullmatch(r"c[0-9a-f]{16}", str(i.get("id"))):
                    out.append({"id": i["id"], "name": clean_carrier_name(i.get("name")), "url": clean_template(i.get("url")), "by": str(i.get("by") or ""), "at": i.get("at")})
            except CarrierError:
                continue                      # a damaged entry is ignored, never shown
        return out

    def add_carrier(self, user_id: str, name: Any, url: Any, example: Any = None) -> None:
        name, template = clean_carrier_name(name), clean_template(url, example)
        with self._lock:
            items = self.shared_carriers()
            fixed = {n.lower() for names, _ in CARRIERS for n in names} | {n.lower() for n in FIXED_NAMES}
            if name.lower() in fixed or any(i["name"].lower() == name.lower() for i in items):
                raise CarrierError("That carrier is already on the list.")
            if len(items) >= MAX_SHARED:
                raise CarrierError("The list of added carriers is full. Remove one you no longer use first.")
            items.append({"id": "c" + secrets.token_hex(8), "name": name, "url": template, "by": user_id, "at": self.clock()})
            self.vault.set_global(SHARED_RECORD, {"items": items})

    def update_carrier(self, carrier_id: str, name: Any, url: Any, example: Any = None) -> None:
        """An administrator corrects a saved carrier. Who added it stays as it was."""
        name, template = clean_carrier_name(name), clean_template(url, example)
        with self._lock:
            items = self.shared_carriers()
            target = next((i for i in items if i["id"] == carrier_id), None)
            if target is None:
                raise KeyError(carrier_id)
            fixed = {n.lower() for names, _ in CARRIERS for n in names} | {n.lower() for n in FIXED_NAMES}
            if name.lower() in fixed or any(i["id"] != carrier_id and i["name"].lower() == name.lower() for i in items):
                raise CarrierError("That carrier is already on the list.")
            target["name"], target["url"] = name, template
            self.vault.set_global(SHARED_RECORD, {"items": items})

    def carrier_addresses(self) -> list[dict[str, str]]:
        """Names with their tracking-page addresses ({number} where the tracking number goes). Only ever sent to administrators."""
        return [{"id": i["id"], "name": i["name"], "url": i["url"].replace("{n}", "{number}")} for i in self.shared_carriers()]

    def remove_carrier(self, user_id: str, carrier_id: str, is_admin: bool) -> None:
        with self._lock:
            items = self.shared_carriers()
            target = next((i for i in items if i["id"] == carrier_id), None)
            if target is None:
                raise KeyError(carrier_id)
            if target["by"] != user_id and not is_admin:
                raise PermissionError(carrier_id)
            self.vault.set_global(SHARED_RECORD, {"items": [i for i in items if i["id"] != carrier_id]})

    # ---------- showing it ----------

    def _row(self, o: dict[str, Any], now: float, shared: Any = ()) -> dict[str, Any]:
        delivered = bool(o.get("delivered_at"))
        return {
            "id": o["id"], "shop": o.get("shop"), "order_number": o.get("order"), "carrier": o.get("carrier"), "tracking": o.get("tracking"),
            "items": o.get("items"), "total": o.get("total"), "note": o.get("note") or "", "status": o.get("status"), "expected": o.get("expected"), "expected_text": o.get("expected_text"),
            "prev_expected": o.get("prev_expected"), "delayed": bool(o.get("delayed")) and not delivered, "delivered_at": o.get("delivered_at"),
            "ack": o.get("ack"), "unsure": bool(o.get("unsure")),
            "needs_confirm": delivered and not o.get("unsure") and not o.get("ack") and float(o.get("snooze_until") or 0) <= now,
            "track_url": track_url(o.get("carrier"), o.get("tracking"), shared), "updated": o.get("updated"),
            "events": [{"at": e["at"], "kind": e["kind"], "subject": e["subject"], "m": e.get("m")} for e in reversed(o.get("events") or [])],
        }

    def view(self, user_id: str) -> dict[str, Any]:
        if not self.enabled(user_id):
            return {"enabled": False, "orders": [], "now": self.clock()}
        now = self.clock()
        with self._lock:
            book = self._load(user_id)
            if self._purge(book, now):
                self._save(user_id, book)
        shared = self.shared_carriers()
        rows = [self._row(o, now, shared) for o in book["orders"].values()]

        def order(r: dict[str, Any]) -> tuple[Any, ...]:
            group = 0 if r["needs_confirm"] else 1 if r["unsure"] else 3 if r["delivered_at"] else 2
            return (group, r["expected"] or "9999", -(r["updated"] or 0))

        rows.sort(key=order)
        return {"enabled": True, "orders": rows, "now": now,
                "carriers": {"fixed": FIXED_NAMES, "shared": [{"id": i["id"], "name": i["name"], "mine": i["by"] == user_id} for i in shared]}}

    # ---------- what the person can do ----------

    def set_note(self, user_id: str, oid: str, text: Any) -> dict[str, Any]:
        """The person's own few words about an order ("new headphones"). Plain text, cut to 500 characters, kept with the order."""
        if not isinstance(text, str):
            raise ValueError("note")
        lines = [re.sub(r"[ \t]+", " ", _CONTROL.sub("", ln)).strip() for ln in text.replace("\r", "").split("\n")]
        note = re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()[:500]
        with self._lock:
            book = self._load(user_id)
            order = book["orders"].get(oid)
            if order is None:
                raise KeyError(oid)
            order["note"] = note
            self._save(user_id, book)
        return self.view(user_id)

    def act(self, user_id: str, oid: str, action: str) -> dict[str, Any]:
        if action not in ACTIONS:
            raise ValueError("unknown action")
        now = self.clock()
        with self._lock:
            book = self._load(user_id)
            order = book["orders"].get(oid)
            if order is None:
                raise KeyError(oid)
            if action == "confirm":
                if not order.get("delivered_at"):
                    raise ValueError("not delivered")
                order["ack"], order["ack_at"] = "got_it", now
            elif action == "undo":
                order["ack"], order["ack_at"], order["snooze_until"] = None, None, 0
            elif action == "not_yet":
                order["snooze_until"] = now + SNOOZE
            elif action == "track":
                order["unsure"] = False
            elif action == "not_order":
                for key, prefix in ((order.get("order_key"), "o"), (order.get("tracking_key"), "t")):
                    if key:
                        book["dismissed"][f"{prefix}:{key}"] = now
                if not order.get("order_key") and not order.get("tracking_key") and order.get("shop_key"):
                    book["dismissed"][f"s:{order['shop_key']}"] = now
                del book["orders"][oid]
            self._save(user_id, book)
        return self.view(user_id)
