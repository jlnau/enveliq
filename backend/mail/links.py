"""The links in an email, listed so a person can see where each one really goes before opening it.

Nothing here fetches anything. The list is built from the email while it is being read and is never stored. Only plain public web
addresses can be opened (the same rule as the Unsubscribe link); every other link is listed with a short reason and cannot be opened."""
from __future__ import annotations

from email.message import Message
from typing import Any
from urllib.parse import urlsplit
import re

from . import scamcheck, unsub

MAX_LINKS = 30
_BARE = re.compile(r"https?://[^\s<>\"'\)\]]+", re.I)
_TRAIL = ".,;:!?"


def _plain_text(msg: Message) -> str:
    try:
        for part in msg.walk():
            if part.is_multipart() or part.get_content_disposition() == "attachment":
                continue
            if part.get_content_type() == "text/plain":
                return str(part.get_content())[:200_000]
    except Exception:
        pass
    return ""


def _host(href: str) -> str:
    try:
        return (urlsplit(href).hostname or "").lower().rstrip(".")
    except ValueError:
        return ""


def find(msg: Message) -> list[dict[str, Any]]:
    """Up to MAX_LINKS web links: ``label`` (what the email says), ``host`` (where it really goes), ``url`` (only when it may be opened),
    ``note`` (plain words, only when something looks off or the link cannot be opened)."""
    pairs = list(scamcheck._anchors(msg))
    for raw in _BARE.findall(_plain_text(msg))[:200]:
        pairs.append((raw.rstrip(_TRAIL), ""))
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for href, label in pairs:
        href = (href or "").strip()
        if not href.lower().startswith(("http://", "https://")) or href in seen:
            continue
        seen.add(href)
        host = _host(href)
        if not host:
            continue
        reason = scamcheck.link_reason(href, label)
        url = unsub.safe_url(href)
        note = reason["text"] if reason else ""
        if not url:
            note = note or "This link cannot be opened from here."
        shown = " ".join((label or "").split())[:80]
        out.append({"label": shown if shown and shown.lower() != href.lower() else "", "host": host[:100], "url": url, "note": note[:300], "flagged": bool(reason)})
        if len(out) >= MAX_LINKS:
            break
    return out
