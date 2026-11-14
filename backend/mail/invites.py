"""Calendar invites (.ics) in an email: reading them, answering them, and putting accepted meetings in the person's calendar.

* Reading: the invite is parsed in memory from the email the mailbox hands over. Nothing from it is stored except the person's own
  answer (see `State`): no title, no place, no people. The AI is not involved; the dates are read by plain code.
* Answering: Accept, Maybe and Decline send the organiser the standard calendar reply (iTIP METHOD:REPLY) as an ordinary email, from
  the address the invite was sent to when this mailbox can send from it. It goes through the same limits and Undo as other replies.
  Propose a new time sends a plain email in words, because calendar apps do not all understand a counter proposal.
* Calendar: an accepted (or maybe) meeting is written to the Google Calendar or CalDAV calendar already connected under Settings,
  Calendar & to-do. A declined or cancelled one is taken out again. Only events Enveliq made itself are ever changed.
The invite is untrusted text: every field is length-limited and stripped of control characters, and nothing in it is ever run.
"""
from __future__ import annotations

import hashlib
import re
import time
from datetime import date, datetime, timedelta, timezone
from email import message_from_bytes, policy
from email.message import EmailMessage
from email.policy import SMTP as SMTP_POLICY
from email.utils import format_datetime, make_msgid, parseaddr
from typing import Any
from zoneinfo import ZoneInfo

MAX_BYTES = 1_000_000
MAX_ATTENDEES = 50
RESPONSES = {"accepted": "ACCEPTED", "tentative": "TENTATIVE", "declined": "DECLINED"}
WORDS = {"accepted": "accepted", "tentative": "tentatively accepted", "declined": "declined"}
STATE_KEEP_DAYS = 180
STATE_MAX = 500

_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_ADDRESS = re.compile(r"^[^@\s<>,;\"]{1,64}@[A-Za-z0-9.-]{1,255}$")
_RRULE = re.compile(r"^[A-Z0-9=;,\-+:]{1,200}$")
_WINDOWS = {
    "AUS Eastern Standard Time": "Australia/Sydney", "E. Australia Standard Time": "Australia/Brisbane", "Cen. Australia Standard Time": "Australia/Adelaide",
    "AUS Central Standard Time": "Australia/Darwin", "W. Australia Standard Time": "Australia/Perth", "Tasmania Standard Time": "Australia/Hobart",
    "New Zealand Standard Time": "Pacific/Auckland", "GMT Standard Time": "Europe/London", "W. Europe Standard Time": "Europe/Berlin",
    "Romance Standard Time": "Europe/Paris", "Central Europe Standard Time": "Europe/Budapest", "Central European Standard Time": "Europe/Warsaw",
    "E. Europe Standard Time": "Europe/Chisinau", "FLE Standard Time": "Europe/Kyiv", "Eastern Standard Time": "America/New_York",
    "Central Standard Time": "America/Chicago", "Mountain Standard Time": "America/Denver", "Pacific Standard Time": "America/Los_Angeles",
    "India Standard Time": "Asia/Kolkata", "China Standard Time": "Asia/Shanghai", "Tokyo Standard Time": "Asia/Tokyo",
    "Singapore Standard Time": "Asia/Singapore", "UTC": "UTC", "Greenwich Standard Time": "Atlantic/Reykjavik",
}


def _clean(value: Any, limit: int) -> str:
    return _CONTROL.sub("", str(value or "")).replace("\r", "").strip()[:limit]


def _oneline(value: Any, limit: int) -> str:
    return re.sub(r"\s+", " ", _clean(value, limit * 2)).strip()[:limit]


# ---------- finding and reading the calendar part ----------

def find(raw: bytes) -> str | None:
    """The text of the first calendar part of an email (inline or attached), or None. Only parts up to 1 MB are looked at."""
    try:
        msg = message_from_bytes(raw, policy=policy.default)
    except Exception:
        return None
    for part in msg.walk():
        if part.is_multipart():
            continue
        ctype = part.get_content_type()
        name = (part.get_filename() or "").lower()
        if ctype not in ("text/calendar", "application/ics") and not (name.endswith(".ics") and ctype in ("application/octet-stream", "text/plain")):
            continue
        try:
            data = part.get_payload(decode=True) or b""
        except Exception:
            continue
        if len(data) > MAX_BYTES or b"BEGIN:VEVENT" not in data.upper():
            continue
        return data.decode("utf-8", "replace")
    return None


def _lines(text: str) -> list[str]:
    out: list[str] = []
    for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if line[:1] in (" ", "\t") and out:
            out[-1] += line[1:]
        else:
            out.append(line)
    return out


def _prop(line: str) -> tuple[str, dict[str, str], str] | None:
    """NAME;PARAM=value;PARAM="v;w":value, split without being fooled by quotes."""
    in_quote, name_end, colon = False, None, -1
    for i, ch in enumerate(line):
        if ch == '"':
            in_quote = not in_quote
        elif ch == ":" and not in_quote:
            colon = i
            break
    if colon < 1:
        return None
    head, value = line[:colon], line[colon + 1:]
    parts: list[str] = []
    buf, in_quote = "", False
    for ch in head:
        if ch == '"':
            in_quote = not in_quote
            buf += ch
        elif ch == ";" and not in_quote:
            parts.append(buf)
            buf = ""
        else:
            buf += ch
    parts.append(buf)
    params: dict[str, str] = {}
    for p in parts[1:]:
        if "=" in p:
            k, v = p.split("=", 1)
            params[k.upper()] = v.strip('"')
    return parts[0].upper(), params, value


def _text(value: str) -> str:
    return value.replace("\\n", "\n").replace("\\N", "\n").replace("\\,", ",").replace("\\;", ";").replace("\\\\", "\\")


def _mail(value: str, params: dict[str, str]) -> str:
    v = value.strip()
    v = v[7:] if v.lower().startswith("mailto:") else params.get("EMAIL", "")
    v = v.strip().split("?")[0]
    return v if _ADDRESS.match(v) else ""


def _zone(name: str) -> ZoneInfo | None:
    name = _WINDOWS.get(name, name)
    if not re.match(r"^[A-Za-z0-9_+\-/]{1,64}$", name):
        return None
    try:
        return ZoneInfo(name)
    except Exception:
        return None


def _when(value: str, params: dict[str, str], home: ZoneInfo) -> tuple[float | None, bool, str, str]:
    """(Unix time, all day, 'YYYY-MM-DD' for all-day, zone name used). Floating times and unknown zones use the person's own zone."""
    v = value.strip()
    try:
        if params.get("VALUE") == "DATE" or re.fullmatch(r"\d{8}", v):
            d = date(int(v[:4]), int(v[4:6]), int(v[6:8]))
            return None, True, d.isoformat(), ""
        m = re.fullmatch(r"(\d{8})T(\d{6})(Z?)", v)
        if not m:
            return None, False, "", ""
        naive = datetime.strptime(m[1] + m[2], "%Y%m%d%H%M%S")
        if m[3]:
            return naive.replace(tzinfo=timezone.utc).timestamp(), False, "", "UTC"
        zone = _zone(params.get("TZID", "")) if params.get("TZID") else None
        use = zone or home
        return naive.replace(tzinfo=use).timestamp(), False, "", getattr(use, "key", "UTC")
    except (ValueError, OverflowError):
        return None, False, "", ""


def _duration(value: str) -> timedelta | None:
    m = re.fullmatch(r"P(?:(\d+)W)?(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?", value.strip())
    if not m or not any(m.groups()):
        return None
    w, d, h, mi, s = (int(x or 0) for x in m.groups())
    return timedelta(weeks=w, days=d, hours=h, minutes=mi, seconds=s)


def parse(text: str, home_zone: str | None = None) -> dict[str, Any] | None:
    """The first event of a calendar file as plain fields, or None. `home_zone` is the person's own time zone name."""
    home = _zone(home_zone or "") or ZoneInfo("UTC")
    method = ""
    ev: dict[str, Any] | None = None
    keep: dict[str, str] = {}
    attendees: list[dict[str, str]] = []
    for line in _lines(text[:MAX_BYTES]):
        got = _prop(line)
        if got is None:
            continue
        name, params, value = got
        if name == "METHOD" and ev is None:
            method = value.strip().upper()[:20]
        elif name == "BEGIN" and value.strip().upper() == "VEVENT":
            if ev is not None:
                break
            ev = {}
        elif name == "END" and value.strip().upper() == "VEVENT":
            break
        elif name == "BEGIN" and ev is not None:               # an alarm or other nested part: its lines are not the event's
            ev["_skip"] = ev.get("_skip", 0) + 1
        elif name == "END" and ev is not None and ev.get("_skip"):
            ev["_skip"] -= 1
        elif ev is not None and not ev.get("_skip"):
            if name in ("DTSTART", "DTEND", "RECURRENCE-ID"):
                ev[name] = (params, value.strip())
                keep[name] = line[:300]
            elif name == "ATTENDEE" and len(attendees) < MAX_ATTENDEES:
                attendees.append({"email": _mail(value, params), "name": _oneline(params.get("CN", ""), 120),
                                  "partstat": params.get("PARTSTAT", "NEEDS-ACTION").upper()[:20], "rsvp": params.get("RSVP", "").upper()})
            elif name == "ORGANIZER":
                ev["ORGANIZER"] = {"email": _mail(value, params), "name": _oneline(params.get("CN", ""), 120)}
            elif name not in ev or name in ("RRULE",):
                ev[name] = (params, value)
    if ev is None or "DTSTART" not in ev:
        return None
    start, all_day, start_day, tz = _when(ev["DTSTART"][1], ev["DTSTART"][0], home)
    if start is None and not all_day:
        return None
    end = end_day = None
    if "DTEND" in ev:
        end, _, end_day, _ = _when(ev["DTEND"][1], ev["DTEND"][0], home)
        end_day = end_day or None
    elif "DURATION" in ev and (dur := _duration(ev["DURATION"][1])) is not None and start is not None:
        end = start + dur.total_seconds()
    if all_day:
        end_day = end_day or (date.fromisoformat(start_day) + timedelta(days=1)).isoformat()
    elif end is None or end < start:
        end = (start or 0) + 3600
    rrule = ""
    if "RRULE" in ev:
        candidate = _clean(ev["RRULE"][1], 200).upper()
        rrule = candidate if _RRULE.match(candidate) else ""
    organizer = ev.get("ORGANIZER") or {"email": "", "name": ""}

    def field(key: str, limit: int, multi: bool = False) -> str:
        if key not in ev:
            return ""
        t = _text(ev[key][1])
        return _clean(t, limit) if multi else _oneline(t, limit)

    try:
        sequence = max(0, min(int(ev.get("SEQUENCE", ({}, "0"))[1] or 0), 100000))
    except ValueError:
        sequence = 0
    return {"method": method or "", "uid": _clean(ev.get("UID", ({}, ""))[1], 300), "sequence": sequence,
            "summary": field("SUMMARY", 200) or "(no title)", "location": field("LOCATION", 300), "description": field("DESCRIPTION", 1500, True),
            "start": start, "end": end, "all_day": all_day, "start_day": start_day, "end_day": end_day, "tz": tz or home_zone or "UTC", "rrule": rrule,
            "status": field("STATUS", 20).upper(), "organizer": organizer, "attendees": attendees,
            "recurrence": bool(ev.get("RECURRENCE-ID")), "raw": keep}


def from_email(raw: bytes, home_zone: str | None = None) -> dict[str, Any] | None:
    text = find(raw)
    return parse(text, home_zone) if text else None


def key_of(invite: dict[str, Any]) -> str:
    """A short, opaque name for this meeting (its calendar id plus the instance for one date of a series)."""
    basis = invite["uid"] + "|" + (invite["raw"].get("RECURRENCE-ID", "") if invite["recurrence"] else "")
    return hashlib.sha256(basis.encode()).hexdigest()[:40]


# ---------- what the person sees ----------

def summary_text(invite: dict[str, Any]) -> str:
    """The invite as a few plain lines, for the file reader and the AI. Dates are read by code, not by the AI."""
    when = ""
    if invite["all_day"]:
        when = invite["start_day"] + (" (all day)" if invite["end_day"] and invite["end_day"] <= (date.fromisoformat(invite["start_day"]) + timedelta(days=1)).isoformat() else f" to {invite['end_day']}")
    elif invite["start"] is not None:
        z = _zone(invite["tz"]) or ZoneInfo("UTC")
        a, b = datetime.fromtimestamp(invite["start"], z), datetime.fromtimestamp(invite["end"] or invite["start"], z)
        when = f"{a:%a %d %b %Y, %H:%M} to {b:%H:%M} ({invite['tz']})" if a.date() == b.date() else f"{a:%a %d %b %Y %H:%M} to {b:%a %d %b %Y %H:%M} ({invite['tz']})"
    kind = {"CANCEL": "Meeting cancelled", "REPLY": "Reply to a meeting", "REQUEST": "Meeting invitation"}.get(invite["method"], "Calendar event")
    lines = [f"{kind}: {invite['summary']}", f"When: {when}"]
    if invite["location"]:
        lines.append("Where: " + invite["location"])
    org = invite["organizer"]
    if org["email"]:
        lines.append("Organiser: " + (f"{org['name']} " if org["name"] else "") + f"({org['email']})")
    if invite["attendees"]:
        lines.append("People: " + ", ".join((a["name"] or a["email"]) for a in invite["attendees"][:10] if a["name"] or a["email"]))
    if invite["rrule"]:
        lines.append("Repeats: yes")
    if invite["description"]:
        lines.append("Notes: " + invite["description"][:600])
    return "\n".join(lines)


def public(invite: dict[str, Any], *, mine: str, answer: dict[str, Any] | None, differs: bool, calendar: str) -> dict[str, Any]:
    """The card's data. `mine` is the address of ours the invite was sent to; `differs` says the organiser is not the sender."""
    org = invite["organizer"]
    can_answer = invite["method"] in ("REQUEST", "") and bool(org["email"]) and invite["status"] != "CANCELLED" and bool(invite["attendees"])
    return {"method": invite["method"] or "PUBLISH", "summary": invite["summary"], "location": invite["location"], "description": invite["description"][:600],
            "start": invite["start"], "end": invite["end"], "all_day": invite["all_day"], "start_day": invite["start_day"], "end_day": invite["end_day"],
            "tz": invite["tz"], "repeats": bool(invite["rrule"]), "cancelled": invite["method"] == "CANCEL" or invite["status"] == "CANCELLED",
            "organizer": {"name": org["name"], "email": org["email"]}, "people": len(invite["attendees"]),
            "can_answer": can_answer, "can_add": invite["method"] in ("", "PUBLISH", "REQUEST") and invite["status"] != "CANCELLED",
            "organizer_differs": bool(differs and can_answer), "mine": mine, "calendar": calendar, "answer": answer}


def organizer_differs(invite: dict[str, Any], sender: str) -> bool:
    """True when the organiser's address is not on the sender's domain (an invite can name anyone as organiser)."""
    org = invite["organizer"]["email"].lower()
    s = (sender or "").lower()
    if not org or not s or "@" not in s:
        return bool(org)
    a, b = org.rsplit("@", 1)[1], s.rsplit("@", 1)[1]
    return not (a == b or a.endswith("." + b) or b.endswith("." + a))


# ---------- answering ----------

def _ics_time(invite: dict[str, Any], which: str) -> str:
    raw = invite["raw"].get(which)
    if raw:
        return _CONTROL.sub("", raw)
    return ""


def _fold(line: str) -> str:
    from .calsync import fold
    return fold(line)


def reply_calendar(invite: dict[str, Any], me: str, my_name: str, response: str, now: float, comment: str = "") -> str:
    """The iTIP reply file: the same meeting, with only the answering person's status."""
    from .calsync import esc
    org = invite["organizer"]
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Enveliq//Invites//EN", "METHOD:REPLY", "BEGIN:VEVENT", "UID:" + invite["uid"],
             "DTSTAMP:" + datetime.fromtimestamp(now, timezone.utc).strftime("%Y%m%dT%H%M%SZ"), f"SEQUENCE:{invite['sequence']}"]
    for which in ("DTSTART", "DTEND", "RECURRENCE-ID"):
        text = _ics_time(invite, which)
        if text:
            lines.append(text)
    cn = f";CN={esc(my_name)}" if my_name and not re.search(r'[";:,]', my_name) else ""
    lines += [f"ORGANIZER:mailto:{org['email']}", f"ATTENDEE;PARTSTAT={RESPONSES[response]}{cn}:mailto:{me}", "SUMMARY:" + esc(invite["summary"])]
    if comment:
        lines.append("COMMENT:" + esc(comment))
    lines += ["END:VEVENT", "END:VCALENDAR"]
    return "\r\n".join(_fold(ln) for ln in lines) + "\r\n"


def pick_identity(service: Any, account: dict[str, Any], invite: dict[str, Any], delivered_to: str | None) -> str:
    """The address to answer from: one of ours named on the invite when this mailbox can send from it, else the usual reply address."""
    from .parse import sending_identities
    ours = {i.lower(): i for i in sending_identities(account)}
    for a in invite["attendees"]:
        if a["email"].lower() in ours:
            return ours[a["email"].lower()]
    return service._pick_from(account, None, delivered_to)


def build_answer(service: Any, account: dict[str, Any], message: dict[str, Any], invite: dict[str, Any], response: str, comment: str) -> tuple[EmailMessage, str, list[str]]:
    from .errors import BridgeError
    org = invite["organizer"]
    ctx = message.get("reply_context") or {}
    chosen = pick_identity(service, account, invite, ctx.get("delivered_to"))
    to_a, _, _ = service._people([f"{org['name']} <{org['email']}>" if org["name"] and not re.search(r'[<>",;]', org["name"]) else org["email"]], [], [])
    my_name = next((a["name"] for a in invite["attendees"] if a["email"].lower() == chosen.lower()), "")
    now = time.time()
    msg = EmailMessage(policy=SMTP_POLICY)
    msg["From"] = chosen
    msg["To"] = to_a
    prefix = {"accepted": "Accepted", "tentative": "Tentative", "declined": "Declined"}[response]
    msg["Subject"] = f"{prefix}: {invite['summary']}"[:900]
    msg["Date"] = format_datetime(datetime.now(timezone.utc))
    msg["Message-ID"] = make_msgid(domain=chosen.rsplit("@", 1)[1])
    original_id = ctx.get("message_id")
    if original_id and re.match(r"^<[^<>\s]{1,300}>$", original_id):
        msg["In-Reply-To"] = original_id
        msg["References"] = original_id
    words = f"{chosen} has {WORDS[response]} this invitation: {invite['summary']}."
    msg.set_content(words + (f"\n\n{comment.strip()}" if comment.strip() else ""))
    try:
        msg.add_alternative(reply_calendar(invite, chosen, my_name, response, now, comment.strip()[:500]), subtype="calendar", params={"method": "REPLY"})
    except Exception:
        raise BridgeError("not_configured", "Enveliq could not build the reply to this invitation.") from None
    return msg, chosen, [a.addr_spec for a in to_a]


def format_slot(start: float, end: float, zone_name: str) -> str:
    z = _zone(zone_name) or ZoneInfo("UTC")
    a, b = datetime.fromtimestamp(start, z), datetime.fromtimestamp(end, z)
    day = f"{a:%A} {a.day} {a:%B %Y}"
    clock = f"{a:%I:%M %p}".lstrip("0").lower() + " to " + f"{b:%I:%M %p}".lstrip("0").lower()
    if b.date() != a.date():
        clock = f"{a:%I:%M %p}".lstrip("0").lower() + f" to {b:%A} " + f"{b:%I:%M %p}".lstrip("0").lower()
    return f"{day}, {clock} ({zone_name})"


def build_proposal(service: Any, account: dict[str, Any], message: dict[str, Any], invite: dict[str, Any], start: float, end: float, zone_name: str, note: str) -> tuple[EmailMessage, str, list[str]]:
    org = invite["organizer"]
    ctx = message.get("reply_context") or {}
    chosen = pick_identity(service, account, invite, ctx.get("delivered_to"))
    to_a, _, _ = service._people([f"{org['name']} <{org['email']}>" if org["name"] and not re.search(r'[<>",;]', org["name"]) else org["email"]], [], [])
    msg = EmailMessage(policy=SMTP_POLICY)
    msg["From"] = chosen
    msg["To"] = to_a
    msg["Subject"] = f"New time suggested: {invite['summary']}"[:900]
    msg["Date"] = format_datetime(datetime.now(timezone.utc))
    msg["Message-ID"] = make_msgid(domain=chosen.rsplit("@", 1)[1])
    original_id = ctx.get("message_id")
    if original_id and re.match(r"^<[^<>\s]{1,300}>$", original_id):
        msg["In-Reply-To"] = original_id
        msg["References"] = original_id
    was = ""
    if invite["start"] is not None and invite["end"] is not None:
        was = "\nThe time in the invitation: " + format_slot(invite["start"], invite["end"], zone_name)
    text = f"Hello{(' ' + org['name']) if org['name'] else ''},\n\nI cannot make the time in your invitation \"{invite['summary']}\". Could we meet at this time instead?\n\n{format_slot(start, end, zone_name)}{was}"
    if note.strip():
        text += "\n\n" + note.strip()
    msg.set_content(text + "\n")
    return msg, chosen, [a.addr_spec for a in to_a]


# ---------- the calendar ----------

def google_body(invite: dict[str, Any], key: str, response: str) -> dict[str, Any]:
    body: dict[str, Any] = {"id": "inv" + key, "summary": invite["summary"], "status": "tentative" if response == "tentative" else "confirmed",
                            "extendedProperties": {"private": {"enveliq_invite": key}}}
    if invite["all_day"]:
        body["start"], body["end"] = {"date": invite["start_day"]}, {"date": invite["end_day"]}
    else:
        z = invite["tz"] if _zone(invite["tz"]) is not None else "UTC"
        body["start"] = {"dateTime": datetime.fromtimestamp(invite["start"], timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "timeZone": z}
        body["end"] = {"dateTime": datetime.fromtimestamp(invite["end"], timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "timeZone": z}
    if invite["location"]:
        body["location"] = invite["location"]
    if invite["description"]:
        body["description"] = invite["description"][:1000]
    if invite["rrule"] and not invite["recurrence"]:
        body["recurrence"] = ["RRULE:" + invite["rrule"]]
    return body


def calendar_file(invite: dict[str, Any], key: str, response: str, now: float) -> str:
    """The meeting as an .ics file for a CalDAV calendar (no METHOD line: it is an event to keep, not an invitation)."""
    from .calsync import esc
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Enveliq//Invites//EN", "BEGIN:VEVENT", f"UID:{invite['uid']}",
             "DTSTAMP:" + datetime.fromtimestamp(now, timezone.utc).strftime("%Y%m%dT%H%M%SZ"), f"SEQUENCE:{invite['sequence']}"]
    for which in ("DTSTART", "DTEND", "RECURRENCE-ID"):
        text = _ics_time(invite, which)
        if text:
            lines.append(text)
    if invite["all_day"] and not _ics_time(invite, "DTEND"):
        lines.append("DTEND;VALUE=DATE:" + invite["end_day"].replace("-", ""))
    elif not invite["all_day"] and not _ics_time(invite, "DTEND"):
        lines.append("DTEND:" + datetime.fromtimestamp(invite["end"], timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    lines.append("SUMMARY:" + esc(invite["summary"]))
    if invite["location"]:
        lines.append("LOCATION:" + esc(invite["location"]))
    if invite["description"]:
        lines.append("DESCRIPTION:" + esc(invite["description"][:1000]))
    if invite["rrule"] and not invite["recurrence"]:
        lines.append("RRULE:" + invite["rrule"])
    lines += ["STATUS:" + ("TENTATIVE" if response == "tentative" else "CONFIRMED"), "END:VEVENT", "END:VCALENDAR"]
    return "\r\n".join(_fold(ln) for ln in lines) + "\r\n"


# ---------- the person's own answers (nothing else about the meeting is kept) ----------

class State:
    """For each meeting: the answer given, when, and the calendar it was written to. Encrypted in the vault, per person."""

    def __init__(self, vault: Any):
        self.vault = vault

    def _load(self, user: str) -> dict[str, Any]:
        raw = self.vault.get_global("invites:" + user) or {}
        return raw if isinstance(raw, dict) else {}

    def get(self, user: str, key: str) -> dict[str, Any] | None:
        entry = self._load(user).get(key)
        return entry if isinstance(entry, dict) else None

    def put(self, user: str, key: str, **fields: Any) -> None:
        data = self._load(user)
        now = time.time()
        data = {k: v for k, v in data.items() if isinstance(v, dict) and now - float(v.get("at", 0)) < STATE_KEEP_DAYS * 86400}
        data[key] = {**data.get(key, {}), **fields, "at": now}
        for old in sorted(data, key=lambda k: data[k].get("at", 0))[:max(0, len(data) - STATE_MAX)]:
            data.pop(old, None)
        self.vault.set_global("invites:" + user, data)

    def clear(self, user: str) -> None:
        self.vault.set_global("invites:" + user, {})
