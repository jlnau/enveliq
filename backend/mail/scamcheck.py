"""A calm "be careful" flag for emails that look like a scam, such as a fake delivery notice or a lookalike bank link.

Everything here is plain code that compares what an email says with what it does. There is no AI in it: the AI never decides
whether something is a scam. The checks are:

  * a link names a well-known website but really goes to another (links that name some other site are not judged, because newsletters
    use tracking links all the time and a flag that cries wolf teaches people to ignore it);
  * a link goes to a bare number (an IP address) instead of a website name;
  * a link goes to a website that copies a well-known name (``paypa1.example``, or a name written with look-alike letters);
  * the sender's name says "PayPal" but the address it came from is somewhere else;
  * the person's own mail provider says it could not confirm who sent the email (a failed DMARC check).

Only host names are ever kept (never a whole link, which can carry a private token), and never any of the email's text.
Words shown to people are plain and never say "this is a scam": they say what looks odd and let the person decide.
"""
from __future__ import annotations

import ipaddress
import re
from email.message import Message
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urlsplit

MAX_REASONS = 4
_LINK_LIMIT = 300
_HTML_LIMIT = 400_000

# Well-known names that scammers copy, with the domains that really belong to them. The list is short on purpose: a name that is
# not here is simply not checked. Add a name only with its real domains (a wrong list would flag honest mail).
BRANDS: dict[str, tuple[str, ...]] = {
    "paypal": ("paypal.com", "paypal.me", "paypal-communication.com"),
    "amazon": ("amazon.com", "amazon.co.uk", "amazon.com.au", "amazon.de", "amazon.ca", "amazon.fr", "amazon.in", "amazon.co.jp", "amazonses.com", "amzn.to", "amzn.com"),
    "apple": ("apple.com", "icloud.com", "me.com", "itunes.com"),
    "microsoft": ("microsoft.com", "office.com", "outlook.com", "live.com", "microsoftonline.com", "office365.com"),
    "google": ("google.com", "gmail.com", "googlemail.com", "youtube.com", "goo.gl", "googleapis.com", "googleusercontent.com", "google-analytics.com", "gstatic.com", "googleadservices.com", "withgoogle.com"),
    "netflix": ("netflix.com",),
    "dhl": ("dhl.com", "dhl.de", "dhl.co.uk", "dhl.com.au", "dhl.fr", "dhl.nl"),
    "fedex": ("fedex.com",),
    "ups": ("ups.com",),
    "usps": ("usps.com", "usps.gov"),
    "auspost": ("auspost.com.au",),
    "royalmail": ("royalmail.com",),
    "evri": ("evri.com",),
    "dpd": ("dpd.com", "dpd.co.uk", "dpd.de"),
}
_LOOKALIKE = str.maketrans({"0": "o", "1": "l", "3": "e", "5": "s", "$": "s", "@": "a"})
_SECOND_LEVEL = {"co", "com", "org", "net", "gov", "edu", "ac", "or", "ne", "go"}
_HOSTLIKE = re.compile(r"^(?:https?://)?(?:www\.)?([a-z0-9][a-z0-9\-]*(?:\.[a-z0-9][a-z0-9\-]*)+)(?::\d+)?(?:[/?#]\S*)?$", re.I)
_DMARC_FAIL = re.compile(r"\bdmarc\s*=\s*fail\b", re.I)


def registrable(host: str) -> str:
    """The part of a host name that belongs to one owner: ``mail.shop.example.com`` gives ``example.com``. There is no public-suffix
    list here, so ``co.uk``-style endings are handled by a short rule; an odd ending only ever makes the check more careful."""
    labels = [x for x in (host or "").lower().strip(".").split(".") if x]
    if len(labels) <= 2:
        return ".".join(labels)
    if len(labels[-1]) == 2 and labels[-2] in _SECOND_LEVEL:
        return ".".join(labels[-3:])
    return ".".join(labels[-2:])


def _host_of(url: str) -> str:
    try:
        return (urlsplit(url.strip()).hostname or "").lower().rstrip(".")
    except ValueError:
        return ""


def _is_ip(host: str) -> bool:
    try:
        ipaddress.ip_address(host.strip("[]"))
        return True
    except ValueError:
        return False


def _owner_of(domain: str) -> str | None:
    """The well-known name that really owns this domain, if any."""
    for brand, domains in BRANDS.items():
        if any(domain == d or domain.endswith("." + d) for d in domains):
            return brand
    return None


def _copied_brand(domain: str) -> str | None:
    """The well-known name this domain imitates, or None. A name only counts when it stands alone as a word of the domain
    (``paypal-login.com``) or is a look-alike spelling of it (``paypa1.com``): ``pineapple.com`` is left alone."""
    if _owner_of(domain):
        return None
    name = domain.rsplit(".", 1)[0] if "." in domain else domain
    if name.endswith((".co", ".com", ".org", ".net")):
        name = name.rsplit(".", 1)[0]
    for token in re.split(r"[\-.]", name):
        fixed = token.translate(_LOOKALIKE).replace("rn", "m").replace("vv", "w")
        for brand in BRANDS:
            if token == brand or fixed == brand:
                return brand
    return None


def _brand_in_name(display: str) -> str | None:
    words = re.split(r"[^a-z0-9]+", (display or "").lower())
    for brand in BRANDS:
        if brand in words:
            return brand
        if brand == "royalmail" and "royal" in words and "mail" in words:
            return brand
        if brand == "auspost" and "australia" in words and "post" in words:
            return brand
    return None


class _Anchors(HTMLParser):
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
        if self._href is not None and len(self._text) < 40:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._href is not None:
            self.found.append((self._href, " ".join(" ".join(self._text).split())))
            self._href = None
            if len(self.found) > _LINK_LIMIT:
                self.found = self.found[:_LINK_LIMIT]


def _anchors(msg: Message) -> list[tuple[str, str]]:
    html = ""
    try:
        for part in msg.walk():
            if part.is_multipart() or part.get_content_disposition() == "attachment":
                continue
            if part.get_content_type() == "text/html":
                html = str(part.get_content())[:_HTML_LIMIT]
                break
    except Exception:
        return []
    if not html:
        return []
    parser = _Anchors()
    try:
        parser.feed(html)
        parser.close()
    except Exception:
        pass
    return parser.found


def _reason(code: str, text: str, key: str) -> dict[str, str]:
    return {"code": code, "text": text[:300], "key": key[:300]}


def header_reasons(msg: Message) -> list[dict[str, str]]:
    """What the headers alone give away: a name that does not match its address, and a failed sender check."""
    found: list[dict[str, str]] = []
    try:
        from .parse import _addresses
        sender = (_addresses(msg, "From") or [("", "")])[0]
    except Exception:
        sender = ("", "")
    display, address = sender
    brand = _brand_in_name(display)
    if brand and "@" in address:
        domain = registrable(address.rsplit("@", 1)[1].lower())
        if _owner_of(domain) != brand:
            found.append(_reason("name_mismatch", f"The sender's name says {brand.capitalize() if brand not in ('dhl', 'ups', 'usps', 'dpd') else brand.upper()}, but the email came from {domain}.", f"name:{brand}:{domain}"))
    try:
        results = " ".join(str(h) for h in (msg.get_all("Authentication-Results", []) or []))[:4000]
    except Exception:
        results = ""
    if _DMARC_FAIL.search(results):
        found.append(_reason("not_confirmed", "Your email provider could not confirm who really sent this.", "dmarc"))
    return found


def link_reasons(msg: Message) -> list[dict[str, str]]:
    """What the links give away. Needs the whole email, so it only runs when the email is already being read."""
    found: list[dict[str, str]] = []
    seen: set[str] = set()
    for href, label in _anchors(msg):
        host = _host_of(href) if href.lower().startswith(("http://", "https://")) else ""
        if not host:
            continue
        domain = registrable(host)
        shown = _HOSTLIKE.match(label.strip()) if label else None
        shown_domain = registrable(shown.group(1).lower()) if shown else ""
        if _is_ip(host):
            code, text, key = "number_link", "A link goes to a number address instead of a website name.", "ip"
        elif host.startswith("xn--") or ".xn--" in host or not host.isascii():
            code, text, key = "odd_letters", f"A link goes to {domain}, which is written with unusual letters that can pass for ordinary ones.", f"odd:{domain}"
        elif shown_domain and shown_domain != domain and _owner_of(shown_domain) and _owner_of(shown_domain) != _owner_of(domain):
            code, text, key = "link_mismatch", f"A link says {shown_domain} but really goes to {domain}.", f"mismatch:{shown_domain}:{domain}"
        elif _copied_brand(domain):
            code, text, key = "copied_name", f"A link goes to {domain}, which copies the name of a well-known company.", f"copy:{domain}"
        else:
            continue
        if key in seen:
            continue
        seen.add(key)
        found.append(_reason(code, text, key))
        if len(found) >= MAX_REASONS:
            break
    return found


def merge(*groups: list[dict[str, Any]] | None) -> list[dict[str, str]]:
    """Several lists of reasons as one, without repeats and never more than MAX_REASONS."""
    merged: list[dict[str, str]] = []
    keys: set[str] = set()
    for group in groups:
        for item in group or []:
            key = str(item.get("key") or item.get("text") or "")
            if not key or key in keys:
                continue
            keys.add(key)
            merged.append({"code": str(item.get("code") or "")[:40], "text": str(item.get("text") or "")[:300], "key": key[:300]})
    return merged[:MAX_REASONS]


def warning(reasons: list[dict[str, Any]] | None) -> dict[str, Any] | None:
    """The flag that is stored with a message and shown by the page, or None when there is nothing to warn about."""
    merged = merge(reasons)
    return {"reasons": merged} if merged else None


def from_headers(msg: Message) -> dict[str, Any] | None:
    return warning(header_reasons(msg))


def from_whole(msg: Message) -> dict[str, Any] | None:
    return warning(merge(header_reasons(msg), link_reasons(msg)))
