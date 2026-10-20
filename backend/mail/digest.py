"""The daily summary email: one special item in Enveliq's own inbox, once a day, with the AI's short summaries organised for the person.

How it works, in plain words:

* The AI that writes each email's summary also judges, from what the email says (a deadline, an urgent request, a question waiting for
  an answer, a payment, a booking, a security matter), whether the reader should deal with it today (`act_today`, with a one-line reason).
  It does not depend on who sent it. The AI only suggests; plain code does everything else.
* With **Put a daily summary in my inbox** on (Settings, Alerts), email that needs the reader today still alerts at once, even from someone
  who is not an important person. The rest does not alert one by one: it is gathered into the daily summary.
* At the person's morning time, one summary item is added to the Enveliq inbox. It is not a provider email and it is not stored in any
  mailbox. It looks different, opens and reads like an email, groups the summaries (what needs you today first, then by kind), and each line
  has a link that opens the original email in Enveliq. Making it sends no push, no sound and no alert.
* Nothing is hidden or marked reviewed by it. Every email stays in the inbox exactly as before; the summary is an extra item that can be
  deleted. A reassessment pass looks again at mail that was not urgent when it came: when an open task for it falls due today, it is sent
  as an alert at once, so a deadline is never waiting for the next summary.

The summary holds only what Enveliq already keeps (the AI's short summary, the subject and the sender's name), in one encrypted record
per person (`digest:<user id>`), and is kept for 7 days.
"""
from __future__ import annotations

import logging
import time
from datetime import date, datetime
from typing import Any, Callable

from .tasks import zone
from .reminders import _at

log = logging.getLogger("enveliq.digest")

RECORD_PREFIX = "digest:"
PLACEHOLDER = "Not summarised yet."
KEEP_DAYS = 7
MAX_ITEMS = 60
FIRST_LOOK_BACK = 86400.0
LONGEST_LOOK_BACK = 3 * 86400.0
URGENT_LOOK_BACK = 3 * 86400.0
RETRY_AFTER = 600.0
SECTION_URGENT = "Needs you today"
SECTION_OTHER = "Everything else"


def _clean(value: Any, limit: int) -> str:
    import re
    if not isinstance(value, str):
        return ""
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", value).strip()[:limit]


class DigestBook:
    def __init__(self, vault: Any, notifier: Any, tasks: Any, alerts: Any = None, clock: Callable[[], float] = time.time):
        self.vault, self.notifier, self.tasks, self.alerts, self.clock = vault, notifier, tasks, alerts, clock

    # ---------- the record ----------
    def _raw(self, user_id: str) -> dict[str, Any]:
        raw = self.vault.get_global(RECORD_PREFIX + user_id) or {}
        return raw if isinstance(raw, dict) else {}

    def _save(self, user_id: str, raw: dict[str, Any]) -> None:
        self.vault.set_global(RECORD_PREFIX + user_id, raw)

    def forget_user(self, user_id: str) -> None:
        self.vault.set_global(RECORD_PREFIX + user_id, {})

    def enabled(self, user_id: str) -> bool:
        try:
            return bool(self.notifier.settings(user_id).get("digest_inbox"))
        except Exception:
            return False

    def _digests(self, raw: dict[str, Any]) -> list[dict[str, Any]]:
        items = raw.get("digests")
        return [d for d in items if isinstance(d, dict) and d.get("id")] if isinstance(items, list) else []

    # ---------- reading ----------
    def listing(self, user_id: str) -> list[dict[str, Any]]:
        """The small row for each summary, newest first. The inbox shows these as special items."""
        out = []
        for d in sorted(self._digests(self._raw(user_id)), key=lambda x: x.get("created_at", 0), reverse=True):
            items = d.get("items") or []
            out.append({"id": d["id"], "day": d.get("day"), "created_at": d.get("created_at"), "read": bool(d.get("read")),
                        "count": len(items), "urgent": sum(1 for i in items if i.get("urgent"))})
        return out

    def get(self, user_id: str, digest_id: str) -> dict[str, Any] | None:
        for d in self._digests(self._raw(user_id)):
            if d["id"] == digest_id:
                return d
        return None

    def mark_read(self, user_id: str, digest_id: str) -> bool:
        raw = self._raw(user_id)
        found = False
        for d in self._digests(raw):
            if d["id"] == digest_id and not d.get("read"):
                d["read"] = True
                found = True
        if found:
            self._save(user_id, raw)
        return self.get(user_id, digest_id) is not None

    def delete(self, user_id: str, digest_id: str) -> bool:
        raw = self._raw(user_id)
        before = self._digests(raw)
        keep = [d for d in before if d["id"] != digest_id]
        if len(keep) == len(before):
            return False
        raw["digests"] = keep
        self._save(user_id, raw)
        return True

    # ---------- making one ----------
    def _mail(self, user_id: str) -> list[tuple[dict[str, Any], dict[str, Any]]]:
        out = []
        try:
            accounts = [a for a in self.vault.list_accounts() if a.get("owner_user_id") == user_id]
        except Exception:
            return out
        for account in accounts:
            try:
                messages = self.vault.list_messages(account["id"])
            except Exception:
                continue
            for m in messages:
                if m.get("state", "unread") == "unread" and not m.get("from_all_mail") and not m.get("ai_pending") and not m.get("found_until") \
                        and m.get("summary") and not str(m.get("summary")).startswith(PLACEHOLDER):
                    out.append((account, m))
        return out

    @staticmethod
    def _item(account: dict[str, Any], m: dict[str, Any], urgent: bool) -> dict[str, Any]:
        return {"account_id": account["id"], "message_id": m["id"], "sender": _clean(m.get("sender_display") or m.get("sender_address"), 120),
                "subject": _clean(m.get("subject"), 200) or "(no subject)", "summary": _clean(m.get("summary"), 400),
                "category": _clean(m.get("category"), 40) or "Other", "reason": _clean(m.get("today_reason"), 140) if urgent else "",
                "urgent": urgent, "received_at": m.get("received_at") or 0}

    def build(self, user_id: str, now: float | None = None, replace_today: bool = False) -> dict[str, Any] | None:
        """Make today's summary from the unread email that came in since the last one. Returns it, or None when there is nothing to say."""
        now = self.clock() if now is None else now
        tz = zone(self.tasks.timezone_of(user_id))
        local = datetime.fromtimestamp(now, tz)
        day = local.date().isoformat()
        raw = self._raw(user_id)
        digests = [d for d in self._digests(raw) if now - float(d.get("created_at") or 0) < KEEP_DAYS * 86400]
        if replace_today:
            digests = [d for d in digests if d.get("day") != day]
        elif any(d.get("day") == day for d in digests):
            return None
        since = max(float(raw.get("last_at") or 0), now - LONGEST_LOOK_BACK) if raw.get("last_at") and not replace_today else now - FIRST_LOOK_BACK
        urgent, rest = [], []
        for account, m in self._mail(user_id):
            when = float(m.get("received_at") or 0)
            if when < since:
                continue
            (urgent if m.get("act_today") is True else rest).append((when, account, m))
        urgent.sort(key=lambda t: t[0], reverse=True)
        rest.sort(key=lambda t: t[0], reverse=True)
        items = [self._item(a, m, True) for _w, a, m in urgent] + [self._item(a, m, False) for _w, a, m in rest]
        items = items[:MAX_ITEMS]
        raw["last_at"] = now
        raw["last_day"] = day
        if not items:
            raw["digests"] = digests
            self._save(user_id, raw)
            return None
        digest = {"id": "d-" + day, "day": day, "created_at": now, "read": False, "items": items}
        raw["digests"] = digests + [digest]
        self._save(user_id, raw)
        return digest

    def maintain(self, user_id: str, now: float | None = None) -> bool:
        """Once a day, at the person's morning time, add the summary to the inbox. Makes no alert of its own. Never raises."""
        now = self.clock() if now is None else now
        try:
            st = self.notifier.settings(user_id)
            if not st.get("digest_inbox"):
                return False
            tz = zone(self.tasks.timezone_of(user_id))
            local = datetime.fromtimestamp(now, tz)
            if local < datetime.combine(local.date(), _at(st["morning_time"]), tz):
                return False
            if self._raw(user_id).get("last_day") == local.date().isoformat():
                return False
            return self.build(user_id, now) is not None
        except Exception:
            log.info("daily summary item failed")
            return False

    # ---------- looking again at mail that could wait ----------
    def reassess(self, user_id: str, now: float | None = None) -> int:
        """Email that was not urgent when it came, but has an open task due today, is announced at once. Returns how many went out. Never raises."""
        now = self.clock() if now is None else now
        try:
            st = self.notifier.settings(user_id)
            if not st.get("digest_inbox") or self.alerts is None:
                return 0
            raw = self._raw(user_id)
            if float(raw.get("reassess_at") or 0) > now:
                return 0
            tz = zone(self.tasks.timezone_of(user_id))
            today = datetime.fromtimestamp(now, tz).date()
            alerted = raw.get("alerted") if isinstance(raw.get("alerted"), dict) else {}
            alerted = {k: v for k, v in alerted.items() if now - float(v) < 14 * 86400}
            due = {(t["account_id"], t["message_id"]) for t in self.tasks.open_tasks(user_id) if date.fromisoformat(t["due"]) <= today}
            fresh = []
            for account, m in self._mail(user_id):
                key = account["id"] + ":" + m["id"]
                if (account["id"], m["id"]) in due and m.get("act_today") is not True and key not in alerted \
                        and now - float(m.get("received_at") or 0) < URGENT_LOOK_BACK:
                    fresh.append({"account_id": account["id"], "id": m["id"], "sender_display": m.get("sender_display"), "sender_address": m.get("sender_address"),
                                  "subject": m.get("subject"), "priority": m.get("priority"), "action_required": True, "act_today": True})
            sent = 0
            if fresh:
                sent = self.alerts.send(user_id, fresh)
                if sent:
                    for f in fresh:
                        alerted[f["account_id"] + ":" + f["id"]] = now
                else:
                    raw["reassess_at"] = now + RETRY_AFTER
            raw["alerted"] = alerted
            self._save(user_id, raw)
            return sent
        except Exception:
            log.info("reassessing urgent email failed")
            return 0

    def tick(self, user_id: str) -> None:
        self.maintain(user_id)
        self.reassess(user_id)
