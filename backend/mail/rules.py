"""Rules: "when mail comes from this sender, archive it" (or mark it reviewed), done for the person as mail arrives.

One encrypted record per person (`rules:<user id>`) under the vault's master key. A rule holds a sender (one
address, or a whole domain written `@example.com`), an optional piece of the subject, and one of two actions:
archive, mark reviewed, or send to the mailbox's Junk folder (which is how a sender is blocked; the email can still be rescued from Junk). There is deliberately no rule that bins mail. A rule is checked against the
sender and subject of mail that has just arrived (nothing else about an email is read) and is never applied to
mail already in the inbox. Mail from a person's important people is never touched by a rule.
"""
from __future__ import annotations

import re
import secrets
import threading
from typing import Any

from .contacts import clean_address

RECORD_PREFIX = "rules:"
MAX_RULES = 50
MAX_SUBJECT = 80
ACTIONS = {"archived": "Archive it", "reviewed": "Mark it reviewed", "junked": "Send it to Junk"}
_LOCK = threading.Lock()
_CTRL = re.compile(r"[\x00-\x1f\x7f]")
_DOMAIN = re.compile(r"^@[A-Za-z0-9.-]{1,253}\.[A-Za-z]{2,24}$")


class RuleError(ValueError):
    """Plain, safe-to-show reason a rule was refused."""


def clean_sender(value: Any) -> str:
    text = str(value or "").strip().lower()
    if "@" not in text and "." in text:
        text = "@" + text                                   # "example.com" means everyone at example.com
    addr = clean_address(text)
    if addr:
        return addr
    if _DOMAIN.match(text):
        return text
    raise RuleError("Type one email address, or a whole website such as @example.com.")


def clean_subject(value: Any) -> str:
    return re.sub(r"\s+", " ", _CTRL.sub(" ", str(value or ""))).strip()[:MAX_SUBJECT]


def sender_matches(rule_sender: str, address: str) -> bool:
    addr = str(address or "").strip().lower()
    if rule_sender.startswith("@"):
        return addr.rpartition("@")[2] == rule_sender[1:]
    return addr == rule_sender


class Rules:
    def __init__(self, vault: Any) -> None:
        self.vault = vault

    def _load(self, user_id: str) -> list[dict[str, Any]]:
        raw = (self.vault.get_global(RECORD_PREFIX + user_id) or {}).get("rules") or []
        return [r for r in raw if isinstance(r, dict) and r.get("id") and r.get("sender") and r.get("action") in ACTIONS]

    def _save(self, user_id: str, rules: list[dict[str, Any]]) -> None:
        self.vault.set_global(RECORD_PREFIX + user_id, {"rules": rules})

    def listing(self, user_id: str) -> list[dict[str, Any]]:
        return [{"id": r["id"], "sender": r["sender"], "subject": r.get("subject", ""), "action": r["action"]} for r in self._load(user_id)]

    def add(self, user_id: str, sender: Any, subject: Any, action: Any) -> list[dict[str, Any]]:
        who, words = clean_sender(sender), clean_subject(subject)
        if action not in ACTIONS:
            raise RuleError("Choose what to do with the email: archive it, mark it reviewed, or send it to Junk.")
        with _LOCK:
            rules = self._load(user_id)
            if any(r["sender"] == who and r.get("subject", "").lower() == words.lower() and r["action"] == action for r in rules):
                return self.listing(user_id)                # already there
            if len(rules) >= MAX_RULES:
                raise RuleError(f"You can keep up to {MAX_RULES} rules. Remove one first.")
            rules.append({"id": "u" + secrets.token_hex(8), "sender": who, "subject": words, "action": action})
            self._save(user_id, rules)
        return self.listing(user_id)

    def remove(self, user_id: str, rule_id: str) -> bool:
        with _LOCK:
            rules = self._load(user_id)
            kept = [r for r in rules if r["id"] != rule_id]
            if len(kept) == len(rules):
                return False
            self._save(user_id, kept)
        return True

    def match(self, user_id: str, address: Any, subject: Any) -> dict[str, Any] | None:
        """The first rule that fits mail from this address with this subject, or None."""
        title = str(subject or "").lower()
        for r in self._load(user_id):
            if not sender_matches(r["sender"], address):
                continue
            words = str(r.get("subject") or "").lower()
            if words and words not in title:
                continue
            return r
        return None

    def forget_user(self, user_id: str) -> None:
        self.vault.set_global(RECORD_PREFIX + user_id, {})
