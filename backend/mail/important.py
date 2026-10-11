"""Important people: addresses a person wants to see first.

One encrypted record per person (`important:<user id>`) under the vault's master key. It holds only
names and email addresses the person chose themselves, never email text, and only that person can read it.
The page uses the list to put mail from these people at the top; Enveliq's server never reorders anything.
"""
from __future__ import annotations

import threading
import time
from typing import Any

from .contacts import clean_address, clean_name

RECORD_PREFIX = "important:"
MAX_PEOPLE = 200
_LOCK = threading.Lock()


class ImportantError(ValueError):
    """The address is not valid, or the list is full. The message is plain and safe to show."""


class ImportantPeople:
    def __init__(self, vault: Any) -> None:
        self.vault = vault

    def _load(self, user_id: str) -> dict[str, dict[str, Any]]:
        return dict((self.vault.get_global(RECORD_PREFIX + user_id) or {}).get("people") or {})

    def _save(self, user_id: str, people: dict[str, dict[str, Any]]) -> None:
        self.vault.set_global(RECORD_PREFIX + user_id, {"people": people})

    def listing(self, user_id: str) -> list[dict[str, Any]]:
        people = self._load(user_id)
        ordered = sorted(people.items(), key=lambda kv: (str(kv[1].get("n", "")).lower() or kv[0], kv[0]))
        return [{"address": a, "name": p.get("n", ""), "added": float(p.get("t", 0))} for a, p in ordered]

    def add(self, user_id: str, address: str, name: str = "") -> list[dict[str, Any]]:
        addr = clean_address(address)
        if not addr:
            raise ImportantError("That does not look like an email address.")
        with _LOCK:
            people = self._load(user_id)
            if addr not in people and len(people) >= MAX_PEOPLE:
                raise ImportantError(f"You can keep up to {MAX_PEOPLE} important people. Remove someone first.")
            entry = people.get(addr) or {"t": time.time()}
            if clean_name(name):
                entry["n"] = clean_name(name)
            entry.setdefault("n", "")
            people[addr] = entry
            self._save(user_id, people)
        return self.listing(user_id)

    def remove(self, user_id: str, address: str) -> bool:
        addr = clean_address(address)
        with _LOCK:
            people = self._load(user_id)
            if not addr or addr not in people:
                return False
            del people[addr]
            self._save(user_id, people)
        return True

    def forget_user(self, user_id: str) -> None:
        self.vault.set_global(RECORD_PREFIX + user_id, {})
