"""Enveliq's own reminder emails carry a signed mark, so a sync does not turn them into tasks.

The mark is an HMAC of the message's own id with a key kept in the vault. Anybody can add a header called
X-Enveliq-Reminder to a message, but only this server can make one that checks out, so a hostile sender cannot use it to hide mail.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
from typing import Any

RECORD = "reminder_mark"
HEADER = "X-Enveliq-Reminder"


def _key(vault: Any) -> bytes:
    rec = vault.get_global(RECORD) or {}
    if not rec.get("key"):
        rec = {"key": secrets.token_hex(32)}
        vault.set_global(RECORD, rec)
    return bytes.fromhex(rec["key"])


def make(vault: Any, message_id: str) -> str:
    return hmac.new(_key(vault), message_id.encode(), hashlib.sha256).hexdigest()[:40]


def ours(vault: Any, message_id: str | None, value: str | None) -> bool:
    if not message_id or not value:
        return False
    return hmac.compare_digest(make(vault, message_id), value.strip())
