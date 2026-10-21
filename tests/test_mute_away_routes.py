"""Version 0.102 through the real app: muting a conversation, the away reply, and per-address signatures."""
from __future__ import annotations

import time
from datetime import date, timedelta
from email.utils import formatdate

from test_bridge import MAILBOX, WORK, add_account, env, sent_message, synced  # noqa: F401  (the shared Bridge fixture)

ALICE = "alice@example.invalid"


def fresh(subject, sender, message_id, *, references=None, extra="", to=MAILBOX, delivered_to=MAILBOX):
    lines = [f"From: {sender}", f"To: {to}", f"Subject: {subject}", f"Date: {formatdate(time.time(), localtime=False)}", f"Message-ID: {message_id}"]
    if delivered_to:
        lines.append(f"Delivered-To: {delivered_to}")
    if references:
        lines.append(f"References: {references}")
    return ("\r\n".join(lines) + "\r\n" + extra + "\r\nA few words.\r\n").encode()


def sync(client, aid):
    r = client.post(f"/api/v1/accounts/{aid}/sync", json={})
    assert r.status_code == 200, r.text
    return {m["subject"]: m for m in client.get(f"/api/v1/accounts/{aid}/messages").json()}


def wait_for(check, seconds=5.0):
    end = time.time() + seconds
    while time.time() < end:
        if check():
            return True
        time.sleep(0.05)
    return check()


# ---------- mute ----------

def test_muting_archives_this_email_and_files_later_replies_in_archive(env):
    _, client, bridge, _ = env
    aid, m = synced(client, bridge)
    r = client.post(f"/api/v1/accounts/{aid}/messages/{m['Quarterly update']['id']}/mute")
    assert r.status_code == 200 and r.json()["muted"] is True
    assert bridge.messages[1]["folder"] == "Archive"
    listing = client.get("/api/v1/me/muted")
    assert listing.headers["cache-control"] == "no-store"
    items = listing.json()["items"]
    assert len(items) == 1 and items[0]["subject"] == "Quarterly update" and items[0]["count"] == 0
    bridge.add(7, fresh("Re: Quarterly update", f"Alice <{ALICE}>", "<a7@example.invalid>", references="<a1@example.invalid>"))
    bridge.add(8, fresh("Something else", "Dan <dan@example.invalid>", "<d8@example.invalid>"))
    sync(client, aid)
    assert bridge.messages[7]["folder"] == "Archive" and bridge.messages[8]["folder"] == "INBOX"
    assert client.get("/api/v1/me/muted").json()["items"][0]["count"] == 1
    # a longer thread stays caught: the reply's own id is now part of the conversation
    bridge.add(9, fresh("Re: Re: Quarterly update", f"Alice <{ALICE}>", "<a9@example.invalid>", references="<a1@example.invalid> <a7@example.invalid>"))
    sync(client, aid)
    assert bridge.messages[9]["folder"] == "Archive"


def test_unmuting_lets_replies_come_back(env):
    _, client, bridge, _ = env
    aid, m = synced(client, bridge)
    client.post(f"/api/v1/accounts/{aid}/messages/{m['Quarterly update']['id']}/mute")
    entry = client.get("/api/v1/me/muted").json()["items"][0]["id"]
    r = client.delete(f"/api/v1/me/muted/{entry}")
    assert r.status_code == 200 and r.json()["items"] == []
    assert client.delete(f"/api/v1/me/muted/{entry}").status_code == 404
    bridge.add(7, fresh("Re: Quarterly update", f"Alice <{ALICE}>", "<a7@example.invalid>", references="<a1@example.invalid>"))
    sync(client, aid)
    assert bridge.messages[7]["folder"] == "INBOX"


def test_a_muted_conversation_is_private_and_needs_sign_in(env):
    appm, client, bridge, _ = env
    from fastapi.testclient import TestClient
    from helpers import create_user, sign_in
    aid, m = synced(client, bridge)
    mid = m["Quarterly update"]["id"]
    create_user(client, "second")
    other = sign_in(appm, "second")
    assert other.post(f"/api/v1/accounts/{aid}/messages/{mid}/mute").status_code in (403, 404)
    assert other.get("/api/v1/me/muted").json()["items"] == []
    anon = TestClient(appm.app, raise_server_exceptions=False)
    assert anon.get("/api/v1/me/muted").status_code == 401
    assert anon.post(f"/api/v1/accounts/{aid}/messages/{mid}/mute").status_code == 401
    assert client.post(f"/api/v1/accounts/{aid}/messages/no-such-message/mute").status_code in (404, 422)


def test_important_people_are_never_muted(env):
    _, client, bridge, _ = env
    aid, m = synced(client, bridge)
    client.post(f"/api/v1/accounts/{aid}/messages/{m['Quarterly update']['id']}/mute")
    client.post("/api/v1/me/important", json={"address": ALICE})
    bridge.add(7, fresh("Re: Quarterly update", f"Alice <{ALICE}>", "<a7@example.invalid>", references="<a1@example.invalid>"))
    sync(client, aid)
    assert bridge.messages[7]["folder"] == "INBOX"


def test_muted_conversations_are_exported_and_forgotten_with_the_person(env):
    appm, client, bridge, _ = env
    aid, m = synced(client, bridge)
    client.post(f"/api/v1/accounts/{aid}/messages/{m['Quarterly update']['id']}/mute")
    me = client.get("/api/v1/me").json()["id"]
    assert "Quarterly update" in client.get("/api/v1/me/export").text
    appm.delete_user_data(me)
    assert not (appm.vault.get_global("muted:" + me) or {}).get("items")


# ---------- away reply ----------

def away_on(client, days_before=0, days_after=3, body="I am away and will answer when I am back."):
    today = date.fromisoformat(client.get("/api/v1/me/away").json()["today"])
    return client.put("/api/v1/me/away", json={"enabled": True, "start": (today - timedelta(days=days_before)).isoformat(),
                                               "end": (today + timedelta(days=days_after)).isoformat(), "body": body})


def test_away_reply_is_off_until_switched_on_and_validates_in_plain_words(env):
    _, client, _, _ = env
    first = client.get("/api/v1/me/away")
    assert first.status_code == 200 and first.json()["enabled"] is False and first.json()["state"] == "off"
    assert first.headers["cache-control"] == "no-store"
    r = client.put("/api/v1/me/away", json={"enabled": True, "start": "2026-10-20", "end": "2026-10-22", "body": " "})
    assert r.status_code == 422 and "message" in r.json()["detail"].lower()
    assert client.put("/api/v1/me/away", json={"enabled": True, "start": "nope", "end": "2026-10-22", "body": "x"}).status_code == 422
    assert client.put("/api/v1/me/away", json={"enabled": True, "start": "2026-10-20", "end": "2026-10-22", "body": "x", "extra": 1}).status_code == 422
    assert away_on(client).json()["state"] == "active"


def test_an_away_reply_goes_once_to_each_person_and_says_it_is_automatic(env):
    _, client, bridge, _ = env
    aid = add_account(client, bridge)
    sync(client, aid)
    bridge.sent.clear()
    assert away_on(client).status_code == 200
    bridge.add(7, fresh("Dinner on Friday?", f"Alice <{ALICE}>", "<a7@example.invalid>"))
    sync(client, aid)
    assert wait_for(lambda: len(bridge.sent) == 1)
    item, msg = sent_message(bridge)
    assert item["to"] == [ALICE] and msg["Auto-Submitted"] == "auto-replied" and msg["Precedence"] == "bulk"
    assert msg["Subject"] == "Automatic reply: Dinner on Friday?" and "I am away" in msg.get_body(("plain",)).get_content()
    assert "A few words" not in msg.as_string()                      # nothing from the email is quoted back
    bridge.add(8, fresh("Following up", f"Alice <{ALICE}>", "<a8@example.invalid>"))
    sync(client, aid)
    time.sleep(0.5)
    assert len(bridge.sent) == 1                                      # one reply per person
    assert client.get("/api/v1/me/away").json()["answered"] == 1


def test_an_away_reply_is_not_sent_to_machines_lists_or_before_it_starts(env):
    _, client, bridge, _ = env
    aid = add_account(client, bridge)
    sync(client, aid)
    bridge.sent.clear()
    away_on(client)
    bridge.add(7, fresh("Your receipt", "Shop <noreply@example.invalid>", "<r7@example.invalid>"))
    bridge.add(8, fresh("Weekly news", "News <news@lists.example.invalid>", "<n8@example.invalid>", extra="List-Id: <news.lists.example.invalid>\r\n"))
    bridge.add(9, fresh("Out of office", "Bot <bot@example.invalid>", "<o9@example.invalid>", extra="Auto-Submitted: auto-replied\r\n"))
    bridge.add(10, fresh("Hidden copy", f"Alice <{ALICE}>", "<h10@example.invalid>", to="team@example.invalid", delivered_to=""))
    sync(client, aid)
    time.sleep(0.6)
    assert bridge.sent == []
    away_on(client, days_before=-2, days_after=5)                       # starts the day after tomorrow
    bridge.add(11, fresh("Hello", f"Carol <carol@example.invalid>", "<c11@example.invalid>"))
    sync(client, aid)
    time.sleep(0.5)
    assert bridge.sent == []


def test_switching_the_away_reply_off_stops_it_and_it_is_private(env):
    appm, client, bridge, _ = env
    from fastapi.testclient import TestClient
    from helpers import create_user, sign_in
    aid = add_account(client, bridge)
    sync(client, aid)
    bridge.sent.clear()
    away_on(client)
    client.put("/api/v1/me/away", json={"enabled": False, "start": "", "end": "", "body": "I am away and will answer when I am back."})
    bridge.add(7, fresh("Dinner?", f"Alice <{ALICE}>", "<a7@example.invalid>"))
    sync(client, aid)
    time.sleep(0.5)
    assert bridge.sent == []
    create_user(client, "second")
    other = sign_in(appm, "second")
    assert other.get("/api/v1/me/away").json()["enabled"] is False
    assert TestClient(appm.app, raise_server_exceptions=False).get("/api/v1/me/away").status_code == 401


# ---------- signatures ----------

def test_a_formatted_signature_and_one_per_sending_address(env):
    _, client, bridge, _ = env
    add_account(client, bridge)
    first = client.get("/api/v1/me/saved").json()
    assert set(first["addresses"]) == {MAILBOX, WORK} and first["signature_html"] == ""
    r = client.put("/api/v1/me/saved/signature", json={"text": "", "html": '<b>Sam</b><br><a href="https://example.com/">site</a><script>x()</script>'})
    assert r.status_code == 200 and "<b>Sam</b>" in r.json()["signature_html"] and "script" not in r.json()["signature_html"]
    assert "Sam" in r.json()["signature"]
    r = client.put(f"/api/v1/me/saved/signatures?address={WORK}", json={"html": "<i>Work team</i>"})
    assert r.status_code == 200 and r.json()["signatures"][0]["address"] == WORK and "Work team" in r.json()["signatures"][0]["text"]
    assert "Sam" in r.json()["signature"]                              # the default stays
    assert client.put("/api/v1/me/saved/signatures?address=stranger@example.invalid", json={"html": "x"}).status_code == 422
    r = client.put(f"/api/v1/me/saved/signatures?address={WORK}", json={"html": ""})
    assert r.json()["signatures"] == []


def test_signatures_of_one_person_are_not_visible_to_another(env):
    appm, client, bridge, _ = env
    from helpers import create_user, sign_in
    add_account(client, bridge)
    client.put("/api/v1/me/saved/signature", json={"text": "", "html": "<b>Private</b>"})
    create_user(client, "second")
    other = sign_in(appm, "second")
    assert other.get("/api/v1/me/saved").json()["signature_html"] == ""
    assert other.put(f"/api/v1/me/saved/signatures?address={WORK}", json={"html": "x"}).status_code == 422


def test_scheduled_emails_can_wait_up_to_a_year():
    from backend.mail.scheduled import MAX_AHEAD
    assert MAX_AHEAD == 366 * 86400
