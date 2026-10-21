"""The formatted (HTML) part of an email the person writes.

The writing box in Enveliq makes simple HTML (bold, lists, links, colours, pictures). Before it is put into an email, this module rebuilds
it from a short list of allowed tags and settings, so nothing but plain formatting can leave Enveliq, whatever the page sent:

* Scripts, forms, frames, plug-ins, SVG, style sheets and every event handler are dropped.
* Links keep only web and mail addresses. Pictures can only be ones the person added to this message (`cid:` references to the pictures
  sent with it); a picture from the internet cannot be put in, so an email never tells a third party it was opened.
* Style rules keep only a short list of harmless settings (colour, size, alignment, indent), each checked.

The plain-text copy that goes with it is written by the page from the same text. Nothing here is stored.
"""
from __future__ import annotations

import base64
import re
from html import escape
from html.parser import HTMLParser
from typing import Any

MAX_HTML = 1_500_000            # characters of HTML read
MAX_DEPTH = 80
MAX_IMAGES = 12
MAX_IMAGE_BYTES = 6_000_000     # one picture
MAX_IMAGES_TOTAL = 12_000_000   # all pictures together
IMAGE_TYPES = {"image/png": "png", "image/jpeg": "jpeg", "image/gif": "gif", "image/webp": "webp"}

TAGS = {"a", "b", "blockquote", "br", "code", "div", "em", "h1", "h2", "h3", "hr", "i", "img", "li", "ol", "p", "pre", "s", "span", "strike",
        "strong", "sub", "sup", "u", "ul", "del"}
VOID = {"br", "hr", "img"}
DROP_ALL = {"script", "style", "noscript", "template", "iframe", "frame", "frameset", "object", "embed", "applet", "svg", "math", "canvas",
            "audio", "video", "select", "textarea", "button", "datalist", "dialog", "title", "head", "xml", "form", "input", "link", "meta"}

_COLOR = re.compile(r"^(?:#[0-9a-fA-F]{3,8}|rgba?\(\s*\d{1,3}\s*,\s*\d{1,3}\s*,\s*\d{1,3}\s*(?:,\s*[0-9.]{1,5}\s*)?\)|[a-zA-Z]{3,25})$")
_LENGTH = re.compile(r"^-?\d{1,4}(?:\.\d{1,2})?(?:px|pt|em|rem|%)?$")
_FAMILY = re.compile(r"^[A-Za-z0-9 ,'\"\-]{1,120}$")
_WEB = re.compile(r"^https?://[^\s\"'<>\\\x00-\x1f]{4,2000}$", re.I)
_MAIL = re.compile(r"^mailto:[^\s\"'<>\\\x00-\x1f]{3,500}$", re.I)
_CID = re.compile(r"^cid:([A-Za-z0-9._\-]{1,100})$")
_ENUM = {
    "text-align": {"left", "right", "center", "justify", "start", "end"},
    "font-weight": {"normal", "bold", "bolder", "lighter", "400", "500", "600", "700"},
    "font-style": {"normal", "italic"},
    "text-decoration": {"none", "underline", "line-through", "underline line-through", "line-through underline"},
    "list-style-type": {"disc", "circle", "square", "decimal", "lower-alpha", "upper-alpha", "lower-roman", "upper-roman", "none"},
}
_COLOR_PROPS = {"color", "background-color"}
_LENGTH_PROPS = {"font-size", "margin-left", "margin-right", "padding-left", "margin", "padding", "margin-top", "margin-bottom", "width", "height",
                 "max-width", "border-width"}


class OutHtmlError(ValueError):
    """A plain, safe-to-show reason the formatted text or a picture was refused."""


def _style(value: str) -> str:
    out = []
    for rule in value.split(";")[:30]:
        name, _, raw = rule.partition(":")
        name, raw = name.strip().lower(), raw.strip()
        if not name or not raw or len(raw) > 200 or "\\" in raw or "/*" in raw or "url(" in raw.lower() or "expression" in raw.lower():
            continue
        if name in _COLOR_PROPS and _COLOR.match(raw):
            out.append(f"{name}:{raw}")
        elif name in _LENGTH_PROPS and _LENGTH.match(raw):
            out.append(f"{name}:{raw}")
        elif name == "font-family" and _FAMILY.match(raw):
            out.append(f"{name}:{raw}")
        elif name in _ENUM and raw.lower() in _ENUM[name]:
            out.append(f"{name}:{raw.lower()}")
        elif name in ("border-left", "border") and re.match(r"^\d{1,2}px (?:solid|dashed|dotted) (?:#[0-9a-fA-F]{3,8}|[a-zA-Z]{3,25})$", raw):
            out.append(f"{name}:{raw}")
    return ";".join(out)


class _Clean(HTMLParser):
    def __init__(self, cids: dict[str, str]) -> None:
        super().__init__(convert_charrefs=True)
        self.cids = cids
        self.out: list[str] = []
        self.stack: list[str] = []
        self.skip = 0
        self.skip_tag = ""

    def _attrs(self, tag: str, attrs: list[tuple[str, str | None]]) -> str:
        keep: list[str] = []
        for name, raw in attrs:
            name, value = name.lower(), (raw or "").strip()
            if name == "style":
                css = _style(value)
                if css:
                    keep.append(f' style="{escape(css, quote=True)}"')
            elif tag == "a" and name == "href" and (_WEB.match(value) or _MAIL.match(value)):
                keep.append(f' href="{escape(value, quote=True)}" rel="noopener noreferrer"')
            elif tag == "img" and name == "src":
                m = _CID.match(value)
                if m and m.group(1) in self.cids:
                    keep.append(f' src="cid:{escape(self.cids[m.group(1)], quote=True)}"')
            elif tag == "img" and name == "alt":
                keep.append(f' alt="{escape(value[:200], quote=True)}"')
            elif tag == "img" and name in ("width", "height") and re.match(r"^\d{1,4}$", value):
                keep.append(f' {name}="{value}"')
            elif tag == "ol" and name == "start" and re.match(r"^\d{1,4}$", value):
                keep.append(f' start="{value}"')
        return "".join(keep)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if self.skip:
            if tag == self.skip_tag:
                self.skip += 1
            return
        if tag in DROP_ALL:
            if tag not in VOID:
                self.skip, self.skip_tag = 1, tag
            return
        if tag not in TAGS:
            return                                  # the tag goes, its text stays
        if tag == "img" and 'src="cid:' not in self._attrs(tag, attrs):
            return                                  # a picture that is not one of this message's own is left out
        if tag in VOID:
            self.out.append(f"<{tag}{self._attrs(tag, attrs)}>")
            return
        if len(self.stack) >= MAX_DEPTH:
            return
        self.stack.append(tag)
        self.out.append(f"<{tag}{self._attrs(tag, attrs)}>")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag.lower() not in VOID and not self.skip:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if self.skip:
            if tag == self.skip_tag:
                self.skip -= 1
            return
        if tag in VOID or tag not in self.stack:
            return
        while self.stack:
            top = self.stack.pop()
            self.out.append(f"</{top}>")
            if top == tag:
                break

    def handle_data(self, data: str) -> None:
        if not self.skip:
            self.out.append(escape(data, quote=False))

    def result(self) -> str:
        while self.stack:
            self.out.append(f"</{self.stack.pop()}>")
        return "".join(self.out)


def clean_html(html: str, cids: dict[str, str] | None = None) -> str:
    """The person's formatted text rebuilt from allowed parts only. [cids] maps a picture's name in the text to its real Content-ID."""
    if len(html) > MAX_HTML:
        raise OutHtmlError("That message is too long to send with its formatting.")
    parser = _Clean(cids or {})
    parser.feed(html)
    parser.close()
    return parser.result()


def check_images(images: list[dict[str, str]]) -> list[tuple[str, str, bytes]]:
    """The pictures sent with a message: (name used in the text, type, content). Refuses anything that is not a real picture."""
    if len(images) > MAX_IMAGES:
        raise OutHtmlError(f"A message can hold at most {MAX_IMAGES} pictures.")
    out: list[tuple[str, str, bytes]] = []
    total = 0
    seen: set[str] = set()
    for item in images:
        name = str(item.get("cid") or "")
        ctype = str(item.get("type") or "").lower()
        if not re.match(r"^[A-Za-z0-9._\-]{1,100}$", name) or name in seen or ctype not in IMAGE_TYPES:
            raise OutHtmlError("A picture in the message could not be used. Remove it and add it again.")
        seen.add(name)
        try:
            data = base64.b64decode(item.get("data", ""), validate=True)
        except Exception:
            raise OutHtmlError("A picture in the message could not be read. Remove it and add it again.") from None
        total += len(data)
        if len(data) > MAX_IMAGE_BYTES or total > MAX_IMAGES_TOTAL:
            raise OutHtmlError("The pictures in this message are too big. Remove one or use a smaller picture.")
        head = data[:12]
        genuine = {"image/png": head.startswith(b"\x89PNG"), "image/jpeg": head.startswith(b"\xff\xd8"),
                   "image/gif": head.startswith(b"GIF8"), "image/webp": head[:4] == b"RIFF" and head[8:12] == b"WEBP"}[ctype]
        if not genuine:
            raise OutHtmlError("A picture in the message is not a real picture file.")
        out.append((name, ctype, data))
    return out


def quote_block_html(head: str, text: str) -> str:
    """The original email under a reply, as a quote: a line saying who wrote it, then their words indented. Plain text, escaped."""
    lines = "<br>".join(escape(line) for line in text.replace("\r\n", "\n").strip("\n").split("\n"))
    return (f'<div style="margin-top:16px">{escape(head)}</div>'
            f'<blockquote style="margin-left:0;padding-left:12px;border-left:2px solid #cccccc;color:#555555">{lines}</blockquote>')


def forward_block_html(head: str, text: str) -> str:
    """The "Forwarded message" block under a forwarded note."""
    head_lines = "<br>".join(escape(line) for line in head.strip("\n").split("\n"))
    lines = "<br>".join(escape(line) for line in text.replace("\r\n", "\n").strip("\n").split("\n"))
    return f'<div style="margin-top:16px;color:#555555">{head_lines}</div><div style="margin-top:8px">{lines}</div>'


def has_content(html: str | None, images: list[Any] | None) -> bool:
    return bool(html and (re.sub(r"<[^>]*>|&nbsp;|\s", "", html) or images))


class _Plain(HTMLParser):
    BLOCK = {"p", "div", "li", "ul", "ol", "blockquote", "h1", "h2", "h3", "pre", "hr"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self.links: list[str] = []
        self.starts: list[int] = []

    def _nl(self) -> None:
        text = "".join(self.out)
        if text and not text.endswith("\n"):
            self.out.append("\n")

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "br":
            self.out.append("\n")
        elif tag == "li":
            self._nl()
            self.out.append("- ")
        elif tag in self.BLOCK:
            self._nl()
        elif tag == "a":
            href = dict(attrs).get("href") or ""
            self.links.append(href if _WEB.match(href) else "")
            self.starts.append(len("".join(self.out)))

    def handle_endtag(self, tag: str) -> None:
        if tag in self.BLOCK:
            self._nl()
        elif tag == "a" and self.starts:
            start, href = self.starts.pop(), self.links.pop()
            label = "".join(self.out)[start:].strip()
            if href and label and label.rstrip("/") != href.rstrip("/") and label != re.sub(r"^https?://", "", href).rstrip("/"):
                self.out.append(f" ({href})")

    def handle_data(self, data: str) -> None:
        self.out.append(data.replace("\xa0", " "))


def to_text(html: str) -> str:
    """The words of formatted text as plain text: lines, "- " for bullets, a link's address after its words."""
    parser = _Plain()
    parser.feed(html)
    parser.close()
    return re.sub(r"\n{3,}", "\n\n", "".join(parser.out)).strip("\n")
