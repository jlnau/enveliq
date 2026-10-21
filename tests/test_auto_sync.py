"""Automatic sync: runs only while the vault is unlocked, never keeps it unlocked, and backs off on failure."""
from __future__ import annotations

import time

import pytest

from fake_bridge import raw_email
from helpers import load_app, setup_admin
from test_bridge import MAILBOX, add_account, mails
from test_llm import FakeModel
from test_summaries import account, start


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def auto(appm, minutes=5):
    from backend.mail.scheduler import AutoSync
    clock = Clock()
    return AutoSync(appm.vault, appm.mail_service, minutes, clock=clock), clock


@pytest.fixture
def env(tmp_path):
    model = FakeModel()
    appm, client, bridge = start(tmp_path, model)
    yield appm, client, bridge, model
    bridge.close()
    model.close()


def listed(client, aid):
    return client.get(f"/api/v1/accounts/{aid}/messages").json()


def test_a_pass_syncs_and_summarises_then_waits_until_due(env):
    appm, client, bridge, model = env
    aid = account(client, bridge, ai=True)
    sync, clock = auto(appm)
    assert sync.run_once() == 1
    got = listed(client, aid)
    from backend.mail.service import PLACEHOLDER_SUMMARY
    assert len(got) == 3 and all(not m["summary"].startswith(PLACEHOLDER_SUMMARY) for m in got)
    state = sync.status_for({aid})["accounts"][aid]
    assert state["ok"] and state["added"] == 3 and state["summarised"] >= 1
    assert sync.run_once() == 0                                   # not due yet
    bridge.add(9, raw_email("Brand new", "Zed <zed@example.invalid>", MAILBOX, message_id="<new9@example.invalid>", body="Hi.\n"))
    clock.now += 5 * 60 + 1
    assert sync.run_once() == 1
    assert "Brand new" in {m["subject"] for m in listed(client, aid)}


def test_a_mailbox_can_opt_out(env):
    appm, client, bridge, _ = env
    aid = add_account(client, bridge, settings={"smtp_port": bridge.smtp_port, "send_identities": [], "auto_sync": False})
    sync, _ = auto(appm)
    assert sync.run_once() == 0 and listed(client, aid) == []


def test_it_can_be_switched_off(env):
    appm, client, bridge, _ = env
    add_account(client, bridge)
    sync, _ = auto(appm, minutes=0)
    assert not sync.enabled and sync.run_once() == 0
    assert sync.status_for(set()) == {"enabled": False, "minutes": 0, "source": "environment", "accounts": {}}


def test_a_failing_mailbox_backs_off_and_recovers(env):
    appm, client, bridge, _ = env
    aid = add_account(client, bridge, port=bridge.imap_port + 1)       # nothing listens there
    sync, clock = auto(appm)
    assert sync.run_once() == 1
    assert sync.status_for({aid})["accounts"][aid]["ok"] is False
    first = sync._next[aid] - clock.now
    clock.now = sync._next[aid] + 1
    assert sync.run_once() == 1
    assert sync._next[aid] - clock.now > first                          # waits longer each time
    assert "127.0.0.1" not in str(sync.state) and "password" not in str(sync.state).lower()


def test_nothing_runs_while_the_vault_is_locked(env):
    appm, client, bridge, _ = env
    add_account(client, bridge)
    sync, _ = auto(appm)
    appm.vault.lock()
    assert sync.run_once() == 0


def test_background_work_does_not_keep_the_vault_unlocked(env):
    appm, client, bridge, _ = env
    add_account(client, bridge)
    sync, _ = auto(appm)
    appm.vault._last_activity = time.monotonic() - 100
    before = appm.vault._last_activity
    assert sync.run_once() == 1
    assert appm.vault._last_activity == before                          # the idle clock did not move
    appm.vault.list_accounts()
    assert appm.vault._last_activity > before                           # ordinary use still does


def test_status_shows_only_your_own_mailboxes(env):
    appm, client, bridge, _ = env
    aid = add_account(client, bridge)
    appm.auto_sync.minutes = 5
    appm.auto_sync.state[aid] = {"ok": True, "added": 1, "removed": 0, "summarised": 0, "at": 1.0}
    r = client.get("/api/v1/sync/status")
    assert r.status_code == 200 and aid in r.json()["accounts"]
    appm.auto_sync.state["00000000-0000-0000-0000-000000000000"] = {"ok": True}
    assert "00000000-0000-0000-0000-000000000000" not in client.get("/api/v1/sync/status").json()["accounts"]


def test_an_administrator_can_set_the_interval_in_the_app(env):
    appm, client, bridge, _ = env
    r = client.get("/api/v1/sync/status").json()
    assert r["minutes"] == 10 and r["source"] == "default" and r["editable"] is True
    assert client.put("/api/v1/sync/config", json={"minutes": 30}).status_code == 200
    r = client.get("/api/v1/sync/status").json()
    assert r["minutes"] == 30 and r["source"] == "saved"
    assert client.put("/api/v1/sync/config", json={"minutes": 1}).json()["minutes"] == 2     # raised to the minimum
    assert client.put("/api/v1/sync/config", json={"minutes": 0}).status_code == 200
    assert client.get("/api/v1/sync/status").json()["enabled"] is False
    assert client.put("/api/v1/sync/config", json={"minutes": 5000}).status_code == 422


def test_the_environment_wins_and_cannot_be_overwritten(tmp_path):
    from helpers import create_user, sign_in
    bridge_dir = tmp_path
    appm, client, bridge = start(bridge_dir, None, ENVELIQ_SYNC_MINUTES="7")
    try:
        r = client.get("/api/v1/sync/status").json()
        assert r["minutes"] == 7 and r["source"] == "environment" and r["editable"] is False
        assert client.put("/api/v1/sync/config", json={"minutes": 3}).status_code == 409
    finally:
        bridge.close()


class Recorder:
    def __init__(self):
        self.calls = []

    def send(self, user_id, new):
        self.calls.append((user_id, new))
        return 1


def test_new_mail_found_by_a_pass_is_announced_but_mail_already_waiting_is_not(env):
    appm, client, bridge, _ = env
    aid = account(client, bridge, ai=False)
    sync, clock = auto(appm)
    sync.mail_alerts = rec = Recorder()
    assert sync.run_once() == 1
    assert len(listed(client, aid)) == 3 and rec.calls == []          # the first read of a new mailbox is not "new mail"
    bridge.add(9, raw_email("Brand new", "Zed <zed@example.invalid>", MAILBOX, message_id="<new9@example.invalid>", body="Hi.\n"))
    clock.now += 5 * 60 + 1
    assert sync.run_once() == 1
    assert len(rec.calls) == 1
    uid, new = rec.calls[0]
    assert uid == appm.vault.list_users()[0]["id"] and [m["subject"] for m in new] == ["Brand new"]
    assert set(new[0]) == {"account_id", "id", "sender_display", "sender_address", "subject", "priority", "action_required", "act_today"}  # internal filtering metadata; no summary or body
    assert new[0]["account_id"] == aid
    clock.now += 5 * 60 + 1
    sync.run_once()
    assert len(rec.calls) == 1                                          # nothing new, nothing sent


def test_the_alert_settings_start_off_and_are_saved(env):
    appm, client, bridge, _ = env
    s = client.get("/api/v1/me/notifications").json()["settings"]
    assert s["mail_on"] is False and s["mail_details"] is False
    r = client.put("/api/v1/me/notifications/settings", json={"mail_on": True})
    assert r.status_code == 200 and r.json()["settings"]["mail_on"] is True and r.json()["settings"]["mail_details"] is False


def test_the_install_manifest_is_public_and_its_icons_are_served(env):
    appm, client, bridge, _ = env
    r = client.get("/manifest.webmanifest")
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/manifest+json")
    m = r.json()
    assert m["name"] == "Enveliq" and m["display"] == "standalone"
    for icon in m["icons"]:
        got = client.get(icon["src"])
        assert got.status_code == 200 and got.headers["content-type"] == "image/png" and got.content[:4] == b"\x89PNG"
    assert "manifest-src 'self'" in client.get("/login").headers["content-security-policy"]
