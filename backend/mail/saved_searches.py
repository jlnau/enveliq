"""Recent and saved searches: what a person typed and the filters they set, kept in their own encrypted vault record.

One record per person (`searches:<user id>`), readable only by that person. It holds the words and filters of the last few searches and of the
searches the person chose to save. It holds no email, no results and no addresses beyond what the person typed into a filter. The audit log never
sees any of it. Both lists can be cleared at any time.
"""
from __future__ import annotations

import re
import secrets
import threading
import time
from typing import Any

RECORD_PREFIX = "searches:"
MAX_RECENT = 8
MAX_SAVED = 30
_LOCK = threading.Lock()
_CTRL = re.compile(r"[\x00-\x1f\x7f]")
_DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")
KEYS = ("query", "sender", "to", "since", "until", "unread", "starred", "files", "include_junk", "account_id", "folder")


class SearchBookError(ValueError):
    """Plain, safe-to-show reason a change was refused."""


def clean_spec(raw: dict[str, Any]) -> dict[str, Any]:
    """Only the known fields, trimmed and typed. Anything else is dropped."""
    out: dict[str, Any] = {}
    for key in ("query", "sender", "to"):
        out[key] = _CTRL.sub(" ", str(raw.get(key) or "")).strip()[:200]
    for key in ("since", "until"):
        v = str(raw.get(key) or "").strip()
        out[key] = v if _DAY.match(v) else ""
    for key in ("unread", "starred", "files", "include_junk"):
        out[key] = bool(raw.get(key))
    out["account_id"] = re.sub(r"[^A-Za-z0-9_-]", "", str(raw.get("account_id") or ""))[:64]
    out["folder"] = _CTRL.sub("", str(raw.get("folder") or ""))[:300] if out["account_id"] else ""
    return out


def _same(a: dict[str, Any], b: dict[str, Any]) -> bool:
    return all(a.get(k) == b.get(k) for k in KEYS)


class SearchBook:
    def __init__(self, vault: Any, clock: Any = time.time) -> None:
        self.vault, self.clock = vault, clock

    def _load(self, user_id: str) -> dict[str, list[dict[str, Any]]]:
        raw = self.vault.get_global(RECORD_PREFIX + user_id) or {}
        return {"recent": [e for e in (raw.get("recent") or []) if isinstance(e, dict)],
                "saved": [e for e in (raw.get("saved") or []) if isinstance(e, dict) and e.get("id")]}

    def _save(self, user_id: str, data: dict[str, list[dict[str, Any]]]) -> None:
        self.vault.set_global(RECORD_PREFIX + user_id, data)

    def listing(self, user_id: str) -> dict[str, Any]:
        data = self._load(user_id)
        return {"recent": data["recent"], "saved": sorted(data["saved"], key=lambda e: str(e.get("name", "")).lower()), "max_saved": MAX_SAVED}

    def remember(self, user_id: str, spec: dict[str, Any]) -> None:
        spec = clean_spec(spec)
        with _LOCK:
            data = self._load(user_id)
            data["recent"] = [spec, *[e for e in data["recent"] if not _same(e, spec)]][:MAX_RECENT]
            self._save(user_id, data)

    def clear_recent(self, user_id: str) -> None:
        with _LOCK:
            data = self._load(user_id)
            data["recent"] = []
            self._save(user_id, data)

    def add(self, user_id: str, name: Any, spec: dict[str, Any]) -> dict[str, Any]:
        title = _CTRL.sub(" ", str(name or "")).strip()[:60]
        if not title:
            raise SearchBookError("Give this search a name.")
        spec = clean_spec(spec)
        with _LOCK:
            data = self._load(user_id)
            for e in data["saved"]:
                if str(e.get("name", "")).lower() == title.lower():          # the same name: replace that one
                    e.update({**spec, "name": title})
                    self._save(user_id, data)
                    return e
            if len(data["saved"]) >= MAX_SAVED:
                raise SearchBookError(f"You can keep up to {MAX_SAVED} saved searches. Remove one first.")
            entry = {"id": "s" + secrets.token_hex(8), "name": title, **spec, "saved_at": self.clock()}
            data["saved"].append(entry)
            self._save(user_id, data)
            return entry

    def remove(self, user_id: str, entry_id: str) -> bool:
        with _LOCK:
            data = self._load(user_id)
            kept = [e for e in data["saved"] if e.get("id") != entry_id]
            if len(kept) == len(data["saved"]):
                return False
            data["saved"] = kept
            self._save(user_id, data)
            return True

    def forget_user(self, user_id: str) -> None:
        self.vault.set_global(RECORD_PREFIX + user_id, {})
