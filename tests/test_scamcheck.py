"""The "Be careful" flag: plain code that compares what an email says with what it does. No AI decides anything here."""
from __future__ import annotations

import email
import json
from email import policy

import pytest

from backend.mail import scamcheck
from fake_bridge import FakeBridge, raw_email
from helpers import load_app, setup_admin
from test_bridge import add_account
from test_llm import FakeModel

ME = "me@example.invalid"
HTML = "MIME-Version: 1.0\r\nContent-Type: text/html; charset=utf-8\r\n"


def msg(html: str = "", sender: str = "Shop <a@shop.example>", extra: str = ""):
    raw = f"From: {sender}\r\nTo: {ME}\r\nSubject: x\r\n{extra}{HTML}\r\n{html}"
    return email.message_from_bytes(raw.encode(), policy=policy.default)


def codes(m) -> list[str]:
    return [r["code"] for r in (scamcheck.from_whole(m) or {"reasons": []})["reasons"]]


# ---------- the checks ----------

def test_a_link_that_names_a_well_known_site_but_goes_elsewhere_is_flagged():
    assert codes(msg('<a href="https://evil.example/x?token=SECRET">www.paypal.com/login</a>')) == ["link_mismatch"]


def test_a_link_to_a_number_address_is_flagged():
    assert codes(msg('<a href="http://203.0.113.9/track">Track my parcel</a>')) == ["number_link"]


def test_lookalike_and_copied_names_are_flagged():
    assert codes(msg('<a href="https://paypa1.example/a">Sign in</a>')) == ["copied_name"]            # a digit one in place of the letter l
    assert codes(msg('<a href="https://dhl-parcel.example/a">Track</a>')) == ["copied_name"]          # the name inside someone else's domain
    assert codes(msg('<a href="https://xn--pypal-4ve.example/a">Sign in</a>')) == ["odd_letters"]    # letters that only pass for ordinary ones


def test_a_sender_name_that_does_not_match_its_address_is_flagged():
    assert codes(msg("hi", sender='"PayPal" <service@gmail.example>')) == ["name_mismatch"]
    assert codes(msg("hi", sender="PayPal <service@paypal.com>")) == []
    assert codes(msg("hi", sender="Amazon <store-news@amazon.co.uk>")) == []


def test_a_failed_sender_check_from_the_providers_own_header_is_flagged():
    assert codes(msg("hi", extra="Authentication-Results: mx.example; dmarc=fail (p=reject)\r\n")) == ["not_confirmed"]
    assert codes(msg("hi", extra="Authentication-Results: mx.example; dmarc=pass\r\n")) == []


def test_ordinary_mail_is_left_alone():
    """Newsletters use tracking links all the time. A flag that cries wolf teaches people to ignore it."""
    html = ('<a href="https://click.esp.example/r/1">www.shop.example/sale</a><a href="https://pineapple.example">Fruit</a>'
            '<a href="https://amzn.to/x">amazon.com</a><a href="https://www.paypal.com/x">paypal.com</a><a href="mailto:a@example.invalid">Write</a>')
    assert scamcheck.from_whole(msg(html)) is None


def test_the_flag_keeps_host_names_only_and_never_more_than_four_reasons():
    html = "".join(f'<a href="https://evil{n}.example/secret/{n}?token=ABC">www.paypal.com</a>' for n in range(10))
    flag = scamcheck.from_whole(msg(html))
    assert len(flag["reasons"]) <= scamcheck.MAX_REASONS
    text = json.dumps(flag)
    assert "secret" not in text and "token" not in text and "ABC" not in text
    assert scamcheck.warning([]) is None and scamcheck.merge(None, []) == []


def test_merging_does_not_repeat_a_reason():
    one = scamcheck.header_reasons(msg("hi", sender='"PayPal" <service@gmail.example>'))
    assert len(scamcheck.merge(one, one)) == 1


def test_a_very_large_or_broken_email_does_not_break_the_check():
    scamcheck.from_whole(msg("<a href=" * 50_000))                     # must simply return, whatever it finds
    assert scamcheck.registrable("a.b.example.co.uk") == "example.co.uk" and scamcheck.registrable("example.com") == "example.com"


# ---------- sync, summaries and View original ----------

@pytest.fixture
def env(tmp_path):
    bridge = FakeBridge(tmp_path)
    bridge.add(1, raw_email("Parcel waiting", "Post <post@example.invalid>", ME, message_id="<s1@example.invalid>", body='<a href="https://evil.example/pay?id=77">www.paypal.com</a>',
                            extra=HTML))
    bridge.add(2, raw_email("Account problem", '"PayPal" <help@gmail.example>', ME, message_id="<s2@example.invalid>",
                            extra="Authentication-Results: mx.example; dmarc=fail\r\n"))
    bridge.add(3, raw_email("Dinner on Friday", "Alice <alice@example.invalid>", ME, message_id="<s3@example.invalid>", body="See you at 7.\n"))
    model = FakeModel()
    (tmp_path / "data").mkdir()
    appm = load_app(tmp_path / "data", ENVELIQ_BRIDGE_CA_FILE=str(bridge.cert_path), ENVELIQ_LLM_URL=model.url, ENVELIQ_LLM_MODEL="test-model")
    client, _ = setup_admin(appm)
    yield client, bridge
    bridge.close()
    model.close()


def listed(client, aid):
    return {m["subject"]: m for m in client.get(f"/api/v1/accounts/{aid}/messages").json()}


def test_sync_flags_what_the_headers_give_away_and_nothing_else(env):
    client, bridge = env
    aid = add_account(client, bridge, settings={"smtp_port": bridge.smtp_port, "send_identities": [], "ai_summaries": True})
    assert client.post(f"/api/v1/accounts/{aid}/sync", json={}).status_code == 200
    got = listed(client, aid)
    assert [r["code"] for r in got["Account problem"]["scam_warning"]["reasons"]] == ["name_mismatch", "not_confirmed"]
    assert got["Dinner on Friday"].get("scam_warning") is None
    assert got["Parcel waiting"].get("scam_warning") is None            # its links are only read when the email itself is opened


def test_view_original_adds_what_the_links_give_away(env):
    client, bridge = env
    aid = add_account(client, bridge, settings={"smtp_port": bridge.smtp_port, "send_identities": [], "ai_summaries": True})
    client.post(f"/api/v1/accounts/{aid}/sync", json={})
    got = listed(client, aid)
    shown = client.get(f"/api/v1/accounts/{aid}/messages/{got['Parcel waiting']['id']}/original").json()
    assert [r["code"] for r in shown["warning"]["reasons"]] == ["link_mismatch"]
    assert "pay?id=77" not in json.dumps(shown["warning"])
    calm = client.get(f"/api/v1/accounts/{aid}/messages/{got['Dinner on Friday']['id']}/original").json()
    assert calm["warning"] is None


def test_summarising_keeps_the_flag_found_in_the_links(env):
    client, bridge = env
    aid = add_account(client, bridge, settings={"smtp_port": bridge.smtp_port, "send_identities": [], "ai_summaries": True})
    client.post(f"/api/v1/accounts/{aid}/sync", json={})
    assert client.post(f"/api/v1/accounts/{aid}/summarise", json={}).status_code == 200
    got = listed(client, aid)
    assert [r["code"] for r in got["Parcel waiting"]["scam_warning"]["reasons"]] == ["link_mismatch"]
    assert [r["code"] for r in got["Account problem"]["scam_warning"]["reasons"]] == ["name_mismatch", "not_confirmed"]   # still there after the summary
    assert got["Dinner on Friday"].get("scam_warning") is None
