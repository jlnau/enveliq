"""Export my data: everything Enveliq keeps about one person, as a readable file.

It is built from that person's own records only, chosen by the signed-in session on
the server. It never holds a password, token, key, authenticator or passkey secret,
the calendar feed address, or another person's mail. Raw email bodies and
attachments are not kept by Enveliq, so they are not in it either.
"""
from __future__ import annotations

import time
from typing import Any, Callable

from . import version

# Records kept per person under a prefix. Each is that person's own list or settings.
PLAIN_RECORDS = {
    "tasks": "tasks:",
    "orders": "ship:",
    "subscriptions": "subs:",
    "trips": "trips:",
    "junk_mail": "junk:",
    "waiting_for_replies": "wait:",
    "writing_help": "writehelp:",
    "writing_style": "style:",
    "daily_summaries": "digest:",
    "important_people": "important:",
    "signature_and_saved_replies": "saved:",
    "drafts": "drafts:",
    "emails_to_send_later": "scheduled:",
    "rules": "rules:",
    "clean_up_kept_senders": "senders:",
    "assistant_chats": "agent:",
}
# Never copied out of a record, wherever they appear.
SECRET_KEYS = {"password", "secret", "token", "api_key", "refresh_token", "oauth_refresh_token", "feed_token", "totp", "passkeys", "recovery", "values"}


def strip_secrets(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: strip_secrets(v) for k, v in value.items() if str(k).lower() not in SECRET_KEYS}
    if isinstance(value, list):
        return [strip_secrets(v) for v in value]
    return value


def build_exporter(vault: Any, users: Any, *, public_account: Callable, public_message: Callable, principal_of: Callable,
                   prefs: Callable, contacts_of: Callable, threads_of: Callable, notify_state: Callable, sync_state: Callable) -> Callable[[str], dict[str, Any]]:
    def export(user_id: str) -> dict[str, Any]:
        user = users.get(user_id)
        me = principal_of(user)
        out: dict[str, Any] = {
            "about_this_file": "Everything Enveliq keeps about you. It does not hold passwords, keys, tokens or other people's mail.",
            "enveliq_version": version.VERSION,
            "exported_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "you": {**users.public(user, include_security=False), "about": user.get("about") or ""},
            "review_settings": prefs(user_id),
        }
        boxes = []
        for account in vault.list_accounts():
            if account.get("owner_user_id") != user_id:                  # only mailboxes this person owns
                continue
            card = public_account(account, me)
            card["kept_messages"] = [public_message(m) for m in vault.list_messages(account["id"])]
            boxes.append(strip_secrets(card))
        out["mailboxes"] = boxes
        for key, prefix in PLAIN_RECORDS.items():
            out[key] = strip_secrets(vault.get_global(prefix + user_id) or {})
        out["address_book"] = contacts_of(user_id)
        out["conversations"] = threads_of(user_id)
        out["notification_settings"] = notify_state(user_id)
        out["calendar_settings"] = sync_state(user_id)
        return out
    return export
