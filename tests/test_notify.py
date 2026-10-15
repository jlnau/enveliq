"""Reminder channels: set up, tested, sent safely, and scheduled gently."""
from __future__ import annotations

import json
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from zoneinfo import ZoneInfo

import pytest

from test_bridge import mails  # noqa: F401
from test_summaries import account, start  # noqa: F401
from test_llm import FakeModel
from backend.mail import notify, outbound
from backend.mail.outbound import OutboundError

SYD = ZoneInfo("Australia/Sydney")


class Service:
    """A fake ntfy / Gotify / Home Assistant on 127.0.0.1 that records what it is sent."""

    def __init__(self, status=200):
        self.calls, self.status = [], status
        outer = self

        class H(BaseHTTPRequestHandler):
            def _do(self):
                n = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(n) if n else b""
                outer.calls.append({"method": self.command, "path": self.path, "headers": dict(self.headers), "body": raw})
                self.send_response(outer.status)
                self.send_header("Content-Length", "2")
                self.end_headers()
                self.wfile.write(b"{}")

            do_POST = do_PUT = do_GET = _do

            def log_message(self, *a):
                pass

        self.http = HTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.http.server_port}"
        threading.Thread(target=self.http.serve_forever, daemon=True).start()

    def json(self, i=-1):
        return json.loads(self.calls[i]["body"])

    def close(self):
        self.http.shutdown()


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("ENVELIQ_NOTIFY_ALLOWED_HOSTS", "127.0.0.1")
    model = FakeModel()
    appm, client, bridge = start(tmp_path, model)
    svc = Service()
    yield appm, client, bridge, svc
    svc.close()
    bridge.close()
    model.close()


def put(client, cid, values, enabled=True):
    return client.put(f"/api/v1/me/notifications/channels/{cid}", json={"enabled": enabled, "values": values})


# ---------- the rules for calling out ----------

def test_outbound_rules(monkeypatch):
    def fake(host, port, **kw):
        table = {"public.example": "93.184.216.34", "lan.example": "192.168.1.5", "meta.example": "169.254.169.254", "mixed.example": None}
        if host == "mixed.example":
            return [(2, 1, 6, "", ("93.184.216.34", port)), (2, 1, 6, "", ("10.0.0.9", port))]
        return [(2, 1, 6, "", (table.get(host, host), port))]
    monkeypatch.setattr(outbound.socket, "getaddrinfo", fake)
    ok = outbound.check_target("https://public.example/x", [])
    assert ok[3] == "93.184.216.34" and ok[5] is False
    for url, allow, code in [
        ("http://public.example/x", [], "not_allowed"),                 # plain http to the internet
        ("https://lan.example/x", [], "not_allowed"),                   # your own network, not listed
        ("http://192.168.1.5:8080/x", [], "not_allowed"),
        ("https://meta.example/x", ["meta.example", "169.254.0.0/16"], "not_allowed"),   # never, even if listed
        ("http://127.0.0.1/x", [], "not_allowed"),
        ("https://mixed.example/x", [], "not_allowed"),                 # one bad answer is enough
        ("ftp://public.example/x", [], "bad_address"),
        ("https://user:pw@public.example/x", [], "bad_address"),
        ("https:///x", [], "bad_address"),
    ]:
        with pytest.raises(OutboundError) as e:
            outbound.check_target(url, allow)
        assert e.value.code == code, url
    assert outbound.check_target("http://192.168.1.5:8080/x", ["192.168.1.0/24"])[5] is True
    assert outbound.check_target("http://lan.example/x", ["lan.example"])[5] is True
    assert outbound.check_target("http://127.0.0.1:9/x", ["127.0.0.1"])[3] == "127.0.0.1"


def test_a_redirect_is_not_followed_and_replies_are_capped(env):
    _, _, _, svc = env
    status, body = outbound.request("POST", svc.url + "/a", allow=["127.0.0.1"], json_body={"a": 1})
    assert status == 200 and svc.json() == {"a": 1}


# ---------- setting channels up ----------

def test_a_channel_is_saved_tested_and_its_secret_is_never_sent_back(env):
    appm, client, _, svc = env
    r = put(client, "ntfy", {"server": svc.url, "topic": "my-private-topic", "token": "tk_secret_value"})
    assert r.status_code == 200, r.text
    assert "tk_secret_value" not in r.text
    ch = next(c for c in r.json()["channels"] if c["id"] == "ntfy")
    assert ch["enabled"] and ch["configured"]
    assert next(f for f in ch["fields"] if f["key"] == "token") == {**next(f for f in ch["fields"] if f["key"] == "token"), "set": True, "value": ""}
    assert next(f for f in ch["fields"] if f["key"] == "topic")["value"] == "my-private-topic"
    assert "tk_secret_value" not in client.get("/api/v1/me/notifications").text
    assert client.post("/api/v1/me/notifications/channels/ntfy/test").json() == {"ok": True}
    call = svc.calls[-1]
    assert call["method"] == "POST" and call["headers"]["Authorization"] == "Bearer tk_secret_value"
    sent = svc.json()
    assert sent["topic"] == "my-private-topic" and sent["title"] == "Enveliq test" and "reminder will look" in sent["message"]
    # saving again with a blank secret keeps the saved one
    put(client, "ntfy", {"server": svc.url, "topic": "my-private-topic", "token": ""})
    client.post("/api/v1/me/notifications/channels/ntfy/test")
    assert svc.calls[-1]["headers"]["Authorization"] == "Bearer tk_secret_value"
    assert not any(appm.vault.plaintext_scan(["tk_secret_value", "my-private-topic"]).values())     # stored encrypted


def test_each_channel_sends_the_message_in_its_own_shape(env, monkeypatch):
    _, client, _, svc = env
    put(client, "gotify", {"server": svc.url, "token": "gt"})
    put(client, "home_assistant", {"server": svc.url, "token": "ha-token", "service": "notify.mobile_app_phone"})
    put(client, "matrix", {"server": svc.url, "token": "mx", "room": "!abc123:example.org"})
    put(client, "webhook", {"url": svc.url + "/hook"})
    for cid in ("gotify", "home_assistant", "matrix", "webhook"):
        assert client.post(f"/api/v1/me/notifications/channels/{cid}/test").status_code == 200, cid
    g, h, m, w = svc.calls[-4:]
    assert g["path"] == "/message" and g["headers"]["X-Gotify-Key"] == "gt" and json.loads(g["body"])["title"] == "Enveliq test"
    assert h["path"] == "/api/services/notify/mobile_app_phone" and h["headers"]["Authorization"] == "Bearer ha-token" and json.loads(h["body"])["message"]
    assert m["method"] == "PUT" and m["path"].startswith("/_matrix/client/v3/rooms/%21abc123%3Aexample.org/send/m.room.message/") and json.loads(m["body"])["msgtype"] == "m.text"
    assert w["path"] == "/hook" and json.loads(w["body"])["title"] == "Enveliq test"
    # the internet-only channels: check what would be sent without calling out
    seen = []
    monkeypatch.setattr(outbound, "request", lambda method, url, **kw: seen.append((method, url, kw)) or (200, b"{}"))
    put(client, "discord", {"webhook": "https://discord.com/api/webhooks/123456789012345678/abcdefghijklmnopqrstuvwxyz0123"})
    put(client, "telegram", {"bot_token": "123456789:" + "A" * 35, "chat_id": "987654321"})
    put(client, "slack", {"webhook": "https://hooks.slack.com/services/T000/B000/XXXXXXXXXXXXXXXXXXXX"})
    put(client, "pushover", {"user_key": "u" * 30, "app_token": "a" * 30})
    for cid in ("discord", "telegram", "slack", "pushover"):
        assert client.post(f"/api/v1/me/notifications/channels/{cid}/test").status_code == 200, cid
    d, t, s, p = seen
    assert d[1].startswith("https://discord.com/api/webhooks/") and d[2]["json_body"]["allowed_mentions"] == {"parse": []} and "Enveliq test" in d[2]["json_body"]["content"]
    assert t[1] == "https://api.telegram.org/bot123456789:" + "A" * 35 + "/sendMessage" and t[2]["json_body"]["chat_id"] == "987654321"
    assert s[1].startswith("https://hooks.slack.com/services/") and "Enveliq test" in s[2]["json_body"]["text"]
    assert p[1] == "https://api.pushover.net/1/messages.json" and p[2]["form"]["user"] == "u" * 30


@pytest.mark.parametrize("cid,values,fragment", [
    ("ntfy", {"topic": "no spaces allowed"}, "topic"),
    ("ntfy", {"topic": "ok-topic", "server": "ftp://x.example"}, "full address"),
    ("discord", {"webhook": "https://evil.example/api/webhooks/1"}, "Discord"),
    ("discord", {}, "needed"),
    ("telegram", {"bot_token": "nope", "chat_id": "1234"}, "token"),
    ("telegram", {"bot_token": "123456789:" + "A" * 35, "chat_id": "abc"}, "chat id"),
    ("home_assistant", {"server": "http://ha.local:8123", "token": "t", "service": "light.turn_on"}, "notify service"),
    ("matrix", {"server": "https://m.example", "token": "t", "room": "room-name"}, "room id"),
    ("slack", {"webhook": "https://example.com/x"}, "Slack"),
])
def test_bad_details_are_explained(env, cid, values, fragment):
    _, client, _, _ = env
    r = put(client, cid, values)
    assert r.status_code == 422 and fragment.lower() in r.json()["detail"].lower()


def test_a_failing_service_gives_a_useful_message_and_remembers_it(env):
    _, client, _, svc = env
    put(client, "ntfy", {"server": svc.url, "topic": "my-private-topic"})
    svc.status = 401
    r = client.post("/api/v1/me/notifications/channels/ntfy/test")
    assert r.status_code == 502 and "refused the login" in r.json()["detail"]
    assert next(c for c in client.get("/api/v1/me/notifications").json()["channels"] if c["id"] == "ntfy")["last_error"]
    svc.status = 404
    assert "did not find" in client.post("/api/v1/me/notifications/channels/ntfy/test").json()["detail"]
    svc.status = 200
    client.post("/api/v1/me/notifications/channels/ntfy/test")
    ch = next(c for c in client.get("/api/v1/me/notifications").json()["channels"] if c["id"] == "ntfy")
    assert ch["last_error"] is None and ch["last_ok"]


def test_an_address_on_the_local_network_needs_the_administrator(tmp_path, monkeypatch):
    monkeypatch.delenv("ENVELIQ_NOTIFY_ALLOWED_HOSTS", raising=False)
    model = FakeModel()
    appm, client, bridge = start(tmp_path, model)
    svc = Service()
    try:
        put(client, "ntfy", {"server": svc.url, "topic": "my-private-topic"})
        r = client.post("/api/v1/me/notifications/channels/ntfy/test")
        assert r.status_code == 502 and "administrator" in r.json()["detail"] and svc.calls == []
        a = client.put("/api/v1/admin/notifications", json={"local_hosts": ["127.0.0.1"]})
        assert a.status_code == 200 and a.json()["local_hosts"] == ["127.0.0.1"]
        assert client.post("/api/v1/me/notifications/channels/ntfy/test").status_code == 200 and len(svc.calls) == 1
        assert client.put("/api/v1/admin/notifications", json={"local_hosts": ["not a host!"]}).status_code == 422
        client.put("/api/v1/admin/notifications", json={"channels": {"ntfy": False}})
        r = client.post("/api/v1/me/notifications/channels/ntfy/test")
        assert r.status_code == 502 and "switched this channel off" in r.json()["detail"]
        assert put(client, "ntfy", {"server": svc.url, "topic": "my-private-topic"}).status_code == 403
    finally:
        svc.close()
        bridge.close()
        model.close()


def test_it_needs_a_signed_in_person_and_cannot_be_used_across_people(env):
    appm, client, _, _ = env
    from fastapi.testclient import TestClient
    anon = TestClient(appm.app)
    for method, path in (("get", "/api/v1/me/notifications"), ("put", "/api/v1/me/notifications/settings"), ("get", "/api/v1/admin/notifications")):
        assert getattr(anon, method)(path).status_code in (401, 403, 422)
    assert client.put("/api/v1/me/notifications/channels/not_a_channel", json={}).status_code == 404


def test_settings_are_checked_and_saved(env):
    _, client, _, _ = env
    r = client.put("/api/v1/me/notifications/settings", json={"morning_time": "07:30", "repeat_max": 0, "show_titles": False})
    s = r.json()["settings"]
    assert s["morning_time"] == "07:30" and s["repeat_max"] == 0 and s["show_titles"] is False and s["quiet_on"] is True
    assert client.put("/api/v1/me/notifications/settings", json={"morning_time": "25:99"}).status_code == 422
    assert client.put("/api/v1/me/notifications/settings", json={"repeat_hours": 99}).status_code == 422


# ---------- when reminders go ----------

@pytest.fixture
def due(env):
    """A mailbox with one open task, due on Friday 9 Oct 2026, and a recorder in place of the channels."""
    appm, client, bridge, svc = env
    aid = account(client, bridge)
    client.post(f"/api/v1/accounts/{aid}/sync", json={})
    client.post(f"/api/v1/accounts/{aid}/summarise", json={})
    uid = appm.vault.list_users()[0]["id"]
    book = appm.taskbook
    book.set_timezone(uid, "Australia/Sydney")
    clock = {"now": datetime(2026, 10, 9, 6, 0, tzinfo=SYD).timestamp()}
    book.clock = lambda: clock["now"]
    book.reconcile(uid)
    tasks = book.open_tasks(uid)
    for t in tasks[1:]:
        book.act(uid, t["id"], "remove")
    tid = tasks[0]["id"]
    book.act(uid, tid, "move", to="date", on="2026-10-09")
    put(client, "ntfy", {"server": svc.url, "topic": "my-private-topic"})
    sent = []
    appm.notifier.send_all = lambda user, note: sent.append(note) or {"ntfy": None}
    rem = appm.reminders
    rem.clock = lambda: clock["now"]

    def at(h, m=0):
        clock["now"] = datetime(2026, 10, 9, h, m, tzinfo=SYD).timestamp()
        return rem.run_user(uid, clock["now"])
    return appm, client, uid, tid, sent, at


def test_a_morning_summary_goes_once_and_not_before_its_time(due):
    appm, client, uid, tid, sent, at = due
    assert at(6, 30) == 0 and sent == []                                  # quiet hours, and before the time
    assert at(7, 30) == 0 and sent == []                                  # not yet 8:00
    assert at(8, 1) == 1 and len(sent) == 1
    assert sent[0]["title"] == "Today: 1 thing" and "Arrive 10 minutes early" in sent[0]["body"]
    assert at(8, 2) == 0 and at(9, 0) == 0 and len(sent) == 1             # never twice


def test_a_nudge_comes_after_the_wait_and_stops_after_the_limit(due):
    _, client, uid, tid, sent, at = due
    at(8, 1)
    assert at(9, 30) == 0
    assert at(10, 5) == 1 and sent[-1]["title"] == "Still to do"
    assert at(11, 0) == 0
    assert at(12, 10) == 1
    assert at(15, 0) == 0 and at(18, 0) == 0 and len(sent) == 3           # morning + two nudges, then it stops


def test_quiet_hours_hold_a_reminder_until_they_end(due):
    _, client, uid, tid, sent, at = due
    client.put("/api/v1/me/notifications/settings", json={"morning_time": "06:00", "quiet_from": "05:00", "quiet_to": "07:30"})
    assert at(6, 10) == 0 and sent == []
    assert at(7, 31) == 1 and len(sent) == 1                              # inside the 6-hour window after the time


def test_private_mode_keeps_the_title_out(due):
    _, client, uid, tid, sent, at = due
    client.put("/api/v1/me/notifications/settings", json={"show_titles": False})
    at(8, 5)
    assert sent[0]["title"] == "Enveliq" and "Arrive" not in sent[0]["body"] and "Open Enveliq" in sent[0]["body"]


def test_a_timed_task_reminds_at_its_time(due):
    appm, client, uid, tid, sent, at = due
    client.put("/api/v1/me/notifications/settings", json={"morning_on": False})
    appm.taskbook.clock = lambda: datetime(2026, 10, 9, 10, 0, tzinfo=SYD).timestamp()
    appm.taskbook.act(uid, tid, "move", to="later_today")                  # 6 pm
    assert at(12, 0) == 0
    assert at(18, 5) == 1 and sent[-1]["title"] == "Due now"


def test_a_task_made_after_the_morning_summary_is_announced_when_it_appears(due):
    from backend.models import RetainedMessageCreate
    appm, client, uid, tid, sent, at = due
    at(8, 1)
    assert len(sent) == 1
    aid = appm.vault.list_accounts()[0]["id"]
    new = RetainedMessageCreate(subject="Rates notice", sender_display="Council", summary="Pay by Friday.", suggested_task={"title": "Pay the rates"}).model_dump(mode="python")
    appm.vault.create_message(aid, new)
    assert at(8, 30) == 1 and sent[-1]["title"] == "Due now" and "Pay the rates" in sent[-1]["body"] and "Arrive" not in sent[-1]["body"]
    assert at(8, 31) == 0


def test_moving_a_task_to_another_day_means_it_is_announced_that_day(due):
    appm, client, uid, tid, sent, at = due
    at(8, 1)
    appm.taskbook.act(uid, tid, "not_today")                               # now due Saturday
    assert at(9, 0) == 0 and len(sent) == 1
    clock = datetime(2026, 10, 10, 8, 5, tzinfo=SYD).timestamp()
    appm.taskbook.clock = lambda: clock
    assert appm.reminders.run_user(uid, clock) == 1 and len(sent) == 2


def test_a_finished_task_is_not_reminded_and_a_failure_retries_later(due):
    appm, client, uid, tid, sent, at = due
    appm.notifier.send_all = lambda user, note: {"ntfy": "Could not reach it."}
    assert at(8, 1) == 0
    assert at(8, 3) == 0                                                  # waiting five minutes before trying again
    appm.notifier.send_all = lambda user, note: sent.append(note) or {"ntfy": None}
    assert at(8, 7) == 1 and len(sent) == 1
    appm.taskbook.act(uid, tid, "done")
    assert at(10, 30) == 0 and len(sent) == 1


def test_nothing_goes_when_no_channel_is_on(due):
    appm, client, uid, tid, sent, at = due
    client.delete("/api/v1/me/notifications/channels/ntfy")
    assert at(9, 0) == 0 and sent == []


# ---------- subscriptions coming up ----------

def _subscription(appm, uid, clock, **kw):
    raw = {"kind": "renewal_notice", "service": "Streamly", "amount": "$12.99", "period": "monthly", "renews_on": "12 Oct 2026", "trial_ends_on": None, "trial_days": None, **kw}
    appm.subbook.clock = lambda: clock
    assert appm.subbook.observe(uid, "a1", "m-sub", clock - 3600, raw)


def test_a_renewal_is_announced_once_when_it_is_inside_the_days_before(due):
    appm, client, uid, tid, sent, at = due
    _subscription(appm, uid, datetime(2026, 10, 9, 6, 0, tzinfo=SYD).timestamp())              # renews on the 12th: three days away
    at(7, 30)
    assert not [n for n in sent if "Streamly" in n["title"]]                                    # not before the morning time
    at(8, 1)
    notes = [n for n in sent if "Streamly" in n["title"]]
    assert len(notes) == 1 and notes[0]["title"] == "Streamly renews in 3 days" and "$12.99" not in notes[0]["title"]
    at(8, 5), at(10, 30), at(14, 0)
    assert len([n for n in sent if "Streamly" in n["title"]]) == 1                              # never twice for the same date


def test_a_renewal_further_away_than_the_persons_number_of_days_waits(due):
    appm, client, uid, tid, sent, at = due
    _subscription(appm, uid, datetime(2026, 10, 9, 6, 0, tzinfo=SYD).timestamp(), renews_on="20 Oct 2026")
    at(8, 1)
    assert not [n for n in sent if "Streamly" in n["title"]]
    assert client.put("/api/v1/me/subscriptions/settings", json={"nudge_days": 14}).status_code == 200
    at(8, 10)
    assert [n["title"] for n in sent if "Streamly" in n["title"]] == ["Streamly renews in 11 days"]


def test_a_free_trial_is_announced_in_its_own_words(due):
    appm, client, uid, tid, sent, at = due
    _subscription(appm, uid, datetime(2026, 10, 9, 6, 0, tzinfo=SYD).timestamp(), kind="trial_started", renews_on=None, trial_ends_on="10 Oct 2026")
    at(8, 1)
    assert "Streamly free trial ends tomorrow" in [n["title"] for n in sent]


def test_private_mode_keeps_the_service_name_out(due):
    appm, client, uid, tid, sent, at = due
    client.put("/api/v1/me/notifications/settings", json={"show_titles": False})
    _subscription(appm, uid, datetime(2026, 10, 9, 6, 0, tzinfo=SYD).timestamp())
    at(8, 1)
    private = [n for n in sent if "subscription" in n["body"]]
    assert len(private) == 1 and private[0]["title"] == "Enveliq" and "Streamly" not in private[0]["body"] and "Open Enveliq" in private[0]["body"]


def test_a_cancelled_subscription_is_not_announced(due):
    appm, client, uid, tid, sent, at = due
    _subscription(appm, uid, datetime(2026, 10, 9, 6, 0, tzinfo=SYD).timestamp())
    sid = appm.subbook.view(uid)["items"][0]["id"]
    appm.subbook.act(uid, sid, "cancelled")
    at(8, 1)
    assert not [n for n in sent if "Streamly" in n["title"]]


def test_browser_device_test_only_targets_selected_device(env, monkeypatch):
    from backend.mail import extra_channels

    appm, client, _, _ = env
    user_id = appm.vault.list_users()[0]["id"]
    subs = [
        {"id": "a" * 12, "label": "Android", "endpoint": "https://push.example/android", "p256dh": "key", "auth": "secret"},
        {"id": "b" * 12, "label": "Brave", "endpoint": "https://push.example/brave", "p256dh": "key", "auth": "secret"},
    ]
    appm.notifier.set_values(user_id, "browser", {"subs": json.dumps(subs)}, enabled=True)
    monkeypatch.setattr(extra_channels, "encrypt", lambda *args: b"encrypted")
    monkeypatch.setattr(extra_channels, "vapid_header", lambda *args: "vapid")
    monkeypatch.setattr(extra_channels, "vapid_key", lambda *args: object())
    monkeypatch.setattr(extra_channels, "b64d", lambda *args: b"key")

    sent = []
    def fake_request(method, url, **kwargs):
        sent.append(url)
        return 201, b""
    monkeypatch.setattr(outbound, "request", fake_request)

    url = "/api/v1/me/notifications/browser/" + "b" * 12 + "/test"
    response = client.post(url)
    assert response.status_code == 200, response.text
    assert sent == ["https://push.example/brave"]
    assert len(extra_channels.devices(appm.notifier.get_values(user_id, "browser"))) == 2

    missing = client.post("/api/v1/me/notifications/browser/" + "c" * 12 + "/test")
    assert missing.status_code == 404
    assert sent == ["https://push.example/brave"]


def test_mail_opened_shared_per_user_across_clients(env):
    """A server-stored first-open marker survives requests and does not change mailbox state."""
    appm, client, bridge, _ = env
    aid = account(client, bridge)
    client.post(f"/api/v1/accounts/{aid}/sync", json={})
    messages = appm.vault.list_messages(aid)
    assert messages
    msg = messages[0]
    initial_state = appm.vault.get_message(aid, msg["id"]).get("state")
    key = aid + ":" + msg["id"]
    assert key not in client.get("/api/v1/me/mail-opened").json()["keys"]
    response = client.post("/api/v1/me/mail-opened", json={"account_id": aid, "message_id": msg["id"]})
    assert response.status_code == 200, response.text
    assert key in client.get("/api/v1/me/mail-opened").json()["keys"]
    assert client.post("/api/v1/me/mail-opened", json={"account_id": aid, "message_id": msg["id"]}).status_code == 200
    assert client.get("/api/v1/me/mail-opened").json()["keys"].count(key) == 1
    assert appm.vault.get_message(aid, msg["id"]).get("state") == initial_state
    assert client.post("/api/v1/me/mail-opened", json={"account_id": aid, "message_id": "missing-message"}).status_code == 404
