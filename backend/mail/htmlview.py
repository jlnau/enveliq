"""A safe, formatted copy of an email's HTML, for "View original email".

The email stays in the mailbox. This module takes the raw message the server just fetched, rebuilds its HTML from a short list
of allowed tags and settings, and hands back one page. Nothing is stored.

Two layers keep it safe, and either one alone would be enough to stop a script:

1. The rebuild. Scripts, forms, frames, plug-ins, SVG and every event handler are dropped. Links keep only web and mail
   addresses. Style rules lose anything that can load a file or run code.
2. The page is served with its own strict Content-Security-Policy (see `policy`) and is shown by the app in a frame with no
   access to the app (no cookies, no storage, no way to reach the page around it). The only script allowed is one fixed script
   of ours, pinned by its hash; it only tells the app how tall the email is and which link was pressed.

Pictures that travel inside the email are shown. Pictures that live on the internet are not loaded unless the person asks, because
they can tell the sender the email was opened.
"""
from __future__ import annotations

import base64
import email
import hashlib
import re
from email import policy
from html import escape
from html.parser import HTMLParser
from typing import Any
from urllib.parse import unquote

MAX_HTML = 2_000_000          # characters of HTML read
MAX_OUT = 3_000_000           # characters of page written (pictures included)
MAX_INLINE_ONE = 2_500_000    # bytes, one embedded picture
MAX_INLINE_ALL = 6_000_000    # bytes, all embedded pictures together
MAX_DEPTH = 120
PICTURE_TYPES = ("image/png", "image/jpeg", "image/gif", "image/webp")

TAGS = {
    "a", "abbr", "address", "article", "aside", "b", "bdi", "bdo", "big", "blockquote", "body", "br", "caption", "center", "cite", "code",
    "col", "colgroup", "dd", "del", "details", "dfn", "div", "dl", "dt", "em", "figcaption", "figure", "font", "footer", "h1", "h2", "h3",
    "h4", "h5", "h6", "header", "hr", "i", "img", "ins", "kbd", "li", "main", "mark", "nav", "ol", "p", "pre", "q", "s", "samp", "section",
    "small", "span", "strike", "strong", "sub", "summary", "sup", "table", "tbody", "td", "tfoot", "th", "thead", "tr", "tt", "u", "ul", "var",
}
VOID = {"br", "hr", "img", "col"}
# Dropped together with everything inside them.
DROP_ALL = {"script", "noscript", "template", "iframe", "frame", "frameset", "object", "embed", "applet", "svg", "math", "canvas", "audio",
            "video", "select", "textarea", "button", "datalist", "dialog", "title", "xml"}
COMMON = {"class", "style", "dir", "lang", "title", "align", "valign", "width", "height", "bgcolor", "color", "border", "cellpadding",
          "cellspacing", "colspan", "rowspan", "nowrap", "face", "size", "text", "abbr", "scope", "span", "start", "type", "reversed", "value"}
EXTRA = {"img": {"src", "alt"}, "a": {"href"}}

_BAD_CSS = re.compile(r"expression\s*\(|javascript\s*:|vbscript\s*:|behavio(?:u)?r\s*:|-moz-binding|@import|@charset|@namespace|@font-face|@font-feature|image-set\s*\(", re.I)
_URL = re.compile(r"url\(\s*(['\"]?)(.*?)\1\s*\)", re.I | re.S)
_CSS_COMMENT = re.compile(r"/\*.*?\*/", re.S)
_DATA_IMG = re.compile(r"^data:image/(?:png|jpeg|gif|webp);base64,[A-Za-z0-9+/=\s]{1,3500000}$", re.I)
_WEB = re.compile(r"^https?://[^\s\"'<>\\\x00-\x1f]{4,2000}$", re.I)
_MAIL = re.compile(r"^mailto:[^\s\"'<>\\\x00-\x1f]{3,500}$", re.I)
_TEL = re.compile(r"^tel:[0-9+\-().\s]{3,40}$", re.I)
_CID = re.compile(r"^cid:\s*<?([^>\s]{1,300})>?\s*$", re.I)
_POSITION = re.compile(r"(?:^|;)\s*position\s*:\s*(?:fixed|sticky|absolute)", re.I)
_POSITION_ANY = re.compile(r"position\s*:\s*(?:fixed|sticky)", re.I)

# The one script of ours. It never reads the email; it reports the height and the link that was pressed.
SCRIPT = (
    "(function(){var p=window.parent;function h(){var b=document.body;if(!b)return 0;var r=b.getBoundingClientRect(),m=parseFloat(getComputedStyle(b).marginBottom)||0;"
    "return Math.ceil(Math.max(r.bottom+(window.pageYOffset||0)+m,b.scrollHeight))+2}"
    "function s(){p.postMessage({enveliq:'height',height:h()},'*')}"
    "addEventListener('load',s);addEventListener('resize',s);setTimeout(s,300);setTimeout(s,1500);"
    "if(window.ResizeObserver&&document.body){var o=new ResizeObserver(s);o.observe(document.body);o.observe(document.documentElement)}"
    "document.addEventListener('click',function(e){var t=e.target,a=t&&t.closest?t.closest('a[href]'):null;if(!a)return;"
    "e.preventDefault();p.postMessage({enveliq:'link',href:a.href},'*')},true);s()})();"
)
SCRIPT_HASH = "sha256-" + base64.b64encode(hashlib.sha256(SCRIPT.encode()).digest()).decode()

BASE_CSS = ("html{color-scheme:light}html,body{margin:0;padding:0}body{background:#fff;color:#202124;font:15px/1.5 -apple-system,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;"
            "padding:12px;overflow-wrap:anywhere}img{max-width:100%;height:auto}table{max-width:100%}pre{white-space:pre-wrap}"
            "a[href]{color:#1a56c4}[data-blocked]{display:inline-block;min-width:8px;min-height:8px}")


# Last word on the page's own size: the email may not give the page a fixed height or its own scrollbar, or the email would sit in a small box.
GROW_CSS = "html,body{height:auto!important;min-height:0!important;max-height:none!important;overflow:visible!important}"


def policy_header(images: bool) -> str:
    """The Content-Security-Policy of the formatted page. Nothing may load, run or leave unless it is listed here."""
    return ("sandbox allow-scripts; default-src 'none'; script-src '" + SCRIPT_HASH + "'; style-src 'unsafe-inline'; img-src data:" + (" https:" if images else "")
            + "; base-uri 'none'; form-action 'none'; frame-ancestors 'self'")


class Result:
    """What a rebuild found: the page, and how many pictures from the internet were held back."""

    def __init__(self, page: str, blocked: int) -> None:
        self.page, self.blocked = page, blocked


def clean_css(css: str, remote: bool, counter: list[int] | None = None) -> str:
    """Style rules without anything that can load a file from elsewhere or run code. Pictures inside the email (data:) stay."""
    css = _CSS_COMMENT.sub("", css or "")
    if _BAD_CSS.search(css):
        css = _without_bad_rules(css)
    css = _POSITION_ANY.sub("position:static", css)

    def keep(m: re.Match[str]) -> str:
        target = m.group(2).strip()
        if _DATA_IMG.match(target):
            return m.group(0)
        if remote and re.match(r"^https://[^\s\"'<>\\]{4,2000}$", target, re.I):
            return m.group(0)
        if counter is not None and re.match(r"^https?://", target, re.I):
            counter[0] += 1
        return "none"

    return _URL.sub(keep, css).replace("<", "\\3c ")


def _without_bad_rules(css: str) -> str:
    """Drop every rule (or one-line statement such as @import) that holds something not allowed; keep the rest."""
    pieces: list[str] = []
    depth, buf = 0, ""
    for ch in css:
        buf += ch
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth = max(0, depth - 1)
            if depth == 0:
                pieces.append(buf)
                buf = ""
        elif ch == ";" and depth == 0:
            pieces.append(buf)
            buf = ""
    pieces.append(buf)
    return "".join(p for p in pieces if not _BAD_CSS.search(p))


def clean_style_attr(value: str, remote: bool, counter: list[int]) -> str:
    """The inline style of one tag: each setting is kept or dropped on its own."""
    decls = []
    for d in _CSS_COMMENT.sub("", value or "").split(";"):
        d = d.strip()
        if not d or ":" not in d:
            continue
        name = d.split(":", 1)[0].strip().lower()
        if name.startswith(("mso-", "-")) or _BAD_CSS.search(d) or _POSITION.search(";" + d):
            continue
        decls.append(clean_css(d, remote, counter))
    return "; ".join(x for x in decls if x.strip())[:4000]


class _Rebuild(HTMLParser):
    def __init__(self, cids: dict[str, str], remote: bool, no_links: bool = False) -> None:
        super().__init__(convert_charrefs=True)
        self.cids, self.remote, self.no_links = cids, remote, no_links
        self.out: list[str] = []
        self.css: list[str] = []
        self.stack: list[str] = []
        self.skip = 0                 # inside a tag that is dropped with its contents
        self.in_style = False
        self.blocked = [0]
        self.body_attrs = ""
        self.size = 0

    # ----- helpers -----
    def emit(self, text: str) -> None:
        self.size += len(text)
        if self.size <= MAX_OUT:
            self.out.append(text)

    def attrs_for(self, tag: str, attrs: list[tuple[str, str | None]]) -> str:
        allowed = COMMON | EXTRA.get(tag, set())
        parts: list[str] = []
        for name, raw in attrs:
            name = (name or "").lower()
            value = (raw or "")[:4000]
            if name not in allowed or name.startswith("on"):
                continue
            if name == "style":
                value = clean_style_attr(value, self.remote, self.blocked)
                if not value:
                    continue
            elif name == "src":
                value = self.picture(value)
                if value is None:
                    continue
            elif name == "href":
                value = value.strip()
                if not (_WEB.match(value) or _MAIL.match(value) or _TEL.match(value)):
                    continue
            elif name in ("class", "dir", "lang", "title", "face", "type", "scope", "abbr", "text", "value", "start", "align", "valign", "color", "bgcolor"):
                value = re.sub(r"[\x00-\x1f]", "", value)[:200]
            parts.append(f' {name}="{escape(value, quote=True)}"')
        if tag == "a" and any(p.startswith(" href=") for p in parts):
            parts.append(' target="_blank" rel="noopener noreferrer nofollow"')
        return "".join(parts)

    def picture(self, value: str) -> str | None:
        value = value.strip()
        m = _CID.match(value)
        if m:
            return self.cids.get(unquote(m.group(1)).strip("<>").lower())
        if _DATA_IMG.match(value):
            return re.sub(r"\s+", "", value)
        if re.match(r"^https?://", value, re.I):
            if self.remote and re.match(r"^https://[^\s\"'<>\\]{4,2000}$", value, re.I):
                return value
            self.blocked[0] += 1
        return None

    # ----- parser events -----
    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if self.skip:
            if tag in DROP_ALL and tag not in VOID:
                self.skip += 1
            return
        if tag == "style":
            self.in_style = True
            return
        if tag in DROP_ALL:
            self.skip = 1
            return
        if tag not in TAGS:
            return                      # an unknown tag (Outlook's o:p, vector shapes, custom tags): drop the tag, keep what is inside
        if tag == "a" and self.no_links:
            tag, attrs = "span", [(n, v) for n, v in attrs if (n or "").lower() != "href"]      # junk view: a link is just text
        if tag == "body":
            self.body_attrs = self.attrs_for("body", attrs)
            return
        if len(self.stack) >= MAX_DEPTH and tag not in VOID:
            return
        a = self.attrs_for(tag, attrs)
        if tag == "img":
            if " src=" not in a:
                a += " data-blocked=\"1\""
            self.emit(f"<img{a}>")
            return
        if tag in VOID:
            self.emit(f"<{tag}{a}>")
            return
        self.stack.append(tag)
        self.emit(f"<{tag}{a}>")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in DROP_ALL or tag.lower() == "style":
            return                      # "<script/>" opens nothing a browser would close; never let it swallow the rest
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if self.skip:
            if tag in DROP_ALL:
                self.skip -= 1
            return
        if tag == "style":
            self.in_style = False
            return
        if tag in VOID or tag not in TAGS or tag == "body":
            return
        if tag == "a" and self.no_links:
            tag = "span"
        if tag in self.stack:
            while self.stack:
                top = self.stack.pop()
                self.emit(f"</{top}>")
                if top == tag:
                    break

    def handle_data(self, data: str) -> None:
        if self.in_style:
            self.css.append(data)
        elif not self.skip:
            self.emit(escape(data, quote=False))

    def finish(self) -> None:
        while self.stack:
            self.emit(f"</{self.stack.pop()}>")


def html_part(msg: Any) -> str | None:
    """The HTML of the email, or None when it has only plain text."""
    try:
        body = msg.get_body(preferencelist=("html",))
        if body is not None and body.get_content_type() == "text/html":
            return str(body.get_content())[:MAX_HTML]
    except Exception:
        return None
    return None


def has_html(msg: Any) -> bool:
    return html_part(msg) is not None


def embedded_pictures(msg: Any) -> dict[str, str]:
    """Pictures that travel inside the email, ready to show: Content-ID (lower case, no brackets) -> data address."""
    out: dict[str, str] = {}
    total = 0
    try:
        for part in msg.walk():
            if part.is_multipart():
                continue
            ctype = part.get_content_type()
            cid = str(part.get("Content-ID") or "").strip().strip("<>").lower()
            if not cid or ctype not in PICTURE_TYPES:
                continue
            data = part.get_payload(decode=True) or b""
            if not data or len(data) > MAX_INLINE_ONE or total + len(data) > MAX_INLINE_ALL:
                continue
            total += len(data)
            out[cid] = f"data:{ctype};base64," + base64.b64encode(data).decode("ascii")
    except Exception:
        pass
    return out


def render(raw: bytes, remote_images: bool = False, no_links: bool = False) -> Result | None:
    """The formatted page for the raw email, or None when the email has no HTML. With `no_links` nothing in it can be clicked."""
    msg = email.message_from_bytes(raw, policy=policy.default)
    html = html_part(msg)
    if html is None:
        return None
    return rebuild(html, embedded_pictures(msg), remote_images, no_links)


def rebuild(html: str, cids: dict[str, str] | None = None, remote_images: bool = False, no_links: bool = False) -> Result:
    parser = _Rebuild(cids or {}, remote_images, no_links)
    try:
        parser.feed(html[:MAX_HTML])
        parser.close()
    except Exception:
        pass
    parser.finish()
    css = clean_css("".join(parser.css)[:400_000], remote_images, parser.blocked)
    page = ("<!doctype html><html><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
            "<meta name=\"referrer\" content=\"no-referrer\"><style>" + BASE_CSS + "</style><style>" + css + "</style></head>"
            "<body" + parser.body_attrs + ">" + "".join(parser.out) + "<script>" + SCRIPT + "</script></body></html>")
    return Result(page, min(parser.blocked[0], 999))
