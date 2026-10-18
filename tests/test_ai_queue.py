"""The AI queue: new mail waits out of the inbox until its summary and the summaries of its files are ready."""
from __future__ import annotations

import json
import time

import pytest

from fake_bridge import FakeBridge
from test_attachment_flag import PLAIN
from test_bridge import html_mail
from test_llm import GOOD, FakeModel
from test_summaries import account, messages, start  # noqa: F401
from backend.models import RetainedMessageCreate


_real_sleep = time.sleep                                   # the tests below replace time.sleep for the server; waiting here stays real


def wait_for(check, seconds=20.0):
    end = time.time() + seconds
    while time.time() < end:
        got = check()
        if got:
            return got
        _real_sleep(0.05)
    raise AssertionError("it did not happen in time")


@pytest.fixture
def held(tmp_path, monkeypatch):
    from backend.mail import extra_routes
    monkeypatch.setattr(extra_routes.time, "sleep", lambda s: None)       # no waiting between tries in a test
    model = FakeModel()
    appm, client, bridge = start(tmp_path, model)
    appm.mail_service.hold_new_mail = True
    for uid in list(bridge.messages):
        del bridge.messages[uid]
    yield appm, client, bridge, model
    bridge.close()
    model.close()


def listing(client, aid):
    return client.get(f"/api/v1/accounts/{aid}/messages").json()


def test_new_mail_is_not_listed_until_its_summary_is_ready_and_then_has_it(held):
    appm, client, bridge, model = held
    bridge.add(1, PLAIN)
    aid = account(client, bridge)
    assert client.post(f"/api/v1/accounts/{aid}/sync", json={}).json()["added"] == 1
    first = wait_for(lambda: listing(client, aid))             # it appears only when ready...
    assert len(first) == 1 and first[0]["summary"] == GOOD["summary"] and first[0]["ai_pending"] is False


def test_an_email_with_files_appears_only_after_its_files_are_done(held):
    appm, client, bridge, model = held
    bridge.add(2, html_mail())
    aid = account(client, bridge)
    client.post(f"/api/v1/accounts/{aid}/sync", json={})
    first = wait_for(lambda: listing(client, aid))
    only = first[0]
    assert only["summary"] == GOOD["summary"]
    assert [r["filename"] for r in only["attachment_summaries"]] == ["report.pdf"]      # already there the first time it can be seen
    assert only["attachment_count"] == 1


def test_the_list_is_empty_while_the_email_waits(held):
    appm, client, bridge, model = held
    bridge.add(3, PLAIN)
    aid = account(client, bridge)
    appm.mail_service.on_pending, real = (lambda acct, ids: None), appm.mail_service.on_pending      # nobody works the line yet
    client.post(f"/api/v1/accounts/{aid}/sync", json={})
    stored = appm.vault.list_messages(aid)
    assert len(stored) == 1 and stored[0]["ai_pending"] is True
    assert listing(client, aid) == []
    appm.mail_service.on_pending = real
    assert len(wait_for(lambda: listing(client, aid))) == 1                                  # a later look puts it in the line after a restart


def test_nothing_is_held_when_the_mailbox_does_not_use_ai_summaries(held):
    appm, client, bridge, model = held
    bridge.add(4, PLAIN)
    aid = account(client, bridge, ai=False)
    client.post(f"/api/v1/accounts/{aid}/sync", json={})
    shown = listing(client, aid)
    assert len(shown) == 1 and shown[0]["ai_pending"] is False


def test_held_mail_is_shown_as_it_is_when_the_mailbox_stops_using_summaries(held):
    appm, client, bridge, model = held
    aid = account(client, bridge, ai=False)
    body = RetainedMessageCreate(subject="Waiting", summary="Not summarised yet.", ai_pending=True)
    appm.vault.create_message(aid, body.model_dump(mode="python"))
    assert [m["subject"] for m in listing(client, aid)] == ["Waiting"]


def test_a_summary_that_keeps_failing_still_shows_the_email_and_says_why(tmp_path, monkeypatch):
    from backend.mail import extra_routes
    monkeypatch.setattr(extra_routes.time, "sleep", lambda s: None)
    model = FakeModel(reply="I cannot help with that.")
    appm, client, bridge = start(tmp_path, model)
    try:
        appm.mail_service.hold_new_mail = True
        for uid in list(bridge.messages):
            del bridge.messages[uid]
        bridge.add(5, PLAIN)
        aid = account(client, bridge)
        client.post(f"/api/v1/accounts/{aid}/sync", json={})
        shown = wait_for(lambda: listing(client, aid))
        assert shown[0]["summary"].startswith("Not summarised yet") and shown[0]["ai_pending"] is False
        assert len(model.requests) >= 3                                                  # it was tried more than once
        item = wait_for(lambda: next((i for i in client.get("/api/v1/me/summary-queue").json()["items"] if i["state"] == "failed"), None))
        assert "not in a form" in item["error"] and item["auto"] is True
    finally:
        bridge.close()
        model.close()


def test_handled_mail_is_not_hidden(held):
    appm, client, bridge, model = held
    aid = account(client, bridge)
    body = RetainedMessageCreate(subject="Archived by a rule", summary="Not summarised yet.", ai_pending=True, state="archived", resolved_at=time.time())
    appm.vault.create_message(aid, body.model_dump(mode="python"))
    assert [m["subject"] for m in listing(client, aid)] == ["Archived by a rule"]


def test_the_queue_shows_new_mail_waiting_and_only_to_its_owner(held):
    appm, client, bridge, model = held
    from backend.mail.summary_queue import SummaryQueue
    q = SummaryQueue(lambda a, m: None, autostart=False)
    q.add("sam", "a1", "m1", auto=True)
    q.add("sam", "a1", "m2")
    assert q.listing("sam")["new_mail"] == 1 and q.listing("sam")["waiting"] == 2
    assert q.listing("someone-else")["items"] == [] and q.listing("someone-else")["new_mail"] == 0


def test_new_mail_waiting_does_not_count_against_the_button_limit():
    from backend.mail.summary_queue import MAX_WAITING, SummaryQueue
    q = SummaryQueue(lambda a, m: None, autostart=False)
    for i in range(MAX_WAITING + 5):
        q.add("sam", "a1", f"auto{i}", auto=True)
    q.add("sam", "a1", "pressed")                                     # still allowed
    assert q.listing("sam")["waiting"] == MAX_WAITING + 6


# ---------- unread emails that still have no summary are tried again, and the reason is said when they cannot be ----------

def _with_summaries(appm, aid, on=True):
    acct = appm.vault.get_account(aid)
    return {**acct, "settings": {**(acct.get("settings") or {}), "ai_summaries": on}}


def _placeholder_mail(held, ai=False):
    appm, client, bridge, model = held
    bridge.add(1, PLAIN)
    aid = account(client, bridge, ai=ai)
    assert client.post(f"/api/v1/accounts/{aid}/sync", json={}).json()["added"] == 1
    got = listing(client, aid)
    assert len(got) == 1 and got[0]["summary"].startswith("Not summarised yet")
    return appm, client, aid


def test_mail_that_arrived_before_summaries_were_switched_on_is_summarised_by_the_next_sync(held):
    appm, client, aid = _placeholder_mail(held, ai=False)
    acct = _with_summaries(appm, aid)
    assert appm.mail_service.enqueue_unsummarised(appm.vault, acct) == 1
    done = wait_for(lambda: [m for m in listing(client, aid) if m["summary"] == GOOD["summary"]])
    assert len(done) == 1


def test_a_failed_try_is_repeated_with_waits_and_then_stops_with_a_reason(held):
    appm, client, aid = _placeholder_mail(held, ai=False)
    svc, acct = appm.mail_service, _with_summaries(appm, aid)
    queued: list[str] = []
    svc.on_pending = lambda account, ids: queued.extend(ids)         # nobody works the line: only count the tries
    now = 1000.0
    assert svc.enqueue_unsummarised(appm.vault, acct, now) == 1
    assert svc.enqueue_unsummarised(appm.vault, acct, now + 10) == 0                 # too soon
    for step in svc.RETRY_DELAYS:
        now += step + 1
        assert svc.enqueue_unsummarised(appm.vault, acct, now) == 1
    now += 100000
    assert svc.enqueue_unsummarised(appm.vault, acct, now) == 0                      # gave up
    assert len(queued) == len(svc.RETRY_DELAYS) + 1
    svc.problems[queued[0]] = "The AI model did not answer."
    notice = svc.summary_notice(appm.vault, appm.vault.get_account(aid)["owner_user_id"])
    assert notice and notice["retrying"] is False and "tried several times" in notice["text"] and "did not answer" in notice["text"]
    svc.retry_now(queued[0])                                                          # Try again starts the count over
    assert svc.enqueue_unsummarised(appm.vault, acct, now) == 1


def test_the_reason_is_said_when_no_model_is_set_up_or_summaries_are_off(held):
    appm, client, aid = _placeholder_mail(held, ai=False)
    svc, user = appm.mail_service, appm.vault.get_account(aid)["owner_user_id"]
    assert "switched off for this mailbox" in svc.summary_notice(appm.vault, user)["text"]
    assert svc.enqueue_unsummarised(appm.vault, appm.vault.get_account(aid)) == 0      # nothing is tried while it cannot work
    acct = _with_summaries(appm, aid)
    assert svc.summary_notice(appm.vault, "someone-else") is None                      # nobody else's mailbox is described
    svc.summariser.config = type(svc.summariser.config)()                              # no model
    assert svc.enqueue_unsummarised(appm.vault, acct) == 0


def test_the_queue_route_carries_the_notice_only_for_the_signed_in_person(held):
    appm, client, aid = _placeholder_mail(held, ai=False)
    r = client.get("/api/v1/me/summary-queue").json()
    assert r["notice"]["count"] == 1 and "switched off" in r["notice"]["text"]
