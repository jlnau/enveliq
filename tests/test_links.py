"""The list of links in View original: where each one really goes, and which ones may be opened. Plain code, no AI, nothing fetched or stored."""
from __future__ import annotations

import email
import json
from email import policy

import pytest

from backend.mail import links
from fake_bridge import FakeBridge, raw_email
from helpers import load_app, setup_admin
from test_bridge import add_account
from test_llm import FakeModel

ME = "me@example.invalid"
HTML = "MIME-Version: 1.0\r\nContent-Type: text/html; charset=utf-8\r\n"


def msg(body: str, html: bool = True):
    head = HTML if html else "Content-Type: text/plain; charset=utf-8\r\n"
    return email.message_from_bytes(f"From: a@shop.example\r\nTo: {ME}\r\nSubject: x\r\n{head}\r\n{body}".encode(), policy=policy.default)


def test_each_link_shows_its_real_website_and_what_the_email_calls_it():
    got = links.find(msg('<a href="https://orders.example.com/o/1?token=ABC">View your order</a>'))
    assert got == [{"label": "View your order", "host": "orders.example.com", "url": "https://orders.example.com/o/1?token=ABC", "note": "", "flagged": False}]


def test_an_odd_link_says_why_in_words():
    got = links.find(msg('<a href="https://evil.example/pay">www.paypal.com/login</a>'))
    assert got[0]["flagged"] is True and "paypal.com but really goes to evil.example" in got[0]["note"]


def test_only_plain_public_web_addresses_can_be_opened():
    got = links.find(msg('<a href="http://203.0.113.9/x">a</a><a href="http://192.168.1.5/x">b</a><a href="https://intranet/x">c</a>'
                         '<a href="https://shop.example:9999/x">d</a><a href="https://u:p@shop.example/x">e</a><a href="javascript:alert(1)">f</a>'
                         '<a href="mailto:a@example.invalid">g</a><a href="https://ok.example/x">h</a>'))
    by_host = {g["host"]: g for g in got}
    assert [g["host"] for g in got if g["url"]] == ["ok.example"]
    assert all(g["note"] for g in got if not g["url"])           # each one that cannot be opened says so
    assert "javascript" not in json.dumps(got) and "mailto" not in json.dumps(got)
    assert by_host["203.0.113.9"]["flagged"] is True


def test_the_same_link_is_listed_once_and_bare_addresses_in_plain_text_are_found():
    got = links.find(msg('<a href="https://ok.example/a">one</a><a href="https://ok.example/a">two</a>'))
    assert len(got) == 1
    got = links.find(msg("Track it at https://track.example/p/9, thanks.", html=False))
    assert [g["url"] for g in got] == ["https://track.example/p/9"]


def test_never_more_than_thirty_links_and_a_broken_email_does_not_break_it():
    many = "".join(f'<a href="https://s{n}.example/">x</a>' for n in range(100))
    assert len(links.find(msg(many))) == links.MAX_LINKS
    links.find(msg("<a href=" * 50_000))


@pytest.fixture
def env(tmp_path):
    bridge = FakeBridge(tmp_path)
    bridge.add(1, raw_email("Parcel waiting", "Post <post@example.invalid>", ME, message_id="<l1@example.invalid>", body='<a href="https://evil.example/pay?id=77">www.paypal.com</a>', extra=HTML))
    bridge.add(2, raw_email("Dinner on Friday", "Alice <alice@example.invalid>", ME, message_id="<l2@example.invalid>", body="See you at 7.\n"))
    model = FakeModel()
    (tmp_path / "data").mkdir()
    appm = load_app(tmp_path / "data", ENVELIQ_BRIDGE_CA_FILE=str(bridge.cert_path), ENVELIQ_LLM_URL=model.url, ENVELIQ_LLM_MODEL="test-model")
    client, _ = setup_admin(appm)
    yield client, bridge
    bridge.close()
    model.close()


def test_view_original_lists_the_links_and_keeps_none_of_them(env):
    client, bridge = env
    aid = add_account(client, bridge, settings={"smtp_port": bridge.smtp_port, "send_identities": [], "ai_summaries": True})
    client.post(f"/api/v1/accounts/{aid}/sync", json={})
    got = {m["subject"]: m for m in client.get(f"/api/v1/accounts/{aid}/messages").json()}
    shown = client.get(f"/api/v1/accounts/{aid}/messages/{got['Parcel waiting']['id']}/original").json()
    assert [l["host"] for l in shown["links"]] == ["evil.example"] and shown["links"][0]["flagged"] is True
    assert client.get(f"/api/v1/accounts/{aid}/messages/{got['Dinner on Friday']['id']}/original").json()["links"] == []
    # what is kept for the message holds no link address
    assert "pay?id=77" not in json.dumps(client.get(f"/api/v1/accounts/{aid}/messages").json())
