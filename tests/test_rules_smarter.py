"""Stage 5, smarter mail rules: more conditions, star / snooze / safe sender, edit and order, Check, and Run on existing mail."""
from __future__ import annotations

import time

from fake_bridge import raw_email, raw_email_with
from test_bridge import MAILBOX, env, mails, synced  # noqa: F401  (the shared Bridge fixture)

ALICE = "alice@example.invalid"


def spec(**over):
    body = {"sender": "", "subject": "", "action": "archived", "advanced": True}
    body.update(over)
    return body


def post(client, **over):
    return client.post("/api/v1/me/rules", json=spec(**over))


def rules(client):
    return client.get("/api/v1/me/rules").json()["rules"]


def listing(client, aid):
    return {m["subject"]: m for m in client.get(f"/api/v1/accounts/{aid}/messages").json()}


def with_list_mail(bridge):
    bridge.add(4, raw_email("Weekly digest", "Dana <dana@example.invalid>", MAILBOX, message_id="<d4@example.invalid>",
                            extra="Cc: team@example.invalid\r\nList-Id: Digest <digest.news.example.invalid>\r\n"))
    bridge.add(5, raw_email_with("Report", "Eve <eve@example.invalid>", MAILBOX, message_id="<e5@example.invalid>", file=("r.pdf", b"x" * 3000)))


# ---------- the rule itself ----------

def test_a_rule_can_use_several_new_conditions_and_reads_back(env):
    _, client, _, _ = env
    r = post(client, sender="@example.invalid", not_subject="receipt", to="team@example.invalid", mailing_list="news.example", files=True, larger_mb=2)
    assert r.status_code == 200
    rule = r.json()["rules"][0]
    assert rule["not_subject"] == "receipt" and rule["to"] == "team@example.invalid" and rule["list"] == "news.example" and rule["files"] is True and rule["larger_mb"] == 2


def test_a_rule_with_nothing_to_look_for_is_refused_in_plain_words(env):
    _, client, _, _ = env
    r = post(client)
    assert r.status_code == 422 and "at least one thing to look for" in r.json()["detail"]
    assert rules(client) == []


def test_bad_sizes_and_snooze_times_are_refused(env):
    _, client, _, _ = env
    assert post(client, sender=ALICE, larger_mb=5000).status_code == 422
    assert post(client, sender=ALICE, action="snoozed", hours=0).status_code == 422
    assert post(client, sender=ALICE, action="snoozed", hours=24 * 31).status_code == 422
    assert post(client, sender=ALICE, action="snoozed", hours=4).status_code == 200


def test_a_rule_can_be_changed_in_place_and_keeps_its_place(env):
    _, client, _, _ = env
    post(client, sender=ALICE)
    post(client, sender="bob@example.invalid")
    first = rules(client)[0]["id"]
    r = client.put(f"/api/v1/me/rules/{first}", json=spec(sender=ALICE, subject="invoice", action="starred"))
    assert r.status_code == 200
    got = r.json()["rules"]
    assert [x["id"] for x in got][0] == first and got[0]["subject"] == "invoice" and got[0]["action"] == "starred" and len(got) == 2
    assert client.put("/api/v1/me/rules/u0000000000000000", json=spec(sender=ALICE)).status_code == 404


def test_rules_can_be_moved_up_and_down(env):
    _, client, _, _ = env
    for who in ("a@example.invalid", "b@example.invalid", "c@example.invalid"):
        post(client, sender=who)
    ids = [x["id"] for x in rules(client)]
    client.post(f"/api/v1/me/rules/{ids[2]}/move", json={"direction": "up"})
    assert [x["id"] for x in rules(client)] == [ids[0], ids[2], ids[1]]
    client.post(f"/api/v1/me/rules/{ids[0]}/move", json={"direction": "down"})
    assert [x["id"] for x in rules(client)] == [ids[2], ids[0], ids[1]]
    client.post(f"/api/v1/me/rules/{ids[2]}/move", json={"direction": "up"})            # already at the top: nothing breaks
    assert [x["id"] for x in rules(client)][0] == ids[2]
    assert client.post(f"/api/v1/me/rules/{ids[0]}/move", json={"direction": "sideways"}).status_code == 422
    assert client.post("/api/v1/me/rules/u0000000000000000/move", json={"direction": "up"}).status_code == 404


def test_another_person_cannot_see_edit_move_or_run_my_rules(env):
    appm, client, _, _ = env
    from helpers import create_user, sign_in
    rid = post(client, sender=ALICE).json()["rules"][0]["id"]
    create_user(client, "second")
    other = sign_in(appm, "second")
    assert rules(other) == []
    assert other.put(f"/api/v1/me/rules/{rid}", json=spec(sender=ALICE)).status_code == 404
    assert other.post(f"/api/v1/me/rules/{rid}/move", json={"direction": "up"}).status_code == 404
    assert other.post("/api/v1/me/rules/run", json={"confirm": False}).json()["total"] == 0


# ---------- the conditions, as mail arrives ----------

def test_subject_does_not_have_leaves_those_emails_alone(env):
    _, client, bridge, _ = env
    post(client, sender="@example.invalid", not_subject="invoice")
    synced(client, bridge)
    assert bridge.messages[1]["folder"] == "Archive" and bridge.messages[3]["folder"] == "INBOX"


def test_to_cc_list_and_file_conditions(env):
    _, client, bridge, _ = env
    with_list_mail(bridge)
    post(client, to="team@example.invalid")                      # Cc counts
    aid, _ = synced(client, bridge)
    assert bridge.messages[4]["folder"] == "Archive" and bridge.messages[1]["folder"] == "INBOX"


def test_a_mailing_list_rule_fits_only_that_list(env):
    _, client, bridge, _ = env
    with_list_mail(bridge)
    post(client, mailing_list="digest.news.example")
    synced(client, bridge)
    assert bridge.messages[4]["folder"] == "Archive" and bridge.messages[1]["folder"] == "INBOX" and bridge.messages[5]["folder"] == "INBOX"


def test_a_has_a_file_rule_fits_mail_with_an_attachment(env):
    _, client, bridge, _ = env
    with_list_mail(bridge)
    post(client, files=True)
    synced(client, bridge)
    assert bridge.messages[5]["folder"] == "Archive" and bridge.messages[4]["folder"] == "INBOX"


def test_a_size_rule_uses_the_size_the_mailbox_reports(env):
    _, client, bridge, _ = env
    with_list_mail(bridge)
    bridge.messages[5]["raw"] = bridge.messages[5]["raw"] + b"x" * (2 * 1024 * 1024)
    post(client, larger_mb=1)
    synced(client, bridge)
    assert bridge.messages[5]["folder"] == "Archive" and bridge.messages[1]["folder"] == "INBOX"


# ---------- new actions ----------

def test_a_star_rule_stars_new_mail(env):
    _, client, bridge, _ = env
    post(client, sender=ALICE, action="starred")
    aid, _ = synced(client, bridge)
    assert "\\Flagged" in bridge.messages[1]["flags"] and bridge.messages[1]["folder"] == "INBOX"
    assert listing(client, aid)["Quarterly update"]["starred"] is True


def test_a_snooze_rule_snoozes_new_mail_for_the_time_chosen(env):
    _, client, bridge, _ = env
    post(client, sender=ALICE, action="snoozed", hours=4)
    aid, _ = synced(client, bridge)
    until = listing(client, aid)["Quarterly update"]["snoozed_until"]
    assert until and abs(until - (time.time() + 4 * 3600)) < 120
    assert listing(client, aid)["Weekly news"]["snoozed_until"] is None


def test_a_safe_sender_stops_every_later_rule_and_leaves_the_email_alone(env):
    _, client, bridge, _ = env
    bridge.folders.append(("\\HasNoChildren \\Junk", "Spam"))
    post(client, sender=ALICE, action="safe")
    post(client, sender="@example.invalid", action="junked")
    synced(client, bridge)
    assert bridge.messages[1]["folder"] == "INBOX"                 # safe, though the website rule would have junked it
    assert bridge.messages[3]["folder"] == "Spam"


def test_the_first_rule_that_acts_wins_and_order_changes_that(env):
    _, client, bridge, _ = env
    post(client, sender=ALICE, action="starred")
    post(client, sender="@example.invalid", action="archived")
    synced(client, bridge)
    assert "\\Flagged" in bridge.messages[1]["flags"] and bridge.messages[1]["folder"] == "INBOX"
    assert bridge.messages[3]["folder"] == "Archive"


# ---------- Check, and Run on existing mail ----------

def test_check_counts_what_a_rule_would_have_matched_and_changes_nothing(env):
    _, client, bridge, _ = env
    aid, _ = synced(client, bridge)
    r = client.post("/api/v1/me/rules/preview", json=spec(sender="@example.invalid"))
    assert r.status_code == 200 and r.json() == {"matches": 2, "checked": 3}
    assert client.post("/api/v1/me/rules/preview", json=spec(sender=ALICE, action="starred")).json()["matches"] == 1
    assert client.post("/api/v1/me/rules/preview", json=spec()).status_code == 422
    assert rules(client) == [] and all(m["folder"] == "INBOX" for m in bridge.messages.values())


def test_run_on_existing_mail_counts_first_and_only_acts_when_confirmed(env):
    _, client, bridge, _ = env
    aid, _ = synced(client, bridge)
    post(client, sender=ALICE, action="archived")
    post(client, sender="bob@example.invalid", action="safe")
    plan = client.post("/api/v1/me/rules/run", json={"confirm": False}).json()
    assert plan["total"] == 1 and plan["counts"] == {"archived": 1} and plan["limit"] == 500
    assert bridge.messages[1]["folder"] == "INBOX"                                  # counting changed nothing
    done = client.post("/api/v1/me/rules/run", json={"confirm": True}).json()
    assert done["done"] == {"archived": 1} and done["failed"] == 0
    assert bridge.messages[1]["folder"] == "Archive" and bridge.messages[3]["folder"] == "INBOX"
    assert client.post("/api/v1/me/rules/run", json={}).json()["total"] == 0


def test_run_on_existing_mail_is_written_to_the_log_without_any_mail_content(env):
    appm, client, bridge, _ = env
    synced(client, bridge)
    post(client, sender=ALICE, action="archived")
    seen = []
    appm.vault.audit_hooks.append(lambda event: seen.append(dict(event)))
    client.post("/api/v1/me/rules/run", json={"confirm": True})
    ran = [e for e in seen if e.get("event") == "rules_run_on_existing"]
    assert len(ran) == 1 and ran[0]["done"] == 1
    assert "Quarterly" not in repr(seen) and ALICE not in repr(seen)


def test_run_on_existing_mail_needs_sign_in_and_is_limited(env):
    appm, client, bridge, _ = env
    from fastapi.testclient import TestClient
    anon = TestClient(appm.app, raise_server_exceptions=False)
    assert anon.post("/api/v1/me/rules/run", json={"confirm": True}).status_code == 401
    assert anon.post("/api/v1/me/rules/preview", json=spec(sender=ALICE)).status_code == 401
    assert client.post("/api/v1/me/rules/run", json={"confirm": True}).status_code == 200
    for _ in range(2):
        client.post("/api/v1/me/rules/run", json={"confirm": True})
    assert client.post("/api/v1/me/rules/run", json={"confirm": True}).status_code == 429
    assert client.post("/api/v1/me/rules/run", json={"confirm": False, "extra": 1}).status_code == 422


def test_older_stored_mail_without_the_new_facts_does_not_fit_those_conditions():
    from backend.mail.rules import fits
    old = {}
    assert fits({"sender": "", "to": "x@example.invalid"}, ALICE, "s", old) is False
    assert fits({"sender": "", "list": "news"}, ALICE, "s", old) is False
    assert fits({"sender": "", "larger_mb": 1}, ALICE, "s", old) is False
    assert fits({"sender": ALICE, "not_subject": "x"}, ALICE, "s", old) is True
