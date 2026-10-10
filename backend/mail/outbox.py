"""Undo send: replies wait in a short queue before they leave.

A person can choose to have every reply held for up to a minute. While it is
held they can cancel it and get their text back. The queue lives in this
server's memory only (nothing about it is written to disk), so a restart
within the waiting time drops the held replies; the window is a minute at most.
The reply is checked when it is queued (addresses, sender) and sent by a
background thread when its time comes. The thread's work never counts as
activity, so it cannot keep an idle vault from locking.
"""
from __future__ import annotations

import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from email.message import EmailMessage
from typing import Any, Callable

from ..models import RetainedMessageCreate
from .errors import BridgeError

log = logging.getLogger("enveliq.outbox")

MAX_DELAY = 60
MAX_PENDING = 10          # per person
KEEP_RESULT = 120.0       # how long a finished item stays listed, so a page can show the outcome


@dataclass
class Item:
    user_id: str
    account_id: str
    message_id: str | None            # the email being replied to; None for a new email
    msg: EmailMessage
    chosen: str
    recipients: list[str]
    body: str
    send_at: float
    draft: dict[str, Any] | None = None   # a new email's recipients and subject, handed back on undo
    on_sent: Callable[[], None] | None = None
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    state: str = "pending"            # pending, sending, sent, failed
    error: str | None = None
    done_at: float = 0.0


class Outbox:
    def __init__(self, vault: Any, service: Any, audit: Callable[[dict[str, Any]], None] | None = None, clock: Callable[[], float] = time.time):
        self.vault = vault
        self.service = service
        self.audit = audit or vault.audit
        self.clock = clock
        self._items: dict[str, Item] = {}
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # ---------- queue ----------

    def enqueue(self, user_id: str, account_id: str, message_id: str | None, built: tuple[EmailMessage, str, list[str]], body: str, delay: float,
                draft: dict[str, Any] | None = None, on_sent: Callable[[], None] | None = None) -> Item:
        delay = max(1.0, min(float(delay), float(MAX_DELAY)))
        with self._lock:
            self._forget_old()
            if sum(1 for i in self._items.values() if i.user_id == user_id and i.state in ("pending", "sending")) >= MAX_PENDING:
                raise BridgeError("busy", "Too many replies are waiting to send. Wait a moment.")
            msg, chosen, recipients = built
            item = Item(user_id, account_id, message_id, msg, chosen, recipients, body, self.clock() + delay, draft=draft, on_sent=on_sent)
            self._items[item.id] = item
        self.start()
        return item

    def listing(self, user_id: str) -> list[dict[str, Any]]:
        with self._lock:
            self._forget_old()
            return [self.public(i) for i in sorted(self._items.values(), key=lambda i: i.send_at) if i.user_id == user_id]

    @staticmethod
    def public(item: Item) -> dict[str, Any]:
        return {"id": item.id, "kind": "new" if item.draft else "reply", "account_id": item.account_id, "message_id": item.message_id, "state": item.state,
                "send_at": item.send_at, "from": item.chosen, "to": item.recipients[0] if item.recipients else "", "error": item.error,
                "subject": (item.draft or {}).get("subject", "")}

    def cancel(self, user_id: str, item_id: str) -> Item | None:
        """Take a waiting reply back. None if there is no such reply for this person; raises if it has already gone."""
        with self._lock:
            item = self._items.get(item_id)
            if item is None or item.user_id != user_id:
                return None
            if item.state != "pending":
                raise BridgeError("conflict", "That reply has already been sent.")
            del self._items[item_id]
            return item

    def _forget_old(self) -> None:
        now = self.clock()
        for key in [k for k, i in self._items.items() if i.state in ("sent", "failed") and now - i.done_at > KEEP_RESULT]:
            del self._items[key]

    # ---------- sending ----------

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="enveliq-outbox", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        while not self._stop.wait(0.5):
            try:
                self.run_due()
            except Exception:
                log.warning("outbox pass failed")

    def run_due(self) -> int:
        """Send every reply whose time has come. Returns how many were attempted."""
        with self._lock:
            now = self.clock()
            due = [i for i in self._items.values() if i.state == "pending" and i.send_at <= now]
            for item in due:
                item.state = "sending"
        for item in due:
            self._send(item)
        return len(due)

    def _send(self, item: Item) -> None:
        error = None
        try:
            with self.vault.passive():
                account = self.vault.get_account(item.account_id)
                self.service.bridge.send(self.service.target(account), item.msg, item.chosen, item.recipients)
        except BridgeError as err:
            error = err.code
        except Exception:
            error = "failed"
        if error is None:
            try:
                if item.message_id:
                    self.service.mark_replied(self.vault, item.account_id, item.message_id)
                    self.audit({"event": "reply_sent", "actor_user_id": item.user_id, "account_id": item.account_id,
                                "message_id": item.message_id, "at": time.time(), "undo_window": True})
                else:
                    self.audit({"event": "email_sent", "actor_user_id": item.user_id, "account_id": item.account_id,
                                "at": time.time(), "undo_window": True})
                if item.on_sent:
                    item.on_sent()
            except Exception:
                log.info("noting the reply failed")
        else:
            log.info("queued reply failed (%s)", error)
        with self._lock:
            item.state = "failed" if error else "sent"
            item.error = error
            item.done_at = self.clock()
