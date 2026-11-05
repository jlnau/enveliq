"""Stage 3: folders. List, make one, move an email into one, look inside one, open an email in one."""
from __future__ import annotations

from fake_bridge import raw_email
from test_bridge import MAILBOX, env, synced  # noqa: F401


def folders(client, aid):
    r = client.get(f"/api/v1/accounts/{aid}/folders")
    assert r.status_code == 200, r.text
    return r.json()["folders"]


def test_the_folder_list_leaves_out_inbox_and_marks_the_ones_you_can_move_into(env):
    _, client, bridge, _ = env
    aid, _ = synced(client, bridge)
    bridge.folders.append(("\\HasNoChildren", "Bills"))
    rows = {r["label"]: r for r in folders(client, aid)}
    assert "Inbox" not in rows and rows["Bills"]["target"] is True
    assert rows["Archive"]["target"] is False or rows["Archive"]["special"] is True
    assert rows["Bin"]["target"] is False


def test_making_a_folder_shows_it_in_the_mailbox_and_a_duplicate_is_refused(env):
    _, client, bridge, _ = env
    aid, _ = synced(client, bridge)
    r = client.post(f"/api/v1/accounts/{aid}/folders", json={"name": "Receipts"})
    assert r.status_code == 201 and r.json()["label"] == "Receipts"
    assert any(n.endswith("Receipts") for _f, n in bridge.folders)
    assert client.post(f"/api/v1/accounts/{aid}/folders", json={"name": "receipts"}).status_code == 409
    for bad in ("", "a/b", "x" * 200, "Inbox"):
        assert client.post(f"/api/v1/accounts/{aid}/folders", json={"name": bad}).status_code == 422


def test_moving_an_email_puts_it_in_the_folder_and_it_leaves_the_list(env):
    _, client, bridge, _ = env
    aid, m = synced(client, bridge)
    bridge.folders.append(("\\HasNoChildren", "Bills"))
    mid = m["Quarterly update"]["id"]
    r = client.post(f"/api/v1/accounts/{aid}/messages/{mid}/move", json={"folder": "Bills"})
    assert r.status_code == 204
    assert bridge.messages[1]["folder"] == "Bills"
    assert "Quarterly update" not in {x["subject"] for x in client.get(f"/api/v1/accounts/{aid}/messages").json()}


def test_a_move_only_goes_to_a_folder_the_mailbox_listed(env):
    _, client, bridge, _ = env
    aid, m = synced(client, bridge)
    mid = m["Quarterly update"]["id"]
    for bad in ("Nowhere", "INBOX", "Trash"):
        assert client.post(f"/api/v1/accounts/{aid}/messages/{mid}/move", json={"folder": bad}).status_code == 404
    assert bridge.messages[1]["folder"] == "INBOX"
    assert client.post(f"/api/v1/accounts/{aid}/messages/nope/move", json={"folder": "Bills"}).status_code in (404, 422)


def test_looking_inside_a_folder_lists_newest_first_and_opens_one_email(env):
    _, client, bridge, _ = env
    aid, _ = synced(client, bridge)
    bridge.folders.append(("\\HasNoChildren", "Bills"))
    for uid, subject in ((20, "Old bill"), (21, "New bill")):
        bridge.add(uid, raw_email(subject, "Power Co <bills@example.invalid>", MAILBOX, message_id=f"<b{uid}@example.invalid>", body="Pay this.\n"))
        bridge.messages[uid]["folder"] = "Bills"
    page = client.get(f"/api/v1/accounts/{aid}/folder-mail", params={"folder": "Bills"}).json()
    assert [r["subject"] for r in page["rows"]] == ["New bill", "Old bill"] and page["total"] == 2 and page["more"] is False
    opened = client.get(f"/api/v1/folder-mail/{page['rows'][0]['token']}/original")
    assert opened.status_code == 200 and "Pay this." in opened.text
    assert client.get(f"/api/v1/accounts/{aid}/folder-mail", params={"folder": "Secret"}).status_code == 404
    assert client.get(f"/api/v1/folder-mail/{page['rows'][0]['token'][:-3]}abc/original").status_code == 404
