"""Which optional features are on.

An administrator switches each feature on or off for the whole server. A person
can then switch off, for themselves, any feature the administrator left on
(someone who only wants the inbox can turn the rest off). A feature is in use
only when both agree. Everything is on until someone turns it off.
"""
from __future__ import annotations

from typing import Any

KEYS = ("compose", "address_book", "sent", "media", "all_mail", "shipping", "subscriptions", "travel", "waiting", "messages", "write_help", "rss", "tags", "find_mail")
LABELS = {
    "compose": "New email",
    "address_book": "Address book",
    "sent": "Sent (last 14 days)",
    "media": "Pictures and attachment previews",
    "all_mail": "All emails (last 14 days)",
    "shipping": "Shipping (follow online orders)",
    "subscriptions": "Subscriptions (renewals and free trials)",
    "travel": "Trips (flights, stays and hire cars)",
    "waiting": "Waiting for reply (follow sent mail)",
    "messages": "Messages (write to the other people here)",
    "write_help": "Writing help (AI suggests or checks a reply)",
    "rss": "News feeds (follow websites you like)",
    "tags": "Tags (the labels from your mail service)",
    "find_mail": "Find any email (search all your mail)",
}
RECORD = "features"


def admin_flags(vault: Any) -> dict[str, bool]:
    saved = vault.get_global(RECORD) or {}
    return {k: saved.get(k) is not False for k in KEYS}


def save_admin_flags(vault: Any, flags: dict[str, bool | None]) -> dict[str, bool]:
    current = admin_flags(vault)
    for k in KEYS:
        if flags.get(k) is not None:
            current[k] = bool(flags[k])
    vault.set_global(RECORD, current)
    return current


def _prefs(vault: Any, user_id: str | None) -> dict[str, Any]:
    if not user_id:
        return {}
    try:
        return (vault.get_user(user_id).get("prefs") or {}).get("features") or {}
    except KeyError:
        return {}


def user_flags(vault: Any, user_id: str | None) -> dict[str, bool]:
    raw = _prefs(vault, user_id)
    out = {k: raw.get(k) is not False for k in KEYS}
    out["address_book_auto"] = raw.get("address_book_auto") is not False
    return out


def save_user_flags(vault: Any, users: Any, user_id: str, flags: dict[str, bool | None]) -> dict[str, bool]:
    user = users.get(user_id)
    prefs = dict(user.get("prefs") or {})
    current = user_flags(vault, user_id)
    for k in (*KEYS, "address_book_auto"):
        if flags.get(k) is not None:
            current[k] = bool(flags[k])
    prefs["features"] = current
    user["prefs"] = prefs
    users.save(user)
    return user_flags(vault, user_id)


def effective(vault: Any, user_id: str | None) -> dict[str, bool]:
    admin, mine = admin_flags(vault), user_flags(vault, user_id)
    return {k: admin[k] and mine[k] for k in KEYS}


def overview(vault: Any, user_id: str | None) -> dict[str, Any]:
    admin, mine = admin_flags(vault), user_flags(vault, user_id)
    return {"admin": admin, "user": mine, "effective": {k: admin[k] and mine[k] for k in KEYS}, "labels": LABELS}
