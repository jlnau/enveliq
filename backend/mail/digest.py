"""The daily summary: email that can wait is held out of the inbox and gathered in one place, the summary.

How it works, in plain words:

* The AI that writes each email's summary also judges, from what the email says (a deadline, an urgent request, a question waiting for
  an answer, a payment, a booking, a security matter), whether the reader should deal with it today (`act_today`). It does not depend on
  who sent it. The AI only suggests; plain code does everything else.
* With **Hold email for the daily summary** on (Settings, Alerts), a new email that is not urgent and not from an important person is
  **held**: it leaves the inbox list and goes straight into the summary and into the **Held for summary** list on the left. Urgent mail and
  mail from important people stay in the inbox and alert at once, as before. Mail that was already in the inbox when the switch was turned
  on is left where it is.
* The summary is one running item at the top of the inbox. It is not a provider email and is stored in no mailbox. It is simply the
  list of held email, so it is always up to date: handling an email anywhere (Reviewed, Archive, Bin) takes it out of the summary.
* Each line in the summary can be marked Reviewed, archived or binned (the normal actions), or taken **out of the summary**, which puts it
  back in the inbox. **Done with summary** puts everything still in it back in the inbox, unhandled and unchanged, and closes the summary;
  the next held email starts a new one. The summary also closes by itself when nothing is left in it. Email still held after 7 days goes back
  in the inbox by itself, so nothing is ever kept out of sight for long.
* Once a day, at the daily summary time, one alert says how many emails are waiting and opens the summary. Nothing else about the summary
  alerts.
* Nothing is lost or hidden for good. A held email is still an ordinary unread email in the mailbox and in Enveliq; only the inbox list is
  different. Turning the switch off puts every held email back in the inbox. A second look every minute puts an email back in the inbox
  (and alerts once) if an open task for it falls due today.

Held email is only a flag on Enveliq's own stored record (`held_for_summary`, `held_at`). The summary holds nothing of its own.
"""
from __future__ import annotations

import logging
import time
from datetime import date, datetime
from typing import Any, Callable

from .reminders import _at, in_quiet
from .tasks import zone

log = logging.getLogger("enveliq.digest")

RECORD_PREFIX = "digest:"
PLACEHOLDER = "Not summarised yet."
URGENT_LOOK_BACK = 3 * 86400.0
RETRY_AFTER = 600.0
ALERT_RETRY = 300.0
MAX_CONSIDERED = 5000
HOLD_DAYS = 7                      # an email nobody dealt with goes back in the inbox after this long


def _clean(value: Any, limit: int) -> str:
    import re
    if not isinstance(value, str):
        return ""
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", value).strip()[:limit]


class DigestBook:
    def __init__(self, vault: Any, notifier: Any, tasks: Any, alerts: Any = None, important: Any = None, click_url: str = "",
                 clock: Callable[[], float] = time.time):
        self.vault, self.notifier, self.tasks, self.alerts, self.important, self.click_url, self.clock = vault, notifier, tasks, alerts, important, click_url, clock

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

    # ---------- the person's mail ----------
    def _accounts(self, user_id: str) -> list[dict[str, Any]]:
        try:
            return [a for a in self.vault.list_accounts() if a.get("owner_user_id") == user_id]
        except Exception:
            return []

    def _messages(self, user_id: str) -> list[tuple[dict[str, Any], dict[str, Any]]]:
        out = []
        for account in self._accounts(user_id):
            try:
                for m in self.vault.list_messages(account["id"]):
                    out.append((account, m))
            except Exception:
                continue
        return out

    @staticmethod
    def _ready(m: dict[str, Any]) -> bool:
        return (m.get("state", "unread") == "unread" and not m.get("from_all_mail") and not m.get("ai_pending") and not m.get("found_until")
                and bool(m.get("summary")) and not str(m.get("summary")).startswith(PLACEHOLDER))

    def write(self, account_id: str, message_id: str, **change: Any) -> None:
        """Change fields on one stored message. Only Enveliq's own record changes."""
        from ..models import RetainedMessageCreate
        stored = self.vault.get_message(account_id, message_id)
        data = {k: v for k, v in stored.items() if k != "id"}
        data.update(change)
        self.vault.update_message(account_id, message_id, RetainedMessageCreate(**data).model_dump(mode="python"))

    def _held(self, user_id: str) -> list[tuple[dict[str, Any], dict[str, Any]]]:
        return [(a, m) for a, m in self._messages(user_id) if m.get("held_for_summary") is True and m.get("state", "unread") == "unread" and not m.get("from_all_mail")]

    # ---------- reading the summary ----------
    def view(self, user_id: str) -> dict[str, Any]:
        """The summary as the page shows it: every held email, newest first, with the AI's short summary."""
        held = sorted(self._held(user_id), key=lambda t: float(t[1].get("held_at") or t[1].get("received_at") or 0), reverse=True)
        seen = float(self._raw(user_id).get("seen_at") or 0)
        items = [{"account_id": a["id"], "message_id": m["id"], "sender": _clean(m.get("sender_display") or m.get("sender_address"), 120),
                  "subject": _clean(m.get("subject"), 200) or "(no subject)", "summary": _clean(m.get("summary"), 400),
                  "category": _clean(m.get("category"), 40) or "Other", "held_at": m.get("held_at") or m.get("received_at") or 0, "received_at": m.get("received_at") or 0} for a, m in held]
        return {"enabled": self.enabled(user_id), "count": len(items), "unread": any(float(i["held_at"] or 0) > seen for i in items), "items": items}

    def mark_seen(self, user_id: str) -> None:
        raw = self._raw(user_id)
        raw["seen_at"] = self.clock()
        self._save(user_id, raw)

    # ---------- letting email go back ----------
    def release(self, user_id: str, only: tuple[str, str] | None = None) -> int:
        """Put held email back in the inbox, unchanged. All of it, or just one email. Returns how many went back."""
        n = 0
        for account, m in self._messages(user_id):
            if m.get("held_for_summary") is not True:
                continue
            if only is not None and (account["id"], m["id"]) != only:
                continue
            try:
                self.write(account["id"], m["id"], held_for_summary=False, held_at=None)
                n += 1
            except Exception:
                log.info("putting a held email back failed")
        return n

    # ---------- deciding what is held ----------
    def hold_pass(self, user_id: str, now: float | None = None) -> int:
        """Hold new email that can wait. Mail that was already there when the switch was turned on is left alone. Returns how many were held."""
        now = self.clock() if now is None else now
        raw = self._raw(user_id)
        mail = self._messages(user_id)
        keys = {a["id"] + ":" + m["id"] for a, m in mail}
        considered = raw.get("considered")
        if not isinstance(considered, list):
            raw["considered"] = sorted(keys)[:MAX_CONSIDERED]                      # the first pass only takes note of what is already here
            self._save(user_id, raw)
            return 0
        seen = set(considered)
        held = 0
        for account, m in mail:
            key = account["id"] + ":" + m["id"]
            if m.get("held_for_summary") is True and (m.get("state", "unread") != "unread" or now - float(m.get("held_at") or now) >= HOLD_DAYS * 86400):
                try:
                    self.write(account["id"], m["id"], held_for_summary=False, held_at=None)      # handled elsewhere, or held for 7 days: back in the inbox
                except Exception:
                    pass
                continue
            if key in seen or not self._ready(m):
                continue
            seen.add(key)
            urgent = m.get("act_today") is True or (self.important is not None and self.important.contains(user_id, m.get("sender_address")))
            if urgent:
                continue
            try:
                self.write(account["id"], m["id"], held_for_summary=True, held_at=now)
                held += 1
            except Exception:
                log.info("holding an email for the summary failed")
        raw["considered"] = sorted(seen & keys)[:MAX_CONSIDERED]
        self._save(user_id, raw)
        return held

    # ---------- a second look ----------
    def reassess(self, user_id: str, now: float | None = None) -> int:
        """Email that could wait, but has an open task due today, goes back in the inbox and alerts once. Returns how many alerts went out."""
        now = self.clock() if now is None else now
        try:
            raw = self._raw(user_id)
            if float(raw.get("reassess_at") or 0) > now:
                return 0
            tz = zone(self.tasks.timezone_of(user_id))
            today = datetime.fromtimestamp(now, tz).date()
            alerted = raw.get("alerted") if isinstance(raw.get("alerted"), dict) else {}
            alerted = {k: v for k, v in alerted.items() if now - float(v) < 14 * 86400}
            due = {(t["account_id"], t["message_id"]) for t in self.tasks.open_tasks(user_id) if date.fromisoformat(t["due"]) <= today}
            fresh = []
            for account, m in self._messages(user_id):
                key = account["id"] + ":" + m["id"]
                if (account["id"], m["id"]) in due and self._ready(m) and m.get("act_today") is not True and key not in alerted \
                        and now - float(m.get("received_at") or 0) < URGENT_LOOK_BACK:
                    fresh.append((account, m))
            sent = 0
            if fresh:
                for account, m in fresh:
                    if m.get("held_for_summary") is True:
                        self.write(account["id"], m["id"], held_for_summary=False, held_at=None)         # a deadline: back where it can be seen
                if self.alerts is not None and self.enabled(user_id):
                    sent = self.alerts.send(user_id, [{"account_id": a["id"], "id": m["id"], "sender_display": m.get("sender_display"), "sender_address": m.get("sender_address"),
                                                       "subject": m.get("subject"), "priority": m.get("priority"), "action_required": True, "act_today": True} for a, m in fresh])
                if sent:
                    for a, m in fresh:
                        alerted[a["id"] + ":" + m["id"]] = now
                else:
                    raw["reassess_at"] = now + RETRY_AFTER
            raw["alerted"] = alerted
            self._save(user_id, raw)
            return sent
        except Exception:
            log.info("reassessing urgent email failed")
            return 0

    # ---------- the one daily alert ----------
    def daily_alert(self, user_id: str, now: float | None = None) -> bool:
        """Once a day, at the daily summary time, say how many emails are waiting in the summary. Returns True when an alert went out."""
        now = self.clock() if now is None else now
        try:
            st = self.notifier.settings(user_id)
            tz = zone(self.tasks.timezone_of(user_id))
            local = datetime.fromtimestamp(now, tz)
            if local < datetime.combine(local.date(), _at(st["morning_time"]), tz):
                return False
            raw = self._raw(user_id)
            day = local.date().isoformat()
            if raw.get("alert_day") == day or float(raw.get("alert_retry") or 0) > now:
                return False
            if st.get("quiet_on") and in_quiet(local.time(), _at(st["quiet_from"]), _at(st["quiet_to"])):
                return False                                                                    # it waits until quiet hours end
            n = len(self._held(user_id))
            if n == 0 or not self.notifier.has_any(user_id):
                raw["alert_day"] = day
                self._save(user_id, raw)
                return False
            note = {"title": "Your daily summary", "body": f"{n} email{'s are' if n != 1 else ' is'} waiting in your summary. Open it when you like.",
                    "priority": "normal", "url": (self.click_url + "/?summary=1") if self.click_url else None}
            results = self.notifier.send_all(user_id, note)
            if any(v is None for v in results.values()):
                raw["alert_day"] = day
                raw.pop("alert_retry", None)
                self._save(user_id, raw)
                return True
            raw["alert_retry"] = now + ALERT_RETRY
            self._save(user_id, raw)
            return False
        except Exception:
            log.info("daily summary alert failed")
            return False

    # ---------- every minute ----------
    def tick(self, user_id: str) -> None:
        try:
            if not self.enabled(user_id):
                raw = self._raw(user_id)
                if raw.get("considered") is not None or raw.get("held"):
                    self.release(user_id)                                                       # switched off: everything goes back in the inbox
                    raw = self._raw(user_id)
                    raw.pop("considered", None)
                    raw.pop("held", None)
                    self._save(user_id, raw)
                return
            self.hold_pass(user_id)
            self.reassess(user_id)
            self.daily_alert(user_id)
        except Exception:
            log.info("daily summary pass failed")
