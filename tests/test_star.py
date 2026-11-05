"""Stage 2: star an email. It is the mailbox's own Flagged flag, kept in step both ways by every sync."""
from __future__ import annotations

from fake_bridge import raw_email
from test_bridge import MAILBOX, env, synced  # noqa: F401  (the shared Bridge fixture)
from test_review import resolve


def raw_flagged_read() -> bytes:
    return raw_email("Starred and read", "Cara <cara@example.invalid>", MAILBOX, message_id="<s9@example.invalid>", body="Keep this.\n")


def star(client, aid, mid, on=True):
    return client.post(f"/api/v1/accounts/{aid}/messages/{mid}/star", json={"starred": on})


def listing(client, aid):
    return {m["subject"]: m for m in client.get(f"/api/v1/accounts/{aid}/messages").json()}


def test_starring_sets_the_mailbox_flag_and_unstarring_takes_it_off(env):
    _, client, bridge, _ = env
    aid, m = synced(client, bridge)
    mid = m["Quarterly update"]["id"]
    assert star(client, aid, mid).json() == {"starred": True}
    assert "\\Flagged" in bridge.messages[1]["flags"] and listing(client, aid)["Quarterly update"]["starred"] is True
    assert star(client, aid, mid, False).status_code == 200
    assert "\\Flagged" not in bridge.messages[1]["flags"] and listing(client, aid)["Quarterly update"]["starred"] is False


def test_a_star_set_in_the_mailbox_shows_after_a_sync_and_a_removed_one_goes(env):
    _, client, bridge, _ = env
    aid, m = synced(client, bridge)
    bridge.messages[2]["flags"].add("\\Flagged")
    client.post(f"/api/v1/accounts/{aid}/sync", json={})
    assert listing(client, aid)["Weekly news"]["starred"] is True and listing(client, aid)["Quarterly update"]["starred"] is False
    bridge.messages[2]["flags"].discard("\\Flagged")
    client.post(f"/api/v1/accounts/{aid}/sync", json={})
    assert listing(client, aid)["Weekly news"]["starred"] is False


def test_a_starred_email_that_is_already_read_is_listed_as_a_quiet_starred_entry(env):
    _, client, bridge, _ = env
    aid, _ = synced(client, bridge)
    bridge.add(9, raw_flagged_read())
    bridge.messages[9]["flags"].update({"\\Seen", "\\Flagged"})
    client.post(f"/api/v1/accounts/{aid}/sync", json={})
    entry = listing(client, aid)["Starred and read"]
    assert entry["starred"] is True and entry["from_all_mail"] is True and entry["state"] == "unread"
    client.post(f"/api/v1/accounts/{aid}/sync", json={})
    assert len([x for x in client.get(f"/api/v1/accounts/{aid}/messages").json() if x["subject"] == "Starred and read"]) == 1      # not added twice


def test_only_inbox_emails_can_be_starred_and_other_people_cannot(env):
    appm, client, bridge, _ = env
    aid, m = synced(client, bridge)
    archived = m["Weekly news"]["id"]
    assert resolve(client, aid, archived, "archived").status_code == 204
    assert star(client, aid, archived).status_code == 409
    assert star(client, aid, "nope").status_code in (404, 422)
    assert "\\Flagged" not in bridge.messages[2]["flags"]
