"""Snooze: keep an email out of the inbox list until a time the person picked. Only Enveliq's own record changes."""
from __future__ import annotations

import time

import pytest

from helpers import create_user, sign_in
from test_llm import FakeModel
from test_review import by_state, resolve
from test_summaries import start, synced as synced_ai

HOUR, DAY = 3600, 86400


@pytest.fixture
def env(tmp_path):
    model = FakeModel()
    appm, client, bridge = start(tmp_path, model)
    aid = synced_ai(client, bridge)
    yield appm, client, bridge, aid
    bridge.close()
    model.close()


def snooze(client, aid, mid, until):
    return client.post(f"/api/v1/accounts/{aid}/messages/{mid}/snooze", json={"until": until})


def test_snoozing_is_remembered_and_leaves_the_real_mailbox_alone(env):
    appm, client, bridge, aid = env
    mail = by_state(client, aid)["unread"]["Weekly news"]
    until = time.time() + 3 * HOUR
    r = snooze(client, aid, mail["id"], until)
    assert r.status_code == 200 and abs(r.json()["snoozed_until"] - until) < 1
    again = by_state(client, aid)["unread"]["Weekly news"]
    assert abs(again["snoozed_until"] - until) < 1 and again["state"] == "unread"
    assert all("\\Seen" not in m["flags"] for m in bridge.messages.values())          # nothing was marked read or moved
    assert client.post(f"/api/v1/accounts/{aid}/sync", json={}).json()["added"] == 0   # a sync does not forget it or add it twice
    assert abs(by_state(client, aid)["unread"]["Weekly news"]["snoozed_until"] - until) < 1


def test_it_can_be_brought_back_now(env):
    _, client, _, aid = env
    mail = by_state(client, aid)["unread"]["Weekly news"]
    snooze(client, aid, mail["id"], time.time() + HOUR)
    assert snooze(client, aid, mail["id"], None).status_code == 200
    assert by_state(client, aid)["unread"]["Weekly news"]["snoozed_until"] is None


def test_only_a_sensible_time_is_accepted(env):
    _, client, _, aid = env
    mail = by_state(client, aid)["unread"]["Weekly news"]
    assert snooze(client, aid, mail["id"], time.time() - 10).status_code == 422
    assert snooze(client, aid, mail["id"], time.time() + 400 * DAY).status_code == 422
    assert client.post(f"/api/v1/accounts/{aid}/messages/{mail['id']}/snooze", json={"until": "tomorrow"}).status_code == 422
    assert by_state(client, aid)["unread"]["Weekly news"]["snoozed_until"] is None


def test_a_handled_email_loses_its_snooze_and_cannot_be_snoozed(env):
    _, client, _, aid = env
    mail = by_state(client, aid)["unread"]["Weekly news"]
    snooze(client, aid, mail["id"], time.time() + HOUR)
    assert resolve(client, aid, mail["id"], "reviewed").status_code == 204
    card = by_state(client, aid)["reviewed"]["Weekly news"]
    assert card["snoozed_until"] is None
    assert snooze(client, aid, card["id"], time.time() + HOUR).status_code == 409


def test_nobody_else_can_snooze_my_mail(env):
    appm, client, _, aid = env
    mail = by_state(client, aid)["unread"]["Weekly news"]
    create_user(client, "cara")
    other = sign_in(appm, "cara")
    assert snooze(other, aid, mail["id"], time.time() + HOUR).status_code in (403, 404)
    assert by_state(client, aid)["unread"]["Weekly news"]["snoozed_until"] is None
