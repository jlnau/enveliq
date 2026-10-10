"""Reporting for Grafana: metrics endpoint, Loki push, webhook, log lines. Counts and timings only, safe destinations."""
from __future__ import annotations

import hashlib
import hmac
import io
import json
import socket
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from helpers import create_user, sign_in
from test_llm import FakeModel
from test_summaries import start, synced
from backend.reporting import core, net
from backend.reporting.net import Destination, DestinationError

BODY = {"instance": "home", "label_mode": "id", "categories": {"activity": True, "security": True},
        "prometheus": {"enabled": False}, "logs": {"enabled": False},
        "loki": {"enabled": False, "url": "", "auth": "none", "username": "", "secret": None, "tenant": "", "labels": {}},
        "webhook": {"enabled": False, "url": "", "secret": None},
        "otlp": {"enabled": False, "url": "", "auth": "none", "username": "", "secret": None, "interval": 60},
        "grafana": {"enabled": False, "url": "", "secret": None, "folder": "Enveliq", "prometheus_uid": "", "loki_uid": "", "annotations": True}}
MAIL_WORDS = ["Quarterly update", "Weekly news", "Invoice question", "alice@example.invalid", "bob@example.invalid", "Alice Example",
              "Numbers are attached", "me@example.invalid", "work@example.invalid", "simplelogin", "Arrive 10 minutes early", GOOD_SUMMARY := "Dentist appointment"]


class Sink:
    """A fake Loki / webhook server that records what it is sent."""

    def __init__(self, status=204):
        self.got: list[tuple[str, dict, bytes]] = []
        outer = self

        class H(BaseHTTPRequestHandler):
            def do_POST(self):
                n = int(self.headers.get("Content-Length", 0))
                outer.got.append((self.path, {k.lower(): v for k, v in self.headers.items()}, self.rfile.read(n)))
                self.send_response(status)
                self.send_header("Content-Length", "0")
                self.end_headers()

            def log_message(self, *a):
                pass

        self.server = HTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.port = self.server.server_address[1]
        self.url = f"http://127.0.0.1:{self.port}"

    def close(self):
        self.server.shutdown()
        self.server.server_close()


class allow_loopback:
    """Tests talk to a server on this machine, which the real rules refuse: let the check pass for that one port only."""

    def __init__(self, port):
        self.port = port

    def __enter__(self):
        self.orig = net.check_destination

        def fake(url, **kw):
            d = self.orig(url.replace(f"127.0.0.1:{self.port}", "192.168.1.5:%d" % self.port), resolve=lambda *a, **k: [(0, 0, 0, "", ("192.168.1.5", self.port))])
            return Destination(d.scheme, "127.0.0.1", d.port, d.path, ("127.0.0.1",))
        net.check_destination = fake

    def __exit__(self, *a):
        net.check_destination = self.orig


@pytest.fixture
def env(tmp_path):
    model = FakeModel()
    appm, client, bridge = start(tmp_path, model)
    yield appm, client, bridge
    bridge.close()
    model.close()


def put(client, **over):
    body = json.loads(json.dumps(BODY))
    for k, v in over.items():
        body[k] = {**body[k], **v} if isinstance(v, dict) and isinstance(body.get(k), dict) else v
    return client.put("/api/v1/admin/reporting", json=body)


def token_for(client) -> str:
    return client.post("/api/v1/admin/reporting/token").json()["token"]


def scrape(client, token):
    return client.get("/metrics", headers={"Authorization": f"Bearer {token}"})


# ---------- the metrics address ----------

def test_metrics_need_a_token_and_everything_is_off_by_default(env):
    appm, client, _ = env
    assert client.get("/metrics").status_code == 401
    cfg = client.get("/api/v1/admin/reporting").json()["config"]
    assert cfg["prometheus"] == {"enabled": False, "has_token": False} and cfg["logs"]["enabled"] is False
    assert cfg["loki"]["enabled"] is False and cfg["webhook"]["enabled"] is False
    r = put(client, prometheus={"enabled": True})
    assert r.status_code == 400 and "token" in r.json()["detail"]


def test_token_is_shown_once_old_tokens_stop_working_and_only_a_hash_is_kept(env):
    appm, client, _ = env
    t1 = token_for(client)
    assert t1.startswith("enq_") and len(t1) > 40
    assert put(client, prometheus={"enabled": True}).status_code == 200
    assert scrape(client, t1).status_code == 200
    assert t1 not in json.dumps(client.get("/api/v1/admin/reporting").json())
    t2 = token_for(client)
    assert scrape(client, t1).status_code == 401 and scrape(client, t2).status_code == 200
    stored = appm.vault.get_global("reporting_config")
    assert t2 not in json.dumps(stored) and stored["prometheus"]["token_hash"] == hashlib.sha256(t2.encode()).hexdigest()


def test_a_wrong_token_or_switched_off_metrics_are_refused_and_guessing_is_limited(env):
    appm, client, _ = env
    token = token_for(client)
    assert scrape(client, token).status_code == 401                      # created but not switched on yet
    put(client, prometheus={"enabled": True})
    assert scrape(client, "enq_wrong").status_code == 401
    assert client.get("/metrics", headers={"Authorization": "Basic abc"}).status_code == 401
    codes = [scrape(client, "enq_guess").status_code for _ in range(40)]
    assert 429 in codes


def test_only_administrators_can_use_reporting(env):
    appm, client, _ = env
    create_user(client, "sam")
    sam = sign_in(appm, "sam")
    assert sam.get("/api/v1/admin/reporting").status_code == 403
    assert sam.put("/api/v1/admin/reporting", json=BODY).status_code == 403
    assert sam.post("/api/v1/admin/reporting/token").status_code == 403
    assert sam.post("/api/v1/admin/reporting/test", json={"sink": "logs"}).status_code == 403


def test_metrics_report_counts_and_timings_from_real_activity_and_no_mail_content(env):
    appm, client, bridge = env
    token = token_for(client)
    put(client, prometheus={"enabled": True})
    aid = synced(client, bridge)
    assert client.post(f"/api/v1/accounts/{aid}/summarise", json={}).json()["summarised"] == 3
    text = scrape(client, token).text
    assert "enveliq_up 1" in text and "enveliq_vault_unlocked 1" in text and 'enveliq_info{version="' in text
    assert 'enveliq_sync_runs_total{mailbox="mb_' in text and 'result="ok"' in text
    assert "enveliq_sync_duration_seconds_bucket" in text and "enveliq_last_sync_success_timestamp_seconds" in text
    assert 'enveliq_ai_requests_total{provider="custom",result="ok"} 3' in text or 'enveliq_ai_requests_total{provider="custom",result="ok"} 3.0' in text
    assert 'enveliq_summaries_total{result="ok"} 3' in text
    assert 'enveliq_messages{mailbox="mb_' in text and 'state="unread"} 3' in text
    assert "enveliq_unread_by_priority" in text and "enveliq_unread_by_category" in text
    for word in MAIL_WORDS:
        assert word not in text


def test_mailboxes_are_anonymous_by_default_and_named_only_when_the_administrator_chooses(env):
    appm, client, bridge = env
    token = token_for(client)
    put(client, prometheus={"enabled": True})
    synced(client, bridge)
    name = appm.vault.list_accounts()[0]["display_name"]
    assert name
    text = scrape(client, token).text
    assert 'mailbox="mb_' in text and name not in text
    assert put(client, prometheus={"enabled": True}, label_mode="name").status_code == 200
    appm.reporter._labels.clear()
    named = scrape(client, token).text
    assert f'enveliq_messages{{mailbox="{name}"' in named
    assert "mb_" not in named.split("enveliq_messages")[1].split("\n")[0]


def test_the_vault_being_locked_stops_the_metrics_and_forgets_the_settings(env):
    appm, client, _ = env
    token = token_for(client)
    put(client, prometheus={"enabled": True})
    assert scrape(client, token).status_code == 200
    appm.vault.lock()
    assert client.get("/metrics", headers={"Authorization": f"Bearer {token}"}).status_code == 503
    assert appm.reporter.config() is None


# ---------- what an event may carry ----------

def test_events_keep_only_allowed_fields_with_plain_values():
    out = core.clean_fields({"code": "ai_unreachable", "outcome": "a@b.example", "provider": "x" * 80, "subject": "Invoice", "sender": "bob@example.invalid",
                             "summary": "text", "duration_ms": 12.3456, "added": True, "count": float("nan"), "ok": False, "actor": "u-1", "user": "name with spaces"})
    assert out == {"code": "ai_unreachable", "duration_ms": 12.346, "ok": False, "actor": "u-1"}


def test_security_events_from_the_audit_log_are_reported_without_addresses(env):
    appm, client, _ = env
    r = appm.reporter
    appm.vault.audit({"event": "sign_in_failed", "user_id": "u-9", "at": 1.0, "client": "203.0.113.9", "email": "x@example.invalid"})
    text = r.metrics_text()
    assert 'enveliq_events_total{category="security",event="sign_in_failed"}' in text
    assert 'enveliq_signins_total{method="password",result="failed"}' in text
    assert "203.0.113.9" not in text and "example.invalid" not in text


# ---------- sending: logs, Loki, webhook ----------

def test_log_lines_go_to_the_container_output_as_json(env):
    appm, client, bridge = env
    out = io.StringIO()
    appm.reporter.out = out
    assert put(client, logs={"enabled": True}).status_code == 200
    synced(client, bridge)
    appm.reporter.flush()
    lines = [json.loads(l) for l in out.getvalue().splitlines()]
    assert any(l["event"] == "sync_completed" and l["app"] == "enveliq" and l["instance"] == "home" and l["added"] == 3 for l in lines)
    for word in MAIL_WORDS:
        assert word not in out.getvalue()


def test_loki_push_has_the_right_shape_labels_tenant_and_login_and_no_mail_content(env):
    appm, client, bridge = env
    sink = Sink()
    try:
        with allow_loopback(sink.port):
            r = put(client, loki={"enabled": True, "url": sink.url, "auth": "basic", "username": "grafana", "secret": "pw-123", "tenant": "home", "labels": {"site": "lxc"}})
            assert r.status_code == 200, r.text
            aid = synced(client, bridge)
            client.post(f"/api/v1/accounts/{aid}/summarise", json={})
            appm.reporter.flush()
        assert sink.got
        path, headers, body = sink.got[0]
        assert path == "/loki/api/v1/push" and headers["x-scope-orgid"] == "home" and headers["authorization"].startswith("Basic ")
        data = json.loads(body)
        stream = next(s for s in data["streams"] if s["stream"]["event"] == "sync_completed")
        assert stream["stream"]["job"] == "enveliq" and stream["stream"]["instance"] == "home" and stream["stream"]["site"] == "lxc" and stream["stream"]["level"] == "info"
        ts, line = stream["values"][0]
        assert ts.isdigit() and len(ts) == 19 and json.loads(line)["added"] == 3
        everything = b"".join(g[2] for g in sink.got).decode()
        for word in MAIL_WORDS:
            assert word not in everything
        assert "pw-123" not in everything
        assert appm.reporter.sinks["loki"].sent >= 1 and appm.reporter.sinks["loki"].last_error is None
    finally:
        sink.close()


def test_webhook_batches_are_signed_so_the_receiver_can_check_them(env):
    appm, client, bridge = env
    sink = Sink(status=200)
    try:
        with allow_loopback(sink.port):
            assert put(client, webhook={"enabled": True, "url": sink.url + "/hook", "secret": "shared-secret"}).status_code == 200
            synced(client, bridge)
            appm.reporter.flush()
        path, headers, body = sink.got[0]
        assert path == "/hook"
        assert headers["x-enveliq-signature"] == "sha256=" + hmac.new(b"shared-secret", body, hashlib.sha256).hexdigest()
        data = json.loads(body)
        assert data["source"] == "enveliq" and data["instance"] == "home" and any(e["event"] == "sync_completed" for e in data["events"])
        for word in MAIL_WORDS:
            assert word not in body.decode()
    finally:
        sink.close()


def test_secrets_are_never_returned_and_can_be_kept_or_removed(env):
    appm, client, _ = env
    sink = Sink()
    try:
        with allow_loopback(sink.port):
            put(client, loki={"enabled": True, "url": sink.url, "auth": "bearer", "secret": "tok-abc"}, webhook={"enabled": False, "url": sink.url, "secret": "wh-xyz"})
            shown = json.dumps(client.get("/api/v1/admin/reporting").json())
            assert "tok-abc" not in shown and "wh-xyz" not in shown and '"has_secret": true' in shown
            put(client, loki={"enabled": True, "url": sink.url, "auth": "bearer", "secret": None})            # keep
            assert appm.vault.get_global("reporting_config")["loki"]["secret"] == "tok-abc"
            put(client, loki={"enabled": True, "url": sink.url, "auth": "bearer", "secret": ""})              # remove
            assert appm.vault.get_global("reporting_config")["loki"]["secret"] == ""
    finally:
        sink.close()


def test_the_test_button_reports_plain_results(env):
    appm, client, _ = env
    sink = Sink(status=401)
    try:
        with allow_loopback(sink.port):
            put(client, loki={"enabled": False, "url": sink.url, "auth": "none"})
            r = client.post("/api/v1/admin/reporting/test", json={"sink": "loki"}).json()
        assert r["ok"] is False and r["code"] == "http_401" and "401" in r["message"]
    finally:
        sink.close()
    out = io.StringIO()
    appm.reporter.out = out
    assert client.post("/api/v1/admin/reporting/test", json={"sink": "logs"}).json()["ok"] is True and "report_test" in out.getvalue()
    assert client.post("/api/v1/admin/reporting/test", json={"sink": "nope"}).status_code == 400


def test_settings_that_are_not_valid_are_refused(env):
    appm, client, _ = env
    assert put(client, loki={"enabled": True, "url": "", "auth": "none"}).status_code == 400
    assert put(client, loki={"enabled": True, "url": "http://127.0.0.1:3100", "auth": "none"}).status_code == 400
    assert put(client, loki={"enabled": True, "url": "http://169.254.169.254/latest", "auth": "none"}).status_code == 400
    assert put(client, loki={"enabled": False, "url": "http://192.168.1.5:3100", "auth": "none", "labels": {"job": "x"}}).status_code == 400
    assert put(client, loki={"enabled": False, "url": "http://192.168.1.5:3100", "auth": "none", "labels": {"bad key": "x"}}).status_code == 400
    assert put(client, instance="has spaces").status_code == 400
    assert put(client, label_mode="everything").status_code == 400


def test_switching_a_kind_of_event_off_stops_it_being_queued(env):
    appm, client, _ = env
    put(client, logs={"enabled": True}, categories={"activity": True, "security": False})
    r = appm.reporter
    r._queue.clear()
    r.event("sign_in_failed", user="u-1")
    r.event("sync_completed", added=1)
    assert [e["event"] for e in r._queue] == ["sync_completed"]


def test_the_queue_is_bounded_and_never_blocks(env):
    appm, client, _ = env
    put(client, logs={"enabled": True})
    r = appm.reporter
    r._queue.clear()
    for i in range(core.QUEUE_MAX + 25):
        r.event("sync_completed", added=i)
    assert len(r._queue) == core.QUEUE_MAX and r.sinks["logs"].dropped >= 25


# ---------- where reports may be sent ----------

def public(*a, **k):
    return [(0, 0, 0, "", ("93.184.216.34", 443))]


def private(*a, **k):
    return [(0, 0, 0, "", ("192.168.1.20", 3100))]


def code(url, resolve=private):
    try:
        net.check_destination(url, resolve=resolve)
        return "ok"
    except DestinationError as err:
        return err.code


def test_destinations_on_the_owners_network_are_fine_and_unsafe_ones_are_not():
    assert code("http://192.168.1.20:3100") == "ok" and code("https://alloy.lan:3100") == "ok"
    for bad in ("http://127.0.0.1:3100", "http://localhost:3100", "http://169.254.169.254/latest/meta-data", "http://0.0.0.0:3100", "http://[::1]:3100", "http://[fe80::1]:3100", "http://224.0.0.1/"):
        host = bad.split("//")[1].split("/")[0].rsplit(":", 1)[0].strip("[]")
        assert code(bad, resolve=lambda *a, h=host, **k: [(0, 0, 0, "", (h if host != "localhost" else "127.0.0.1", 3100))]) == "host_not_allowed", bad
    assert code("ftp://192.168.1.20") == "bad_address" and code("http://user:pw@192.168.1.20") == "bad_address" and code("http://") == "bad_address"
    assert code("http://192.168.1.20:99999") == "bad_address"


def test_public_servers_need_https_and_a_name_that_resolves():
    assert code("http://logs.example.net", resolve=public) == "needs_https"
    assert code("https://logs.example.net", resolve=public) == "ok"

    def missing(*a, **k):
        raise socket.gaierror("no such host")
    assert code("https://nowhere.invalid", resolve=missing) == "unresolvable"


def test_a_name_that_resolves_to_both_a_public_and_a_blocked_address_is_refused():
    both = lambda *a, **k: [(0, 0, 0, "", ("93.184.216.34", 443)), (0, 0, 0, "", ("127.0.0.1", 443))]
    assert code("https://sneaky.example.net", resolve=both) == "host_not_allowed"


def test_the_administrators_host_list_limits_where_reports_go(monkeypatch=None):
    import os
    os.environ["ENVELIQ_REPORT_ALLOWED_HOSTS"] = "alloy.lan"
    try:
        assert code("https://alloy.lan:3100") == "ok"
        assert code("http://192.168.1.20:3100") == "host_not_allowed"
    finally:
        os.environ.pop("ENVELIQ_REPORT_ALLOWED_HOSTS", None)
