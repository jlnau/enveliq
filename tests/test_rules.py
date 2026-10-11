"""Rules: archive (or mark reviewed) mail from chosen senders as it arrives, for the person who made the rule."""
from __future__ import annotations

from test_bridge import MAILBOX, add_account, env, mails, synced  # noqa: F401  (the shared Bridge fixture)

ALICE = "alice@example.invalid"


def add_rule(client, sender=ALICE, action="archived", subject=""):
    return client.post("/api/v1/me/rules", json={"sender": sender, "subject": subject, "action": action})


def rules(client):
    return client.get("/api/v1/me/rules").json()["rules"]


# ---------- the rules themselves ----------

def test_a_new_person_has_no_rules_and_it_is_never_cached(env):
    _, client, _, _ = env
    r = client.get("/api/v1/me/rules")
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
    assert r.json()["rules"] == [] and set(r.json()["actions"]) == {"archived", "reviewed"}


def test_adding_listing_and_removing_a_rule(env):
    _, client, _, _ = env
    r = add_rule(client, "Alice@Example.invalid", "archived", "  weekly   report ")
    assert r.status_code == 200
    rule = r.json()["rules"][0]
    assert (rule["sender"], rule["subject"], rule["action"]) == (ALICE, "weekly report", "archived") and rule["id"].startswith("u")
    assert len(add_rule(client, ALICE, "archived", "weekly report").json()["rules"]) == 1          # the same rule twice is one rule
    assert len(add_rule(client, ALICE, "reviewed", "weekly report").json()["rules"]) == 2
    r = client.delete(f"/api/v1/me/rules/{rule['id']}")
    assert r.status_code == 200 and len(r.json()["rules"]) == 1
    assert client.delete(f"/api/v1/me/rules/{rule['id']}").status_code == 404


def test_a_whole_website_can_be_a_sender(env):
    _, client, _, _ = env
    assert add_rule(client, "@Example.invalid").json()["rules"][0]["sender"] == "@example.invalid"
    assert add_rule(client, "shop.example.invalid").json()["rules"][1]["sender"] == "@shop.example.invalid"


def test_a_bad_sender_or_action_is_refused_in_plain_words(env):
    _, client, _, _ = env
    for bad in ["", "not an address", "a@b", "x@@example.invalid", "foo bar.com"]:
        r = add_rule(client, bad)
        assert r.status_code == 422 and "email address" in str(r.json()["detail"]), bad
    r = add_rule(client, ALICE, "binned")                  # there is deliberately no rule that bins mail
    assert r.status_code == 422 and "archive it, or mark it reviewed" in str(r.json()["detail"])
    assert add_rule(client, ALICE, "deleted").status_code == 422
    assert client.post("/api/v1/me/rules", json={"sender": ALICE, "action": "archived", "extra": 1}).status_code == 422
    assert rules(client) == []


def test_there_is_a_limit_on_rules(env):
    appm, client, _, _ = env
    from backend.mail.rules import MAX_RULES
    me = client.get("/api/v1/me").json()["id"]
    appm.vault.set_global("rules:" + me, {"rules": [{"id": f"u{n:016x}", "sender": f"p{n}@example.invalid", "subject": "", "action": "archived"} for n in range(MAX_RULES)]})
    r = add_rule(client, "one-more@example.invalid")
    assert r.status_code == 422 and "up to" in str(r.json()["detail"])


def test_a_bad_rule_id_is_refused(env):
    _, client, _, _ = env
    assert client.delete("/api/v1/me/rules/not-an-id").status_code == 422


def test_each_person_has_their_own_rules_and_sign_in_is_needed(env):
    appm, client, _, _ = env
    from fastapi.testclient import TestClient
    from helpers import create_user, sign_in
    create_user(client, "second")
    other = sign_in(appm, "second")
    rid = add_rule(client).json()["rules"][0]["id"]
    assert rules(other) == []
    assert other.delete(f"/api/v1/me/rules/{rid}").status_code == 404
    assert len(rules(client)) == 1
    anon = TestClient(appm.app, raise_server_exceptions=False)
    assert anon.get("/api/v1/me/rules").status_code == 401
    assert anon.post("/api/v1/me/rules", json={"sender": ALICE, "action": "archived"}).status_code == 401
    assert anon.delete(f"/api/v1/me/rules/{rid}").status_code == 401


def test_rules_are_exported_for_me_only_and_forgotten_with_the_person(env):
    appm, client, _, _ = env
    from helpers import create_user, sign_in
    me = client.get("/api/v1/me").json()["id"]
    add_rule(client, "private-sender@example.invalid")
    create_user(client, "second")
    other = sign_in(appm, "second")
    assert "private-sender@example.invalid" in client.get("/api/v1/me/export").text
    assert "private-sender@example.invalid" not in other.get("/api/v1/me/export").text
    appm.delete_user_data(me)
    assert not (appm.vault.get_global("rules:" + me) or {}).get("rules")


# ---------- applied as mail arrives ----------

def test_a_rule_archives_new_mail_from_that_sender_and_only_that_sender(env):
    _, client, bridge, _ = env
    add_rule(client, ALICE, "archived")
    aid, m = synced(client, bridge)
    assert bridge.messages[1]["folder"] == "Archive" and "\\Seen" in bridge.messages[1]["flags"]
    assert bridge.messages[2]["folder"] == "INBOX" and bridge.messages[3]["folder"] == "INBOX"
    listed = client.get(f"/api/v1/accounts/{aid}/messages").json()
    assert sorted(x["state"] for x in listed) == ["archived", "unread", "unread"]          # kept for a few days like any archived email
    assert [x["state"] for x in listed if x["subject"] == "Quarterly update"] == ["archived"]


def test_a_whole_website_rule_covers_everyone_at_it(env):
    _, client, bridge, _ = env
    add_rule(client, "@example.invalid", "archived")
    synced(client, bridge)
    assert bridge.messages[1]["folder"] == "Archive" and bridge.messages[3]["folder"] == "Archive"
    assert bridge.messages[2]["folder"] == "INBOX"


def test_a_subject_narrows_a_rule(env):
    _, client, bridge, _ = env
    add_rule(client, ALICE, "archived", "invoice")
    aid, _ = synced(client, bridge)
    assert bridge.messages[1]["folder"] == "INBOX"
    add_rule(client, ALICE, "archived", "QUARTERLY")
    assert client.post(f"/api/v1/accounts/{aid}/sync", json={}).status_code == 200
    assert bridge.messages[1]["folder"] == "INBOX"          # a rule is only applied to mail that has just arrived


def test_a_subject_that_fits_still_archives_the_email(env):
    _, client, bridge, _ = env
    add_rule(client, ALICE, "archived", "QUARTERLY")
    synced(client, bridge)
    assert bridge.messages[1]["folder"] == "Archive"


def test_a_reviewed_rule_marks_it_read_and_leaves_it_in_the_inbox(env):
    _, client, bridge, _ = env
    add_rule(client, ALICE, "reviewed")
    synced(client, bridge)
    assert "\\Seen" in bridge.messages[1]["flags"] and bridge.messages[1]["folder"] == "INBOX"


def test_mail_from_an_important_person_is_never_touched_by_a_rule(env):
    _, client, bridge, _ = env
    client.post("/api/v1/me/important", json={"address": ALICE})
    add_rule(client, "@example.invalid", "archived")
    synced(client, bridge)
    assert bridge.messages[1]["folder"] == "INBOX" and "\\Seen" not in bridge.messages[1]["flags"]
    assert bridge.messages[3]["folder"] == "Archive"


def test_another_persons_rule_does_not_touch_my_mailbox(env):
    appm, client, bridge, _ = env
    from helpers import create_user, sign_in
    create_user(client, "second")
    other = sign_in(appm, "second")
    add_rule(other, ALICE, "archived")
    synced(client, bridge)
    assert all(m["folder"] == "INBOX" for m in bridge.messages.values())


def test_removing_a_rule_stops_it(env):
    _, client, bridge, _ = env
    rid = add_rule(client).json()["rules"][0]["id"]
    client.delete(f"/api/v1/me/rules/{rid}")
    synced(client, bridge)
    assert bridge.messages[1]["folder"] == "INBOX"


def test_the_resolve_buttons_still_work_the_same(env):
    _, client, bridge, _ = env
    aid, m = synced(client, bridge)
    r = client.post(f"/api/v1/accounts/{aid}/messages/{m['Quarterly update']['id']}/resolve", json={"outcome": "archived"})
    assert r.status_code == 204 and bridge.messages[1]["folder"] == "Archive"
