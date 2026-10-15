"""Messages from other services on your network (Home Assistant and the like), kept as a person's notifications.

A service connects to Enveliq's WebSocket door with a key that one person made for themselves, and sends short plain-text
notes. Each note lands in that person's own list, shown under the bell at the top of the inbox. Nothing here can read mail,
tasks or anyone else's list: a key belongs to exactly one person and only ever adds to that person's notifications.

Storage, inside the encrypted vault:
  inbound:keys      {"keys": {sha256(key): {"user": id, "made": time}}}   only the hash of a key is kept
  inbox:<user id>   {"items": [{"id", "title", "message", "source", "at", "unread"}]}
"""
from __future__ import annotations

import hashlib
import re
import secrets
import threading
import time
from typing import Any, Callable

KEYS_RECORD = "inbound:keys"
ITEMS_PREFIX = "inbox:"
KEY_PREFIX = "evq_"
MAX_ITEMS = 100                # notifications kept per person; the oldest go first
MAX_TITLE = 100
MAX_MESSAGE = 500
MAX_SOURCE = 40
MAX_FRAME = 4096               # characters in one WebSocket message
MAX_CONNECTIONS = 5            # open doors per person at once
MAX_PER_MINUTE = 30            # notes per key per minute

_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f‪-‮⁦-⁩]")


class InboundError(ValueError):
    """Something a service sent was not acceptable. The text is safe to send back to it."""


def clean(value: Any, limit: int, *, name: str, required: bool = False) -> str:
    if value is None:
        value = ""
    if not isinstance(value, str):
        raise InboundError(f"{name} must be text.")
    text = _CONTROL.sub("", value).replace("\r\n", "\n").strip()
    text = re.sub(r"[ \t]+", " ", text)
    if required and not text:
        raise InboundError(f"{name} is empty.")
    if len(text) > limit:
        raise InboundError(f"{name} is too long (at most {limit} characters).")
    return text


def _hash(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8", "replace")).hexdigest()


class InboundBook:
    def __init__(self, vault: Any, clock: Callable[[], float] = time.time):
        self.vault = vault
        self.clock = clock
        self._lock = threading.RLock()

    # keys
    def _keys(self) -> dict[str, dict[str, Any]]:
        raw = self.vault.get_global(KEYS_RECORD) or {}
        keys = raw.get("keys")
        return keys if isinstance(keys, dict) else {}

    def make_key(self, user_id: str) -> str:
        """A new key for this person. The old one stops working. The key is shown once; only its hash is kept."""
        key = KEY_PREFIX + secrets.token_urlsafe(32)
        with self._lock:
            keys = {h: v for h, v in self._keys().items() if v.get("user") != user_id}
            keys[_hash(key)] = {"user": user_id, "made": self.clock()}
            self.vault.set_global(KEYS_RECORD, {"keys": keys})
        return key

    def key_made(self, user_id: str) -> float:
        return max((float(v.get("made") or 0) for v in self._keys().values() if v.get("user") == user_id), default=0.0)

    def revoke_key(self, user_id: str) -> None:
        with self._lock:
            keys = self._keys()
            kept = {h: v for h, v in keys.items() if v.get("user") != user_id}
            if len(kept) != len(keys):
                self.vault.set_global(KEYS_RECORD, {"keys": kept})

    def user_for(self, key: str) -> str | None:
        if not isinstance(key, str) or not key.startswith(KEY_PREFIX) or len(key) > 200:
            return None
        found = self._keys().get(_hash(key))
        return str(found["user"]) if found and found.get("user") else None

    # notifications
    def _load(self, user_id: str) -> list[dict[str, Any]]:
        raw = self.vault.get_global(ITEMS_PREFIX + user_id) or {}
        items = raw.get("items")
        return [i for i in items if isinstance(i, dict)] if isinstance(items, list) else []

    def _save(self, user_id: str, items: list[dict[str, Any]]) -> None:
        self.vault.set_global(ITEMS_PREFIX + user_id, {"items": items})

    def add(self, user_id: str, title: Any, message: Any = "", source: Any = "") -> dict[str, Any]:
        item = {
            "id": "n" + secrets.token_hex(8),
            "title": clean(title, MAX_TITLE, name="The title"),
            "message": clean(message, MAX_MESSAGE, name="The message"),
            "source": clean(source, MAX_SOURCE, name="The source"),
            "at": self.clock(),
            "unread": True,
        }
        if not item["title"] and not item["message"]:
            raise InboundError("Send a title or a message.")
        with self._lock:
            items = [item] + self._load(user_id)
            self._save(user_id, items[:MAX_ITEMS])
        return item

    def view(self, user_id: str) -> dict[str, Any]:
        items = self._load(user_id)
        return {
            "items": [{"id": i["id"], "title": i.get("title", ""), "message": i.get("message", ""), "source": i.get("source", ""),
                       "at": i.get("at"), "unread": bool(i.get("unread"))} for i in items if i.get("id")],
            "unread": sum(1 for i in items if i.get("unread")),
            "key_made": self.key_made(user_id) or None,
        }

    def unread(self, user_id: str) -> int:
        return sum(1 for i in self._load(user_id) if i.get("unread"))

    def mark_read(self, user_id: str) -> None:
        with self._lock:
            items = self._load(user_id)
            if any(i.get("unread") for i in items):
                for i in items:
                    i["unread"] = False
                self._save(user_id, items)

    def dismiss(self, user_id: str, item_id: str) -> bool:
        with self._lock:
            items = self._load(user_id)
            kept = [i for i in items if i.get("id") != item_id]
            if len(kept) == len(items):
                return False
            self._save(user_id, kept)
            return True

    def clear(self, user_id: str) -> None:
        with self._lock:
            self._save(user_id, [])

    def forget_user(self, user_id: str) -> None:
        """A person was deleted: their notifications go and their key stops working."""
        with self._lock:
            self.revoke_key(user_id)
            self._save(user_id, [])
