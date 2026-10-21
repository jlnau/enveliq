"""Reviewed and Archived lists, how long they are kept, and AI instructions.

When someone marks an email Reviewed or Archives it, the real mailbox is changed
straight away (marked read, or moved to Archive). Enveliq can also keep the
short summary card for a few days so they can look again. Only the fields that
were already stored (sender, subject, summary and the like) are kept; the email
text and attachment details are dropped, and so is the link back to the mailbox
message, except on a Reviewed card, which keeps it so the email can be marked
unread again.

Each person chooses whether to keep each list and for how many days; an
administrator sets the longest anyone may choose. Cards past their time are
removed. Administrators and each person can also add instructions for how
summaries are written. They are added to the model's fixed instructions and can
never change the reply format or the rule to ignore commands inside an email.
An administrator can also replace the built-in prompt itself; the reply format
and that rule are still always added after it.
"""
from __future__ import annotations

import re
import time
from typing import Any

from .llm import DEFAULT_PROMPT, FIXED_PROMPT, PROMPT_MAX, PROMPT_MIN

CONFIG_RECORD = "review_config"
DEFAULT_MAX_DAYS = 14
ABSOLUTE_MAX_DAYS = 90
DEFAULT_USER_DAYS = 7
ADMIN_INSTRUCTIONS_MAX = 2000
USER_INSTRUCTIONS_MAX = 1000
KEPT_STATES = ("reviewed", "archived")
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def clean_instructions(value: Any, limit: int) -> str:
    text = _CONTROL.sub("", str(value or "")).replace("\r\n", "\n").strip()
    return text[:limit]


def clean_prompt(value: Any) -> str:
    text = _CONTROL.sub("", str(value or "")).replace("\r\n", "\n").strip()
    return text[:PROMPT_MAX]


def prompt_state(vault: Any) -> dict[str, Any]:
    """The built-in prompt as the administrator sees it: the part that can be replaced, the part that is always added, and any replacement."""
    custom = clean_prompt((vault.get_global(CONFIG_RECORD) or {}).get("prompt"))
    return {"default": DEFAULT_PROMPT, "fixed": FIXED_PROMPT, "custom": custom, "in_use": bool(custom),
            "min": PROMPT_MIN, "max": PROMPT_MAX}


def active_prompt(vault: Any) -> str:
    """The replacement prompt, or "" to use the built-in one."""
    return prompt_state(vault)["custom"]


def save_prompt(vault: Any, prompt: str) -> dict[str, Any]:
    """Store a replacement prompt, or restore the built-in one when `prompt` is empty."""
    text = clean_prompt(prompt)
    if text and len(text) < PROMPT_MIN:
        raise ValueError("too_short")
    data = dict(vault.get_global(CONFIG_RECORD) or {})
    if text:
        data["prompt"] = text
    else:
        data.pop("prompt", None)
    vault.set_global(CONFIG_RECORD, data)
    return prompt_state(vault)


def admin_config(vault: Any) -> dict[str, Any]:
    saved = vault.get_global(CONFIG_RECORD) or {}
    days = saved.get("max_days")
    if not isinstance(days, int) or isinstance(days, bool) or not 1 <= days <= ABSOLUTE_MAX_DAYS:
        days = DEFAULT_MAX_DAYS
    return {"max_days": days, "instructions": clean_instructions(saved.get("instructions"), ADMIN_INSTRUCTIONS_MAX)}


def save_admin_config(vault: Any, max_days: int, instructions: str) -> dict[str, Any]:
    data = dict(vault.get_global(CONFIG_RECORD) or {})
    data["max_days"] = max(1, min(int(max_days), ABSOLUTE_MAX_DAYS))
    data["instructions"] = clean_instructions(instructions, ADMIN_INSTRUCTIONS_MAX)
    vault.set_global(CONFIG_RECORD, data)
    return {"max_days": data["max_days"], "instructions": data["instructions"]}


def _user_record(vault: Any, user_id: str | None) -> dict[str, Any]:
    if not user_id:
        return {}
    try:
        return vault.get_user(user_id).get("prefs") or {}
    except KeyError:
        return {}


def user_prefs(vault: Any, user_id: str | None) -> dict[str, Any]:
    """What the person chose, with the administrator's maximum applied."""
    cfg = admin_config(vault)
    raw = _user_record(vault, user_id)
    days = raw.get("keep_days")
    if not isinstance(days, int) or isinstance(days, bool) or days < 1:
        days = DEFAULT_USER_DAYS
    return {
        "keep_reviewed": raw.get("keep_reviewed") is not False,
        "keep_archived": raw.get("keep_archived") is not False,
        "keep_days": min(days, cfg["max_days"]),
        "max_days": cfg["max_days"],
        "instructions": clean_instructions(raw.get("instructions"), USER_INSTRUCTIONS_MAX),
        "undo_send_seconds": clean_undo_seconds(raw.get("undo_send_seconds")),
    }


def clean_undo_seconds(value: Any) -> int:
    """Seconds a reply is held so it can be cancelled: 0 (send at once) to 60."""
    if not isinstance(value, int) or isinstance(value, bool):
        return 0
    return max(0, min(value, 60))


def save_user_prefs(vault: Any, users: Any, user_id: str, *, keep_reviewed: bool, keep_archived: bool,
                    keep_days: int, instructions: str, undo_send_seconds: int | None = None) -> dict[str, Any]:
    cfg = admin_config(vault)
    user = users.get(user_id)
    kept_undo = clean_undo_seconds((user.get("prefs") or {}).get("undo_send_seconds"))
    kept_features = (user.get("prefs") or {}).get("features")
    user["prefs"] = {
        "keep_reviewed": bool(keep_reviewed), "keep_archived": bool(keep_archived),
        "keep_days": max(1, min(int(keep_days), cfg["max_days"])),
        "instructions": clean_instructions(instructions, USER_INSTRUCTIONS_MAX),
        "undo_send_seconds": kept_undo if undo_send_seconds is None else clean_undo_seconds(undo_send_seconds),
    }
    if kept_features is not None:
        user["prefs"]["features"] = kept_features
    users.save(user)
    return user_prefs(vault, user_id)


def instructions_for(vault: Any, user_id: str | None) -> str:
    """The administrator's instructions followed by the person's own."""
    parts = []
    admin = admin_config(vault)["instructions"]
    mine = user_prefs(vault, user_id)["instructions"]
    if admin:
        parts.append(admin)
    if mine:
        parts.append("The reader also asks:\n" + mine)
    return "\n\n".join(parts)


def kept_state_for(vault: Any, user_id: str | None, outcome: str) -> str | None:
    """'reviewed' or 'archived' if this outcome should leave a card behind, else None."""
    if outcome not in KEPT_STATES:
        return None
    prefs = user_prefs(vault, user_id)
    return outcome if prefs["keep_" + outcome] else None


def keep_record(message: dict[str, Any], state: str, now: float | None = None) -> dict[str, Any]:
    """The stored card for a resolved item: no attachment details. An Archived card has no mailbox link (the email has moved);
    a Reviewed card keeps its link, which is only a pointer to the email's place in the mailbox, so Mark unread can find it again."""
    data = {k: v for k, v in message.items() if k != "id"}
    data.update(state=state, resolved_at=now if now is not None else time.time(),
                source_locator=message.get("source_locator") if state == "reviewed" else None,
                attachments=[], attachment_summaries=[], from_all_mail=False, snoozed_until=None, held_for_summary=False, held_at=None)
    return data


def purge_expired(vault: Any, account: dict[str, Any], now: float | None = None) -> int:
    """Delete kept cards that are past their time, or whose list the owner switched off."""
    now = time.time() if now is None else now
    prefs = user_prefs(vault, account.get("owner_user_id"))
    removed = 0
    for m in vault.list_messages(account["id"]):
        state = m.get("state")
        if state not in KEPT_STATES:
            continue
        age = now - float(m.get("resolved_at") or 0)
        if not prefs["keep_" + state] or age > prefs["keep_days"] * 86400:
            vault.delete_message(account["id"], m["id"])
            removed += 1
    return removed
