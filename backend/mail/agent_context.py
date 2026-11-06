"""What the Agent chat is shown, each time the person asks something: their own Enveliq, as plain text.

The chat model gets no tools and cannot look anything up. Instead, plain code here gathers what the signed-in person can see in
Enveliq and hands it over as data with the question:

* their emails as Enveliq keeps them (the AI-written summary, sender, subject, date), the newest few and the ones that match the
  words of the question. Never an email's text or a file: those are not stored.
* their trips and bookings, open tasks, orders and replies they are waiting for.

The person comes from the signed-in session, so only that person's mailboxes and lists are read. Everything is cut down to a small
size, control characters are removed, and the text is labelled as data. It is built fresh for each question and is not saved in the
chat.
"""
from __future__ import annotations

import re
import time
import unicodedata
from datetime import datetime
from typing import Any

from .tasks import zone

MAX_CONTEXT = 7000          # characters handed to the model in all
RECENT = 6                  # newest emails always shown
MATCHED = 10                # most emails shown because they match the question
SUMMARY_CHARS = 450
MAX_SCAN = 4000             # emails looked through per question
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_WORD = re.compile(r"[^\W_]+", re.UNICODE)
STOP = frozenset("""the and for are was were you your yours with this that these those have has had not but can could would should will
what when where which who whom why how any all some about from into out over under there their they them then than too very just
did does done get got give gave tell told show find look see saw say said let lets please email emails mail mails message messages
newest latest recent last first next new old today tomorrow yesterday week month year ive ill dont whats thats""".split())


def fold(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", str(text).casefold()) if not unicodedata.combining(c))


def _stem(word: str) -> str:
    """'flights' and 'flight' are the same word for matching."""
    return word[:-1] if len(word) > 4 and word.endswith("s") and not word.endswith("ss") else word


def terms(text: str) -> set[str]:
    return {_stem(w) for w in _WORD.findall(fold(text)) if len(w) >= 3 and w not in STOP}


def line(value: Any, limit: int) -> str:
    return re.sub(r"\s+", " ", _CONTROL.sub("", str(value or ""))).strip()[:limit]


def _when(ts: Any, tz: Any, with_time: bool = True) -> str:
    try:
        d = datetime.fromtimestamp(float(ts), tz)
    except (TypeError, ValueError, OverflowError, OSError):
        return "date unknown"
    return d.strftime("%a %d %b %Y").replace(" 0", " ", 1) + (d.strftime(" %H:%M") if with_time else "")


def _day(iso: Any) -> str:
    try:
        return datetime.strptime(str(iso), "%Y-%m-%d").strftime("%a %d %b %Y").replace(" 0", " ", 1)
    except ValueError:
        return line(iso, 20)


class Sources:
    """The parts of Enveliq the chat may read. Each is optional; one that is missing or fails is simply left out."""

    def __init__(self, vault: Any, tasks: Any = None, trips: Any = None, shipping: Any = None, waiting: Any = None):
        self.vault, self.tasks, self.trips, self.shipping, self.waiting = vault, tasks, trips, shipping, waiting


def _trips(src: Sources, user_id: str) -> list[str]:
    out: list[str] = []
    try:
        for trip in (src.trips.view(user_id).get("trips") or []) if src.trips else []:
            if trip.get("state") == "past" or trip.get("cancelled"):
                continue
            for b in trip.get("bookings") or []:
                if b.get("status") == "cancelled":
                    continue
                bits = [line(b.get("kind"), 20).capitalize() or "Booking", line(b.get("provider"), 60)]
                route = " to ".join(x for x in (line(b.get("from"), 60), line(b.get("to"), 60)) if x)
                when = _day(b.get("start")) + (f" at {line(b.get('start_time'), 8)}" if b.get("start_time") else "")
                if b.get("end"):
                    when += f" until {_day(b.get('end'))}" + (f" at {line(b.get('end_time'), 8)}" if b.get("end_time") else "")
                extra = [f"reference {line(b.get('reference'), 40)}" if b.get("reference") else "", line(b.get("detail"), 160), f"status {line(b.get('status'), 20)}"]
                out.append("- " + ", ".join(x for x in [" ".join(x for x in bits if x), route, when, *extra] if x))
            if len(out) >= 25:
                break
    except Exception:
        return []
    return out[:25]


def _tasks(src: Sources, user_id: str) -> list[str]:
    out: list[str] = []
    try:
        for t in (src.tasks.view(user_id).get("tasks") or []) if src.tasks else []:
            if t.get("state") != "open":
                continue
            due = _day(t.get("due"))
            out.append(f"- {line(t.get('title'), 120)} (due {due}" + (f", from {line(t.get('sender'), 60)}" if t.get("sender") else "") + ")"
                       + (f": {line(t.get('detail'), 140)}" if t.get("detail") else ""))
    except Exception:
        return []
    return out[:15]


def _orders(src: Sources, user_id: str) -> list[str]:
    out: list[str] = []
    try:
        for o in (src.shipping.view(user_id).get("orders") or []) if src.shipping else []:
            if o.get("delivered_at") and o.get("ack"):
                continue
            out.append("- " + ", ".join(x for x in [line(o.get("shop"), 60), f"order {line(o.get('order_number'), 40)}" if o.get("order_number") else "",
                                                    f"status {line(o.get('status'), 30)}", f"expected {line(o.get('expected') or o.get('expected_text'), 40)}" if (o.get("expected") or o.get("expected_text")) else "",
                                                    f"carrier {line(o.get('carrier'), 40)}" if o.get("carrier") else "", line(o.get("items"), 120)] if x))
    except Exception:
        return []
    return out[:10]


def _waiting(src: Sources, user_id: str, tz: Any) -> list[str]:
    out: list[str] = []
    try:
        for n in (src.waiting.view(user_id).get("notes") or []) if src.waiting else []:
            if n.get("state") != "waiting":
                continue
            out.append(f"- {line(n.get('subject'), 100)} (sent to {line(', '.join(n.get('to') or []), 100)} on {_when(n.get('sent_at'), tz, False)}"
                       + (f"; you asked: {line(n.get('ask'), 120)}" if n.get("ask") else "") + ")")
    except Exception:
        return []
    return out[:10]


def _emails(src: Sources, user_id: str, query: str) -> list[dict[str, Any]]:
    """This person's stored emails, newest first, restricted to mailboxes they own."""
    rows: list[dict[str, Any]] = []
    try:
        accounts = [a for a in src.vault.list_accounts() if a.get("owner_user_id") == user_id]
    except Exception:
        return []
    for account in accounts:
        try:
            for m in src.vault.list_messages(account["id"]):
                rows.append({**m, "_account": line(account.get("label") or account.get("email_address"), 60)})
        except Exception:
            continue
    rows = sorted(rows, key=lambda m: float(m.get("received_at") or 0), reverse=True)[:MAX_SCAN]
    want = terms(query)
    scored: list[tuple[int, int]] = []
    if want:
        for i, m in enumerate(rows):
            hay = terms(" ".join(str(m.get(k) or "") for k in ("subject", "sender_display", "sender_address", "category", "summary")))
            hay |= terms(" ".join(str(a.get("filename") or "") + " " + str(a.get("summary") or "") for a in (m.get("attachment_summaries") or []) if isinstance(a, dict)))
            score = len(want & hay)
            if score:
                scored.append((score, i))
    picked = {i for _, i in sorted(scored, key=lambda x: (-x[0], x[1]))[:MATCHED]} | set(range(min(RECENT, len(rows))))
    return [rows[i] for i in sorted(picked)]


def _email_block(n: int, m: dict[str, Any], tz: Any) -> str:
    summary = line(m.get("summary"), SUMMARY_CHARS)
    if summary.startswith("Not summarised yet"):
        summary = "(no summary yet)"
    files = [f"{line(a.get('filename'), 60)}: {line(a.get('summary'), 100)}" for a in (m.get("attachment_summaries") or []) if isinstance(a, dict)][:3]
    task = m.get("suggested_task") if isinstance(m.get("suggested_task"), dict) else None
    sender = line(m.get("sender_display"), 80)
    addr = line(m.get("sender_address"), 80)
    return (f"[E{n}] Received {_when(m.get('received_at'), tz)}. From: {sender}{' <' + addr + '>' if addr and addr not in sender else ''}. Subject: {line(m.get('subject'), 120)}. "
            f"Mailbox: {m.get('_account') or 'unknown'}. Folder in Enveliq: {'inbox' if m.get('state', 'unread') == 'unread' else m.get('state')}. "
            f"Needs action: {'yes' if m.get('action_required') else 'no'}. Summary: {summary}"
            + (f" Files: {'; '.join(files)}." if files else "")
            + (f" Suggested task: {line(task.get('title'), 100)}" + (f" ({line(task.get('due'), 30)})" if task.get("due") else "") + "." if task and task.get("title") else ""))


def build(src: Sources, user_id: str, question: str, earlier: str = "", now: float | None = None) -> str:
    """The data block for one question. `earlier` is the person's previous question, so a follow-up like "and the second one?" still finds its email."""
    now = time.time() if now is None else now
    tzname = None
    try:
        tzname = src.tasks.timezone_of(user_id) if src.tasks else None
    except Exception:
        tzname = None
    tz = zone(tzname)
    today = datetime.fromtimestamp(now, tz)
    parts = [f"TODAY: {today.strftime('%A %d %B %Y').replace(' 0', ' ', 1)}, {today.strftime('%H:%M')} ({tzname or 'UTC'})"]
    for title, rows in (("TRIPS AND BOOKINGS (from the person's email)", _trips(src, user_id)), ("OPEN TASKS", _tasks(src, user_id)),
                        ("ORDERS (from the person's email)", _orders(src, user_id)), ("WAITING FOR A REPLY", _waiting(src, user_id, tz))):
        parts.append(f"{title}:\n" + ("\n".join(rows) if rows else "- none"))
    head = "\n\n".join(parts)
    emails = _emails(src, user_id, f"{question} {earlier}")
    # Newest first; the number is only a label so the answer can say which email it used.
    blocks: list[str] = []
    used = len(head) + 200
    for m in sorted(emails, key=lambda m: float(m.get("received_at") or 0), reverse=True):
        text = _email_block(len(blocks) + 1, m, tz)
        if used + len(text) > MAX_CONTEXT:
            break
        blocks.append(text)
        used += len(text) + 1
    mail = ("EMAILS ENVELIQ HAS KEPT, newest first (a short AI-written summary of each, not the email itself; a few recent ones and the ones that "
            "match the question, not the whole mailbox):\n" + "\n".join(blocks)) if blocks else "EMAILS ENVELIQ HAS KEPT: none."
    return head + "\n\n" + mail


__all__ = ["Sources", "build", "terms"]
