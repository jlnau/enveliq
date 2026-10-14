"""Drafts: emails a person started and has not sent, kept for 14 days.

One encrypted record per person (`drafts:<user id>`) under the vault's master key. A draft holds only what the
person typed: who it is for, the subject and their own words, and which email it answers. It never holds the
original email's text, and attachments are not kept. Only that person can read it. A draft that has not been
saved again for 14 days is removed the next time the list is read or a draft is saved.
"""
from __future__ import annotations

import re
import secrets
import threading
import time
from typing import Any, Callable

RECORD_PREFIX = "drafts:"
KEEP_SECONDS = 14 * 86400
MAX_DRAFTS = 50
MAX_BODY = 100_000
MAX_PEOPLE = 50
KINDS = ("new", "reply", "reply_all", "forward")
_LOCK = threading.Lock()
_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")       # everything except new line and tab
_LINE = re.compile(r"[\x00-\x1f\x7f]")


class DraftError(ValueError):
    """Plain, safe-to-show reason a change was refused."""


def _line(value: Any, limit: int) -> str:
    return _LINE.sub(" ", str(value or "")).strip()[:limit]


def _people(values: Any) -> list[str]:
    return [p for p in (_line(v, 320) for v in list(values or [])[:MAX_PEOPLE]) if p]


class Drafts:
    def __init__(self, vault: Any, clock: Callable[[], float] = time.time) -> None:
        self.vault = vault
        self.clock = clock

    def _load(self, user_id: str) -> list[dict[str, Any]]:
        raw = self.vault.get_global(RECORD_PREFIX + user_id) or {}
        cutoff = self.clock() - KEEP_SECONDS
        return [d for d in (raw.get("items") or []) if isinstance(d, dict) and d.get("id") and float(d.get("updated", 0)) >= cutoff]

    def _save(self, user_id: str, items: list[dict[str, Any]]) -> None:
        self.vault.set_global(RECORD_PREFIX + user_id, {"items": items})

    def _public(self, d: dict[str, Any]) -> dict[str, Any]:
        return {**{k: d.get(k) for k in ("id", "kind", "account_id", "message_id", "from_address", "to", "cc", "bcc", "subject", "body", "created", "updated")},
                "expires": float(d.get("updated", 0)) + KEEP_SECONDS}

    def listing(self, user_id: str) -> list[dict[str, Any]]:
        """The person's drafts, newest first. Also removes the ones older than 14 days."""
        with _LOCK:
            raw = self.vault.get_global(RECORD_PREFIX + user_id) or {}
            items = self._load(user_id)
            if len(items) != len(raw.get("items") or []):
                self._save(user_id, items)
        return [self._public(d) for d in sorted(items, key=lambda d: d.get("updated", 0), reverse=True)]

    def save(self, user_id: str, draft_id: str | None, data: dict[str, Any]) -> dict[str, Any] | None:
        """Create a draft (draft_id None) or replace one. None when that draft no longer exists."""
        kind = data.get("kind")
        if kind not in KINDS:
            raise DraftError("This kind of email cannot be saved as a draft.")
        to, cc, bcc = _people(data.get("to")), _people(data.get("cc")), _people(data.get("bcc"))
        subject = _line(data.get("subject"), 900)
        body = _CTRL.sub("", str(data.get("body") or "").replace("\r\n", "\n").replace("\r", "\n"))[:MAX_BODY]
        if not (to or cc or bcc or subject or body.strip()):
            raise DraftError("There is nothing to save yet.")
        now = self.clock()
        with _LOCK:
            items = self._load(user_id)
            old = next((d for d in items if d["id"] == draft_id), None) if draft_id else None
            if draft_id and old is None:
                return None
            if old is None and len(items) >= MAX_DRAFTS:
                raise DraftError(f"You can keep up to {MAX_DRAFTS} drafts. Delete one first.")
            fresh = {"id": old["id"] if old else "d" + secrets.token_hex(8), "kind": kind,
                     "account_id": _line(data.get("account_id"), 64) or None, "message_id": _line(data.get("message_id"), 64) or None,
                     "from_address": _line(data.get("from_address"), 320) or None, "to": to, "cc": cc, "bcc": bcc,
                     "subject": subject, "body": body, "created": old["created"] if old else now, "updated": now}
            self._save(user_id, [d for d in items if d["id"] != fresh["id"]] + [fresh])
        return self._public(fresh)

    def remove(self, user_id: str, draft_id: str) -> bool:
        with _LOCK:
            items = self._load(user_id)
            kept = [d for d in items if d["id"] != draft_id]
            if len(kept) == len(items):
                return False
            self._save(user_id, kept)
        return True

    def forget_user(self, user_id: str) -> None:
        self.vault.set_global(RECORD_PREFIX + user_id, {})
