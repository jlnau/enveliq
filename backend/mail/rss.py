"""News feeds (RSS and Atom) that a person follows.

Each person has their own list of feeds, kept in one encrypted record (`rss:<user id>`). Enveliq fetches each feed now and
then and keeps only a short plain-text version of the newest entries (title, a few lines of text, a link, a date). Nobody
else can see another person's feeds.

A feed is written by a stranger, so everything in it is untrusted: the document is refused if it declares entities or a
document type (the usual XML tricks), every value is cut to a short length, stripped of tags and control characters, and
shown only as plain text. A link is kept only when it is an ordinary web address with no user name in it, and the person's
own browser opens it. Enveliq's own contact with the feed's site goes through the same careful outbound path as other
calls (mail/outbound.py): the address is resolved and pinned, local network addresses need an administrator's allow list,
redirects are followed by hand and checked again each time, and the reply is size-capped.

The first time a feed is read, its entries are the starting point and are not counted as new. Entries that appear later
are new until the person opens the pop-up.
"""
from __future__ import annotations

import hashlib
import html
import logging
import re
import secrets
import threading
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Callable
from urllib.parse import urljoin, urlsplit
from xml.etree import ElementTree as ET

from . import outbound

log = logging.getLogger("enveliq.rss")

RECORD_PREFIX = "rss:"
MAX_FEEDS = 20
MAX_ITEMS = 25                     # entries kept per feed
MAX_BODY = 512 * 1024              # bytes read from a feed
MAX_TEXT = 1500
MAX_TITLE = 200
REFRESH_EVERY = 30 * 60            # each feed is read at most every 30 minutes by the background pass
MANUAL_EVERY = 60                  # "Check now" at most once a minute
MAX_REDIRECTS = 3
MAX_URL = 600
MAX_ERRORS_SHOWN = 160

_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_TAG = re.compile(r"<[^>]*>")
_BREAKS = re.compile(r"(?i)<\s*(br|/p|/div|/li|/h[1-6])\b[^>]*>")
_SPACE = re.compile(r"[ \t\r\f\v]+")
_BLANKS = re.compile(r"\n\s*\n+")
_SCRIPT = re.compile(r"(?is)<(script|style)\b.*?</\1\s*>")


class FeedError(Exception):
    """Something about the feed that can be said to the person in plain words."""


def plain(value: Any, limit: int) -> str:
    """Tags, entities, control characters and extra blank space removed; cut to `limit` characters."""
    text = str(value or "")
    text = _SCRIPT.sub(" ", text)
    text = _BREAKS.sub("\n", text)
    text = _TAG.sub("", text)
    text = html.unescape(text)
    text = _TAG.sub("", text)                  # entities can hide a second layer of tags
    text = _CONTROL.sub("", text)
    text = _SPACE.sub(" ", text)
    text = "\n".join(line.strip() for line in text.split("\n"))
    text = _BLANKS.sub("\n\n", text).strip()
    if len(text) > limit:
        text = text[: limit - 1].rstrip() + "…"
    return text


def safe_link(value: Any, base: str = "") -> str:
    raw = str(value or "").strip()
    if not raw or len(raw) > MAX_URL * 2:
        return ""
    try:
        full = urljoin(base, raw) if base else raw
        parts = urlsplit(full)
    except ValueError:
        return ""
    if parts.scheme not in ("http", "https") or not parts.hostname or parts.username or parts.password:
        return ""
    if _CONTROL.search(full) or " " in full:
        return ""
    return full[:MAX_URL * 2]


def clean_feed_url(value: Any) -> str:
    raw = str(value or "").strip()
    if raw and "://" not in raw:
        raw = "https://" + raw
    if not raw or len(raw) > MAX_URL or _CONTROL.search(raw) or " " in raw:
        raise FeedError("Paste the web address of the feed. It usually starts with https://")
    try:
        parts = urlsplit(raw)
        parts.port
    except ValueError:
        raise FeedError("Paste the web address of the feed. It usually starts with https://") from None
    if parts.scheme not in ("http", "https") or not parts.hostname or parts.username or parts.password:
        raise FeedError("Use a web address that starts with https:// and has no user name in it.")
    return raw


# ---------- reading a feed document ----------

def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower() if isinstance(tag, str) else ""


def _child_text(node: ET.Element, *names: str) -> str:
    for child in node:
        if _local(child.tag) in names:
            return "".join(child.itertext()) if len(child) else (child.text or "")
    return ""


def _when(text: str) -> float | None:
    text = (text or "").strip()
    if not text:
        return None
    try:
        stamp = parsedate_to_datetime(text)
    except (TypeError, ValueError, IndexError):
        try:
            stamp = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    try:
        return stamp.timestamp()
    except (OverflowError, OSError, ValueError):
        return None


def _atom_link(node: ET.Element) -> str:
    best = ""
    for child in node:
        if _local(child.tag) != "link":
            continue
        rel = (child.get("rel") or "alternate").lower()
        href = child.get("href") or ""
        if rel == "alternate" and href:
            return href
        if not best and href:
            best = href
    return best


def parse_feed(data: bytes, base: str, now: float) -> dict[str, Any]:
    """{'title': str, 'items': [{'key', 'title', 'text', 'link', 'at'}]} from RSS 2.0 or Atom, or raise FeedError."""
    head = data[:4096].lower()
    if b"<!doctype" in head or b"<!entity" in data.lower():
        raise FeedError("That feed uses features Enveliq does not accept, so it was not added.")
    try:
        root = ET.fromstring(data)
    except (ET.ParseError, ValueError):
        raise FeedError("That address did not give a news feed. Check it and try again.") from None
    kind = _local(root.tag)
    if kind == "rss":
        channel = next((c for c in root if _local(c.tag) == "channel"), None)
        if channel is None:
            raise FeedError("That address did not give a news feed. Check it and try again.")
        entries = [c for c in channel if _local(c.tag) == "item"]
        title = _child_text(channel, "title")
        scope = channel
    elif kind == "feed":
        entries = [c for c in root if _local(c.tag) == "entry"]
        title = _child_text(root, "title")
        scope = root
    elif kind == "rdf":
        entries = [c for c in root if _local(c.tag) == "item"]
        title = _child_text(next((c for c in root if _local(c.tag) == "channel"), root), "title")
        scope = root
    else:
        raise FeedError("That address did not give a news feed. Check it and try again.")
    site = safe_link(_atom_link(scope) if kind == "feed" else _child_text(scope, "link"), base) or base
    items = []
    for node in entries[: MAX_ITEMS * 2]:
        link = safe_link(_atom_link(node) if kind == "feed" else (_child_text(node, "link") or _child_text(node, "guid")), site)
        body = _child_text(node, "encoded", "content", "description", "summary")
        head_line = plain(_child_text(node, "title"), MAX_TITLE)
        text = plain(body, MAX_TEXT)
        if not head_line and not text:
            continue
        ident = _child_text(node, "guid", "id").strip() or link or head_line
        key = hashlib.sha256(ident.encode("utf-8", "replace")).hexdigest()[:20]
        at = _when(_child_text(node, "pubdate", "published", "updated", "date")) or now
        items.append({"key": key, "title": head_line or "(no title)", "text": text, "link": link, "at": min(at, now + 86400)})
    return {"title": plain(title, MAX_TITLE), "items": items[:MAX_ITEMS]}


# ---------- the book ----------

class RssBook:
    def __init__(self, vault: Any, clock: Callable[[], float] = time.time, fetcher: Callable[[str], bytes] | None = None):
        self.vault = vault
        self.clock = clock
        self.fetcher = fetcher
        self._lock = threading.RLock()

    # storage
    def _load(self, user_id: str) -> dict[str, Any]:
        raw = self.vault.get_global(RECORD_PREFIX + user_id) or {}
        feeds = raw.get("feeds") if isinstance(raw.get("feeds"), dict) else {}
        return {"feeds": feeds}

    def _save(self, user_id: str, book: dict[str, Any]) -> None:
        self.vault.set_global(RECORD_PREFIX + user_id, book)

    def enabled(self, user_id: str | None) -> bool:
        if not user_id:
            return False
        from . import features
        return bool(features.effective(self.vault, user_id).get("rss"))

    # fetching
    def fetch(self, url: str) -> tuple[bytes, str]:
        """(document, final address). Redirects are followed by hand, each checked again."""
        if self.fetcher:
            return self.fetcher(url), url
        allow = outbound.listed(self.vault)
        headers = {"Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml;q=0.9, */*;q=0.5"}
        current = url
        for _ in range(MAX_REDIRECTS + 1):
            try:
                status, reply, data = outbound.request_full("GET", current, allow=allow, headers=headers, max_bytes=MAX_BODY)
            except outbound.OutboundError as err:
                raise FeedError(err.message) from None
            if status in (301, 302, 303, 307, 308):
                where = safe_link(reply.get("location", ""), current)
                if not where:
                    raise FeedError("That address sent Enveliq somewhere it will not go.")
                current = where
                continue
            if status != 200:
                raise FeedError(f"That site answered with an error ({status}).")
            return data, current
        raise FeedError("That address keeps sending Enveliq somewhere else.")

    def _read(self, url: str) -> tuple[dict[str, Any], str]:
        data, final = self.fetch(url)
        return parse_feed(data[:MAX_BODY], final, self.clock()), final

    # changes
    def add_feed(self, user_id: str, url: str) -> dict[str, Any]:
        url = clean_feed_url(url)
        with self._lock:
            book = self._load(user_id)
            if len(book["feeds"]) >= MAX_FEEDS:
                raise FeedError("You follow a lot of feeds already. Remove one first.")
            if any(f.get("url") == url for f in book["feeds"].values()):
                raise FeedError("You already follow that feed.")
        parsed, final = self._read(url)                  # network outside the lock
        now = self.clock()
        with self._lock:
            book = self._load(user_id)
            if len(book["feeds"]) >= MAX_FEEDS:
                raise FeedError("You follow a lot of feeds already. Remove one first.")
            if any(f.get("url") == url for f in book["feeds"].values()):
                raise FeedError("You already follow that feed.")
            fid = "r" + secrets.token_hex(8)
            name = parsed["title"] or (urlsplit(final).hostname or "Feed")
            book["feeds"][fid] = {"id": fid, "url": url, "title": name, "added": now, "checked": now, "error": "",
                                  "items": [{**i, "unread": False} for i in parsed["items"]]}
            self._save(user_id, book)
        return self.view(user_id)

    def remove_feed(self, user_id: str, feed_id: str) -> dict[str, Any]:
        with self._lock:
            book = self._load(user_id)
            if feed_id not in book["feeds"]:
                raise KeyError(feed_id)
            del book["feeds"][feed_id]
            self._save(user_id, book)
        return self.view(user_id)

    def _merge(self, feed: dict[str, Any], parsed: dict[str, Any], now: float) -> None:
        known = {i["key"] for i in feed.get("items", [])}
        fresh = [{**i, "unread": True} for i in parsed["items"] if i["key"] not in known]
        keep = {i["key"]: i for i in parsed["items"]}
        old = [i for i in feed.get("items", []) if i["key"] in keep]          # still listed by the site
        merged = fresh + old
        merged.sort(key=lambda i: i.get("at") or 0, reverse=True)
        feed["items"] = merged[:MAX_ITEMS]
        if parsed["title"]:
            feed["title"] = parsed["title"]
        feed["checked"] = now
        feed["error"] = ""

    def refresh_one(self, user_id: str, feed_id: str) -> None:
        with self._lock:
            feed = self._load(user_id)["feeds"].get(feed_id)
            if not feed:
                return
            url = feed["url"]
        try:
            parsed, _ = self._read(url)
            error = ""
        except FeedError as err:
            parsed, error = None, str(err)[:MAX_ERRORS_SHOWN]
        now = self.clock()
        with self._lock:
            book = self._load(user_id)
            feed = book["feeds"].get(feed_id)
            if not feed:
                return
            if parsed is not None:
                self._merge(feed, parsed, now)
            else:
                feed["checked"] = now
                feed["error"] = error
            self._save(user_id, book)

    def refresh(self, user_id: str, *, force: bool = False) -> dict[str, Any]:
        now = self.clock()
        with self._lock:
            feeds = list(self._load(user_id)["feeds"].values())
        for feed in feeds:
            wait = MANUAL_EVERY if force else REFRESH_EVERY
            if now - float(feed.get("checked") or 0) >= wait:
                self.refresh_one(user_id, feed["id"])
        return self.view(user_id)

    def mark_seen(self, user_id: str) -> dict[str, Any]:
        with self._lock:
            book = self._load(user_id)
            changed = False
            for feed in book["feeds"].values():
                for item in feed.get("items", []):
                    if item.get("unread"):
                        item["unread"] = False
                        changed = True
            if changed:
                self._save(user_id, book)
        return self.view(user_id)

    # reading
    def view(self, user_id: str) -> dict[str, Any]:
        book = self._load(user_id)
        feeds, new = [], 0
        for feed in sorted(book["feeds"].values(), key=lambda f: float(f.get("added") or 0)):
            items = [{"title": i["title"], "text": i.get("text", ""), "link": i.get("link", ""), "at": i.get("at"), "new": bool(i.get("unread"))}
                     for i in feed.get("items", [])]
            count = sum(1 for i in items if i["new"])
            new += count
            feeds.append({"id": feed["id"], "title": feed.get("title") or feed.get("url"), "url": feed["url"], "checked": feed.get("checked"),
                          "error": feed.get("error") or "", "new": count, "items": items})
        return {"enabled": self.enabled(user_id), "new": new, "feeds": feeds, "max_feeds": MAX_FEEDS}

    def count_new(self, user_id: str) -> int:
        return sum(1 for f in self._load(user_id)["feeds"].values() for i in f.get("items", []) if i.get("unread"))


class RssRefresher:
    """Reads every person's feeds in the background, a few at a time, while the vault is unlocked."""

    def __init__(self, vault: Any, book: RssBook):
        self.vault, self.book = vault, book
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread:
            return
        self._thread = threading.Thread(target=self._run, name="enveliq-rss", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def tick(self) -> None:
        for user_id in [u["id"] for u in self.vault.list_users() if not u.get("disabled")]:
            if self._stop.is_set():
                return
            if self.book.enabled(user_id):
                self.book.refresh(user_id)

    def _run(self) -> None:
        while not self._stop.wait(300):
            try:
                self.tick()
            except Exception:
                log.warning("feed pass failed")
