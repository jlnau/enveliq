"""Junk Mail: the emails your mail services put in their Junk or Spam folders, checked by the AI.

Enveliq reads only the headers of recent mail in each connected mailbox's junk folder, then (when an AI model is set up)
shows one email at a time to the model and keeps its answer: "Yes, it's junk" or "Needs review", with a short summary.
The email itself stays in the mailbox. Nothing here is a retained message, so junk never reaches the inbox, reminders,
Found emails or the summary queue.

Each person has one encrypted record (`junk:<user id>`) holding, per email: who, what subject, when, where it sits in the mailbox
(never sent to the page), and the AI's answer. No email body is stored. The email can be viewed with links, pictures from the
internet and anything that runs switched off. "Not junk" moves the email to the real Inbox at the mail service, and marks it unread
so the next sync brings it into Enveliq's inbox.
"""
from __future__ import annotations

import logging
import re
import secrets
import threading
import time
from typing import Any

from .bridge import locator, parse_folder_locator
from .errors import BridgeError
from .parse import clean, render_original, summarise_headers, sending_identities

log = logging.getLogger(__name__)
RECORD_PREFIX = "junk:"
LOOK_BACK_DAYS = 30
PER_MAILBOX = 50
MAX_ITEMS = 200
MAX_TRIES = 3
JUNK_NAMES = ("junk", "spam", "junk email", "junk e-mail", "bulk mail", "[gmail]/spam", "inbox.junk", "inbox.spam")
VERDICTS = ("junk", "review")
ID_RE = re.compile(r"^j[0-9a-f]{23}$")


def junk_folder(session: Any, kind: str) -> str:
    """The name of this mailbox's junk folder. Proton Bridge always calls it Spam; other services mark it with a special-use flag, else the usual names."""
    if kind != "imap":
        return "Spam"
    folders = session.list_folders()
    for flags, name in folders:
        if "\\junk" in flags:
            return name
    by_lower = {name.lower(): name for _flags, name in folders}
    for hint in JUNK_NAMES:
        if hint in by_lower:
            return by_lower[hint]
    raise BridgeError("not_found", "Enveliq could not find this mailbox's Junk or Spam folder.")


class JunkBook:
    def __init__(self, vault: Any, service: Any, clock: Any = time.time):
        self.vault = vault
        self.service = service
        self.clock = clock
        self._lock = threading.RLock()

    # ---------- storage ----------

    def _load(self, user: str) -> dict[str, Any]:
        raw = self.vault.get_global(RECORD_PREFIX + user) or {}
        items = raw.get("items") if isinstance(raw.get("items"), dict) else {}
        problems = [str(p)[:300] for p in raw.get("problems", [])[:5]] if isinstance(raw.get("problems"), list) else []
        return {"items": {k: v for k, v in items.items() if isinstance(v, dict) and ID_RE.match(str(k))}, "problems": problems}

    def _save(self, user: str, data: dict[str, Any]) -> None:
        items = data["items"]
        if len(items) > MAX_ITEMS:
            for key in sorted(items, key=lambda k: items[k].get("received_at") or 0)[: len(items) - MAX_ITEMS]:
                del items[key]
        self.vault.set_global(RECORD_PREFIX + user, data)

    def forget_user(self, user: str) -> None:
        self.vault.set_global(RECORD_PREFIX + user, {})

    # ---------- what the page sees ----------

    def view(self, user: str) -> dict[str, Any]:
        self.service.refresh_ai(self.vault)          # the AI settings an administrator saved in the app, if any
        with self._lock:
            data = self._load(user)
        labels = {a["id"]: str(a.get("email_address") or a.get("name") or "Mailbox") for a in self._mailboxes(user)}
        out = []
        for key, it in data["items"].items():
            out.append({"id": key, "mailbox": labels.get(it.get("account_id"), "Mailbox"), "subject": it.get("subject") or "(no subject)",
                        "sender_display": it.get("sender_display"), "sender_address": it.get("sender_address"), "received_at": it.get("received_at"),
                        "verdict": it.get("verdict") if it.get("verdict") in VERDICTS else None, "summary": it.get("summary") or "", "reason": it.get("reason") or "",
                        "failed": bool(it.get("verdict") not in VERDICTS and it.get("tries", 0) >= MAX_TRIES), "has_files": bool(it.get("has_attachments"))})
        out.sort(key=lambda x: x["received_at"] or 0, reverse=True)
        pending = sum(1 for x in out if x["verdict"] is None and not x["failed"])
        return {"items": out, "total": len(out), "pending": pending, "needs_review": sum(1 for x in out if x["verdict"] == "review"),
                "junk": sum(1 for x in out if x["verdict"] == "junk"), "ai": bool(self.service.summariser.enabled), "problems": data.get("problems", [])}

    def _mailboxes(self, user: str) -> list[dict[str, Any]]:
        from .service import MAIL_METHODS
        return [a for a in self.vault.list_accounts() if a.get("owner_user_id") == user and a.get("auth_method") in MAIL_METHODS]

    # ---------- reading the junk folders ----------

    def refresh(self, user: str) -> dict[str, Any]:
        """Look at each mailbox's junk folder: add new emails (headers only), forget ones that are gone. Per mailbox; one failing does not stop the others."""
        problems: list[str] = []
        with self._lock:
            data = self._load(user)
            items = data["items"]
            for account in self._mailboxes(user):
                label = str(account.get("email_address") or account.get("name") or "Mailbox")
                try:
                    self._refresh_one(account, items)
                except BridgeError as err:
                    problems.append(f"{label}: {err.message}")
                except Exception as exc:
                    log.exception("junk mail: reading a junk folder failed")          # the traceback holds no email text
                    problems.append(f"{label}: could not be read ({type(exc).__name__}).")
            cutoff = self.clock() - LOOK_BACK_DAYS * 86400
            for key in [k for k, v in items.items() if (v.get("received_at") or self.clock()) < cutoff]:
                del items[key]
            data["problems"] = problems[:5]
            self._save(user, data)
        return self.view(user)

    def _refresh_one(self, account: dict[str, Any], items: dict[str, Any]) -> None:
        target = self.service.target(account)
        account_id = account["id"]
        with self.service.bridge.session(target) as s:
            folder = junk_folder(s, target.kind)
            validity = s.select_folder(folder, readonly=True)
            uids = s.recent_uids(LOOK_BACK_DAYS, PER_MAILBOX)
            here = {locator(validity, u, folder): u for u in uids}
            for key in [k for k, v in items.items() if v.get("account_id") == account_id and v.get("locator") not in here]:
                del items[key]                                   # moved, deleted or emptied at the mail service
            known = {v.get("locator") for v in items.values() if v.get("account_id") == account_id}
            fresh = [u for loc, u in here.items() if loc not in known]
            identities = sending_identities(account)
            for uid, block in s.header_blocks(fresh):
                info = summarise_headers(block, identities)
                if info is None:
                    continue
                key = "j" + secrets.token_hex(11) + "0"
                items[key] = {"account_id": account_id, "locator": locator(validity, uid, folder), "subject": clean(info["subject"], 300),
                              "sender_display": clean(info["sender_display"] or "", 120) or None, "sender_address": clean(info["sender_address"] or "", 320) or None,
                              "received_at": info["received_at"] or self.clock(), "has_attachments": bool(info["has_attachments"]), "tries": 0}

    # ---------- the AI check ----------

    def classify(self, user: str, limit: int = 6) -> dict[str, Any]:
        """Ask the model about a few emails that have no answer yet. Bounded, so one request stays short; the page calls again while some are left."""
        self.service.refresh_ai(self.vault)
        if not self.service.summariser.enabled:
            return self.view(user)
        self.service.summariser.check_url()
        with self._lock:
            data = self._load(user)
            todo = [k for k, v in sorted(data["items"].items(), key=lambda kv: kv[1].get("received_at") or 0, reverse=True)
                    if v.get("verdict") not in VERDICTS and v.get("tries", 0) < MAX_TRIES][:limit]
            accounts = {a["id"]: a for a in self._mailboxes(user)}
            for key in todo:
                it = data["items"][key]
                account = accounts.get(it.get("account_id"))
                it["tries"] = it.get("tries", 0) + 1
                if account is None:
                    continue
                try:
                    raw = self._fetch(account, it)
                    text = render_original(raw)["text"]
                    answer = self.service.summariser.judge_junk(it.get("subject") or "", f"{it.get('sender_display') or ''} <{it.get('sender_address') or ''}>", text)
                except BridgeError:
                    continue
                except Exception:
                    log.exception("junk mail: checking one email failed")
                    continue
                it.update(verdict=answer["verdict"], summary=answer["summary"], reason=answer["reason"])
            self._save(user, data)
        return self.view(user)

    # ---------- one email ----------

    def _item(self, user: str, key: str) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        if not ID_RE.match(key or ""):
            raise KeyError(key)
        data = self._load(user)
        it = data["items"].get(key)
        if it is None:
            raise KeyError(key)
        account = next((a for a in self._mailboxes(user) if a["id"] == it.get("account_id")), None)
        if account is None:
            raise KeyError(key)
        return data, it, account

    def _fetch(self, account: dict[str, Any], it: dict[str, Any]) -> bytes:
        folder, validity, uid = parse_folder_locator(it.get("locator"))
        with self.service.bridge.session(self.service.target(account)) as s:
            if s.select_folder(folder, readonly=True) != validity:
                raise BridgeError("not_found", "This email can no longer be found in the Junk folder.")
            return s.original(uid)

    def original(self, user: str, key: str) -> bytes:
        _data, it, account = self._item(user, key)
        return self._fetch(account, it)

    def not_junk(self, user: str, key: str) -> None:
        """Move the email to the real Inbox at the mail service (unread, so the next sync brings it into Enveliq), then forget it here."""
        with self._lock:
            data, it, account = self._item(user, key)
            folder, validity, uid = parse_folder_locator(it.get("locator"))
            with self.service.bridge.session(self.service.target(account)) as s:
                if s.select_folder(folder, readonly=False) != validity:
                    raise BridgeError("not_found", "This email can no longer be found in the Junk folder.")
                s.mark_unseen(uid)
                s.move(uid, "INBOX")
            del data["items"][key]
            self._save(user, data)
        try:
            self.service.sync(self.vault, account)              # so it shows in Enveliq's inbox straight away
        except BridgeError:
            pass
