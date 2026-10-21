"""Clean up: see the mailing lists that fill the inbox, unsubscribe, archive what is there, archive new ones, or keep them."""
from __future__ import annotations

import json

import pytest

from fake_bridge import raw_email
from helpers import create_user, sign_in
from test_bridge import MAILBOX
from test_summaries import account, start
from backend.mail import senders as senders_mod
from backend.mail.bridge import locator
from backend.mail.senders import SenderBook

UNSUB = "List-Unsubscribe: <https://news.example.com/u/abc?t=1>, <mailto:leave@news.example.com?subject=unsubscribe>\r\n"


def lm(uid, subject, sender, *, unsub=True):
    return uid, raw_email(subject, sender, MAILBOX, message_id=f"<m{uid}@example.invalid>", extra=UNSUB if unsub else "")


@pytest.fixture
def env(tmp_path):
    appm, client, bridge = start(tmp_path, None)
    for uid in list(bridge.messages):
        del bridge.messages[uid]                                    # only the mail this file adds
    rows = [lm(10, "Sale one", "Newsy <news@example.com>"), lm(11, "Sale two", "Newsy <news@example.com>"), lm(12, "Sale three", "Newsy <news@example.com>"),
            lm(20, "Deal one", "Shop <shop@example.net>"), lm(21, "Deal two", "Shop <shop@example.net>"),
            lm(30, "Lunch", "Friend <friend@example.org>", unsub=False), lm(31, "Dinner", "Friend <friend@example.org>", unsub=False),
            lm(32, "Supper", "Friend <friend@example.org>", unsub=False), lm(33, "Brunch", "Friend <friend@example.org>", unsub=False),
            lm(34, "Tea", "Friend <friend@example.org>", unsub=False), lm(35, "Walk", "Friend <friend@example.org>", unsub=False),
            lm(40, "Only once", "Once <once@example.com>"),
            lm(50, "Me to me", f"Me <{MAILBOX}>")]
    for uid, raw in rows:
        bridge.add(uid, raw)
    bridge.messages[10]["flags"].add("\\Seen")                       # one of Newsy's three was opened
    yield appm, client, bridge
    bridge.close()


def listing(client, refresh=True):
    r = client.get("/api/v1/me/senders" + ("?refresh=true" if refresh else ""))
    assert r.status_code == 200, r.text
    return r.json()


def by_address(data):
    return {s["address"]: s for s in data["senders"]}


def test_only_mailing_lists_are_listed_with_their_counts(env):
    _, client, bridge = env
    account(client, bridge, ai=False)
    got = by_address(listing(client))
    assert set(got) == {"news@example.com", "shop@example.net"}               # not the friend (no unsubscribe header), not a single email, not me
    news = got["news@example.com"]
    assert news["count"] == 3 and news["opened"] == 1 and news["name"] == "Newsy"
    assert news["unsubscribe"]["url"] == "https://news.example.com/u/abc?t=1" and news["unsubscribe"]["mailto"] == "leave@news.example.com"
    assert listing(client)["senders"][0]["address"] == "news@example.com"      # busiest first


def test_what_the_page_gets_holds_no_mailbox_numbers_or_email_text(env):
    _, client, bridge = env
    account(client, bridge, ai=False)
    text = json.dumps(listing(client))
    assert "INBOX" not in text and "locator" not in text and "Sale one" not in text and "account_id" not in text


def test_important_people_and_kept_senders_are_never_listed(env):
    appm, client, bridge = env
    account(client, bridge, ai=False)
    assert client.post("/api/v1/me/important", json={"address": "shop@example.net", "name": "Shop"}).status_code == 200
    got = by_address(listing(client))
    assert set(got) == {"news@example.com"}
    sid = got["news@example.com"]["id"]
    assert client.post(f"/api/v1/me/senders/{sid}/keep").status_code == 200
    assert listing(client)["senders"] == [] and listing(client, refresh=False)["kept"] == 1
    assert listing(client)["senders"] == []                                    # still hidden after looking again
    assert client.delete("/api/v1/me/senders/keep").json()["senders"][0]["address"] == "news@example.com"


def test_a_flagged_email_never_offers_an_unsubscribe_address(env):
    _, client, bridge = env
    for uid in (60, 61):
        bridge.add(uid, raw_email("Your parcel", "PayPal <help@parcel-notice.example>", MAILBOX, message_id=f"<p{uid}@example.invalid>", extra=UNSUB))
    account(client, bridge, ai=False)
    row = by_address(listing(client))["help@parcel-notice.example"]
    assert row["flagged"] is True and row["unsubscribe"] is None


def test_archiving_moves_only_that_sender_marks_them_read_and_can_be_undone(env):
    _, client, bridge = env
    account(client, bridge, ai=False)
    sid = by_address(listing(client))["news@example.com"]["id"]
    r = client.post(f"/api/v1/me/senders/{sid}/archive")
    assert r.status_code == 200 and r.json()["archived"] == 3 and r.json()["more"] is False
    assert bridge.in_folder("Archive") == [10, 11, 12]
    assert {"\\Seen"} <= bridge.messages[11]["flags"] and {"\\Seen"} <= bridge.messages[12]["flags"]
    assert 20 in bridge.in_folder("INBOX") and 30 in bridge.in_folder("INBOX")             # nobody else was touched
    assert "news@example.com" not in by_address(r.json())
    token = r.json()["undo"]
    assert token and r.json()["undo_seconds"] == 600
    back = client.post("/api/v1/me/senders/undo", json={"token": token})
    assert back.status_code == 200 and back.json()["restored"] == 3
    assert bridge.in_folder("Archive") == [] or all(bridge.messages[u]["folder"] != "Archive" for u in (10, 11, 12))
    assert set(bridge.in_folder("INBOX")) >= {10, 11, 12}
    assert "\\Seen" in bridge.messages[10]["flags"]                                        # it was opened before, so it stays opened
    assert "\\Seen" not in bridge.messages[11]["flags"] and "\\Seen" not in bridge.messages[12]["flags"]     # unread again, as before
    assert client.post("/api/v1/me/senders/undo", json={"token": token}).status_code == 404             # only once


def test_a_wrong_or_old_undo_does_nothing(env):
    appm, client, bridge = env
    account(client, bridge, ai=False)
    sid = by_address(listing(client))["shop@example.net"]["id"]
    token = client.post(f"/api/v1/me/senders/{sid}/archive").json()["undo"]
    assert client.post("/api/v1/me/senders/undo", json={"token": "not-the-token-at-all"}).status_code == 404
    appm.senderbook.clock = lambda: 10 ** 12                                                # ten minutes pass
    assert client.post("/api/v1/me/senders/undo", json={"token": token}).status_code == 404
    assert bridge.messages[20]["folder"] == "Archive"


def test_one_press_moves_at_most_the_cap_and_says_there_is_more(env, monkeypatch):
    _, client, bridge = env
    account(client, bridge, ai=False)
    monkeypatch.setattr(senders_mod, "CAP", 2)
    sid = by_address(listing(client))["news@example.com"]["id"]
    r = client.post(f"/api/v1/me/senders/{sid}/archive").json()
    assert r["archived"] == 2 and r["more"] is True


def test_email_with_an_open_task_is_left_in_the_inbox():
    class V:
        def get_message(self, account_id, message_id):
            return {"source_locator": locator(7, 11)}
    book = SenderBook(V(), None, None, None, held=lambda user: {("a1", "m1"), ("other", "m2")})
    assert book._protected("u1", {"id": "a1"}) == {11}


def test_always_archive_makes_a_normal_mail_rule(env):
    _, client, bridge = env
    account(client, bridge, ai=False)
    sid = by_address(listing(client))["shop@example.net"]["id"]
    assert client.post(f"/api/v1/me/senders/{sid}/always").status_code == 200
    rules = client.get("/api/v1/me/rules").json()["rules"]
    assert any(r["sender"] == "shop@example.net" and r["action"] == "archived" for r in rules)
    assert client.post(f"/api/v1/me/senders/{sid}/always").status_code == 200              # again: no second rule
    assert len([r for r in client.get("/api/v1/me/rules").json()["rules"] if r["sender"] == "shop@example.net"]) == 1


def test_someone_else_cannot_see_or_use_my_senders(env):
    appm, client, bridge = env
    account(client, bridge, ai=False)
    sid = by_address(listing(client))["news@example.com"]["id"]
    create_user(client, "casey")
    other = sign_in(appm, "casey")
    assert other.get("/api/v1/me/senders?refresh=true").json()["senders"] == []
    for path in ("archive", "keep", "always"):
        assert other.post(f"/api/v1/me/senders/{sid}/{path}").status_code == 404
    assert other.post("/api/v1/me/senders/undo", json={"token": "x" * 16}).status_code == 404
    assert bridge.messages[10]["folder"] == "INBOX"
    assert other.post("/api/v1/me/senders/not-an-id/archive").status_code == 422


def test_clean_up_has_its_own_switch_and_needs_a_signed_in_person(env):
    appm, client, bridge = env
    account(client, bridge, ai=False)
    assert "clean_up" in client.get("/api/v1/me/features").json()["labels"]
    assert client.put("/api/v1/admin/features", json={"clean_up": False}).status_code == 200
    assert client.get("/api/v1/me/senders").status_code == 403
    assert client.put("/api/v1/admin/features", json={"clean_up": True}).status_code == 200
    assert client.put("/api/v1/me/features", json={"clean_up": False}).status_code == 200
    assert client.get("/api/v1/me/senders").status_code == 403
    from fastapi.testclient import TestClient
    assert TestClient(appm.app).get("/api/v1/me/senders").status_code in (401, 403)


def test_only_the_keep_list_is_stored_and_it_goes_with_the_person(env):
    appm, client, bridge = env
    aid = account(client, bridge, ai=False)
    sid = by_address(listing(client))["news@example.com"]["id"]
    client.post(f"/api/v1/me/senders/{sid}/keep")
    user = appm.vault.get_account(aid)["owner_user_id"]
    assert appm.vault.get_global("senders:" + user) == {"kept": ["news@example.com"]}       # no counts, names, subjects or links
    appm.delete_user_data(user)
    assert not (appm.vault.get_global("senders:" + user) or {}).get("kept")
