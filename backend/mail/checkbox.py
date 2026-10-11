"""Forward to check: a person forwards a suspicious email to the household's check address and gets one line back.

An administrator marks one of their own mailboxes as the check address and lists the people who may use it. Everything here is plain code
(the same rules as the Be careful flag); the AI is not involved. Rules that keep it harmless:

* Only an allow-listed sender gets an answer, and only when the provider did not say the sender was forged. Anyone else is ignored and never
  answered, so the address cannot be used to bounce mail at strangers.
* Automatic mail (mailing lists, bulk mail, other auto-replies) is ignored, and every answer says it is automatic, so two robots cannot
  start a loop. Each person gets a few answers a day, and the whole address a few more.
* The forwarded email is read once, in memory. Nothing from it is stored or logged. The answer is a single fixed sentence or the reasons the
  Be careful flag uses (host names, never the rest of a link).
* The check mailbox is never read as an inbox: it is not synced and nothing from it is kept for anyone.
* The answer never says an email is safe. "Nothing odd found" is not a promise.
"""
from __future__ import annotations

import email
import re
import time
from email import policy
from email.message import EmailMessage, Message
from email.utils import format_datetime, make_msgid
from datetime import datetime, timezone
from typing import Any, Callable

from . import links as linklist, scamcheck
from .errors import BridgeError
from .parse import _addresses, clean, parse_headers

CONFIG_RECORD = "check_config"
MAX_ALLOWED = 50
PER_PERSON_DAY = 10
PER_ADDRESS_DAY = 60
PER_PASS = 8
MIN_SECONDS = 120.0
FIELDS = "FROM SUBJECT MESSAGE-ID AUTHENTICATION-RESULTS AUTO-SUBMITTED PRECEDENCE LIST-ID X-AUTORESPONSE X-AUTO-RESPONSE-SUPPRESS"
_EMAIL = re.compile(r"^[A-Za-z0-9._%+\-]{1,64}@[A-Za-z0-9.\-]{1,253}\.[A-Za-z]{2,63}$")
_ANGLE_ID = re.compile(r"^<[^<>\s]{1,994}>$")
_ROBOTS = ("mailer-daemon", "postmaster", "noreply", "no-reply", "donotreply", "do-not-reply")

SAFE = "Nothing odd found. That does not prove it is safe."
LINKS_ONLY = "Nothing odd found in its links. I could not see who sent it, because it was not forwarded as an attachment. That does not prove it is safe."
NOTHING = "I could not find an email to check. Forward it as an attachment (in most mail apps: Forward, then choose Forward as attachment) and I will look at it."


def clean_allowed(values: list[str]) -> list[str]:
    """The allow-list as lower-case addresses without repeats. Raises ValueError for anything that is not an email address."""
    out: list[str] = []
    for value in values:
        text = str(value).strip().lower()
        if not text:
            continue
        if not _EMAIL.match(text):
            raise ValueError(f"“{str(value).strip()[:80]}” is not an email address.")
        if text not in out:
            out.append(text)
    if len(out) > MAX_ALLOWED:
        raise ValueError(f"Add at most {MAX_ALLOWED} addresses.")
    return out


def forwarded(msg: Message) -> Message | None:
    """The first email attached to this one (a message forwarded as an attachment), or None."""
    try:
        for part in msg.walk():
            if part is not msg and part.get_content_type() == "message/rfc822":
                inner = part.get_payload()
                if isinstance(inner, list) and inner and isinstance(inner[0], Message):
                    return inner[0]
    except Exception:
        return None
    return None


def verdict(raw: bytes) -> str:
    """The one line to send back for a forwarded email."""
    outer = email.message_from_bytes(raw, policy=policy.default)
    inner = forwarded(outer)
    target = inner if inner is not None else outer
    try:
        found = linklist.find(target)
        from_links = [{"text": item["note"], "key": item["note"]} for item in found if item["flagged"]]
        reasons = scamcheck.merge(scamcheck.header_reasons(inner) if inner is not None else [], from_links)
        links = bool(found)
    except Exception:
        reasons, links = [], False
    if reasons:
        return "Be careful: " + " ".join(r["text"] for r in reasons[:scamcheck.MAX_REASONS])
    if inner is not None:
        return SAFE
    return LINKS_ONLY if links else NOTHING


def automatic(headers: Message) -> bool:
    """True for mail a robot sent: other auto-replies, mailing lists and bulk mail."""
    auto = str(headers.get("Auto-Submitted") or "").strip().lower()
    if auto and auto != "no":
        return True
    if str(headers.get("Precedence") or "").strip().lower() in ("bulk", "junk", "list", "auto_reply"):
        return True
    return bool(headers.get("List-Id") or headers.get("X-Autoresponse") or headers.get("X-Auto-Response-Suppress"))


class CheckBox:
    def __init__(self, vault: Any, service: Any, clock: Callable[[], float] = time.time):
        self.vault, self.service, self.clock = vault, service, clock
        self.last: dict[str, Any] = {}
        self._due = 0.0
        self._sent: dict[str, list[float]] = {}

    # ---------- settings (administrators) ----------

    def config(self) -> dict[str, Any]:
        try:
            saved = self.vault.get_global(CONFIG_RECORD) or {}
        except Exception:
            saved = {}
        allowed = [a for a in saved.get("allowed", []) if isinstance(a, str)]
        account = saved.get("account_id") if isinstance(saved.get("account_id"), str) else None
        return {"account_id": account, "allowed": allowed}

    def save(self, account_id: str | None, allowed: list[str]) -> dict[str, Any]:
        self.vault.set_global(CONFIG_RECORD, {"account_id": account_id, "allowed": allowed})
        return self.config()

    def account_id(self) -> str | None:
        """The mailbox that is the check address, or None. Safe to call while Enveliq is locked."""
        try:
            return self.config()["account_id"] if self.vault.is_unlocked() else None
        except Exception:
            return None

    # ---------- answering ----------

    def _allow(self, sender: str, now: float) -> bool:
        """Whether one more answer may go to this person and this address today. Counts as it asks."""
        day = now - 86400
        for key in list(self._sent):
            self._sent[key] = [t for t in self._sent[key] if t > day]
            if not self._sent[key]:
                del self._sent[key]
        mine = self._sent.get(sender, [])
        total = sum(len(v) for v in self._sent.values())
        if len(mine) >= PER_PERSON_DAY or total >= PER_ADDRESS_DAY:
            return False
        self._sent.setdefault(sender, []).append(now)
        return True

    def eligible(self, headers: Message, mailbox: str, allowed: list[str]) -> str | None:
        """The sender's address when this email may be answered, otherwise None."""
        sender = ((_addresses(headers, "From") or [("", "")])[0][1] or "").strip().lower()
        if not sender or sender not in allowed or sender == mailbox.lower():
            return None
        if any(sender.split("@")[0].startswith(r) for r in _ROBOTS) or automatic(headers):
            return None
        if scamcheck.sender_check(headers)["result"] == "not_confirmed":
            return None
        return sender

    @staticmethod
    def reply(mailbox: str, sender: str, headers: Message, line: str) -> EmailMessage:
        out = EmailMessage()
        out["From"] = mailbox
        out["To"] = sender
        subject = clean(headers.get("Subject"), 150) or "your email"
        out["Subject"] = subject if subject.lower().startswith("re:") else "Re: " + subject
        mid = str(headers.get("Message-ID") or "").strip()
        if _ANGLE_ID.match(mid):
            out["In-Reply-To"] = mid
            out["References"] = mid
        out["Auto-Submitted"] = "auto-replied"
        out["Precedence"] = "bulk"
        out["Date"] = format_datetime(datetime.now(timezone.utc))
        out["Message-ID"] = make_msgid(domain=(mailbox.rsplit("@", 1)[1] if "@" in mailbox else "enveliq.invalid"))
        out.set_content(line)
        return out

    def poll(self) -> int:
        """Look at the check address now and then. Returns how many answers were sent."""
        now = self.clock()
        if now < self._due:
            return 0
        self._due = now + MIN_SECONDS
        try:
            return self.run_once()
        except BridgeError as err:
            self.last = {"at": now, "ok": False, "error": err.code, "answered": 0}
        except Exception:
            self.last = {"at": now, "ok": False, "error": "failed", "answered": 0}
        return 0

    def run_once(self) -> int:
        cfg = self.config()
        if not cfg["account_id"] or not cfg["allowed"]:
            return 0
        try:
            account = self.vault.get_account(cfg["account_id"])
        except KeyError:
            return 0
        mailbox = str(account.get("email_address") or "")
        target = self.service.target(account)
        lock = self.service.locks.acquire(account["id"])
        answered = ignored = 0
        try:
            with self.service.bridge.session(target) as s:
                s.select_inbox(readonly=False)
                uids = s.unseen_uids(2, PER_PASS * 4)[:PER_PASS]
                heads = dict(s.header_blocks(uids, fields=FIELDS))
                for uid in uids:
                    s.mark_seen(uid)                     # first, so a failure can never make it answer twice
                    sender = self.eligible(parse_headers(heads.get(uid, b"")), mailbox, cfg["allowed"]) if uid in heads else None
                    if not sender or not self._allow(sender, self.clock()):
                        ignored += 1
                        continue
                    raw = s.original(uid)
                    line = verdict(raw)
                    self.service.bridge.send(target, self.reply(mailbox, sender, parse_headers(heads[uid]), line), mailbox, [sender])
                    answered += 1
        finally:
            lock.release()
        self.last = {"at": self.clock(), "ok": True, "answered": answered, "ignored": ignored}
        return answered
