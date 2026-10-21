"""The daily summary: one calm note each morning with what is waiting, instead of many small ones.

It is the old "morning summary" made fuller. Besides the tasks due today it can say how many sent emails are still waiting for a reply,
how many parcels are out for delivery, which subscriptions and free trials are coming up and, if the person asked for it, how many
unread emails are waiting.

Everything here is counted by Enveliq from results it already holds. The AI is not asked anything and never counts or decides.
No email text is read. Names and subjects of emails are never put in the note; the lines are counts and, only when the person allows
titles, the names of services or shops that are already on their lists.
"""
from __future__ import annotations

import time
from typing import Any, Callable

MAX_LISTED = 5


def _plural(n: int, one: str, many: str) -> str:
    return f"{n} {one if n == 1 else many}"


class DailySummary:
    def __init__(self, vault: Any, shipping: Any = None, waiting: Any = None, subs: Any = None, held: Callable[[str], set[tuple[str, str]]] | None = None,
                 clock: Callable[[], float] = time.time):
        self.vault, self.shipping, self.waiting, self.subs, self.held, self.clock = vault, shipping, waiting, subs, held, clock

    # ---------- what is waiting ----------
    def unread(self, user_id: str) -> int:
        """Unread emails in this person's own mailboxes that are ready (summary done, not from the 'include read' list, not held by a task)."""
        held = self.held(user_id) if self.held else set()
        total = 0
        try:
            accounts = [a for a in self.vault.list_accounts() if a.get("owner_user_id") == user_id]
        except Exception:
            return 0
        for account in accounts:
            try:
                for m in self.vault.list_messages(account["id"]):
                    if m.get("state", "unread") == "unread" and not m.get("from_all_mail") and not m.get("ai_pending") and (account["id"], m["id"]) not in held:
                        total += 1
            except Exception:
                continue
        return total

    def counts(self, user_id: str, *, with_unread: bool = False, now: float | None = None) -> dict[str, Any]:
        """Plain numbers for this person alone. `names` are service and shop names (never email subjects or senders)."""
        now = self.clock() if now is None else now
        out: dict[str, Any] = {"waiting": 0, "parcels": 0, "coming": 0, "unread": 0, "coming_lines": [], "parcel_shops": []}
        try:
            if self.waiting is not None:
                view = self.waiting.view(user_id)
                out["waiting"] = sum(1 for n in view.get("notes", []) if n.get("due"))
        except Exception:
            pass
        try:
            if self.shipping is not None:
                orders = self.shipping.view(user_id).get("orders", [])
                out["parcel_shops"] = [str(o.get("shop") or "") for o in orders if o.get("status") == "out_for_delivery" and not o.get("delivered_at")]
                out["parcels"] = len(out["parcel_shops"])
        except Exception:
            pass
        try:
            if self.subs is not None:
                coming = self.subs.due_nudges(user_id, now)
                out["coming"] = len(coming)
                out["coming_lines"] = coming
        except Exception:
            pass
        if with_unread:
            out["unread"] = self.unread(user_id)
        return out

    @staticmethod
    def extra(counts: dict[str, Any]) -> int:
        """How many things beyond tasks the summary has to say."""
        return int(counts.get("waiting", 0)) + int(counts.get("parcels", 0)) + int(counts.get("coming", 0)) + int(counts.get("unread", 0) > 0)

    # ---------- the words ----------
    def lines(self, counts: dict[str, Any], private: bool) -> list[str]:
        """One short line per thing. With titles off, only how many."""
        out: list[str] = []
        if counts.get("unread"):
            out.append(f"• {_plural(counts['unread'], 'unread email', 'unread emails')} waiting")
        if counts.get("waiting"):
            out.append(f"• {_plural(counts['waiting'], 'email', 'emails')} you sent still waiting for a reply")
        if counts.get("parcels"):
            shops = [s for s in counts.get("parcel_shops", []) if s]
            if not private and len(shops) == counts["parcels"] and counts["parcels"] <= 3:
                out.append("• Out for delivery today: " + ", ".join(shops))
            else:
                out.append(f"• {_plural(counts['parcels'], 'parcel', 'parcels')} out for delivery")
        if counts.get("coming"):
            lines = counts.get("coming_lines", [])
            if not private and len(lines) <= 3:
                for d in lines:
                    what = "free trial ends" if d.get("kind") == "trial_ends" else "renews"
                    when = "today" if d.get("days") == 0 else "tomorrow" if d.get("days") == 1 else f"in {d.get('days')} days"
                    out.append(f"• {d.get('service')} {what} {when}")
            else:
                out.append(f"• {_plural(counts['coming'], 'subscription', 'subscriptions')} coming up")
        return out

    def title_for(self, tasks_due: int, counts: dict[str, Any]) -> str:
        n = tasks_due + int(counts.get("waiting", 0)) + int(counts.get("parcels", 0)) + int(counts.get("coming", 0))
        if n == 0 and counts.get("unread"):
            return "Your day"
        return f"Today: {_plural(n, 'thing', 'things')}"
