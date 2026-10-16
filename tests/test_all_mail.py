"""All emails: the last 60 days of the inbox as quiet entries, Generate summary, and the line it waits in."""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime

import pytest

from test_bridge import mails
from test_summaries import GOOD, SECRET_WORDS, account, messages, start  # noqa: F401
from test_llm import FakeModel
from backend.mail.errors import BridgeError
from backend.mail.summary_queue import SummaryQueue


def read_mail(subject, days_ago, uid_id, body="Read text.\n"):
    when = format_datetime(datetime.now(timezone.utc) - timedelta(days=days_ago))
    return (f"From: Dana <dana@example.invalid>\nTo: me@example.invalid\nSubject: {subject}\nDate: {when}\n"
            f"Message-ID: <{uid_id}@example.invalid>\n\n{body}").replace("\n", "\r\n").encode()


@pytest.fixture
def env(tmp_path):
    model = FakeModel()
    appm, client, bridge = start(tmp_path, model)
    yield appm, client, bridge, model
    bridge.close()
    model.close()


def with_read_mail(bridge):
    for uid, subject, days in ((601, "Read yesterday", 1), (602, "Read last week", 9), (603, "Read long ago", 30), (604, "Read outside window", 75)):
        bridge.add(uid, read_mail(subject, days, f"r{uid}", SECRET_WORDS))
        bridge.messages[uid]["flags"].add("\\Seen")


def wait_done(appm, client, timeout=10):
    end = time.time() + timeout
    while time.time() < end:
        q = client.get("/api/v1/me/summary-queue").json()
        if q["waiting"] == 0 and q["writing"] == 0:
            return q
        time.sleep(0.05)
    raise AssertionError("the queue did not finish")


def test_recent_mail_is_listed_quietly_and_only_for_60_days(env):
    _, client, bridge, model = env
    aid = account(client, bridge)
    client.post(f"/api/v1/accounts/{aid}/sync", json={})
    with_read_mail(bridge)
    r = client.post(f"/api/v1/accounts/{aid}/inbox/recent")
    assert r.status_code == 200, r.text
    assert r.json()["added"] == 3
    msgs = messages(client, aid)
    assert msgs["Read yesterday"]["from_all_mail"] is True and msgs["Read yesterday"]["summary"].startswith("Not summarised yet")
    assert "Read long ago" in msgs and "Read outside window" not in msgs and msgs["Quarterly update"]["from_all_mail"] is False        # the unread ones keep their normal place
    assert client.post(f"/api/v1/accounts/{aid}/inbox/recent").json()["added"] == 0                  # nothing is added twice
    assert model.requests == []                                                                      # listing never calls the AI


def test_sync_and_automatic_summaries_leave_the_quiet_entries_alone(env):
    _, client, bridge, model = env
    aid = account(client, bridge)
    with_read_mail(bridge)
    client.post(f"/api/v1/accounts/{aid}/sync", json={})
    client.post(f"/api/v1/accounts/{aid}/inbox/recent")
    client.post(f"/api/v1/accounts/{aid}/sync", json={})
    assert "Read yesterday" in messages(client, aid)                                                  # not "no longer unread" to the sync
    assert client.post(f"/api/v1/accounts/{aid}/summarise", json={}).json()["summarised"] == 3        # only the three unread emails
    assert messages(client, aid)["Read yesterday"]["summary"].startswith("Not summarised yet")


def test_generate_summary_goes_through_the_line_and_keeps_no_text(env):
    appm, client, bridge, model = env
    aid = account(client, bridge)
    with_read_mail(bridge)
    client.post(f"/api/v1/accounts/{aid}/inbox/recent")
    msgs = messages(client, aid)
    ids = [msgs["Read yesterday"]["id"], msgs["Read last week"]["id"]]
    for mid in ids:
        r = client.post(f"/api/v1/accounts/{aid}/messages/{mid}/summary")
        assert r.status_code == 202
    wait_done(appm, client)
    after = messages(client, aid)
    assert after["Read yesterday"]["summary"] == GOOD["summary"] and after["Read yesterday"]["from_all_mail"] is True
    assert after["Read last week"]["summary"] == GOOD["summary"]
    assert SECRET_WORDS not in str(after)
    assert len(model.requests) == 2
    listing = client.get("/api/v1/me/summary-queue").json()
    assert all(i["state"] == "done" for i in listing["items"])


def test_generate_summary_refuses_when_the_feature_is_off_or_no_model(env):
    _, client, bridge, _ = env
    aid = account(client, bridge)
    with_read_mail(bridge)
    client.post(f"/api/v1/accounts/{aid}/inbox/recent")
    mid = messages(client, aid)["Read yesterday"]["id"]
    client.put("/api/v1/me/features", json={"all_mail": False})
    assert client.post(f"/api/v1/accounts/{aid}/messages/{mid}/summary").status_code == 403
    assert client.post(f"/api/v1/accounts/{aid}/inbox/recent").status_code == 403
    assert "Read yesterday" not in messages(client, aid)             # switching it off forgets the quiet entries


def test_a_reviewed_quiet_entry_becomes_an_ordinary_kept_card(env):
    _, client, bridge, _ = env
    aid = account(client, bridge)
    with_read_mail(bridge)
    client.post(f"/api/v1/accounts/{aid}/inbox/recent")
    mid = messages(client, aid)["Read yesterday"]["id"]
    assert client.post(f"/api/v1/accounts/{aid}/messages/{mid}/resolve", json={"outcome": "reviewed"}).status_code == 204
    kept = messages(client, aid).get("Read yesterday")
    assert kept is None or (kept["state"] == "reviewed" and kept["from_all_mail"] is False)


# ---------- the line itself ----------

def test_the_line_is_first_come_first_served_one_at_a_time_and_survives_listing(_=None):
    ran = []
    q = SummaryQueue(lambda a, m: ran.append(m), autostart=False)
    for m in ("m1", "m2", "m3"):
        q.add("u1", "a1", m)
    q.add("u2", "a1", "other")
    mine = q.listing("u1")
    assert [i["position"] for i in mine["items"]] == [1, 2, 3] and mine["waiting"] == 3 and mine["writing"] == 0
    assert q.add("u1", "a1", "m1").state == "waiting" and len(q.listing("u1")["items"]) == 3        # pressing twice does not queue twice
    assert q.cancel("u1", "a1", "m2") and not q.cancel("u2", "a1", "m1")
    while q.work_once():
        pass
    assert ran == ["m1", "m3", "other"] and all(i["state"] == "done" for i in q.listing("u1")["items"])


def test_a_failed_request_is_listed_with_its_reason_and_can_be_retried(_=None):
    calls = []

    def run(a, m):
        calls.append(m)
        if len(calls) == 1:
            raise BridgeError("ai_unreachable", "The AI server could not be reached.")

    q = SummaryQueue(run, autostart=False)
    q.add("u1", "a1", "m1")
    q.work_once()
    item = q.listing("u1")["items"][0]
    assert item["state"] == "failed" and "could not be reached" in item["error"]
    q.add("u1", "a1", "m1")
    assert q.listing("u1")["items"][0]["state"] == "waiting"
    q.work_once()
    assert q.listing("u1")["items"][0]["state"] == "done"


def test_nobody_can_fill_the_line(_=None):
    q = SummaryQueue(lambda a, m: None, autostart=False)
    for i in range(50):
        q.add("u1", "a1", f"m{i}")
    with pytest.raises(BridgeError):
        q.add("u1", "a1", "one-too-many")
    q.add("u2", "a1", "fine")


def test_another_person_cannot_use_my_mailbox_through_the_new_routes(env):
    from helpers import create_user, sign_in
    appm, client, bridge, model = env
    aid = account(client, bridge)
    with_read_mail(bridge)
    client.post(f"/api/v1/accounts/{aid}/inbox/recent")
    mid = messages(client, aid)["Read yesterday"]["id"]
    client.post(f"/api/v1/accounts/{aid}/messages/{mid}/summary")
    wait_done(appm, client)
    create_user(client, "sam")
    other = sign_in(appm, "sam")
    base = f"/api/v1/accounts/{aid}"
    for method, url in (("post", f"{base}/inbox/recent"), ("post", f"{base}/messages/{mid}/summary"), ("delete", f"{base}/messages/{mid}/summary"),
                        ("get", f"{base}/messages/{mid}/attachments/0/view")):
        assert getattr(other, method)(url).status_code in (403, 404), url
    assert other.get("/api/v1/me/summary-queue").json()["items"] == []        # nobody else's line is visible
    assert len(model.requests) == 1


def test_listing_and_summaries_never_change_the_mailbox(env):
    appm, client, bridge, _ = env
    aid = account(client, bridge)
    with_read_mail(bridge)
    client.post(f"/api/v1/accounts/{aid}/inbox/recent")
    mid = messages(client, aid)["Read yesterday"]["id"]
    client.post(f"/api/v1/accounts/{aid}/messages/{mid}/summary")
    wait_done(appm, client)
    assert not any(w in line for line in bridge.log for w in ("STORE", "APPEND", "EXPUNGE", "COPY", "MOVE"))
    assert appm.vault.plaintext_scan(["Read yesterday", "dana@example.invalid", SECRET_WORDS]) == {"Read yesterday": False, "dana@example.invalid": False, SECRET_WORDS: False}
