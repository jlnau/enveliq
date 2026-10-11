"""Forward to check: one plain line back for an email a person forwards, and nothing for anyone else. Plain code; no AI, nothing stored."""
from __future__ import annotations

import email
from email import policy
from email.message import EmailMessage

import pytest

from backend.mail import checkbox as C
from backend.mail.errors import BridgeError
from fake_bridge import FakeBridge, raw_email
from helpers import load_app, setup_admin
from test_bridge import MAILBOX, add_account

FRIEND = "friend@example.invalid"
BAD_HTML = '<a href="https://evil.example/pay">www.paypal.com/login</a>'


def forwarded(sender: str = FRIEND, html: str | None = BAD_HTML, extra: dict[str, str] | None = None, text: str = "Is this real?") -> bytes:
    outer = EmailMessage()
    outer["From"], outer["To"], outer["Subject"], outer["Message-ID"] = sender, MAILBOX, "Fwd: parcel", "<f1@example.invalid>"
    for k, v in (extra or {}).items():
        outer[k] = v
    outer.set_content(text)
    if html is not None:
        inner = EmailMessage()
        inner["From"], inner["To"], inner["Subject"] = "Shop <a@shop.example>", FRIEND, "Parcel"
        inner.set_content("hi")
        inner.add_alternative(html, subtype="html")
        outer.add_attachment(inner)
    return outer.as_bytes()


def head(raw: bytes):
    return email.message_from_bytes(raw, policy=policy.default)


# ---------- the answer ----------

def test_an_odd_forwarded_email_gets_the_reasons_and_never_the_rest_of_a_link():
    line = C.verdict(forwarded())
    assert line.startswith("Be careful: ") and "paypal.com but really goes to evil.example" in line
    assert "pay" not in line.replace("paypal", "")


def test_nothing_odd_never_says_it_is_safe():
    line = C.verdict(forwarded(html='<a href="https://ok.example/x">Read more</a>'))
    assert line == C.SAFE and "does not prove it is safe" in line


def test_an_email_that_was_not_attached_is_checked_by_its_links_only_and_says_so():
    assert C.verdict(forwarded(html=None, text="see https://ok.example/x")) == C.LINKS_ONLY
    assert C.verdict(forwarded(html=None, text="see http://203.0.113.9/x")).startswith("Be careful: ")
    assert C.verdict(forwarded(html=None)) == C.NOTHING


def test_the_forwarders_own_headers_are_not_judged():
    """The person who forwarded it is not the sender being checked."""
    raw = forwarded(sender='"PayPal" <friend@example.invalid>', html='<a href="https://ok.example/x">x</a>')
    assert C.verdict(raw) == C.SAFE


# ---------- who is answered ----------

def test_the_allow_list_is_tidy_and_strict():
    assert C.clean_allowed([" Friend@Example.invalid ", "friend@example.invalid", ""]) == ["friend@example.invalid"]
    with pytest.raises(ValueError):
        C.clean_allowed(["not an address"])
    with pytest.raises(ValueError):
        C.clean_allowed([f"a{n}@example.invalid" for n in range(C.MAX_ALLOWED + 1)])


def box():
    return C.CheckBox(vault=None, service=None, clock=lambda: 1_000.0)


def test_only_a_listed_person_is_answered_and_robots_never_are():
    b, allowed = box(), [FRIEND]
    ok = lambda raw: b.eligible(head(raw), "check@example.invalid", allowed)
    assert ok(forwarded()) == FRIEND
    assert ok(forwarded(sender="stranger@example.invalid")) is None
    assert ok(forwarded(extra={"Auto-Submitted": "auto-replied"})) is None            # another robot: never start a loop
    assert ok(forwarded(extra={"Precedence": "bulk"})) is None
    assert ok(forwarded(extra={"List-Id": "<news.example.invalid>"})) is None
    assert ok(forwarded(extra={"Authentication-Results": "mx.example; dmarc=fail"})) is None      # a forged sender is not answered
    assert b.eligible(head(forwarded(sender="check@example.invalid")), "check@example.invalid", ["check@example.invalid"]) is None   # never itself


def test_each_person_and_the_whole_address_have_a_daily_limit():
    b = box()
    assert all(b._allow(FRIEND, 1_000.0 + n) for n in range(C.PER_PERSON_DAY))
    assert not b._allow(FRIEND, 1_100.0)
    assert b._allow(FRIEND, 1_000.0 + 86_401 + C.PER_PERSON_DAY)                 # a day later it works again
    b = box()
    assert all(b._allow(f"p{n}@example.invalid", 1_000.0) for n in range(C.PER_ADDRESS_DAY))
    assert not b._allow("one-more@example.invalid", 1_000.0)


def test_the_reply_is_one_line_marked_automatic():
    r = C.CheckBox.reply("check@example.invalid", FRIEND, head(forwarded()), "Nothing odd found. That does not prove it is safe.")
    assert r["Auto-Submitted"] == "auto-replied" and r["To"] == FRIEND and r["Subject"] == "Re: Fwd: parcel" and r["In-Reply-To"] == "<f1@example.invalid>"
    assert r.get_content().strip() == "Nothing odd found. That does not prove it is safe."


# ---------- the check mailbox, end to end ----------

@pytest.fixture
def env(tmp_path):
    bridge = FakeBridge(tmp_path)
    bridge.add(1, forwarded())
    bridge.add(2, forwarded(sender="stranger@example.invalid"))
    bridge.add(3, forwarded(extra={"Auto-Submitted": "auto-replied"}))
    (tmp_path / "data").mkdir()
    appm = load_app(tmp_path / "data", ENVELIQ_BRIDGE_CA_FILE=str(bridge.cert_path))
    client, _ = setup_admin(appm)
    yield appm, client, bridge
    bridge.close()


def choose(client, aid, allowed=(FRIEND,)):
    return client.put("/api/v1/admin/check-address", json={"account_id": aid, "allowed": list(allowed)})


def test_the_check_address_answers_the_listed_person_once_and_nobody_else(env):
    appm, client, bridge = env
    aid = add_account(client, bridge, settings={"smtp_port": bridge.smtp_port, "send_identities": []})
    assert choose(client, aid).status_code == 200
    assert appm.checkbox.run_once() == 1
    assert len(bridge.sent) == 1 and bridge.sent[0]["to"] == [FRIEND]
    reply = email.message_from_bytes(bridge.sent[0]["data"], policy=policy.default)
    assert reply.get_content().strip().startswith("Be careful: ") and reply["Auto-Submitted"] == "auto-replied"
    assert appm.checkbox.run_once() == 0 and len(bridge.sent) == 1               # read mail is not answered twice
    assert all("\\Seen" in bridge.messages[u]["flags"] for u in (1, 2, 3))


def test_nothing_happens_until_an_administrator_chooses_and_lists_someone(env):
    appm, client, bridge = env
    aid = add_account(client, bridge, settings={"smtp_port": bridge.smtp_port, "send_identities": []})
    assert appm.checkbox.run_once() == 0
    choose(client, aid, allowed=())
    assert appm.checkbox.run_once() == 0 and bridge.sent == []


def test_that_mailbox_is_never_read_as_an_inbox(env):
    appm, client, bridge = env
    aid = add_account(client, bridge, settings={"smtp_port": bridge.smtp_port, "send_identities": []})
    choose(client, aid)
    r = client.post(f"/api/v1/accounts/{aid}/sync", json={})
    assert r.status_code == 409 and client.get(f"/api/v1/accounts/{aid}/messages").json() == []
    with pytest.raises(BridgeError) as err:                                    # "All emails" must not list it either
        appm.mail_service.keep_recent(appm.vault, appm.vault.get_account(aid))
    assert err.value.code == "check_address"
    mine = [a for a in client.get("/api/v1/accounts").json() if a["id"] == aid][0]
    assert mine["check_address"] is True
    choose(client, None)
    assert [a for a in client.get("/api/v1/accounts").json() if a["id"] == aid][0]["check_address"] is False


def test_the_settings_are_for_administrators_and_validate_what_they_get(env):
    appm, client, bridge = env
    aid = add_account(client, bridge, settings={"smtp_port": bridge.smtp_port, "send_identities": []})
    assert choose(client, aid, allowed=["nope"]).status_code == 422
    assert choose(client, "0" * 8 + "-0000-4000-8000-" + "0" * 12).status_code == 404            # not one of their own mailboxes
    saved = choose(client, aid, allowed=["Friend@Example.invalid"]).json()
    assert saved["allowed"] == [FRIEND] and saved["account_id"] == aid and [a["id"] for a in saved["accounts"]] == [aid]
    assert "password" not in str(saved)
    from fastapi.testclient import TestClient
    assert TestClient(appm.app).get("/api/v1/admin/check-address").status_code in (401, 403)      # not signed in
