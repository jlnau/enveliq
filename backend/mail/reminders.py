"""When to send reminders, and what they say.

Every minute (while the vault is unlocked) each person who has a reminder channel on is checked:

* a **morning summary** at their chosen time, listing what is due today (including anything that was missed);
* a **reminder** for a task with a time ("Later today"), at that time, and for a task made later in the day, when it appears;
* a gentle **nudge** if a task is still open a couple of hours after it was announced, a limited number of times;
* nothing during **quiet hours**: it is held and sent when they end.

What was sent is remembered per task and date, so a restart or a slow channel never repeats a message. If every
channel fails, it tries again in five minutes. The page itself (the Today card and the Tasks badge) needs none of this.
"""
from __future__ import annotations

import json
import logging
import threading
import time
from datetime import date, datetime, time as dtime, timedelta
from typing import Any, Callable

from .notify import Notifier
from .tasks import TaskBook, zone

log = logging.getLogger("enveliq.reminders")
MORNING_WINDOW = timedelta(hours=6)
RETRY_SECONDS = 300
MAX_LISTED = 5


def _at(text: str) -> dtime:
    return dtime(int(text[:2]), int(text[3:5]))


def in_quiet(now: dtime, start: dtime, end: dtime) -> bool:
    if start == end:
        return False
    return start <= now < end if start < end else (now >= start or now < end)


class Reminders:
    def __init__(self, vault: Any, tasks: TaskBook, notifier: Notifier, click_url: str = "", clock: Callable[[], float] = time.time):
        self.vault, self.tasks, self.notifier, self.click_url, self.clock = vault, tasks, notifier, click_url, clock
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # ---------- the words ----------
    def _list(self, tasks: list[dict[str, Any]], private: bool, today: date) -> str:
        if private:
            return ""
        lines = []
        for t in tasks[:MAX_LISTED]:
            late = (today - date.fromisoformat(t["due"])).days
            lines.append(f"• {t['title']}" + (f" (waiting since {date.fromisoformat(t['due']).strftime('%a')})" if late > 0 else ""))
        if len(tasks) > MAX_LISTED:
            lines.append(f"and {len(tasks) - MAX_LISTED} more")
        return "\n".join(lines)

    def note(self, kind: str, tasks: list[dict[str, Any]], private: bool, today: date) -> dict[str, Any]:
        n = len(tasks)
        things = f"{n} thing{'s' if n != 1 else ''}"
        title = {"morning": f"Today: {things}", "due": "Due now" if n == 1 else f"Due now: {things}", "nudge": "Still to do" if n == 1 else f"Still to do: {things}"}[kind]
        if private:
            body = {"morning": f"You have {things} to do today. Open Enveliq to see them.", "due": f"{things} due. Open Enveliq to see them.",
                    "nudge": f"{things} still waiting. Open Enveliq to see them."}[kind]
            title = "Enveliq"
        else:
            body = self._list(tasks, False, today)
        return {"title": title, "body": body, "priority": "high" if any(t.get("priority") == "high" for t in tasks) else "normal", "url": self.click_url or None}

    # ---------- one person ----------
    def run_user(self, uid: str, now: float | None = None) -> int:
        """Send whatever is due for this person. Returns how many messages went out."""
        now = self.clock() if now is None else now
        n = self.notifier
        if not n.has_any(uid):
            return 0
        state = n.get_state(uid)
        before = json.dumps(state, sort_keys=True)
        if float(state.get("retry_at") or 0) > now:
            return 0
        st = n.settings(uid)
        self.tasks.reconcile(uid)
        tz = zone(self.tasks.timezone_of(uid))
        local = datetime.fromtimestamp(now, tz)
        if st["quiet_on"] and in_quiet(local.time(), _at(st["quiet_from"]), _at(st["quiet_to"])):
            return 0
        today = local.date()
        open_tasks = self.tasks.open_tasks(uid)
        key = lambda t: f"{t['id']}|{t['due']}|{t.get('remind_at')}"
        live = {key(t) for t in open_tasks}
        sent_state: dict[str, Any] = state.setdefault("tasks", {})
        for k in [k for k in sent_state if k not in live]:
            del sent_state[k]
        due_today = [t for t in open_tasks if date.fromisoformat(t["due"]) <= today]
        due_today.sort(key=lambda t: (t["due"], 0 if t.get("priority") == "high" else 1))
        start = datetime.combine(today, _at(st["morning_time"]), tz)
        private = not st["show_titles"]
        plan: list[tuple[dict[str, Any], list[str], str]] = []
        in_summary: set[str] = set()
        morning_now = st["morning_on"] and local >= start and state.get("morning_date") != today.isoformat() and local - start < MORNING_WINDOW
        if morning_now:
            listed = [t for t in due_today if not t.get("remind_at") or t["remind_at"] <= now]
            if listed:
                plan.append((self.note("morning", listed, private, today), [key(t) for t in listed], "morning"))
                in_summary = {key(t) for t in listed}
            else:
                state["morning_date"] = today.isoformat()
        if st["due_on"]:
            fresh = []
            for t in due_today:
                k = key(t)
                if k in sent_state or k in in_summary:
                    continue
                if t.get("remind_at"):
                    if now >= t["remind_at"]:
                        fresh.append(t)
                elif local >= start and (not st["morning_on"] or state.get("morning_date") == today.isoformat() or local - start >= MORNING_WINDOW):
                    fresh.append(t)
            if fresh:
                plan.append((self.note("due", fresh, private, today), [key(t) for t in fresh], "due"))
        if st["repeat_max"] > 0:
            wait = st["repeat_hours"] * 3600
            again = [t for t in due_today if key(t) in sent_state and sent_state[key(t)]["count"] < 1 + st["repeat_max"] and now - sent_state[key(t)]["last"] >= wait]
            if again:
                plan.append((self.note("nudge", again, private, today), [key(t) for t in again], "nudge"))
        sent = 0
        failed = False
        for note, keys, kind in plan:
            results = n.send_all(uid, note)
            if any(v is None for v in results.values()):
                sent += 1
                for k in keys:
                    e = sent_state.setdefault(k, {"count": 0, "last": 0})
                    e["count"] += 1
                    e["last"] = now
                if kind == "morning":
                    state["morning_date"] = today.isoformat()
            else:
                failed = True
        if failed and not sent:
            state["retry_at"] = now + RETRY_SECONDS
        else:
            state.pop("retry_at", None)
        if json.dumps(state, sort_keys=True) != before:
            n.set_state(uid, state)
        return sent

    # ---------- the loop ----------
    def tick(self) -> int:
        if not self.vault.is_unlocked():
            return 0
        total = 0
        with self.vault.passive():
            try:
                users = [u["id"] for u in self.vault.list_users() if not u.get("disabled")]
            except Exception:
                return 0
            for uid in users:
                if self._stop.is_set() or not self.vault.is_unlocked():
                    break
                try:
                    total += self.run_user(uid)
                except Exception:
                    log.info("reminders for one person failed")        # never anything from the task or the email
        return total

    def start(self) -> None:
        if self._thread:
            return
        self._thread = threading.Thread(target=self._run, name="enveliq-reminders", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        while not self._stop.wait(60):
            try:
                self.tick()
            except Exception:
                log.warning("reminder pass failed")
