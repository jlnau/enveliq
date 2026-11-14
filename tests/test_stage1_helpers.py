"""Stage 1 helpers: send with high importance, show the headers of an email, download an email as .eml."""
from __future__ import annotations

from test_bridge import env, sent_message, synced  # noqa: F401  (the shared Bridge fixture)


def first_id(m):
    return m["Quarterly update"]["id"]


def test_a_reply_is_sent_with_high_importance_only_when_asked(env):
    _, client, bridge, _ = env
    aid, m = synced(client, bridge)
    base = f"/api/v1/accounts/{aid}/messages/{first_id(m)}/reply"
    assert client.post(base, json={"body": "Plain one."}).status_code == 200
    _, plain = sent_message(bridge)
    assert plain["Importance"] is None and plain["X-Priority"] is None
    assert client.post(base, json={"body": "This matters.", "important": True}).status_code == 200
    _, flagged = sent_message(bridge)
    assert flagged["Importance"] == "high" and flagged["X-Priority"].startswith("1")


def test_a_new_email_and_a_forward_can_carry_high_importance(env):
    _, client, bridge, _ = env
    aid, m = synced(client, bridge)
    r = client.post(f"/api/v1/accounts/{aid}/send", json={"to": ["dana@example.invalid"], "subject": "Urgent", "body": "Please look.", "important": True})
    assert r.status_code == 200, r.text
    _, msg = sent_message(bridge)
    assert msg["Importance"] == "high"
    r = client.post(f"/api/v1/accounts/{aid}/messages/{first_id(m)}/forward", json={"to": ["dana@example.invalid"], "body": "FYI", "important": True})
    assert r.status_code == 200, r.text
    _, fwd = sent_message(bridge)
    assert fwd["Importance"] == "high"


def test_headers_are_fetched_on_demand_and_not_stored(env):
    appm, client, bridge, _ = env
    aid, m = synced(client, bridge)
    r = client.get(f"/api/v1/accounts/{aid}/messages/{first_id(m)}/original/headers")
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
    head = r.json()["headers"]
    assert "Subject: Quarterly update" in head and "\n\n" not in head
    appm.vault.lock()
    assert not any(appm.vault.plaintext_scan(["Subject: Quarterly update"]).values())


def test_the_whole_email_downloads_as_eml(env):
    _, client, bridge, _ = env
    aid, m = synced(client, bridge)
    r = client.get(f"/api/v1/accounts/{aid}/messages/{first_id(m)}/original/eml")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("message/rfc822")
    assert 'attachment; filename="email.eml"' in r.headers["content-disposition"]
    assert r.headers["cache-control"] == "no-store"
    assert b"Subject: Quarterly update" in r.content


def test_an_unknown_email_answers_not_found_for_headers_and_eml(env):
    _, client, bridge, _ = env
    aid, m = synced(client, bridge)
    missing = f"/api/v1/accounts/{aid}/messages/9f7186e0-f55e-45a3-bac3-4c3d235370d0"
    assert client.get(missing + "/original/headers").status_code == 404
    assert client.get(missing + "/original/eml").status_code == 404


def test_send_later_keeps_high_importance(env):
    import time
    appm, client, bridge, _ = env
    aid, _m = synced(client, bridge)
    r = client.post("/api/v1/me/scheduled", json={"kind": "new", "account_id": aid, "to": ["dana@example.invalid"], "subject": "Later", "body": "Soon.",
                                                  "important": True, "send_at": time.time() + 3600})
    assert r.status_code == 201, r.text
    appm.scheduled_sender.clock = lambda: time.time() + 7200
    assert appm.scheduled_sender.run_due() == 1
    _, msg = sent_message(bridge)
    assert msg["Importance"] == "high" and msg["X-Priority"].startswith("1")
