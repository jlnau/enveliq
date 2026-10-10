"""Undo send: replies held for a chosen time, cancelled with the text returned, and the replied flag."""
from __future__ import annotations

from test_bridge import env, synced  # noqa: F401  (the shared Bridge fixture)

PREFS = {"keep_reviewed": True, "keep_archived": True, "keep_days": 7, "instructions": ""}


def set_undo(client, seconds):
    r = client.put("/api/v1/me/preferences", json={**PREFS, "undo_send_seconds": seconds})
    assert r.status_code == 200, r.text
    return r.json()


def message_id(m, subject):
    return m[subject]["id"]


def test_default_sends_at_once_and_marks_the_email_replied(env):
    _, client, bridge, _ = env
    aid, m = synced(client, bridge)
    assert client.get("/api/v1/me/preferences").json()["undo_send_seconds"] == 0
    r = client.post(f"/api/v1/accounts/{aid}/messages/{message_id(m, 'Quarterly update')}/reply", json={"body": "Thanks."})
    assert r.status_code == 200 and r.json()["sent"] is True and len(bridge.sent) == 1
    listed = {x["subject"]: x for x in client.get(f"/api/v1/accounts/{aid}/messages").json()}
    assert listed["Quarterly update"]["replied_at"] > 0 and not listed["Weekly news"].get("replied_at")


def test_preference_is_kept_when_other_settings_are_saved_without_it(env):
    _, client, _, _ = env
    assert set_undo(client, 20)["undo_send_seconds"] == 20
    r = client.put("/api/v1/me/preferences", json=PREFS)
    assert r.json()["undo_send_seconds"] == 20
    assert client.put("/api/v1/me/preferences", json={**PREFS, "undo_send_seconds": 61}).status_code == 422
    assert client.put("/api/v1/me/preferences", json={**PREFS, "undo_send_seconds": -1}).status_code == 422
    assert set_undo(client, 0)["undo_send_seconds"] == 0


def test_reply_is_held_then_cancelled_and_never_sent(env):
    appm, client, bridge, _ = env
    aid, m = synced(client, bridge)
    set_undo(client, 20)
    mid = message_id(m, "Quarterly update")
    r = client.post(f"/api/v1/accounts/{aid}/messages/{mid}/reply", json={"body": "Draft text"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["queued"] is True and body["send_at"] - body["now"] > 15 and "sent" not in body
    assert bridge.sent == []
    box = client.get("/api/v1/me/outbox").json()
    assert [i["state"] for i in box["items"]] == ["pending"] and box["items"][0]["message_id"] == mid
    assert "Draft text" not in str(box)                                    # the list never carries the text
    assert appm.outbox.run_due() == 0 and bridge.sent == []                # not due yet
    c = client.delete(f"/api/v1/me/outbox/{body['id']}")
    assert c.status_code == 200 and c.json()["body"] == "Draft text" and c.json()["message_id"] == mid
    assert client.get("/api/v1/me/outbox").json()["items"] == []
    assert client.delete(f"/api/v1/me/outbox/{body['id']}").status_code == 404
    for item in list(appm.outbox._items.values()):
        item.send_at = 0
    appm.outbox.run_due()
    assert bridge.sent == []


def test_held_reply_is_sent_when_its_time_comes(env):
    appm, client, bridge, _ = env
    aid, m = synced(client, bridge)
    set_undo(client, 5)
    mid = message_id(m, "Weekly news")
    r = client.post(f"/api/v1/accounts/{aid}/messages/{mid}/reply", json={"body": "Noted."})
    item_id = r.json()["id"]
    appm.outbox._items[item_id].send_at = 0
    assert appm.outbox.run_due() == 1
    assert len(bridge.sent) == 1 and bridge.sent[0]["to"] == ["news_at_example_invalid_k3j9@simplelogin.co"]
    items = client.get("/api/v1/me/outbox").json()["items"]
    assert [i["state"] for i in items] == ["sent"]
    assert client.delete(f"/api/v1/me/outbox/{item_id}").status_code == 409     # too late to undo
    listed = {x["subject"]: x for x in client.get(f"/api/v1/accounts/{aid}/messages").json()}
    assert listed["Weekly news"]["replied_at"] > 0


def test_bad_sender_is_refused_when_queuing_not_later(env):
    appm, client, bridge, _ = env
    aid, m = synced(client, bridge)
    set_undo(client, 10)
    r = client.post(f"/api/v1/accounts/{aid}/messages/{message_id(m, 'Quarterly update')}/reply",
                    json={"body": "Hi", "from_address": "someone@else.invalid"})
    assert r.status_code == 400
    assert client.get("/api/v1/me/outbox").json()["items"] == []


def test_another_person_cannot_cancel(env):
    appm, client, bridge, _ = env
    aid, m = synced(client, bridge)
    set_undo(client, 10)
    item = appm.outbox.enqueue("someone-else", aid, message_id(m, "Quarterly update"), appm.mail_service.build_reply(
        appm.vault.get_account(aid), appm.vault.get_message(aid, message_id(m, "Quarterly update")), "x", None), "x", 10)
    assert client.get("/api/v1/me/outbox").json()["items"] == []
    assert client.delete(f"/api/v1/me/outbox/{item.id}").status_code == 404
