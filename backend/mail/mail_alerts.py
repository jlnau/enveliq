"""New-email alerts: a short message to a person's own notification channels when new mail has arrived.

Off until the person switches it on. By default it only says how many emails arrived. If the person also allows it, the
sender's name and the subject are included (never the address, never the summary, never any email text). Quiet hours are
respected: nothing is sent during them, and the emails simply wait in the inbox. Tapping the message opens Enveliq at that
email (one email) or at the inbox (several).
"""
from __future__ import annotations

import logging
import time
import urllib.parse
from datetime import datetime
from typing import Any, Callable

from .notify import Notifier, _clean
from .reminders import _at, in_quiet
from .tasks import zone

log = logging.getLogger("enveliq.mail_alerts")
MAX_LISTED = 3


class MailAlerts:
    def __init__(self, notifier: Notifier, click_url: str, timezone_of: Callable[[str], str], clock: Callable[[], float] = time.time, important: Any = None):
        self.notifier, self.click_url, self.timezone_of, self.clock = notifier, click_url, timezone_of, clock
        self.important = important

    @staticmethod
    def _path(account_id: str, message_id: str | None) -> str:
        if not message_id:
            return "/"
        return "/?open=" + urllib.parse.quote(f"{account_id}:{message_id}", safe=":-")

    def note(self, new: list[dict[str, Any]], details: bool) -> dict[str, Any]:
        """`new` holds dicts with account_id, id, sender_display, subject, priority."""
        n = len(new)
        path = self._path(new[0]["account_id"], new[0]["id"]) if n == 1 else "/"
        high = any(m.get("priority") == "high" for m in new)
        if not details:
            title, body = "Enveliq", f"{n} new email{'s' if n != 1 else ''}. Open Enveliq to read {'them' if n != 1 else 'it'}."
        elif n == 1:
            m = new[0]
            title = _clean(m.get("sender_display"), 80) or "New email"
            body = _clean(m.get("subject"), 200) or "(no subject)"
        else:
            title = f"{n} new emails"
            lines = [f"• {_clean(m.get('sender_display'), 40) or 'Someone'}: {_clean(m.get('subject'), 80) or '(no subject)'}" for m in new[:MAX_LISTED]]
            if n > MAX_LISTED:
                lines.append(f"and {n - MAX_LISTED} more")
            body = "\n".join(lines)
        return {"title": title, "body": body, "priority": "high" if high else "normal", "path": path, "url": (self.click_url + path) if self.click_url else None,
                "mail": {"count": n}}

    def send(self, user_id: str, new: list[dict[str, Any]]) -> int:
        """Send one message about `new`. Returns 1 if something went out, else 0. Never raises."""
        if not new:
            return 0
        try:
            st = self.notifier.settings(user_id)
            if not st["mail_on"] or not self.notifier.has_any(user_id):
                return 0
            muted = set(st.get("mail_muted_accounts", []))
            new = [m for m in new if m.get("account_id") not in muted]
            if st.get("digest_mail") and st.get("morning_on", True):
                # New email waits for the daily summary. Only people the person chose to see first still come through at once.
                new = [m for m in new if self.important is not None and self.important.contains(user_id, m.get("sender_address"))]
            mode = st.get("mail_filter", "all")
            if mode == "important":
                new = [m for m in new if self.important is not None and self.important.contains(user_id, m.get("sender_address"))]
            elif mode == "action":
                new = [m for m in new if m.get("action_required") is True]
            if not new:
                return 0
            if st["quiet_on"]:
                local = datetime.fromtimestamp(self.clock(), zone(self.timezone_of(user_id)))
                if in_quiet(local.time(), _at(st["quiet_from"]), _at(st["quiet_to"])):
                    return 0
            results = self.notifier.send_all(user_id, self.note(new, st["mail_details"]))
            return 1 if any(v is None for v in results.values()) else 0
        except Exception:
            log.info("new-email alert failed")
            return 0
