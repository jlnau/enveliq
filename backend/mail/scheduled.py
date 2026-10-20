"""Send later: an email written now that leaves at a time the person chose.

One encrypted record per person (`scheduled:<user id>`), like drafts. It holds only what the person typed: who it is for,
the subject, their own words, which mailbox sends it and, for a reply or forward, which email it answers. Files are not
kept (an email with files is sent now, or kept as a draft). The email is built and sent from the person's own mailbox at
the chosen time, by a background thread, so the server must be running then; one that was down is sent when it starts again.
A reply or forward fetches the original from the mailbox at that moment and never keeps it. If sending fails, the item
stays in the list, marked as failed with the reason, for seven days. Only that person can see or cancel it.
"""
from __future__ import annotations

import logging
import re
import secrets
import threading
import time
from typing import Any, Callable

from .errors import BridgeError

log = logging.getLogger("enveliq.scheduled")

RECORD_PREFIX = "scheduled:"
KINDS = ("new", "reply", "reply_all", "forward")
MAX_ITEMS = 20
MIN_AHEAD = 30                    # seconds: closer than this is just "send now"
MAX_AHEAD = 30 * 86400
KEEP_FAILED = 7 * 86400
MAX_BODY = 100_000
MAX_PEOPLE = 50
_LOCK = threading.Lock()
_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_LINE = re.compile(r"[\x00-\x1f\x7f]")


class ScheduleError(ValueError):
    """Plain, safe-to-show reason a change was refused."""


def _line(value: Any, limit: int) -> str:
    return _LINE.sub(" ", str(value or "")).strip()[:limit]


def _people(values: Any) -> list[str]:
    return [p for p in (_line(v, 320) for v in list(values or [])[:MAX_PEOPLE]) if p]


class ScheduledMail:
    def __init__(self, vault: Any, clock: Callable[[], float] = time.time) -> None:
        self.vault = vault
        self.clock = clock

    def _load(self, user_id: str) -> list[dict[str, Any]]:
        raw = self.vault.get_global(RECORD_PREFIX + user_id) or {}
        cutoff = self.clock() - KEEP_FAILED
        return [d for d in (raw.get("items") or []) if isinstance(d, dict) and d.get("id")
                and not (d.get("state") == "failed" and float(d.get("failed_at", 0)) < cutoff)]

    def _save(self, user_id: str, items: list[dict[str, Any]]) -> None:
        self.vault.set_global(RECORD_PREFIX + user_id, {"items": items})

    @staticmethod
    def public(d: dict[str, Any]) -> dict[str, Any]:
        """What the list shows: never the person's words."""
        people = list(d.get("to") or []) + list(d.get("cc") or []) + list(d.get("bcc") or [])
        return {"id": d["id"], "kind": d.get("kind"), "account_id": d.get("account_id"), "message_id": d.get("message_id"),
                "subject": d.get("subject") or "", "to": (d.get("to") or people or [""])[0], "people": len(people),
                "send_at": d.get("send_at"), "state": d.get("state", "pending"), "error": d.get("error")}

    def listing(self, user_id: str) -> list[dict[str, Any]]:
        with _LOCK:
            return [self.public(d) for d in sorted(self._load(user_id), key=lambda d: d.get("send_at", 0))]

    def add(self, user_id: str, data: dict[str, Any]) -> dict[str, Any]:
        kind = data.get("kind")
        if kind not in KINDS:
            raise ScheduleError("This kind of email cannot be sent later.")
        now = self.clock()
        try:
            send_at = float(data.get("send_at"))
        except (TypeError, ValueError):
            raise ScheduleError("Choose when to send it.") from None
        if send_at < now + MIN_AHEAD:
            raise ScheduleError("Choose a time a little way ahead, or just send it now.")
        if send_at > now + MAX_AHEAD:
            raise ScheduleError("An email can wait up to 30 days.")
        body = _CTRL.sub("", str(data.get("body") or "").replace("\r\n", "\n").replace("\r", "\n"))[:MAX_BODY]
        item = {"id": "s" + secrets.token_hex(8), "kind": kind, "account_id": _line(data.get("account_id"), 64),
                "message_id": _line(data.get("message_id"), 64) or None, "from_address": _line(data.get("from_address"), 320) or None,
                "to": _people(data.get("to")), "cc": _people(data.get("cc")), "bcc": _people(data.get("bcc")),
                "subject": _line(data.get("subject"), 900), "body": body, "send_at": send_at, "created": now, "state": "pending"}
        with _LOCK:
            items = self._load(user_id)
            if sum(1 for d in items if d.get("state") == "pending") >= MAX_ITEMS:
                raise ScheduleError(f"You can have up to {MAX_ITEMS} emails waiting. Cancel one first.")
            self._save(user_id, items + [item])
        return self.public(item)

    def cancel(self, user_id: str, item_id: str) -> dict[str, Any] | None:
        """Take an email back. Returns everything the person wrote, so the page can put it back in a writing window."""
        with _LOCK:
            items = self._load(user_id)
            found = next((d for d in items if d["id"] == item_id), None)
            if found is None:
                return None
            self._save(user_id, [d for d in items if d["id"] != item_id])
        return {**self.public(found), "body": found.get("body", ""), "to_list": found.get("to") or [], "cc_list": found.get("cc") or [],
                "bcc_list": found.get("bcc") or [], "from_address": found.get("from_address")}

    def forget_user(self, user_id: str) -> None:
        self.vault.set_global(RECORD_PREFIX + user_id, {})

    def _update(self, user_id: str, item_id: str, change: dict[str, Any] | None) -> None:
        """Replace one item (or remove it when [change] is None)."""
        with _LOCK:
            items = self._load(user_id)
            kept = []
            for d in items:
                if d["id"] == item_id:
                    if change is not None:
                        kept.append({**d, **change})
                else:
                    kept.append(d)
            self._save(user_id, kept)

    def due(self, user_id: str, now: float) -> list[dict[str, Any]]:
        with _LOCK:
            return [d for d in self._load(user_id) if d.get("state") == "pending" and float(d.get("send_at", 0)) <= now]


class ScheduledSender:
    """Sends the items whose time has come. Its work never counts as activity, so it cannot keep an idle vault awake."""

    def __init__(self, vault: Any, service: Any, book: ScheduledMail, audit: Callable[[dict[str, Any]], None],
                 clock: Callable[[], float] = time.time) -> None:
        self.vault, self.service, self.book, self.audit, self.clock = vault, service, book, audit, clock
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="enveliq-scheduled", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        while not self._stop.wait(15):
            try:
                self.run_due()
            except Exception:
                log.info("scheduled pass skipped")

    def run_due(self) -> int:
        """Send everything that is due. Returns how many were attempted. Does nothing while the vault is locked."""
        sent = 0
        with self.vault.passive():
            try:
                users = [u["id"] for u in self.vault.list_users() if not u.get("disabled")]
            except Exception:
                return 0
            for uid in users:
                try:
                    due = self.book.due(uid, self.clock())
                except Exception:
                    continue
                for item in due:
                    self._send(uid, item)
                    sent += 1
        return sent

    def _send(self, uid: str, item: dict[str, Any]) -> None:
        error = None
        try:
            account = self.vault.get_account(item["account_id"])
            if account.get("owner_user_id") != uid:
                raise BridgeError("not_found", "That mailbox is not yours.")
            kind = item["kind"]
            if kind == "new":
                built = self.service.build_new(account, item["to"], item["cc"], item["bcc"], item["subject"], item["body"], item.get("from_address"), [])
            else:
                message = self.vault.get_message(item["account_id"], item["message_id"])
                if kind == "forward":
                    built = self.service.build_forward(account, message, item["body"], item.get("from_address"), item["to"], item["cc"], item["bcc"], None, None, item.get("subject") or None)
                else:
                    built = self.service.build_reply(account, message, item["body"], item.get("from_address"), item["to"] or None,
                                                     item["cc"] or None, item["bcc"] or None, kind, True, None, item.get("subject") or None)
            self.service.bridge.send(self.service.target(account), built[0], built[1], built[2])
        except BridgeError as err:
            error = err.message or err.code
        except KeyError:
            error = "The email this answers is no longer kept in Enveliq."
        except Exception:
            error = "It could not be sent."
        if error is not None:
            log.info("scheduled email failed")
            self.book._update(uid, item["id"], {"state": "failed", "error": error, "failed_at": self.clock()})
            return
        self.book._update(uid, item["id"], None)
        try:
            if item["kind"] == "new":
                self.audit({"event": "email_sent", "actor_user_id": uid, "account_id": item["account_id"], "at": time.time(), "scheduled": True})
            else:
                if item["kind"] != "forward":
                    self.service.mark_replied(self.vault, item["account_id"], item["message_id"])
                self.audit({"event": "email_forwarded" if item["kind"] == "forward" else "reply_sent", "actor_user_id": uid,
                            "account_id": item["account_id"], "message_id": item["message_id"], "people": len(built[2]), "at": time.time(), "scheduled": True})
        except Exception:
            log.info("noting the scheduled email failed")
