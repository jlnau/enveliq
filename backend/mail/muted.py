"""Muted conversations: a thread a person does not want to hear about again.

Muting remembers the message identifiers of one conversation (the email's own Message-ID and the ones in its References
header). When a later email arrives whose identifiers overlap, it is filed in the mailbox's Archive folder at once, the same way a
rule does, so it never reaches the inbox and never triggers an alert. Nothing is deleted: the emails stay in the connected mailbox,
and an entry can be taken off again (Unmute) at any time. One encrypted record per person (`muted:<user id>`). It holds the subject
line (so the person can recognise the conversation), a count, and opaque identifiers; no email text and no addresses.
"""
from __future__ import annotations

import re
import secrets
import threading
import time
from typing import Any, Iterable

RECORD_PREFIX = "muted:"
MAX_MUTED = 300
MAX_IDS = 150
_LOCK = threading.Lock()
_ID = re.compile(r"^<[^<>\s]{1,994}>$")
_CTRL = re.compile(r"[\x00-\x1f\x7f]")


class MuteError(ValueError):
    """Plain, safe-to-show reason a change was refused."""


def thread_ids(reply_context: dict[str, Any] | None) -> list[str]:
    """The identifiers that tie an email to its conversation: its own Message-ID and everything in References."""
    ctx = reply_context or {}
    out: list[str] = []
    for value in [*(ctx.get("references") or []), ctx.get("message_id")]:
        if isinstance(value, str) and _ID.match(value) and value not in out:
            out.append(value)
    return out


class MutedBook:
    def __init__(self, vault: Any, clock: Any = time.time) -> None:
        self.vault, self.clock = vault, clock

    def _load(self, user_id: str) -> list[dict[str, Any]]:
        raw = self.vault.get_global(RECORD_PREFIX + user_id) or {}
        return [e for e in (raw.get("items") or []) if isinstance(e, dict) and e.get("id") and e.get("ids")]

    def _save(self, user_id: str, items: list[dict[str, Any]]) -> None:
        self.vault.set_global(RECORD_PREFIX + user_id, {"items": items})

    @staticmethod
    def _public(e: dict[str, Any]) -> dict[str, Any]:
        return {"id": e["id"], "subject": e.get("subject", ""), "muted_at": e.get("muted_at"), "count": int(e.get("count") or 0), "last_at": e.get("last_at")}

    def listing(self, user_id: str) -> dict[str, Any]:
        items = sorted(self._load(user_id), key=lambda e: e.get("muted_at") or 0, reverse=True)
        return {"items": [self._public(e) for e in items], "max": MAX_MUTED}

    def add(self, user_id: str, subject: Any, ids: list[str]) -> dict[str, Any]:
        ids = [i for i in ids if isinstance(i, str) and _ID.match(i)][-MAX_IDS:]
        if not ids:
            raise MuteError("This email has no identifier that ties it to a conversation, so it cannot be muted.")
        title = _CTRL.sub(" ", str(subject or "")).strip()[:200] or "(no subject)"
        title = re.sub(r"(?i)^((re|fwd?|aw|sv)\s*:\s*)+", "", title).strip() or title
        with _LOCK:
            items = self._load(user_id)
            for e in items:
                if set(e["ids"]) & set(ids):                         # the conversation is already muted: widen it
                    e["ids"] = list(dict.fromkeys([*e["ids"], *ids]))[-MAX_IDS:]
                    self._save(user_id, items)
                    return self._public(e)
            if len(items) >= MAX_MUTED:
                raise MuteError(f"You can keep up to {MAX_MUTED} muted conversations. Unmute one first.")
            entry = {"id": "q" + secrets.token_hex(8), "subject": title, "ids": ids, "muted_at": self.clock(), "count": 0, "last_at": None}
            items.append(entry)
            self._save(user_id, items)
            return self._public(entry)

    def remove(self, user_id: str, entry_id: str) -> bool:
        with _LOCK:
            items = self._load(user_id)
            kept = [e for e in items if e["id"] != entry_id]
            if len(kept) == len(items):
                return False
            self._save(user_id, kept)
        return True

    def match(self, user_id: str, ids: Iterable[str]) -> str | None:
        """The id of the muted conversation these identifiers belong to, or None."""
        want = set(ids)
        if not want:
            return None
        for e in self._load(user_id):
            if want & set(e["ids"]):
                return e["id"]
        return None

    def hit(self, user_id: str, entry_id: str, ids: Iterable[str]) -> None:
        """An email in a muted conversation was filed away: count it and learn its identifiers, so a long conversation stays caught."""
        with _LOCK:
            items = self._load(user_id)
            for e in items:
                if e["id"] == entry_id:
                    e["ids"] = list(dict.fromkeys([*e["ids"], *[i for i in ids if isinstance(i, str) and _ID.match(i)]]))[-MAX_IDS:]
                    e["count"] = int(e.get("count") or 0) + 1
                    e["last_at"] = self.clock()
                    self._save(user_id, items)
                    return

    def forget_user(self, user_id: str) -> None:
        self.vault.set_global(RECORD_PREFIX + user_id, {})
