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
ACTIONS = {"archived": "Archive it", "reviewed": "Mark it as read", "junked": "Send it to Junk", "notasks": "Never make tasks", "tag": "Always apply tags", "moved": "Move it to a folder", "starred": "Star it", "snoozed": "Snooze it", "safe": "Never send it to Junk"}
# "Never make tasks" does nothing to the email itself: it only stops Enveliq from turning mail from that sender into a task.
# It sits beside the other rules, so a sender can have both (for example archive it, and never make tasks).
NO_TASKS = "notasks"
TAG = "tag"
MAX_TAGS = 10
MAX_TAG_NAME = 40
MOVED = "moved"          # "Move it to a folder": one rule per sender; the folder is looked up in each mailbox when mail arrives
MAX_FOLDER = 300
# These two rules do not move or mark the email, so they sit beside an archive, reviewed or Junk rule instead of replacing it.
SIDE_ACTIONS = {NO_TASKS, TAG}
STARRED, SNOOZED, SAFE = "starred", "snoozed", "safe"        # star it; snooze it for some hours; "safe sender": nothing happens to it and no later rule touches it
MAX_HOURS = 24 * 30
MAX_TEXT = 100
MAX_MB = 1000
EXTRA = ("not_subject", "to", "list", "files", "larger_mb")
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


def clean_tags(value: Any) -> list[str]:
    names: list[str] = []
    for raw in value if isinstance(value, list) else []:
        name = " ".join(_CTRL.sub(" ", str(raw or "")).split())[:MAX_TAG_NAME]
        if name and not any(name.lower() == n.lower() for n in names):
            names.append(name)
    return names[:MAX_TAGS]


def clean_folder(name: Any, label: Any) -> tuple[str, str]:
    folder = _CTRL.sub("", str(name or "")).strip()[:MAX_FOLDER]
    shown = " ".join(_CTRL.sub(" ", str(label or folder)).split())[:80] or folder
    if not folder:
        raise RuleError("Choose which folder the email should go to.")
    return folder, shown


def clean_subject(value: Any) -> str:
    return re.sub(r"\s+", " ", _CTRL.sub(" ", str(value or ""))).strip()[:MAX_SUBJECT]


def clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", _CTRL.sub(" ", str(value or ""))).strip().lower()[:MAX_TEXT]


def fits(rule: dict[str, Any], address: Any, subject: Any, facts: dict[str, Any] | None = None) -> bool:
    """Does this rule's every condition fit this email? The conditions left empty are not asked. A condition that needs something the email
    does not have on record (an older email has no list, size or recipients) does not fit."""
    facts = facts or {}
    if rule.get("sender") and not sender_matches(rule["sender"], address):
        return False
    title = str(subject or "").lower()
    words = str(rule.get("subject") or "").lower()
    if words and words not in title:
        return False
    avoid = str(rule.get("not_subject") or "").lower()
    if avoid and avoid in title:
        return False
    to = str(rule.get("to") or "").lower()
    if to and not any(to in str(x).lower() for x in facts.get("recipients") or []):
        return False
    wanted_list = str(rule.get("list") or "").lower()
    if wanted_list and wanted_list not in str(facts.get("list_id") or "").lower():
        return False
    if rule.get("files") and not facts.get("files"):
        return False
    mb = int(rule.get("larger_mb") or 0)
    if mb:
        size = facts.get("size")
        if not size or int(size) <= mb * 1_048_576:
            return False
    return True


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
        return [r for r in raw if isinstance(r, dict) and r.get("id") and r.get("action") in ACTIONS and (r.get("sender") or any(r.get(k) for k in ("subject", *EXTRA)))]

    def _save(self, user_id: str, rules: list[dict[str, Any]]) -> None:
        self.vault.set_global(RECORD_PREFIX + user_id, {"rules": rules})

    def listing(self, user_id: str) -> list[dict[str, Any]]:
        out = []
        for r in self._load(user_id):
            row = {"id": r["id"], "sender": r.get("sender", ""), "subject": r.get("subject", ""), "action": r["action"]}
            for k in EXTRA:
                if r.get(k):
                    row[k] = r[k]
            if r["action"] == TAG:
                row["tags"] = list(r.get("tags") or [])
            if r["action"] == MOVED:
                row.update(folder=r.get("folder", ""), folder_label=r.get("folder_label") or r.get("folder", ""))
            if r["action"] == SNOOZED:
                row["hours"] = int(r.get("hours") or 0)
            out.append(row)
        return out

    @staticmethod
    def _plain(r: dict[str, Any]) -> bool:
        """A rule with only a sender and subject, the kind the buttons in an email's menu make and replace."""
        return not any(r.get(k) for k in EXTRA)

    def add(self, user_id: str, sender: Any, subject: Any, action: Any, tags: Any = None, folder: Any = None, folder_label: Any = None) -> list[dict[str, Any]]:
        who, words = clean_sender(sender), clean_subject(subject)
        if action not in ACTIONS:
            raise RuleError("Choose what to do with the email: archive it, mark it reviewed, or send it to Junk.")
        if action == TAG:
            # One "always apply tags" rule per sender: saving it again replaces the tags, and saving it with no tags removes it.
            names = clean_tags(tags)
            with _LOCK:
                rules = [r for r in self._load(user_id) if not (r["action"] == TAG and self._plain(r) and r.get("sender") == who and r.get("subject", "") == words)]
                if names:
                    if len(rules) >= MAX_RULES:
                        raise RuleError(f"You can keep up to {MAX_RULES} rules. Remove one first.")
                    rules.append({"id": "u" + secrets.token_hex(8), "sender": who, "subject": words, "action": TAG, "tags": names})
                self._save(user_id, rules)
            return self.listing(user_id)
        if action == MOVED:
            # One "move it to a folder" rule per sender and subject: saving it again changes the folder.
            where, shown = clean_folder(folder, folder_label)
            with _LOCK:
                rules = [r for r in self._load(user_id) if not (r["action"] == MOVED and self._plain(r) and r.get("sender") == who and r.get("subject", "").lower() == words.lower())]
                if len(rules) >= MAX_RULES:
                    raise RuleError(f"You can keep up to {MAX_RULES} rules. Remove one first.")
                rules.append({"id": "u" + secrets.token_hex(8), "sender": who, "subject": words, "action": MOVED, "folder": where, "folder_label": shown})
                self._save(user_id, rules)
            return self.listing(user_id)
        with _LOCK:
            rules = self._load(user_id)
            if any(self._plain(r) and r.get("sender") == who and r.get("subject", "").lower() == words.lower() and r["action"] == action for r in rules):
                return self.listing(user_id)                # already there
            if len(rules) >= MAX_RULES:
                raise RuleError(f"You can keep up to {MAX_RULES} rules. Remove one first.")
            rules.append({"id": "u" + secrets.token_hex(8), "sender": who, "subject": words, "action": action})
            self._save(user_id, rules)
        return self.listing(user_id)

    @staticmethod
    def build(spec: dict[str, Any]) -> dict[str, Any]:
        """Check and tidy a rule the person described, without saving it. Raises RuleError with a plain reason."""
        rule: dict[str, Any] = {"sender": clean_sender(spec["sender"]) if str(spec.get("sender") or "").strip() else "",
                                "subject": clean_subject(spec.get("subject")), "not_subject": clean_subject(spec.get("not_subject")).lower(),
                                "to": clean_text(spec.get("to")), "list": clean_text(spec.get("mailing_list") or spec.get("list")), "files": bool(spec.get("files"))}
        try:
            mb = int(spec.get("larger_mb") or 0)
        except (TypeError, ValueError):
            raise RuleError("Type the size as a whole number of megabytes.") from None
        if not 0 <= mb <= MAX_MB:
            raise RuleError(f"The size can be up to {MAX_MB} megabytes.")
        rule["larger_mb"] = mb
        if not (rule["sender"] or rule["subject"] or any(rule[k] for k in EXTRA)):
            raise RuleError("Choose at least one thing to look for: who it is from, a word in the subject, who it is to, a mailing list, a file or a size.")
        action = spec.get("action")
        if action not in ACTIONS:
            raise RuleError("Choose what to do with the email.")
        rule["action"] = action
        if action == TAG:
            rule["tags"] = clean_tags(spec.get("tags"))
            if not rule["tags"]:
                raise RuleError("Choose at least one tag.")
        if action == MOVED:
            rule["folder"], rule["folder_label"] = clean_folder(spec.get("folder"), spec.get("folder_label"))
        if action == SNOOZED:
            try:
                hours = int(spec.get("hours") or 0)
            except (TypeError, ValueError):
                hours = 0
            if not 1 <= hours <= MAX_HOURS:
                raise RuleError("Choose how long to snooze it for, from 1 hour up to 30 days.")
            rule["hours"] = hours
        rule = {k: v for k, v in rule.items() if v or k in ("sender", "subject", "action")}
        return rule

    def save(self, user_id: str, spec: dict[str, Any], rule_id: str | None = None) -> list[dict[str, Any]]:
        """Make a rule with any of the conditions, or change an existing one in place (it keeps its place in the order)."""
        rule = self.build(spec)
        with _LOCK:
            rules = self._load(user_id)
            if rule_id is None:
                if len(rules) >= MAX_RULES:
                    raise RuleError(f"You can keep up to {MAX_RULES} rules. Remove one first.")
                rules.append({"id": "u" + secrets.token_hex(8), **rule})
            else:
                for i, old in enumerate(rules):
                    if old["id"] == rule_id:
                        rules[i] = {"id": rule_id, **rule}
                        break
                else:
                    raise KeyError(rule_id)
            self._save(user_id, rules)
        return self.listing(user_id)

    def move(self, user_id: str, rule_id: str, delta: int) -> bool:
        """Move a rule up (-1) or down (+1) in the order. The first rule that fits an email is the one that acts."""
        with _LOCK:
            rules = self._load(user_id)
            at = next((i for i, r in enumerate(rules) if r["id"] == rule_id), None)
            if at is None:
                return False
            to = max(0, min(len(rules) - 1, at + (1 if delta > 0 else -1)))
            rules[at], rules[to] = rules[to], rules[at]
            self._save(user_id, rules)
        return True

    def get(self, user_id: str, rule_id: str) -> dict[str, Any] | None:
        return next((r for r in self._load(user_id) if r["id"] == rule_id), None)

    def is_safe(self, user_id: str, address: Any) -> bool:
        """True when a "Never send it to Junk" rule names this sender (a plain sender rule, no other conditions)."""
        return any(r["action"] == SAFE and self._plain(r) and r.get("sender") and not r.get("subject") and sender_matches(r["sender"], address) for r in self._load(user_id))

    def remove(self, user_id: str, rule_id: str) -> bool:
        with _LOCK:
            rules = self._load(user_id)
            kept = [r for r in rules if r["id"] != rule_id]
            if len(kept) == len(rules):
                return False
            self._save(user_id, kept)
        return True

    def match(self, user_id: str, address: Any, subject: Any, facts: dict[str, Any] | None = None) -> dict[str, Any] | None:
        """The first rule that acts on the email (archive, read, Junk, move, star, snooze, safe) that fits, or None."""
        for r in self._load(user_id):
            if r["action"] not in SIDE_ACTIONS and fits(r, address, subject, facts):
                return r
        return None

    def blocks_tasks(self, user_id: str, address: Any, subject: Any, facts: dict[str, Any] | None = None) -> bool:
        """True when a "Never make tasks" rule fits mail from this address with this subject."""
        return any(r["action"] == NO_TASKS and fits(r, address, subject, facts) for r in self._load(user_id))

    def tags_for(self, user_id: str, address: Any, subject: Any, facts: dict[str, Any] | None = None) -> list[str]:
        """The tags every "Always apply tags" rule that fits this mail asks for (no repeats)."""
        out: list[str] = []
        for r in self._load(user_id):
            if r["action"] == TAG and fits(r, address, subject, facts):
                out.extend(n for n in r.get("tags") or [] if not any(n.lower() == o.lower() for o in out))
        return out[:MAX_TAGS]

    def forget_user(self, user_id: str) -> None:
        self.vault.set_global(RECORD_PREFIX + user_id, {})
