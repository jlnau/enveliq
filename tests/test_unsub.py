"""The unsubscribe helper: finds the link of a newsletter, and refuses anything that is not a plain public link."""
from __future__ import annotations

import email
from email import policy

import pytest

from backend.mail import unsub
from backend.mail.parse import render_original, summarise_headers

ME = "me@example.invalid"


def msg(headers: str = "", body: str = "Hello.\n", html: str | None = None):
    if html is None:
        raw = f"From: News <news@example.invalid>\r\nTo: {ME}\r\nSubject: Weekly\r\n{headers}\r\n{body}".encode()
    else:
        raw = (f"From: News <news@example.invalid>\r\nTo: {ME}\r\nSubject: Weekly\r\n{headers}MIME-Version: 1.0\r\n"
               f"Content-Type: text/html; charset=utf-8\r\n\r\n{html}").encode()
    return email.message_from_bytes(raw, policy=policy.default), raw


# ---------- which addresses are accepted ----------

@pytest.mark.parametrize("url", ["https://news.example.invalid/u/abc?x=1", "http://mail.example.org/unsub", "https://a.b.example.net:8443/x"])
def test_plain_public_links_are_accepted(url):
    assert unsub.safe_url(url) == url


@pytest.mark.parametrize("url", [
    "javascript:alert(1)", "data:text/html,<b>x</b>", "ftp://example.org/x", "file:///etc/passwd",
    "https://192.168.1.1/reboot", "http://10.0.0.5/x", "http://127.0.0.1:8765/x", "http://[::1]/x", "http://169.254.169.254/latest",
    "http://localhost/x", "https://router.local/x", "https://nas.home.arpa/x", "https://intranet/x", "https://user:pw@example.org/x",
    "https://example.org:22/x", "https://exa mple.org/x", "https://example.org/\"onmouseover=\"x", "https://example.org/<b>", "https://",
    "https://example.org/" + "a" * 2100, "https://-.example.org./x" + "\x00", "https://" + "a" * 70 + ".example.org/x",
])
def test_anything_else_is_refused(url):
    assert unsub.safe_url(url) is None


def test_mailto_keeps_only_the_address_and_subject():
    assert unsub.safe_mailto("mailto:unsub@example.invalid?subject=Unsubscribe&body=hi&cc=a@b.invalid") == ("unsub@example.invalid", "Unsubscribe")
    assert unsub.safe_mailto("mailto:unsub@example.invalid") == ("unsub@example.invalid", "")
    assert unsub.safe_mailto("mailto:not an address") is None
    assert unsub.safe_mailto("mailto:a@b.invalid,c@d.invalid") is None
    assert unsub.safe_mailto("https://example.org") is None


# ---------- the header ----------

def test_header_with_a_link_and_an_address():
    m, _ = msg("List-Unsubscribe: <mailto:leave@example.invalid?subject=stop>, <https://news.example.invalid/u/1>\r\n")
    assert unsub.from_header(m) == {"url": "https://news.example.invalid/u/1", "mailto": "leave@example.invalid", "subject": "stop",
                                    "host": "news.example.invalid", "source": "header"}


def test_header_with_only_an_address():
    m, _ = msg("List-Unsubscribe: <mailto:leave@example.invalid>\r\n")
    got = unsub.from_header(m)
    assert got["url"] is None and got["mailto"] == "leave@example.invalid" and got["host"] == "example.invalid"


def test_a_header_pointing_inside_the_home_network_is_ignored():
    m, _ = msg("List-Unsubscribe: <http://192.168.1.1/cgi-bin/reboot>\r\n")
    assert unsub.from_header(m) is None
    assert unsub.find(m) is None


def test_no_header_means_none():
    m, _ = msg()
    assert unsub.from_header(m) is None and unsub.find(m) is None


# ---------- the body ----------

def test_link_in_an_html_body_is_found_and_the_footer_one_wins():
    html = ('<p><a href="https://shop.example.invalid/sale">Sale</a></p>'
            '<p><a href="https://shop.example.invalid/prefs?top=1">Unsubscribe</a></p><p>x</p>'
            '<p><a href="https://shop.example.invalid/u/zzz?id=7">Click here to unsubscribe</a></p>')
    m, _ = msg(html=html)
    got = unsub.find(m)
    assert got == {"url": "https://shop.example.invalid/u/zzz?id=7", "mailto": None, "subject": None, "host": "shop.example.invalid", "source": "body"}


def test_link_found_by_its_address_when_the_words_are_a_picture():
    m, _ = msg(html='<a href="https://x.example.invalid/unsubscribe?t=1"><img src="https://x.example.invalid/b.png"></a>')
    assert unsub.find(m)["url"] == "https://x.example.invalid/unsubscribe?t=1"


def test_link_in_a_plain_text_body():
    m, _ = msg(body="Thanks for reading.\n\nTo unsubscribe visit https://news.example.invalid/out/9 any time.\n")
    assert unsub.find(m)["url"] == "https://news.example.invalid/out/9"


def test_unsafe_body_links_are_skipped_not_chosen():
    m, _ = msg(html='<a href="javascript:alert(1)">Unsubscribe</a><a href="http://192.168.1.1/x">Unsubscribe here</a>')
    assert unsub.find(m) is None


def test_header_beats_the_body():
    m, _ = msg("List-Unsubscribe: <https://h.example.invalid/u>\r\n", html='<a href="https://b.example.invalid/u">Unsubscribe</a>')
    assert unsub.find(m)["url"] == "https://h.example.invalid/u"


def test_a_huge_hostile_body_is_handled():
    m, _ = msg(html="<a href='https://x.example.invalid/unsubscribe'>" * 5000 + "unsubscribe")
    unsub.find(m)                                                          # must simply return, not hang or crash


# ---------- through the app's own parsing ----------

def test_summarise_headers_carries_the_header_link_only():
    _, raw = msg("List-Unsubscribe: <https://news.example.invalid/u/1>\r\n", html='<a href="https://b.example.invalid/u">Unsubscribe</a>')
    info = summarise_headers(raw, [ME])
    assert info["unsubscribe"]["url"] == "https://news.example.invalid/u/1" and info["unsubscribe"]["source"] == "header"


def test_render_original_also_finds_a_body_link():
    _, raw = msg(html='<p>Hi</p><a href="https://b.example.invalid/u/5">Unsubscribe</a>')
    got = render_original(raw)["unsubscribe"]
    assert got["url"] == "https://b.example.invalid/u/5" and got["source"] == "body"
