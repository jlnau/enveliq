"""Clean up: see who fills the inbox, and quiet them in a few taps.

The page lists the mailing lists that wrote to the person in the last 60 days, busiest first, with how many emails and how many were
opened. For each one the person can unsubscribe (their own browser opens the sender's page; Enveliq never opens it), archive what is
already in the inbox from that sender, make a rule that archives new email from them, or keep them (hide them from this page).

Rules:
  * Nothing is deleted. There is no Bin here.
  * Only email headers are looked at (From, Date, List-Unsubscribe and what the scam check reads) and they live in server memory for a
    few minutes. No email text is read and nothing about the senders is kept except the person's own "keep" list.
  * Only mailing lists are listed (mail that carries a List-Unsubscribe header). A person who writes to you often is never listed.
  * Important people, the person's own addresses, senders they chose to keep, and email that has an open task are never touched.
  * Which mailbox and which sender is decided here from the signed-in person's own list; the page only sends an opaque id.
  * An email flagged "be careful" never shows an unsubscribe address (unsubscribing from a scam tells the sender the address is real).
"""
from __future__ import annotations

import hashlib
import logging
import re
import secrets
import threading
import time
from typing import Any, Callable

from .errors import BridgeError
from .parse import HEADER_FIELDS, _addresses, parse_headers, sending_identities, summarise_headers

log = logging.getLogger(__name__)

RECORD_PREFIX = "senders:"
DAYS = 60                       # the same window as "Include read mail"
SCAN_LIMIT = 1500               # newest emails looked at per mailbox
MIN_EMAILS = 2                  # a list that wrote once is not worth a row
CAP = 500                       # emails moved by one press
CACHE_SECONDS = 300
UNDO_SECONDS = 600
MAX_KEPT = 500
ID_RE = re.compile(r"^s[0-9a-f]{20}$")
_QUOTE = re.compile(r'[\\"\r\n]')


class SenderError(ValueError):
    """A short reason the person can read."""


def sender_id(user: str, account_id: str, address: str) -> str:
    return "s" + hashlib.sha256(f"{user}\x00{account_id}\x00{address.lower()}".encode()).hexdigest()[:20]


class SenderBook:
    def __init__(self, vault: Any, service: Any, rules: Any, important: Any, held: Callable[[str], set[tuple[str, str]]] | None = None, clock: Callable[[], float] = time.time):
        self.vault, self.service, self.rules, self.important, self.held, self.clock = vault, service, rules, important, held, clock
        self._lock = threading.RLock()
        self._cache: dict[str, dict[str, Any]] = {}
        self._undo: dict[str, dict[str, Any]] = {}

    # ---------- the person's own "keep" list ----------
    def _kept(self, user: str) -> list[str]:
        raw = (self.vault.get_global(RECORD_PREFIX + user) or {}).get("kept") or []
        return [a for a in raw if isinstance(a, str)][:MAX_KEPT]

    def _save_kept(self, user: str, kept: list[str]) -> None:
        self.vault.set_global(RECORD_PREFIX + user, {"kept": kept[:MAX_KEPT]})

    def forget_user(self, user: str) -> None:
        self.vault.set_global(RECORD_PREFIX + user, {})
        with self._lock:
            self._cache.pop(user, None)
            self._undo.pop(user, None)

    # ---------- what the person's mailboxes hold ----------
    def _mailboxes(self, user: str) -> list[dict[str, Any]]:
        from .service import MAIL_METHODS
        return [a for a in self.vault.list_accounts()
                if a.get("owner_user_id") == user and a.get("auth_method") in MAIL_METHODS and not self.service.is_check_address(a)]

    def _scan_one(self, account: dict[str, Any], user: str, rows: dict[str, dict[str, Any]]) -> None:
        identities = {i.lower() for i in sending_identities(account)}
        groups: dict[str, dict[str, Any]] = {}
        with self.service.bridge.session(self.service.target(account)) as s:
            s.select_inbox(readonly=True)
            uids = s.recent_uids(DAYS, SCAN_LIMIT)
            unseen = set(s.unseen_uids(DAYS, SCAN_LIMIT))
            for uid, block in s.header_blocks(uids, HEADER_FIELDS):
                info = summarise_headers(block, list(identities))
                address = str((info or {}).get("sender_address") or "").strip().lower()
                if not info or not address or address in identities:
                    continue
                g = groups.setdefault(address, {"count": 0, "opened": 0, "last": 0.0, "name": "", "unsub": None, "flagged": False, "listed": False})
                g["count"] += 1
                g["opened"] += 0 if uid in unseen else 1
                at = float(info.get("received_at") or 0)
                if at >= g["last"]:
                    g["last"] = at
                    if info.get("sender_display"):
                        g["name"] = str(info["sender_display"])
                    if info.get("unsubscribe"):
                        g["unsub"] = info["unsubscribe"]
                if info.get("unsubscribe") and not g["unsub"]:
                    g["unsub"] = info["unsubscribe"]
                if info.get("scam_warning"):
                    g["flagged"] = True
                g["listed"] = g["listed"] or bool(info.get("unsubscribe"))
        kept = set(self._kept(user))
        for address, g in groups.items():
            if not g["listed"] or g["count"] < MIN_EMAILS or address in kept:
                continue
            if self.important is not None and self.important.contains(user, address):
                continue
            sid = sender_id(user, account["id"], address)
            rows[sid] = {"id": sid, "account_id": account["id"], "mailbox": str(account.get("email_address") or account.get("name") or "Mailbox"), "address": address,
                         "name": (g["name"] or address)[:120], "count": g["count"], "opened": g["opened"], "last": g["last"], "flagged": g["flagged"],
                         "unsub": None if g["flagged"] else g["unsub"]}

    def scan(self, user: str, refresh: bool = False) -> dict[str, Any]:
        """The senders, busiest first. Held in memory for a few minutes so the page can be opened again without asking the mail service again."""
        now = self.clock()
        with self._lock:
            hit = self._cache.get(user)
            if hit and not refresh and now - hit["at"] < CACHE_SECONDS:
                return self._view(user, hit)
        rows: dict[str, dict[str, Any]] = {}
        problems: list[str] = []
        boxes = self._mailboxes(user)
        for account in boxes:
            label = str(account.get("email_address") or account.get("name") or "Mailbox")
            try:
                self._scan_one(account, user, rows)
            except BridgeError as err:
                problems.append(f"{label}: {err.message}")
            except Exception as exc:
                log.exception("clean up: reading a mailbox failed")          # the traceback holds no email text
                problems.append(f"{label}: could not be read ({type(exc).__name__}).")
        with self._lock:
            self._cache[user] = {"at": now, "rows": rows, "problems": problems[:5], "boxes": len(boxes)}
            if len(self._cache) > 256:
                for key in [k for k, v in self._cache.items() if now - v["at"] > CACHE_SECONDS * 4]:
                    self._cache.pop(key, None)
            return self._view(user, self._cache[user])

    def _view(self, user: str, hit: dict[str, Any]) -> dict[str, Any]:
        rows = sorted(hit["rows"].values(), key=lambda r: (-r["count"], r["opened"], r["name"].lower()))
        public = [{"id": r["id"], "name": r["name"], "address": r["address"], "mailbox": r["mailbox"], "count": r["count"], "opened": r["opened"], "last": r["last"],
                   "flagged": r["flagged"], "unsubscribe": r["unsub"]} for r in rows]
        return {"senders": public, "mailboxes": hit["boxes"], "kept": len(self._kept(user)), "days": DAYS, "problems": hit["problems"], "now": self.clock(),
                "undo_offer": self._undo_info(user)}

    def _row(self, user: str, sid: str) -> dict[str, Any]:
        if not ID_RE.match(str(sid)):
            raise KeyError(sid)
        with self._lock:
            hit = self._cache.get(user)
            row = hit["rows"].get(sid) if hit else None
        if row is None:
            raise KeyError(sid)
        return row

    def _drop(self, user: str, sid: str) -> None:
        with self._lock:
            hit = self._cache.get(user)
            if hit:
                hit["rows"].pop(sid, None)

    # ---------- the person's choices ----------
    def keep(self, user: str, sid: str) -> dict[str, Any]:
        row = self._row(user, sid)
        kept = self._kept(user)
        if row["address"] not in kept:
            if len(kept) >= MAX_KEPT:
                raise SenderError("You have kept the most senders Enveliq can remember. Show them again first.")
            kept.append(row["address"])
            self._save_kept(user, kept)
        self._drop(user, sid)
        return self.scan(user)

    def show_kept_again(self, user: str) -> dict[str, Any]:
        self._save_kept(user, [])
        return self.scan(user, refresh=True)

    def always_archive(self, user: str, sid: str) -> dict[str, Any]:
        """A normal Mail rule, so Settings, Mail rules lists it and can remove it."""
        row = self._row(user, sid)
        try:
            self.rules.add(user, row["address"], "", "archived")
        except ValueError as err:
            raise SenderError(str(err)) from None
        return {"ok": True, "address": row["address"]}

    # ---------- archive what is already here ----------
    def _protected(self, user: str, account: dict[str, Any]) -> set[int]:
        """UIDs of emails that have an open task: they need the person, so a bulk move leaves them alone."""
        out: set[int] = set()
        if self.held is None:
            return out
        from .bridge import parse_locator
        for account_id, message_id in self.held(user):
            if account_id != account["id"]:
                continue
            try:
                locator = self.vault.get_message(account_id, message_id).get("source_locator")
                if locator:
                    out.add(parse_locator(locator)[1])
            except Exception:
                continue
        return out

    @staticmethod
    def _quote(value: str) -> str:
        return '"' + _QUOTE.sub("", value) + '"'

    def archive(self, user: str, sid: str) -> dict[str, Any]:
        row = self._row(user, sid)
        account = next((a for a in self._mailboxes(user) if a["id"] == row["account_id"]), None)
        if account is None:
            raise KeyError(sid)
        address = row["address"]
        if self.important is not None and self.important.contains(user, address):
            raise SenderError("This sender is one of your important people, so Enveliq leaves their email alone.")
        protected = self._protected(user, account)
        moved: list[dict[str, Any]] = []
        with self.service.bridge.session(self.service.target(account)) as s:
            s.select_inbox(readonly=False)
            candidates = s.search(["FROM", self._quote(address)])
            exact: list[tuple[int, str]] = []
            for uid, block in s.header_blocks(candidates[: CAP * 3], "FROM MESSAGE-ID"):
                msg = parse_headers(block)
                who = (_addresses(msg, "From") or [("", "")])[0][1].strip().lower()
                if who == address:
                    exact.append((uid, str(msg.get("Message-ID") or "").strip()))
            exact.sort(reverse=True)
            eligible = [(u, m) for u, m in exact if u not in protected]
            left_for_tasks = len(exact) - len(eligible)
            unseen = s.all_unseen_uids()
            folder = s.folder_for("archive")
            for uid, message_id in eligible[:CAP]:
                was_unseen = uid in unseen
                s.mark_seen(uid)
                s.move(uid, folder)
                moved.append({"message_id": message_id, "was_unseen": was_unseen})
        self._drop(user, sid)
        undo = None
        undoable = [m for m in moved if m["message_id"]]
        if undoable:
            undo = secrets.token_urlsafe(12)
            with self._lock:
                self._undo[user] = {"token": undo, "account_id": account["id"], "items": undoable, "until": self.clock() + UNDO_SECONDS, "name": row["name"]}
        return {"archived": len(moved), "more": len(eligible) > len(moved), "left_for_tasks": left_for_tasks, "undo": undo, "undo_seconds": UNDO_SECONDS if undo else 0}

    def _undo_info(self, user: str) -> dict[str, Any] | None:
        with self._lock:
            u = self._undo.get(user)
            if not u or u["until"] <= self.clock():
                self._undo.pop(user, None)
                return None
            return {"token": u["token"], "count": len(u["items"]), "name": u["name"], "seconds": int(u["until"] - self.clock())}

    def undo(self, user: str, token: str) -> dict[str, Any]:
        """Put back what the last bulk archive moved, if it was less than ten minutes ago. Held in memory only."""
        with self._lock:
            u = self._undo.get(user)
            if u and u["until"] <= self.clock():
                self._undo.pop(user, None)
                u = None
            if not u or not secrets.compare_digest(str(token), u["token"]):
                raise KeyError("undo")
            self._undo.pop(user, None)
        account = next((a for a in self._mailboxes(user) if a["id"] == u["account_id"]), None)
        if account is None:
            raise KeyError("undo")
        restored = 0
        with self.service.bridge.session(self.service.target(account)) as s:
            folder = s.folder_for("archive")
            s.select_folder(folder, readonly=False)
            for item in u["items"]:
                ids = s.search(["HEADER", "Message-ID", self._quote(item["message_id"])])
                for uid in ids[:1]:
                    s.move(uid, "INBOX")
                    restored += 1
            s.select_inbox(readonly=False)
            for item in u["items"]:
                if not item["was_unseen"]:
                    continue
                for uid in s.search(["HEADER", "Message-ID", self._quote(item["message_id"])])[:1]:
                    s.mark_unseen(uid)
        with self._lock:
            self._cache.pop(user, None)
        return {"restored": restored}
