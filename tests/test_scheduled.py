"""Send later: scheduled, listed without the words, taken back, sent when due, and private to the person."""
from __future__ import annotations

import time

from helpers import create_user, sign_in
from test_bridge import env, synced  # noqa: F401  (the shared Bridge fixture)
from test_reply_all_forward import sent_message


def soon(seconds=3600):
    return time.time() + seconds


def new_body(aid, **over):
    return {"kind": "new", "account_id": aid, "to": ["dana@example.invalid"], "subject": "Later", "body": "Secret words", "send_at": soon(), **over}


def test_a_new_email_waits_and_the_list_never_shows_the_words(env):
    appm, client, bridge, _ = env
    aid, _m = synced(client, bridge)
    r = client.post("/api/v1/me/scheduled", json=new_body(aid))
    assert r.status_code == 201, r.text
    listed = client.get("/api/v1/me/scheduled").json()["items"]
    assert [i["subject"] for i in listed] == ["Later"] and listed[0]["state"] == "pending"
    assert "Secret words" not in str(listed)
    assert appm.scheduled_sender.run_due() == 0 and bridge.sent == []          # not due yet


def test_it_is_sent_when_the_time_comes_and_leaves_the_list(env):
    appm, client, bridge, _ = env
    aid, _m = synced(client, bridge)
    assert client.post("/api/v1/me/scheduled", json=new_body(aid)).status_code == 201
    appm.scheduled_sender.clock = lambda: time.time() + 7200
    assert appm.scheduled_sender.run_due() == 1
    _, msg = sent_message(bridge)
    assert msg["Subject"] == "Later" and "Secret words" in msg.get_body(preferencelist=("plain",)).get_content()
    assert client.get("/api/v1/me/scheduled").json()["items"] == []


def test_taking_one_back_returns_the_words_and_nothing_is_sent(env):
    appm, client, bridge, _ = env
    aid, _m = synced(client, bridge)
    sid = client.post("/api/v1/me/scheduled", json=new_body(aid)).json()["id"]
    back = client.delete(f"/api/v1/me/scheduled/{sid}")
    assert back.status_code == 200 and back.json()["body"] == "Secret words" and back.json()["to_list"] == ["dana@example.invalid"]
    assert client.delete(f"/api/v1/me/scheduled/{sid}").status_code == 404
    appm.scheduled_sender.clock = lambda: time.time() + 7200
    assert appm.scheduled_sender.run_due() == 0 and bridge.sent == []


def test_a_reply_can_be_scheduled_and_marks_the_email_replied(env):
    appm, client, bridge, _ = env
    aid, m = synced(client, bridge)
    mid = m["Quarterly update"]["id"]
    r = client.post("/api/v1/me/scheduled", json={"kind": "reply", "account_id": aid, "message_id": mid, "body": "Thanks, later.", "send_at": soon()})
    assert r.status_code == 201, r.text
    appm.scheduled_sender.clock = lambda: time.time() + 7200
    assert appm.scheduled_sender.run_due() == 1
    _, msg = sent_message(bridge)
    assert msg["Subject"].startswith("Re:") and "alice@example.invalid" in msg["To"]
    listed = {x["subject"]: x for x in client.get(f"/api/v1/accounts/{aid}/messages").json()}
    assert listed["Quarterly update"]["replied_at"] > 0


def test_bad_times_and_bad_addresses_are_refused_up_front(env):
    _, client, bridge, _ = env
    aid, _m = synced(client, bridge)
    assert client.post("/api/v1/me/scheduled", json=new_body(aid, send_at=time.time() + 1)).status_code == 422
    assert client.post("/api/v1/me/scheduled", json=new_body(aid, send_at=soon(40 * 86400))).status_code == 422
    assert client.post("/api/v1/me/scheduled", json=new_body(aid, to=["not an address"])).status_code >= 400
    assert client.get("/api/v1/me/scheduled").json()["items"] == []


def test_a_failed_send_stays_listed_with_a_reason(env):
    appm, client, bridge, _ = env
    aid, m = synced(client, bridge)
    sid = client.post("/api/v1/me/scheduled", json={"kind": "reply", "account_id": aid, "message_id": m["Quarterly update"]["id"], "body": "x", "send_at": soon()}).json()["id"]
    appm.scheduled_sender.clock = lambda: time.time() + 7200
    appm.scheduled_sender.service = type("Broken", (), {"build_reply": staticmethod(lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))})()
    appm.scheduled_sender.run_due()
    item = client.get("/api/v1/me/scheduled").json()["items"][0]
    assert item["id"] == sid and item["state"] == "failed" and item["error"]


def test_nobody_else_can_see_or_take_back_a_scheduled_email(env):
    appm, client, bridge, _ = env
    aid, _m = synced(client, bridge)
    sid = client.post("/api/v1/me/scheduled", json=new_body(aid)).json()["id"]
    create_user(client, "cara")
    cara = sign_in(appm, "cara")
    assert cara.get("/api/v1/me/scheduled").json()["items"] == []
    assert cara.delete(f"/api/v1/me/scheduled/{sid}").status_code == 404
    assert cara.post("/api/v1/me/scheduled", json=new_body(aid)).status_code in (403, 404)       # not her mailbox
