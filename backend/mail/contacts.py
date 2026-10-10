"""A person's address book: names and email addresses, nothing else.

Built from the people Enveliq has seen (senders of mail it reads, and the people
you write to) and from an imported vCard. It is stored encrypted under the
vault's master key, one record per person, and only that person can read it.
Email text is never part of it.
"""
from __future__ import annotations

import re
import threading
import time
from typing import Any, Iterable

MAX_PEOPLE = 5000
_LOCK = threading.Lock()
_ADDR = re.compile(r"^[^@\s<>\",;:\\\x00-\x1f\x7f]{1,64}@[A-Za-z0-9.-]{1,253}\.[A-Za-z]{2,24}$")
_CTRL = re.compile(r"[\x00-\x1f\x7f]")


def record_id(user_id: str) -> str:
    return f"contacts:{user_id}"


def clean_address(value: Any) -> str | None:
    addr = str(value or "").strip().lower()
    return addr if len(addr) <= 254 and _ADDR.match(addr) else None


def clean_name(value: Any) -> str:
    return _CTRL.sub("", str(value or "")).replace("<", "").replace(">", "").strip()[:120]


def _load(vault: Any, user_id: str) -> dict[str, dict[str, Any]]:
    return dict((vault.get_global(record_id(user_id)) or {}).get("people") or {})


def _save(vault: Any, user_id: str, people: dict[str, dict[str, Any]]) -> None:
    if len(people) > MAX_PEOPLE:                       # keep the most used and most recent
        keep = sorted(people.items(), key=lambda kv: (kv[1].get("c", 0), kv[1].get("t", 0)), reverse=True)[:MAX_PEOPLE]
        people = dict(keep)
    vault.set_global(record_id(user_id), {"people": people})


def _public(addr: str, p: dict[str, Any]) -> dict[str, Any]:
    return {"address": addr, "name": p.get("n", ""), "count": int(p.get("c", 0)), "last": float(p.get("t", 0)), "source": p.get("s", "seen")}


def remember(vault: Any, user_id: str, people: Iterable[tuple[str, str]], source: str = "seen", own: Iterable[str] = ()) -> int:
    """Note people seen or written to. Each mention counts once. Returns how many were new."""
    mine = {a.lower() for a in own}
    now = time.time()
    added = 0
    with _LOCK:
        book = _load(vault, user_id)
        changed = False
        for name, address in people:
            addr = clean_address(address)
            if not addr or addr in mine:
                continue
            entry = book.get(addr)
            if entry is None:
                book[addr] = {"n": clean_name(name), "c": 1, "t": now, "s": source}
                added += 1
            else:
                entry["c"] = int(entry.get("c", 0)) + 1
                entry["t"] = now
                if not entry.get("n") and clean_name(name):
                    entry["n"] = clean_name(name)
            changed = True
        if changed:
            _save(vault, user_id, book)
    return added


def import_people(vault: Any, user_id: str, people: Iterable[tuple[str, str]]) -> dict[str, int]:
    added = skipped = invalid = 0
    now = time.time()
    with _LOCK:
        book = _load(vault, user_id)
        for name, address in people:
            addr = clean_address(address)
            if not addr:
                invalid += 1
                continue
            if addr in book:
                if not book[addr].get("n") and clean_name(name):
                    book[addr]["n"] = clean_name(name)
                skipped += 1
                continue
            book[addr] = {"n": clean_name(name), "c": 0, "t": now, "s": "import"}
            added += 1
        _save(vault, user_id, book)
    return {"added": added, "skipped": skipped, "invalid": invalid}


def search(vault: Any, user_id: str, query: str, limit: int = 8) -> list[dict[str, Any]]:
    q = query.strip().lower()
    book = _load(vault, user_id)
    hits = [(a, p) for a, p in book.items() if q in a or q in str(p.get("n", "")).lower()]

    def rank(item: tuple[str, dict[str, Any]]) -> tuple[int, int, float]:
        a, p = item
        starts = a.startswith(q) or str(p.get("n", "")).lower().startswith(q) or any(w.startswith(q) for w in str(p.get("n", "")).lower().split())
        return (0 if starts else 1, -int(p.get("c", 0)), -float(p.get("t", 0)))

    return [_public(a, p) for a, p in sorted(hits, key=rank)[:limit]]


def listing(vault: Any, user_id: str, offset: int = 0, limit: int = 50) -> dict[str, Any]:
    book = _load(vault, user_id)
    ordered = sorted(book.items(), key=lambda kv: (-int(kv[1].get("c", 0)), -float(kv[1].get("t", 0)), kv[0]))
    return {"total": len(ordered), "items": [_public(a, p) for a, p in ordered[offset:offset + limit]]}


def remove(vault: Any, user_id: str, address: str) -> bool:
    addr = clean_address(address)
    with _LOCK:
        book = _load(vault, user_id)
        if not addr or addr not in book:
            return False
        del book[addr]
        _save(vault, user_id, book)
    return True


def clear(vault: Any, user_id: str) -> None:
    with _LOCK:
        vault.set_global(record_id(user_id), {"people": {}})
