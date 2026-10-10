"""Tasks that make themselves: made from summaries, followed to the email's fate, moved with one tap."""
from __future__ import annotations

import time
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from test_bridge import mails  # noqa: F401
from test_summaries import account, messages, start  # noqa: F401
from test_llm import FakeModel
from backend.mail import tasks as T


@pytest.fixture
def env(tmp_path):
    model = FakeModel()
    appm, client, bridge = start(tmp_path, model)
    yield appm, client, bridge, model
    bridge.close()
    model.close()


def summarised(client, bridge):
    aid = account(client, bridge)
    client.post(f"/api/v1/accounts/{aid}/sync", json={})
    r = client.post(f"/api/v1/accounts/{aid}/summarise", json={})
    assert r.status_code == 200, r.text
    return aid


def listing(client, tz="Australia/Sydney"):
    r = client.get("/api/v1/me/tasks", params={"tz": tz})
    assert r.status_code == 200, r.text
    return r.json()


def test_parse_due_reads_the_usual_words():
    ref, today = date(2026, 10, 7), date(2026, 10, 9)       # a Wednesday email, read on a Friday
    assert T.parse_due("Fri 9 Oct", ref, today) == date(2026, 10, 9)
    assert T.parse_due("October 12", ref, today) == date(2026, 10, 12)
    assert T.parse_due("2026-11-02", ref, today) == date(2026, 11, 2)
    assert T.parse_due("tomorrow", ref, today) == date(2026, 10, 8)
    assert T.parse_due("Friday", ref, today) == date(2026, 10, 9)
    assert T.parse_due("by Monday", ref, today) == date(2026, 10, 12)
    assert T.parse_due("ASAP", ref, today) == today                      # urgent words mean today, whenever the email was sent
    assert T.parse_due("end of the month", ref, today) is None           # "month" is not Monday
    assert T.parse_due("", ref, today) is None and T.parse_due(None, ref, today) is None
    assert T.parse_due("31 Feb", ref, today) is None


def test_a_task_appears_by_itself_when_the_summary_asks_for_one(env):
    _, client, bridge, _ = env
    aid = account(client, bridge)
    client.post(f"/api/v1/accounts/{aid}/sync", json={})
    assert listing(client)["tasks"] == []                                 # nothing to do until there is a summary
    client.post(f"/api/v1/accounts/{aid}/summarise", json={})
    out = listing(client)
    assert len(out["tasks"]) >= 1
    t = out["tasks"][0]
    assert t["title"] == "Arrive 10 minutes early" and t["state"] == "open" and t["due"].endswith("-10-09")
    assert t["detail"] == "Bring the health fund card." and t["sender"]
    assert out["tz"] == "Australia/Sydney" and len(listing(client)["tasks"]) == len(out["tasks"])      # looking again never adds another


def test_it_needs_a_signed_in_person(env):
    appm, _, _, _ = env
    from fastapi.testclient import TestClient
    anon = TestClient(appm.app)
    assert anon.get("/api/v1/me/tasks").status_code in (401, 403)
    assert anon.post("/api/v1/me/tasks/t" + "0" * 23 + "/done").status_code in (401, 403)


def test_done_reopen_and_remove(env):
    appm, client, bridge, _ = env
    summarised(client, bridge)
    tid = listing(client)["tasks"][0]["id"]
    assert client.post(f"/api/v1/me/tasks/{tid}/done").status_code == 200
    t = next(x for x in listing(client)["tasks"] if x["id"] == tid)
    assert t["state"] == "done" and t["reason"] == "you" and t["closed_at"]
    client.post(f"/api/v1/me/tasks/{tid}/reopen")
    assert next(x for x in listing(client)["tasks"] if x["id"] == tid)["state"] == "open"
    client.post(f"/api/v1/me/tasks/{tid}/remove")
    assert all(x["id"] != tid for x in listing(client)["tasks"])
    assert all(x["id"] != tid for x in listing(client)["tasks"])           # and it is not made again from the same email
    assert client.post("/api/v1/me/tasks/t" + "a" * 23 + "/done").status_code == 404
    assert client.post("/api/v1/me/tasks/not-an-id/done").status_code == 422


def test_moving_a_task_is_one_tap(env):
    appm, client, bridge, _ = env
    summarised(client, bridge)
    tz = ZoneInfo("Australia/Sydney")
    fixed = datetime(2026, 10, 9, 10, 0, tzinfo=tz).timestamp()               # a Friday morning
    appm.taskbook.clock = lambda: fixed
    tid = listing(client)["tasks"][0]["id"]

    def move(to, **body):
        r = client.post(f"/api/v1/me/tasks/{tid}/move", json={"to": to, **body})
        assert r.status_code == 200, r.text
        return next(x for x in r.json()["tasks"] if x["id"] == tid)

    t = move("later_today")
    assert t["due"] == "2026-10-09" and datetime.fromtimestamp(t["remind_at"], tz).hour == 18
    assert move("tomorrow")["due"] == "2026-10-10" and move("weekend")["due"] == "2026-10-10"
    assert move("next_week")["due"] == "2026-10-12"
    assert move("date", on="2026-11-01")["due"] == "2026-11-01"
    assert client.post(f"/api/v1/me/tasks/{tid}/move", json={"to": "date", "on": "2020-01-01"}).status_code == 422
    assert client.post(f"/api/v1/me/tasks/{tid}/move", json={"to": "soon"}).status_code == 422
    assert client.post(f"/api/v1/me/tasks/{tid}/move", json={}).status_code == 422
    r = client.post(f"/api/v1/me/tasks/{tid}/not_today")
    assert next(x for x in r.json()["tasks"] if x["id"] == tid)["due"] == "2026-10-10"
    appm.taskbook.clock = lambda: datetime(2026, 10, 9, 23, 0, tzinfo=tz).timestamp()          # too late for "later today"
    assert move("later_today")["due"] == "2026-10-10"


def test_a_missed_task_rolls_to_today_and_says_how_long_it_has_waited(env):
    appm, client, bridge, _ = env
    summarised(client, bridge)
    tz = ZoneInfo("Australia/Sydney")
    appm.taskbook.clock = lambda: datetime(2026, 10, 14, 9, 0, tzinfo=tz).timestamp()
    t = listing(client)["tasks"][0]
    assert t["state"] == "open" and t["days"] < 0                         # the client shows "Waiting since Fri", never "OVERDUE"


def test_dealing_with_the_email_ends_its_task(env):
    appm, client, bridge, _ = env
    aid = summarised(client, bridge)
    mid = next(m for m in client.get(f"/api/v1/accounts/{aid}/messages").json() if m.get("suggested_task"))["id"]
    assert any(x["message_id"] == mid for x in listing(client)["tasks"])
    r = client.post(f"/api/v1/accounts/{aid}/messages/{mid}/resolve", json={"outcome": "binned"})
    assert r.status_code == 204, r.text
    done = [x for x in listing(client)["tasks"] if x["message_id"] == mid]
    assert done and done[0]["state"] == "done" and done[0]["reason"] == "handled" and "dealt with" in done[0]["reason_text"]


def test_replying_ends_the_task(env):
    appm, client, bridge, _ = env
    aid = summarised(client, bridge)
    m = next(m for m in client.get(f"/api/v1/accounts/{aid}/messages").json() if m.get("suggested_task") and (m.get("reply_context") or {}).get("reply_to"))
    assert any(x["message_id"] == m["id"] for x in listing(client)["tasks"])
    r = client.post(f"/api/v1/accounts/{aid}/messages/{m['id']}/reply", json={"body": "On my way."})
    assert r.status_code == 200, r.text
    t = next(x for x in listing(client)["tasks"] if x["message_id"] == m["id"])
    assert t["state"] == "done" and t["reason"] == "replied"


def test_an_email_that_leaves_the_inbox_ends_its_task_and_finished_ones_are_tidied_away(env):
    appm, client, bridge, _ = env
    aid = summarised(client, bridge)
    mid = next(m for m in client.get(f"/api/v1/accounts/{aid}/messages").json() if m.get("suggested_task"))["id"]
    assert any(x["message_id"] == mid for x in listing(client)["tasks"])
    appm.vault.delete_message(aid, mid)                                    # deleted in another app and noticed by a sync
    t = next(x for x in listing(client)["tasks"] if x["message_id"] == mid)
    assert t["state"] == "done" and t["reason"] == "gone"
    appm.taskbook.clock = lambda: time.time() + 2 * 86400
    assert all(x["message_id"] != mid for x in listing(client)["tasks"])


def test_tasks_are_stored_encrypted_and_without_email_text(env):
    appm, client, bridge, _ = env
    summarised(client, bridge)
    t = listing(client)["tasks"][0]
    scan = appm.vault.plaintext_scan([t["title"], t["detail"]])
    assert not any(scan.values())
    assert set(t) >= {"title", "detail", "sender", "due"} and "body" not in t and "source_locator" not in t


def test_an_email_with_an_open_task_stays_even_when_read_elsewhere_until_the_task_is_done(env):
    appm, client, bridge, _ = env
    aid = summarised(client, bridge)
    m = next(m for m in client.get(f"/api/v1/accounts/{aid}/messages").json() if m.get("suggested_task"))
    listing(client)
    uid = int(appm.vault.get_message(aid, m["id"])["source_locator"].split("|")[2])
    bridge.messages[uid]["flags"] = list(bridge.messages[uid]["flags"]) + ["\\Seen"]          # read in another app
    client.post(f"/api/v1/accounts/{aid}/sync", json={})
    assert any(x["id"] == m["id"] for x in client.get(f"/api/v1/accounts/{aid}/messages").json())
    t = next(x for x in listing(client)["tasks"] if x["message_id"] == m["id"])
    assert t["state"] == "open"
    client.post(f"/api/v1/me/tasks/{t['id']}/done")
    client.post(f"/api/v1/accounts/{aid}/sync", json={})
    assert all(x["id"] != m["id"] for x in client.get(f"/api/v1/accounts/{aid}/messages").json())
