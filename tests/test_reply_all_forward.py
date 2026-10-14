"""Reply all (only when an email has Cc), Cc and Bcc on replies, and Forward."""
from __future__ import annotations

import email
from email import policy

from fake_bridge import raw_email_with
from helpers import create_user, sign_in
from test_bridge import MAILBOX, WORK, add_account, env, mails  # noqa: F401  (the shared Bridge fixture)

BOSS = "boss@example.invalid"
PEER = "peer@example.invalid"


def sent_message(bridge, index=-1):
    item = bridge.sent[index]
    return item, email.message_from_bytes(item["data"], policy=policy.default)


def synced_with_cc(client, bridge):
    bridge.add(10, raw_email_with("Plan for May", "Alice Example <alice@example.invalid>", f"{MAILBOX}, Dan <dan@example.invalid>",
                                  cc=f"{BOSS}, {WORK}, Alice Example <alice@example.invalid>", message_id="<cc10@example.invalid>",
                                  file=("plan.pdf", b"%PDF-1.4 made up")))
    aid = add_account(client, bridge)
    assert client.post(f"/api/v1/accounts/{aid}/sync", json={}).status_code == 200
    return aid, {m["subject"]: m for m in client.get(f"/api/v1/accounts/{aid}/messages").json()}


def test_other_people_are_kept_without_names_or_our_own_addresses(env):
    _, client, bridge, _ = env
    aid, m = synced_with_cc(client, bridge)
    ctx = m["Plan for May"]["reply_context"]
    assert ctx["cc"] == [BOSS] and ctx["also_to"] == ["dan@example.invalid"]       # not us, not the sender
    assert m["Quarterly update"]["reply_context"]["cc"] == []                      # nothing on Cc: no Reply all


def test_reply_all_goes_to_sender_and_other_to_with_cc_in_cc(env):
    _, client, bridge, _ = env
    aid, m = synced_with_cc(client, bridge)
    r = client.post(f"/api/v1/accounts/{aid}/messages/{m['Plan for May']['id']}/reply", json={"body": "Sounds good.", "kind": "reply_all"})
    assert r.status_code == 200, r.text
    item, msg = sent_message(bridge)
    assert item["to"] == ["alice@example.invalid", "dan@example.invalid", BOSS]
    assert msg["To"].addresses[0].addr_spec == "alice@example.invalid" and [a.addr_spec for a in msg["Cc"].addresses] == [BOSS]
    assert msg["In-Reply-To"] == "<cc10@example.invalid>"


def test_reply_all_is_refused_when_there_is_no_cc(env):
    _, client, bridge, _ = env
    aid, m = synced_with_cc(client, bridge)
    r = client.post(f"/api/v1/accounts/{aid}/messages/{m['Quarterly update']['id']}/reply", json={"body": "Hi", "kind": "reply_all"})
    assert r.status_code >= 400 and bridge.sent == []


def test_reply_with_chosen_people_bcc_stays_out_of_headers(env):
    _, client, bridge, _ = env
    aid, m = synced_with_cc(client, bridge)
    r = client.post(f"/api/v1/accounts/{aid}/messages/{m['Quarterly update']['id']}/reply",
                    json={"body": "Hi", "to": ["alice@example.invalid", "ALICE@example.invalid"], "cc": [PEER], "bcc": [BOSS, PEER]})
    assert r.status_code == 200, r.text
    item, msg = sent_message(bridge)
    assert item["to"] == ["alice@example.invalid", PEER, BOSS]                      # repeats dropped, case ignored
    assert BOSS not in item["data"].decode() and msg["Bcc"] is None


def test_reply_refuses_bad_addresses_and_header_tricks(env):
    _, client, bridge, _ = env
    aid, m = synced_with_cc(client, bridge)
    url = f"/api/v1/accounts/{aid}/messages/{m['Quarterly update']['id']}/reply"
    assert client.post(url, json={"body": "Hi", "cc": ["not an address"]}).status_code >= 400
    assert client.post(url, json={"body": "Hi", "cc": ["a@example.invalid\r\nBcc: x@example.invalid"]}).status_code >= 400
    assert client.post(url, json={"body": "Hi", "to": [f"p{i}@example.invalid" for i in range(51)]}).status_code == 422
    assert bridge.sent == []


def test_forward_quotes_the_original_and_sends_its_file(env):
    _, client, bridge, _ = env
    aid, m = synced_with_cc(client, bridge)
    r = client.post(f"/api/v1/accounts/{aid}/messages/{m['Plan for May']['id']}/forward",
                    json={"to": ["mum@example.invalid"], "cc": [PEER], "bcc": [BOSS], "body": "See below."})
    assert r.status_code == 200 and r.json()["sent"] is True, r.text
    item, msg = sent_message(bridge)
    assert item["to"] == ["mum@example.invalid", PEER, BOSS] and msg["Subject"] == "Fwd: Plan for May"
    assert msg["In-Reply-To"] is None and BOSS not in item["data"].decode().split("\r\n\r\n")[0]
    text = msg.get_body(preferencelist=("plain",)).get_content()
    assert text.startswith("See below.") and "Forwarded message" in text and "alice@example.invalid" in text and "Subject: Plan for May" in text
    assert [p.get_filename() for p in msg.iter_attachments()] == ["plan.pdf"]
    listed = {x["subject"]: x for x in client.get(f"/api/v1/accounts/{aid}/messages").json()}
    assert not listed["Plan for May"].get("replied_at")                              # forwarding is not replying


def test_forward_can_leave_the_file_out_and_needs_someone_to_send_to(env):
    _, client, bridge, _ = env
    aid, m = synced_with_cc(client, bridge)
    url = f"/api/v1/accounts/{aid}/messages/{m['Plan for May']['id']}/forward"
    assert client.post(url, json={"body": "x"}).status_code >= 400
    assert client.post(url, json={"to": ["mum@example.invalid"], "keep_files": []}).status_code == 200
    _, msg = sent_message(bridge)
    assert list(msg.iter_attachments()) == []


def test_another_person_cannot_forward_or_reply_all(env):
    appm, client, bridge, _ = env
    aid, m = synced_with_cc(client, bridge)
    create_user(client, "cara")
    cara = sign_in(appm, "cara")
    base = f"/api/v1/accounts/{aid}/messages/{m['Plan for May']['id']}"
    assert cara.post(base + "/forward", json={"to": ["mum@example.invalid"]}).status_code == 404
    assert cara.post(base + "/reply", json={"body": "Hi", "kind": "reply_all"}).status_code == 404
    assert bridge.sent == []


def test_held_forward_is_listed_as_a_forward_and_not_marked_replied(env):
    appm, client, bridge, _ = env
    aid, m = synced_with_cc(client, bridge)
    assert client.put("/api/v1/me/preferences", json={"keep_reviewed": True, "keep_archived": True, "keep_days": 7, "instructions": "", "undo_send_seconds": 10}).status_code == 200
    r = client.post(f"/api/v1/accounts/{aid}/messages/{m['Plan for May']['id']}/forward", json={"to": ["mum@example.invalid"], "bcc": [BOSS]})
    assert r.status_code == 200 and r.json()["queued"] is True and bridge.sent == []
    assert client.get("/api/v1/me/outbox").json()["items"][0]["kind"] == "forward"
    c = client.delete(f"/api/v1/me/outbox/{r.json()['id']}").json()
    assert c["kind"] == "forward" and c["to_list"] == ["mum@example.invalid"] and c["bcc_list"] == [BOSS]
    assert bridge.sent == []


def body_of(msg):
    return msg.get_body(preferencelist=("plain",)).get_content().replace("\r\n", "\n")      # sent mail uses CRLF line ends


def test_every_reply_carries_the_whole_original_under_the_persons_words(env):
    _, client, bridge, _ = env
    aid, m = synced_with_cc(client, bridge)
    r = client.post(f"/api/v1/accounts/{aid}/messages/{m['Plan for May']['id']}/reply", json={"body": "Sounds good."})
    assert r.status_code == 200, r.text
    _, msg = sent_message(bridge)
    text = body_of(msg)
    assert text.startswith("Sounds good.\n\nOn Wed, 07 Oct 2026 09:00:00 +1100, Alice Example <alice@example.invalid> wrote:\n> Hello there.")
    assert not msg.is_multipart() or not list(msg.iter_attachments())              # quoted in the text, not attached


def test_reply_all_and_replies_with_chosen_people_carry_it_too(env):
    _, client, bridge, _ = env
    aid, m = synced_with_cc(client, bridge)
    url = f"/api/v1/accounts/{aid}/messages/{m['Plan for May']['id']}/reply"
    assert client.post(url, json={"body": "A", "kind": "reply_all"}).status_code == 200
    assert "> Hello there." in body_of(sent_message(bridge)[1])
    assert client.post(url, json={"body": "B", "to": [PEER]}).status_code == 200
    assert "> Hello there." in body_of(sent_message(bridge)[1])


def test_when_the_person_already_put_it_in_their_message_it_is_not_added_again(env):
    _, client, bridge, _ = env
    aid, m = synced_with_cc(client, bridge)
    mine = "Thanks.\n\nOn Wed, Alice wrote:\n> Hello (I cut the rest)"
    r = client.post(f"/api/v1/accounts/{aid}/messages/{m['Plan for May']['id']}/reply", json={"body": mine, "add_original": False})
    assert r.status_code == 200, r.text
    text = body_of(sent_message(bridge)[1])
    assert text.strip() == mine and text.count("wrote:") == 1


def test_the_original_is_quoted_only_in_what_is_sent_never_kept(env):
    appm, client, bridge, _ = env
    aid, m = synced_with_cc(client, bridge)
    client.post(f"/api/v1/accounts/{aid}/messages/{m['Plan for May']['id']}/reply", json={"body": "Ok."})
    assert "Hello there." not in str(appm.vault.get_message(aid, m["Plan for May"]["id"]))
