"""News feeds: reading RSS and Atom safely, what counts as new, privacy between people, and the routes."""
from __future__ import annotations

import json

import pytest

from test_summaries import start  # noqa: F401
from test_bridge import mails  # noqa: F401
from backend.mail import rss as R

NOW = 1_790_000_000.0

RSS = b"""<?xml version="1.0"?><rss version="2.0"><channel><title>Garden Notes</title><link>https://feeds.example.com/</link>
<item><title>Spring beds</title><link>https://feeds.example.com/spring</link><guid>g1</guid><pubDate>Mon, 12 Oct 2026 08:00:00 GMT</pubDate>
<description>&lt;p&gt;Plant &lt;b&gt;early&lt;/b&gt; this year.&lt;/p&gt;&lt;script&gt;alert(1)&lt;/script&gt;</description></item>
<item><title>Compost</title><link>javascript:alert(1)</link><guid>g2</guid><description>Turn it weekly.</description></item>
</channel></rss>"""

ATOM = b"""<?xml version="1.0" encoding="utf-8"?><feed xmlns="http://www.w3.org/2005/Atom"><title>Harbour Report</title>
<link rel="alternate" href="https://news.example.com/"/>
<entry><title>Tide times</title><id>tag:news.example.com,2026:1</id><link rel="alternate" href="/tides"/><updated>2026-10-12T08:00:00Z</updated><summary>Low at noon.</summary></entry></feed>"""


class FakeVault:
    def __init__(self):
        self.g: dict = {}

    def get_global(self, k):
        return self.g.get(k)

    def set_global(self, k, v):
        self.g[k] = json.loads(json.dumps(v))

    def get_user(self, uid):
        raise KeyError(uid)


def make(docs):
    v = FakeVault()
    clock = {"t": NOW}
    b = R.RssBook(v, clock=lambda: clock["t"], fetcher=lambda url: docs[url])
    b.clock_ = clock
    return b


def test_rss_is_read_as_plain_text_with_safe_links():
    out = R.parse_feed(RSS, "https://feeds.example.com/rss", NOW)
    assert out["title"] == "Garden Notes"
    first, second = out["items"]
    assert first["title"] == "Spring beds" and first["text"] == "Plant early this year." and first["link"] == "https://feeds.example.com/spring"
    assert "<" not in first["text"] and "alert" not in first["text"]
    assert second["link"] == ""                        # javascript: is never kept


def test_atom_is_read_and_relative_links_are_made_whole():
    out = R.parse_feed(ATOM, "https://news.example.com/feed", NOW)
    assert out["title"] == "Harbour Report" and out["items"][0]["link"] == "https://news.example.com/tides" and out["items"][0]["text"] == "Low at noon."


@pytest.mark.parametrize("doc", [b"<!DOCTYPE x [<!ENTITY a 'b'>]><rss/>", b"<!ENTITY a 'b'><rss/>", b"<html></html>", b"not xml", b"<rss></rss>"])
def test_bad_or_dangerous_documents_are_refused(doc):
    with pytest.raises(R.FeedError):
        R.parse_feed(doc, "https://feeds.example.com/", NOW)


def test_long_text_is_cut_and_markup_inside_entities_is_removed():
    assert len(R.plain("x" * 5000, R.MAX_TEXT)) == R.MAX_TEXT
    assert R.plain("&lt;img src=x onerror=alert(1)&gt;hi", 100) == "hi"
    assert R.plain("a\x00b\x1fc", 10) == "abc"


def test_feed_addresses_are_checked():
    assert R.clean_feed_url("feeds.example.com/rss") == "https://feeds.example.com/rss"
    for bad in ("", "ftp://x.example.com/a", "https://user:pw@x.example.com/", "https://x.example.com/a b", "https://x.example.com:99999/"):
        with pytest.raises(R.FeedError):
            R.clean_feed_url(bad)


def test_first_read_is_the_starting_point_and_later_entries_are_new():
    url = "https://feeds.example.com/rss"
    docs = {url: RSS}
    b = make(docs)
    view = b.add_feed("u1", url)
    assert view["new"] == 0 and len(view["feeds"][0]["items"]) == 2
    docs[url] = RSS.replace(b"</channel>", b"<item><title>Pruning</title><guid>g3</guid><description>Now.</description></item></channel>")
    b.clock_["t"] += 3600
    view = b.refresh("u1")
    assert view["new"] == 1 and [i["title"] for i in view["feeds"][0]["items"] if i["new"]] == ["Pruning"]
    assert b.mark_seen("u1")["new"] == 0
    b.clock_["t"] += 3600
    assert b.refresh("u1")["new"] == 0                       # nothing new the second time


def test_a_feed_is_not_read_again_too_soon():
    url = "https://feeds.example.com/rss"
    calls = []
    docs = {url: RSS}
    b = R.RssBook(FakeVault(), clock=lambda: NOW + len(calls) * 0, fetcher=lambda u: (calls.append(u), docs[u])[1])
    b.add_feed("u1", url)
    n = len(calls)
    b.refresh("u1")
    assert len(calls) == n                                   # checked just now


def test_a_feed_that_fails_keeps_its_entries_and_says_why():
    url = "https://feeds.example.com/rss"
    docs = {url: RSS}
    b = make(docs)
    b.add_feed("u1", url)
    docs[url] = b"nonsense"
    b.clock_["t"] += 3600
    view = b.refresh("u1")
    assert view["feeds"][0]["error"] and len(view["feeds"][0]["items"]) == 2


def test_limits_duplicates_and_removal():
    docs = {f"https://f{i}.example.com/rss": RSS for i in range(R.MAX_FEEDS + 1)}
    b = make(docs)
    for i in range(R.MAX_FEEDS):
        b.add_feed("u1", f"https://f{i}.example.com/rss")
    with pytest.raises(R.FeedError):
        b.add_feed("u1", f"https://f{R.MAX_FEEDS}.example.com/rss")
    with pytest.raises(R.FeedError):
        b.add_feed("u1", "https://f0.example.com/rss")
    fid = b.view("u1")["feeds"][0]["id"]
    assert len(b.remove_feed("u1", fid)["feeds"]) == R.MAX_FEEDS - 1
    with pytest.raises(KeyError):
        b.remove_feed("u1", fid)


def test_one_person_never_sees_anothers_feeds():
    url = "https://feeds.example.com/rss"
    b = make({url: RSS})
    b.add_feed("u1", url)
    assert b.view("u2")["feeds"] == []
    with pytest.raises(KeyError):
        b.remove_feed("u2", b.view("u1")["feeds"][0]["id"])


def test_redirects_are_followed_by_hand_and_checked(monkeypatch):
    seen = []

    def fake(method, url, **kw):
        seen.append(url)
        if url == "https://a.example.com/x":
            return 301, {"location": "https://b.example.com/y"}, b""
        if url == "https://b.example.com/y":
            return 200, {}, RSS
        return 301, {"location": "http://192.168.1.5/"}, b""
    monkeypatch.setattr(R.outbound, "request_full", fake)
    b = R.RssBook(FakeVault(), clock=lambda: NOW)
    data, final = b.fetch("https://a.example.com/x")
    assert data == RSS and final == "https://b.example.com/y"
    loop = R.RssBook(FakeVault(), clock=lambda: NOW)
    monkeypatch.setattr(R.outbound, "request_full", lambda *a, **k: (302, {"location": "https://a.example.com/x"}, b""))
    with pytest.raises(R.FeedError):
        loop.fetch("https://a.example.com/x")
    monkeypatch.setattr(R.outbound, "request_full", lambda *a, **k: (500, {}, b""))
    with pytest.raises(R.FeedError):
        loop.fetch("https://a.example.com/x")


def test_the_outbound_path_refuses_local_addresses_without_the_allow_list(monkeypatch):
    b = R.RssBook(FakeVault(), clock=lambda: NOW)
    with pytest.raises(R.FeedError):
        b.fetch("http://192.168.1.50/feed.xml")


# ---------- through the app ----------

@pytest.fixture
def env(tmp_path):
    appm, client, bridge = start(tmp_path, None)
    docs = {"https://feeds.example.com/rss": RSS}
    appm.rssbook.fetcher = lambda url: docs[url]
    yield appm, client, docs
    bridge.close()


def test_the_routes(env):
    appm, client, docs = env
    r = client.post("/api/v1/me/rss/feeds", json={"url": "https://feeds.example.com/rss"})
    assert r.status_code == 201 and r.headers["cache-control"] == "no-store" and r.json()["feeds"][0]["title"] == "Garden Notes"
    assert client.post("/api/v1/me/rss/feeds", json={"url": "https://feeds.example.com/rss"}).status_code == 422
    assert client.post("/api/v1/me/rss/feeds", json={"url": "ftp://x"}).status_code == 422
    assert client.post("/api/v1/me/rss/feeds", json={"url": "https://feeds.example.com/rss", "extra": 1}).status_code == 422
    assert client.get("/api/v1/me/rss").json()["new"] == 0
    assert client.post("/api/v1/me/rss/refresh").status_code == 200
    assert client.post("/api/v1/me/rss/seen").status_code == 200
    fid = client.get("/api/v1/me/rss").json()["feeds"][0]["id"]
    assert client.delete("/api/v1/me/rss/feeds/not-an-id").status_code == 422
    assert client.delete("/api/v1/me/rss/feeds/r" + "0" * 16).status_code == 404
    assert client.delete(f"/api/v1/me/rss/feeds/{fid}").status_code == 200
    assert client.get("/api/v1/me/rss").json()["feeds"] == []


def test_an_unreachable_site_says_so_plainly(env):
    appm, client, _ = env

    def gone(url):
        raise R.FeedError("That address could not be found.")
    appm.rssbook.fetcher = gone
    r = client.post("/api/v1/me/rss/feeds", json={"url": "https://missing.example.com/rss"})
    assert r.status_code == 422 and r.json()["detail"] == "That address could not be found."
    assert client.get("/api/v1/me/rss").json()["feeds"] == []


def test_turned_off_nothing_is_added(env):
    appm, client, _ = env
    assert client.put("/api/v1/me/features", json={"rss": False}).status_code == 200
    assert client.post("/api/v1/me/rss/feeds", json={"url": "https://feeds.example.com/rss"}).status_code == 403
    assert client.get("/api/v1/me/rss").json()["enabled"] is False


def test_the_administrator_can_switch_it_off_for_everyone(env):
    _, client, _ = env
    assert client.put("/api/v1/admin/features", json={"rss": False}).status_code == 200
    assert client.get("/api/v1/me/features").json()["effective"]["rss"] is False


def test_another_person_sees_none_of_it(env):
    from helpers import create_user, sign_in
    appm, client, _ = env
    client.post("/api/v1/me/rss/feeds", json={"url": "https://feeds.example.com/rss"})
    create_user(client, "second")
    other = sign_in(appm, "second")
    assert other.get("/api/v1/me/rss").json()["feeds"] == []
    fid = client.get("/api/v1/me/rss").json()["feeds"][0]["id"]
    assert other.delete(f"/api/v1/me/rss/feeds/{fid}").status_code == 404


def test_it_needs_a_signed_in_person(env):
    from fastapi.testclient import TestClient
    appm, _, _ = env
    anon = TestClient(appm.app)
    assert anon.get("/api/v1/me/rss").status_code in (401, 403)
    assert anon.post("/api/v1/me/rss/feeds", json={"url": "https://feeds.example.com/rss"}).status_code in (401, 403)
    assert anon.post("/api/v1/me/rss/seen").status_code in (401, 403)
