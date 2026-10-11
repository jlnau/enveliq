"""Turning raw mail into the small, safe pieces Enveliq uses.

Header parsing reads only what the app needs. Message bodies are rendered to
plain text in memory for "View email"; they are never stored and no HTML,
images, links or scripts from an email are passed on to the browser.
"""
from __future__ import annotations

import email
import re
from email.utils import parsedate_to_datetime
from email import policy
from email.message import Message
from html.parser import HTMLParser
from typing import Any

from ..models import ReplyContext
from . import scamcheck, unsub

_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_ANGLE_ID = re.compile(r"<[^<>\s]{1,994}>")
_MAX_TEXT = 200_000

HEADER_FIELDS = (
    "FROM REPLY-TO TO CC DELIVERED-TO X-ORIGINAL-TO SUBJECT DATE MESSAGE-ID REFERENCES X-ENVELIQ-REMINDER LIST-UNSUBSCRIBE AUTHENTICATION-RESULTS"
)

# Domains used by alias / relay services. A reply to one of these goes to the
# long reverse-alias address exactly as received.
ALIAS_SERVICES = {
    "simplelogin.co": "SimpleLogin",
    "simplelogin.com": "SimpleLogin",
    "aleeas.com": "SimpleLogin",
    "slmail.me": "SimpleLogin",
    "passmail.net": "Proton Pass",
    "passinbox.com": "Proton Pass",
    "pm.me": None,  # a normal Proton address, not an alias service
    "relay.firefox.com": "Firefox Relay",
    "mozmail.com": "Firefox Relay",
    "privaterelay.appleid.com": "Hide My Email",
    "duck.com": "DuckDuckGo Email Protection",
    "anonaddy.com": "addy.io",
    "anonaddy.me": "addy.io",
    "addy.io": "addy.io",
}


def clean(value: Any, limit: int) -> str:
    text = _CONTROL.sub("", str(value or "")).replace("\r", " ").replace("\n", " ").strip()
    return text[:limit]


def parse_headers(raw: bytes) -> Message:
    return email.message_from_bytes(raw[:65_536], policy=policy.default)


def _addresses(msg: Message, name: str) -> list[tuple[str, str]]:
    """(display name, address) pairs from a header; empty on anything odd."""
    out: list[tuple[str, str]] = []
    try:
        for header in msg.get_all(name, []) or []:
            for addr in getattr(header, "addresses", ()):
                if addr.addr_spec:
                    out.append((clean(addr.display_name, 200), addr.addr_spec.strip()))
    except Exception:  # malformed headers are common in the wild
        return out
    return out


def _single(msg: Message, name: str) -> str | None:
    try:
        header = msg.get(name)
    except Exception:
        return None
    if header is None:
        return None
    for addr in getattr(header, "addresses", ()):
        if addr.addr_spec:
            return addr.addr_spec.strip()
    text = clean(header, 320)
    return text or None


def alias_service(address: str | None) -> str | None:
    if not address or "@" not in address:
        return None
    domain = address.rsplit("@", 1)[1].lower()
    for suffix, name in ALIAS_SERVICES.items():
        if domain == suffix or domain.endswith("." + suffix):
            return name
    return None


def sending_identities(account: dict[str, Any]) -> list[str]:
    """Addresses this mailbox may send from: its own address plus any extra
    identities the owner listed in the mailbox settings."""
    out = [str(account.get("email_address") or "").strip()]
    extra = (account.get("settings") or {}).get("send_identities")
    if isinstance(extra, list):
        out += [str(x).strip() for x in extra if isinstance(x, str)]
    seen: set[str] = set()
    result = []
    for item in out:
        if item and item.lower() not in seen and not _CONTROL.search(item):
            seen.add(item.lower())
            result.append(item)
    return result


def _received_at(msg: Message) -> float | None:
    """The Date header as a Unix timestamp, or None if missing or unusable."""
    try:
        stamp = parsedate_to_datetime(clean(msg.get("Date"), 100)).timestamp()
    except (TypeError, ValueError, IndexError, OverflowError):
        return None
    return stamp if 0 <= stamp <= 4_102_444_800 else None


def received_at_of(raw: bytes) -> float | None:
    """The sent date from a block of raw headers."""
    return _received_at(parse_headers(raw))


def summarise_headers(raw: bytes, identities: list[str]) -> dict[str, Any] | None:
    """What Enveliq keeps about an incoming email: who, what subject, and what
    a reply will need. Returns None when there is nobody to reply to *and*
    nothing identifying (junk)."""
    msg = parse_headers(raw)
    sender = (_addresses(msg, "From") or [("", "")])[0]
    reply_to = _single(msg, "Reply-To") or sender[1] or None

    known = {i.lower(): i for i in identities}
    delivered = None
    for name in ("Delivered-To", "X-Original-To"):
        value = _single(msg, name)
        if value and value.lower() in known:
            delivered = known[value.lower()]
            break
    if delivered is None:
        for name in ("To", "Cc"):
            for _, addr in _addresses(msg, name):
                if addr.lower() in known:
                    delivered = known[addr.lower()]
                    break
            if delivered:
                break

    message_id = None
    raw_id = clean(msg.get("Message-ID"), 998)
    found = _ANGLE_ID.search(raw_id)
    if found:
        message_id = found.group(0)
    references = _ANGLE_ID.findall(clean(msg.get("References"), 20_000))[-49:]

    context = None
    if reply_to:
        try:
            context = ReplyContext(
                reply_to=reply_to,
                delivered_to=delivered,
                via_alias=alias_service(reply_to),
                message_id=message_id,
                references=references,
            ).model_dump()
        except ValueError:
            context = None  # unusable address: show the email but offer no reply

    return {
        "subject": clean(msg.get("Subject"), 998) or "(no subject)",
        "sender_display": sender[0] or None,
        "sender_address": sender[1] or None,
        "reply_context": context,
        "message_id": message_id,
        "received_at": _received_at(msg),
        "reminder_mark": clean(msg.get("X-Enveliq-Reminder"), 80) or None,
        "unsubscribe": unsub.from_header(msg),
        "scam_warning": scamcheck.from_headers(msg),
    }


class _TextExtractor(HTMLParser):
    _BLOCK = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "table"}
    _SKIP = {"script", "style", "head", "title"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: Any) -> None:
        if tag in self._SKIP:
            self._skip += 1
        elif tag in self._BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self._SKIP and self._skip:
            self._skip -= 1
        elif tag in self._BLOCK:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self.parts.append(data)


# Marketing and notification emails pad their text with zero-width and other
# invisible characters, and with lines that hold only spaces. They show up as
# huge gaps when the text is displayed plainly. Direction-control characters are
# removed too, so a sender cannot make text read in a misleading order.
_INVISIBLE = re.compile("[\u00ad\u034f\u061c\u115f\u1160\u17b4\u17b5\u180e\u200b-\u200f\u2028\u2029\u202a-\u202e\u2060-\u206f\u3164\ufeff\uffa0]")


def tidy_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\u00a0", " ")
    text = _CONTROL.sub("", _INVISIBLE.sub("", text))
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip("\n")


def html_to_text(html: str) -> str:
    parser = _TextExtractor()
    try:
        parser.feed(html[:2_000_000])
        parser.close()
    except Exception:
        return ""
    text = "".join(parser.parts)
    return re.sub(r"\n{3,}", "\n\n", re.sub(r"[ \t\r\f\v]+", " ", text)).strip()


from .render import can_view  # noqa: E402

PREVIEW_IMAGE_TYPES = {"image/png", "image/jpeg", "image/gif", "image/webp"}
MAX_PARTS = 100


def list_parts(msg: Message) -> list[Message]:
    """The attached or embedded files of an email, in a fixed order, so a number from this list
    always means the same part: anything that is not the text body of the message."""
    out: list[Message] = []
    try:
        for part in msg.walk():
            if part.is_multipart():
                continue
            ctype = part.get_content_type()
            disposition = (part.get_content_disposition() or "").lower()
            if ctype in ("text/plain", "text/html") and disposition != "attachment" and not part.get_filename():
                continue
            if ctype.startswith("message/") and disposition != "attachment":
                continue
            out.append(part)
            if len(out) >= MAX_PARTS:
                break
    except Exception:
        pass
    return out


def part_info(index: int, part: Message) -> dict[str, Any]:
    try:
        payload = part.get_payload(decode=True) or b""
    except Exception:
        payload = b""
    ctype = clean(part.get_content_type(), 127)
    return {"index": index, "filename": clean(part.get_filename() or ("picture" if ctype.startswith("image/") else "attachment"), 255),
            "mime_type": ctype, "size_bytes": len(payload), "inline": bool(part.get("Content-ID")) and (part.get_content_disposition() or "inline") != "attachment",
            "previewable": ctype in PREVIEW_IMAGE_TYPES,
            "viewable": can_view(clean(part.get_filename() or "", 255), ctype)}


def attachment_bytes(raw: bytes, index: int) -> tuple[bytes, str, str] | None:
    """(content, file name, type) of the numbered part, or None."""
    parts = list_parts(email.message_from_bytes(raw, policy=policy.default))
    if not 0 <= index < len(parts):
        return None
    part = parts[index]
    try:
        payload = part.get_payload(decode=True) or b""
    except Exception:
        return None
    info = part_info(index, part)
    return payload, info["filename"], info["mime_type"]


_REMOTE_IMG = re.compile(rb"<img\b[^>]*\bsrc\s*=\s*[\"']?\s*https?:", re.I)


def remote_image_count(msg: Message) -> int:
    count = 0
    try:
        for part in msg.walk():
            if part.get_content_type() == "text/html":
                count += len(_REMOTE_IMG.findall(str(part.get_content()).encode("utf-8", "replace")))
    except Exception:
        pass
    return min(count, 999)


def render_original(raw: bytes) -> dict[str, Any]:
    """Plain-text view of a whole email plus a list of its attachments."""
    msg = email.message_from_bytes(raw, policy=policy.default)
    text = ""
    try:
        body = msg.get_body(preferencelist=("plain", "html"))
        if body is not None:
            content = body.get_content()
            text = content if body.get_content_type() == "text/plain" else html_to_text(content)
    except Exception:
        text = ""
    text = tidy_text(text)
    truncated = len(text) > _MAX_TEXT
    attachments = [part_info(i, p) for i, p in enumerate(list_parts(msg))]
    sender = (_addresses(msg, "From") or [("", "")])[0]
    return {
        "subject": clean(msg.get("Subject"), 998) or "(no subject)",
        "from": {"name": sender[0], "address": sender[1]},
        "to": [{"name": n, "address": a} for n, a in _addresses(msg, "To")[:50]],
        "date": clean(msg.get("Date"), 100),
        "text": text[:_MAX_TEXT],
        "truncated": truncated,
        "attachments": attachments,
        "remote_images": remote_image_count(msg),
        "unsubscribe": unsub.find(msg),
        "warning": scamcheck.from_whole(msg),
    }
