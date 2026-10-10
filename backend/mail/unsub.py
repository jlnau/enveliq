"""Finding the "unsubscribe" link of a newsletter, so the page can show it as a button.

Newsletters are meant to carry a List-Unsubscribe header (RFC 2369). Enveliq reads that first. When there is none, it looks for a
link in the message body whose words say "unsubscribe" or "opt out". Enveliq never opens the link itself: it hands the address to the
person's own browser when they press the button.

An email is written by a stranger, so the address is treated as hostile. Only a plain http(s) address with a real public host name is
accepted. A link to an address inside a home or office network (192.168.x.x, localhost, .local) is dropped, because opening it
from the person's browser could change a setting on their own router.
"""
from __future__ import annotations

import ipaddress
import re
from email.message import Message
from html.parser import HTMLParser
from typing import Any
from urllib.parse import parse_qs, unquote, urlsplit

_CONTROL = re.compile(r"[\x00-\x20\x7f-\x9f\"'<>\\^`{|}]")
_ANGLE = re.compile(r"<([^<>]{1,2100})>")
_ADDRESS = re.compile(r"^[A-Za-z0-9._%+\-]{1,64}@[A-Za-z0-9.\-]{1,253}\.[A-Za-z]{2,63}$")
_WORDS = re.compile(r"unsubscri|opt[\s\-_]?out|stop receiving|remove me|email preferences|manage (?:your )?(?:email )?(?:subscription|preferences)", re.I)
_TEXT_URL = re.compile(r"https?://[^\s<>\"')\]]{4,2000}", re.I)
MAX_URL = 2000
_PRIVATE_SUFFIXES = (".local", ".localdomain", ".internal", ".lan", ".home", ".corp", ".intranet", ".home.arpa")


def safe_url(value: str) -> str | None:
    """The address if it is a plain public http(s) link, otherwise None."""
    text = (value or "").strip()
    if not 8 <= len(text) <= MAX_URL or _CONTROL.search(text):
        return None
    try:
        parts = urlsplit(text)
        host = (parts.hostname or "").lower().rstrip(".")
        port = parts.port
    except ValueError:
        return None
    if parts.scheme not in ("http", "https") or not host or parts.username is not None or parts.password is not None:
        return None
    if port is not None and port not in (80, 443, 8080, 8443):
        return None
    try:
        ip = ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        ip = None
    if ip is not None:
        return None                                   # a bare number is never a newsletter
    if "." not in host or host.endswith(_PRIVATE_SUFFIXES) or host == "localhost" or not re.fullmatch(r"[a-z0-9.\-_]+", host):
        return None
    if any(not label or len(label) > 63 for label in host.split(".")):
        return None
    return text


def safe_mailto(value: str) -> tuple[str, str] | None:
    """(address, subject) from a mailto: link. Only the address and a subject are used; a body, Cc or any other part is dropped."""
    text = (value or "").strip()
    if not text.lower().startswith("mailto:") or len(text) > 600 or re.search(r"[\x00-\x1f\x7f]", text):
        return None
    rest = text[7:]
    address, _, query = rest.partition("?")
    address = unquote(address).strip()
    if not _ADDRESS.match(address):
        return None
    subject = ""
    try:
        subject = (parse_qs(query).get("subject") or [""])[0]
    except ValueError:
        subject = ""
    subject = re.sub(r"[\x00-\x1f\x7f]", " ", subject).strip()[:200]
    return address, subject


def _result(url: str | None, mailto: tuple[str, str] | None, source: str) -> dict[str, Any] | None:
    if not url and not mailto:
        return None
    host = (urlsplit(url).hostname or "").lower() if url else mailto[0].rsplit("@", 1)[1].lower()
    return {"url": url, "mailto": mailto[0] if mailto else None, "subject": (mailto[1] or None) if mailto else None,
            "host": host[:255], "source": source}


def from_header(msg: Message) -> dict[str, Any] | None:
    """From the List-Unsubscribe header: a web address, an email address, or both."""
    try:
        raw = " ".join(str(h) for h in (msg.get_all("List-Unsubscribe", []) or []))
    except Exception:
        return None
    url = mail = None
    for item in _ANGLE.findall(raw[:6000]):
        item = re.sub(r"\s+", "", item)
        if url is None and item.lower().startswith(("http://", "https://")):
            url = safe_url(item)
        elif mail is None and item.lower().startswith("mailto:"):
            mail = safe_mailto(item)
    return _result(url, mail, "header")


class _Links(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.found: list[tuple[str, str]] = []
        self._href: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: Any) -> None:
        if tag == "a":
            self._href = dict(attrs).get("href") or ""
            self._text = []

    def handle_data(self, data: str) -> None:
        if self._href is not None and len(self._text) < 50:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._href is not None:
            self.found.append((self._href, " ".join(self._text)))
            self._href = None
            if len(self.found) > 400:
                self.found = self.found[:400]


def from_body(msg: Message) -> dict[str, Any] | None:
    """From a link in the message whose words say "unsubscribe". The last such link wins, because the real one sits at the foot."""
    html = text = ""
    try:
        for part in msg.walk():
            if part.is_multipart() or part.get_content_disposition() == "attachment":
                continue
            kind = part.get_content_type()
            if kind == "text/html" and not html:
                html = str(part.get_content())[:400_000]
            elif kind == "text/plain" and not text:
                text = str(part.get_content())[:200_000]
    except Exception:
        return None
    best: str | None = None
    if html:
        parser = _Links()
        try:
            parser.feed(html)
            parser.close()
        except Exception:
            pass
        for href, label in parser.found:
            if _WORDS.search(label) or _WORDS.search(unquote(href)[:300]):
                url = safe_url(href)
                if url:
                    best = url
    if best is None and text:
        for line_start in re.finditer(r"(?i)unsubscri|opt[\s\-_]?out", text):
            chunk = text[max(0, line_start.start() - 200): line_start.end() + 300]
            for found in _TEXT_URL.findall(chunk):
                url = safe_url(found.rstrip(".,;"))
                if url:
                    best = url
            if best:
                break
    return _result(best, None, "body") if best else None


def find(msg: Message) -> dict[str, Any] | None:
    """The unsubscribe link of a message: the header if it has one, otherwise a link in the body."""
    return from_header(msg) or from_body(msg)
