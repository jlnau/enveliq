"""Automatic sync: every few minutes, fetch new unread mail for each mailbox
(and summarise it if the owner turned AI summaries on), and forget items
handled in another app.

It does exactly what the Sync mail button does, with these differences:
* It runs only while the vault is unlocked, and its work never counts as
  activity, so it cannot keep an idle vault from locking. When the vault
  locks it pauses until someone unlocks it.
* A mailbox that fails is retried later with a growing delay (up to an hour);
  nothing is logged or audited beyond a fixed error code, never server output.
* A mailbox owner can switch it off per mailbox (settings.auto_sync = false).
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable

from . import review
from .errors import BridgeError
from .service import MAIL_METHODS, MailService

log = logging.getLogger("enveliq.sync")

MIN_MINUTES = 2
DEFAULT_MINUTES = 10
CONFIG_RECORD = "sync_config"
MAX_BACKOFF = 3600.0
SUMMARY_BATCHES = 3


class AutoSync:
    def __init__(self, vault: Any, service: MailService, minutes: int | None, clock: Callable[[], float] = time.monotonic):
        """`minutes` from the server's environment wins (0 = off); None lets an
        administrator choose in the app (default 10)."""
        self.vault = vault
        self.service = service
        self.env_minutes = None if minutes is None else self.clean(minutes)
        self.minutes = DEFAULT_MINUTES if self.env_minutes is None else self.env_minutes
        self.source = "environment" if self.env_minutes is not None else "default"
        self.clock = clock
        self.state: dict[str, dict[str, Any]] = {}      # account id -> last result (no secrets, no mail content)
        self._next: dict[str, float] = {}
        self._fails: dict[str, int] = {}
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.mail_alerts: Any = None                    # set by the application: new-email alerts (mail/mail_alerts.py)
        self.checker: Any = None                        # set by the application: answers forwarded emails (mail/checkbox.py)

    @staticmethod
    def clean(minutes: int) -> int:
        return 0 if minutes <= 0 else max(MIN_MINUTES, min(int(minutes), 1440))

    @property
    def enabled(self) -> bool:
        return self.minutes > 0

    def refresh(self) -> None:
        """Pick the interval in force: the environment wins, else what an administrator saved."""
        if self.env_minutes is not None:
            return
        saved = self.vault.get_global(CONFIG_RECORD) or {}
        if isinstance(saved.get("minutes"), int) and not isinstance(saved.get("minutes"), bool):
            self.minutes, self.source = self.clean(saved["minutes"]), "saved"
        else:
            self.minutes, self.source = DEFAULT_MINUTES, "default"

    def save(self, minutes: int) -> None:
        self.vault.set_global(CONFIG_RECORD, {"minutes": self.clean(minutes)})
        self.refresh()

    def start(self) -> None:
        if self._thread:
            return
        self._thread = threading.Thread(target=self._run, name="enveliq-auto-sync", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        while not self._stop.wait(30):
            try:
                self.run_once()
            except Exception:                           # never let the loop die
                log.warning("auto sync pass failed")

    def run_once(self) -> int:
        """One pass over every mailbox that is due. Returns how many were synced."""
        if not self.vault.is_unlocked():
            return 0
        done = 0
        with self.vault.passive():
            try:
                self.refresh()
                if not self.enabled:
                    return 0
                accounts = self.vault.list_accounts()
            except Exception:
                return 0
            self.service.refresh_ai(self.vault)
            if self.checker is not None:
                try:
                    self.checker.poll()
                except Exception:
                    log.info("check address pass failed")
            for account in accounts:
                try:
                    review.purge_expired(self.vault, account)
                except Exception:
                    log.info("clearing old kept items failed")
            live = {a["id"] for a in accounts}
            for gone in [k for k in self.state if k not in live]:
                self.state.pop(gone, None); self._next.pop(gone, None); self._fails.pop(gone, None)
            arrived: dict[str, list[dict[str, Any]]] = {}      # person -> the emails that arrived in this pass
            for account in accounts:
                if self._stop.is_set() or not self.vault.is_unlocked():
                    break
                if account.get("auth_method") not in MAIL_METHODS or self.service.is_check_address(account):
                    continue
                if (account.get("settings") or {}).get("auto_sync") is False:
                    continue
                now = self.clock()
                if now < self._next.get(account["id"], 0.0):
                    continue
                before = self._known_ids(account) if self.mail_alerts is not None else None
                first = account["id"] not in self.state
                self._sync_one(account)
                done += 1
                if before is not None and account.get("owner_user_id") and not (first and not before):
                    arrived.setdefault(account["owner_user_id"], []).extend(self._new_since(account, before))
            if self.mail_alerts is not None:
                for uid, new in arrived.items():
                    if new:                                       # nothing arrived for this person: say nothing
                        self.mail_alerts.send(uid, new)
        return done

    def _known_ids(self, account: dict[str, Any]) -> set[str]:
        try:
            return {m["id"] for m in self.vault.list_messages(account["id"])}
        except Exception:
            return set()

    def _new_since(self, account: dict[str, Any], before: set[str]) -> list[dict[str, Any]]:
        """The unread emails stored since `before`, as the small facts an alert needs (no summary, no address)."""
        try:
            fresh = [m for m in self.vault.list_messages(account["id"])
                     if m["id"] not in before and m.get("state", "unread") == "unread" and not m.get("from_all_mail") and not m.get("ai_pending")]
        except Exception:
            return []
        fresh.sort(key=lambda m: m.get("received_at") or 0, reverse=True)
        return [{"account_id": account["id"], "id": m["id"], "sender_display": m.get("sender_display"), "sender_address": m.get("sender_address"), "subject": m.get("subject"), "priority": m.get("priority"), "action_required": m.get("action_required")} for m in fresh]

    def _sync_one(self, account: dict[str, Any]) -> None:
        aid = account["id"]
        result: dict[str, Any] = {"at": time.time(), "ok": False}
        try:
            r = self.service.sync(self.vault, account)
            result.update(ok=True, added=r["added"], removed=r.get("removed", 0), summarised=0)
            queued = self.service.on_pending is not None and self.service.hold_new_mail
            if queued:
                self.service.enqueue_held(self.vault, account)         # new mail waits in the AI queue; the queue writes the summaries
            if not queued and (account.get("settings") or {}).get("ai_summaries") and self.service.summariser.enabled:
                try:
                    for _ in range(SUMMARY_BATCHES):
                        s = self.service.summarise_pending(self.vault, account)
                        result["summarised"] += s["summarised"]
                        if not s["remaining"] or not s["summarised"]:
                            break
                except BridgeError as err:
                    result["ai_error"] = err.code
            if self.service.waits is not None:
                try:
                    self.service.waiting_scan(self.vault, account)
                except Exception:                       # following sent mail never makes a sync look failed
                    log.info("waiting scan failed")
            self._fails[aid] = 0
        except BridgeError as err:
            if err.code == "busy":                      # someone is syncing it by hand right now
                self._next[aid] = self.clock() + 60.0
                return
            result["error"] = err.code
            self._fails[aid] = self._fails.get(aid, 0) + 1
            log.info("auto sync failed (%s)", err.code)
        except Exception:
            result["error"] = "failed"
            self._fails[aid] = self._fails.get(aid, 0) + 1
            log.info("auto sync failed")
        wait = self.minutes * 60.0 * (2 ** min(self._fails.get(aid, 0), 6) if self._fails.get(aid) else 1)
        self._next[aid] = self.clock() + min(wait, max(MAX_BACKOFF, self.minutes * 60.0))
        self.state[aid] = result

    def status_for(self, account_ids: set[str]) -> dict[str, Any]:
        return {"enabled": self.enabled, "minutes": self.minutes, "source": self.source,
                "accounts": {k: v for k, v in self.state.items() if k in account_ids}}
