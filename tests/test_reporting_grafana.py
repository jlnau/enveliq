"""Reporting v0.33: OpenTelemetry push, the Grafana connection (dashboard, annotations) and the tidy settings."""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from backend.reporting import grafana
from test_reporting import BODY, MAIL_WORDS, Sink, allow_loopback, env, put   # noqa: F401  (env is a fixture)
from test_summaries import synced

TOKEN = "glsa_test_token_do_not_leak"


class FakeGrafana:
    """Enough of Grafana's HTTP API to install a dashboard and take annotations."""

    def __init__(self, datasources_status=200):
        self.calls: list[tuple[str, str, dict, object]] = []
        self.folders: list[dict] = []
        self.datasources_status = datasources_status
        outer = self

        class H(BaseHTTPRequestHandler):
            def _go(self, method):
                n = int(self.headers.get("Content-Length", 0) or 0)
                raw = self.rfile.read(n) if n else b""
                payload = json.loads(raw) if raw else None
                headers = {k.lower(): v for k, v in self.headers.items()}
                outer.calls.append((method, self.path, headers, payload))
                status, answer = 200, {}
                if headers.get("authorization") != f"Bearer {TOKEN}":
                    status, answer = 401, {"message": "bad token"}
                elif self.path == "/api/org":
                    answer = {"id": 1, "name": "Home"}
                elif self.path == "/api/datasources":
                    if outer.datasources_status != 200:
                        status = outer.datasources_status
                    else:
                        answer = [{"uid": "prom-1", "name": "Prometheus", "type": "prometheus"}, {"uid": "loki-1", "name": "Loki", "type": "loki"},
                                  {"uid": "pg", "name": "Postgres", "type": "postgres"}]
                elif self.path.startswith("/api/folders") and method == "GET":
                    answer = outer.folders
                elif self.path == "/api/folders" and method == "POST":
                    folder = {"uid": "fold-1", "title": payload["title"]}
                    outer.folders.append(folder)
                    answer = folder
                elif self.path == "/api/dashboards/db":
                    answer = {"status": "success", "url": "/d/enveliq-overview/enveliq"}
                elif self.path == "/api/annotations":
                    answer = {"id": 1}
                else:
                    status = 404
                body = json.dumps(answer).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                self._go("GET")

            def do_POST(self):
                self._go("POST")

            def log_message(self, *a):
                pass

        self.server = HTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.port = self.server.server_address[1]
        self.url = f"http://127.0.0.1:{self.port}"

    def close(self):
        self.server.shutdown()
        self.server.server_close()


def graf(fake, **over):
    return {"enabled": True, "url": fake.url, "secret": TOKEN, "folder": "Enveliq", "prometheus_uid": "prom-1", "loki_uid": "loki-1", "annotations": True, **over}


# ---------- OpenTelemetry ----------

def test_metrics_are_pushed_as_opentelemetry_with_the_right_shape_and_no_mail_content(env):
    appm, client, bridge = env
    sink = Sink(status=200)
    try:
        with allow_loopback(sink.port):
            r = put(client, otlp={"enabled": True, "url": sink.url, "auth": "bearer", "secret": "otlp-secret-1", "interval": 30})
            assert r.status_code == 200, r.text
            aid = synced(client, bridge)
            client.post(f"/api/v1/accounts/{aid}/summarise", json={})
            appm.reporter.flush()
        path, headers, body = sink.got[0]
        assert path == "/v1/metrics" and headers["authorization"] == "Bearer otlp-secret-1" and headers["content-type"] == "application/json"
        data = json.loads(body)
        resource = data["resourceMetrics"][0]
        attrs = {a["key"]: a["value"]["stringValue"] for a in resource["resource"]["attributes"]}
        assert attrs["service.name"] == "enveliq" and attrs["service.instance.id"] == "home"
        metrics = {m["name"]: m for m in resource["scopeMetrics"][0]["metrics"]}
        events = metrics["enveliq_events"]["sum"]                       # `_total` is added back by the receiver
        assert events["isMonotonic"] is True and events["aggregationTemporality"] == 2
        assert "enveliq_events_total" not in metrics
        hist = metrics["enveliq_sync_duration_seconds"]["histogram"]["dataPoints"][0]
        assert len(hist["bucketCounts"]) == len(hist["explicitBounds"]) + 1 and sum(int(c) for c in hist["bucketCounts"]) == int(hist["count"])
        assert "enveliq_vault_unlocked" in metrics and "enveliq_messages" in metrics
        for word in MAIL_WORDS:
            assert word not in body.decode()
        assert "otlp-secret-1" not in body.decode()
        assert appm.reporter.sinks["otlp"].sent == 1
    finally:
        sink.close()


def test_the_push_waits_for_its_interval(env):
    appm, client, _ = env
    sink = Sink(status=200)
    try:
        with allow_loopback(sink.port):
            put(client, otlp={"enabled": True, "url": sink.url + "/v1/metrics", "interval": 300})
            appm.reporter.flush()
            appm.reporter.flush()
        assert len(sink.got) == 1 and sink.got[0][0] == "/v1/metrics"
    finally:
        sink.close()


def test_the_otlp_test_button_and_its_errors(env):
    appm, client, _ = env
    sink = Sink(status=401)
    try:
        with allow_loopback(sink.port):
            put(client, otlp={"enabled": False, "url": sink.url})
            r = client.post("/api/v1/admin/reporting/test", json={"sink": "otlp"}).json()
        assert r["ok"] is False and r["code"] == "http_401"
    finally:
        sink.close()


# ---------- Grafana ----------

def test_grafana_needs_a_token_and_a_safe_address(env):
    _, client, _ = env
    assert put(client, grafana={"enabled": True, "url": "http://192.168.1.9:3000"}).status_code == 400
    assert put(client, grafana={"enabled": True, "url": "http://127.0.0.1:3000", "secret": "t"}).status_code == 400
    assert put(client, grafana={"enabled": True, "url": "http://169.254.169.254", "secret": "t"}).status_code == 400
    assert put(client, grafana={"enabled": False, "url": "", "folder": "bad/folder"}).status_code == 400
    assert put(client, grafana={"enabled": False, "url": "", "prometheus_uid": "a b"}).status_code == 400
    assert put(client, otlp={"enabled": True, "url": ""}).status_code == 400
    assert put(client, otlp={"enabled": False, "interval": 7}).status_code == 400


def test_connection_test_lists_data_sources_and_never_shows_the_token(env):
    appm, client, _ = env
    fake = FakeGrafana()
    try:
        with allow_loopback(fake.port):
            assert put(client, grafana=graf(fake)).status_code == 200
            shown = json.dumps(client.get("/api/v1/admin/reporting").json())
            assert TOKEN not in shown and '"has_secret": true' in shown
            r = client.post("/api/v1/admin/reporting/test", json={"sink": "grafana"}).json()
            assert r["ok"] is True
            ds = client.get("/api/v1/admin/reporting/grafana/datasources").json()["datasources"]
        assert {d["uid"] for d in ds} == {"prom-1", "loki-1"}                    # only Prometheus and Loki
        assert all(c[2]["authorization"] == f"Bearer {TOKEN}" for c in fake.calls)
    finally:
        fake.close()


def test_a_wrong_token_and_a_forbidden_list_are_explained(env):
    _, client, _ = env
    fake = FakeGrafana(datasources_status=403)
    try:
        with allow_loopback(fake.port):
            assert put(client, grafana=graf(fake)).status_code == 200
            r = client.get("/api/v1/admin/reporting/grafana/datasources")
            assert r.status_code == 502 and r.json()["detail"]["code"] == "http_403" and "Editor" in r.json()["detail"]["message"]
            put(client, grafana=graf(fake, secret="wrong"))
            t = client.post("/api/v1/admin/reporting/test", json={"sink": "grafana"}).json()
        assert t["ok"] is False and t["code"] == "http_401" and "token" in t["message"]
    finally:
        fake.close()


def test_the_dashboard_is_installed_into_a_folder_with_the_chosen_data_sources(env):
    _, client, _ = env
    fake = FakeGrafana()
    try:
        with allow_loopback(fake.port):
            put(client, grafana=graf(fake, folder="Home lab"))
            r = client.post("/api/v1/admin/reporting/grafana/dashboard")
            assert r.status_code == 200 and r.json()["url"] == fake.url + "/d/enveliq-overview/enveliq"
            post = next(c for c in fake.calls if c[1] == "/api/dashboards/db")[3]
            assert post["overwrite"] is True and post["folderUid"] == "fold-1"
            assert fake.folders == [{"uid": "fold-1", "title": "Home lab"}]
            text = json.dumps(post["dashboard"])
            assert "${DS_" not in text and "prom-1" in text and "loki-1" in text and "__inputs" not in post["dashboard"]
            assert post["dashboard"]["uid"] == "enveliq-overview"
            client.post("/api/v1/admin/reporting/grafana/dashboard")             # again: the folder is found, not made twice
            assert len(fake.folders) == 1
            assert client.get("/api/v1/admin/reporting").json()["config"]["grafana"]["dashboard_url"].endswith("/d/enveliq-overview/enveliq")
    finally:
        fake.close()


def test_without_a_loki_the_log_panel_is_left_out(env):
    dash = grafana.dashboard_for("prom-1", "")
    assert not any((p.get("datasource") or {}).get("type") == "loki" for p in dash["panels"]) and "loki" not in json.dumps(dash)


def test_with_only_loki_a_dashboard_drawn_from_the_event_logs_is_installed(env):
    _, client, _ = env
    dash = grafana.dashboard_for("", "loki-1")
    text = json.dumps(dash)
    assert dash["uid"] == "enveliq-overview" and "${DS_" not in text and "prometheus" not in text and "loki-1" in text and len(dash["panels"]) >= 12
    fake = FakeGrafana()
    try:
        with allow_loopback(fake.port):
            put(client, grafana=graf(fake, prometheus_uid=""))
            r = client.post("/api/v1/admin/reporting/grafana/dashboard")
            assert r.status_code == 200
            sent = next(c for c in fake.calls if c[1] == "/api/dashboards/db")[3]["dashboard"]
        assert all(p["datasource"]["type"] == "loki" for p in sent["panels"])
    finally:
        fake.close()


def test_with_no_data_source_nothing_is_installed(env):
    _, client, _ = env
    fake = FakeGrafana()
    try:
        with allow_loopback(fake.port):
            put(client, grafana=graf(fake, prometheus_uid="", loki_uid=""))
            r = client.post("/api/v1/admin/reporting/grafana/dashboard")
        assert r.status_code == 502 and r.json()["detail"]["code"] == "no_datasource" and not fake.calls
    finally:
        fake.close()


def test_the_copy_in_docs_is_the_same_as_the_one_that_is_installed():
    here = Path(__file__).resolve().parent.parent
    assert (here / "docs/grafana/enveliq-dashboard.json").read_text() == grafana.DASHBOARD_FILE.read_text()
    assert (here / "docs/grafana/enveliq-dashboard-loki.json").read_text() == grafana.LOKI_DASHBOARD_FILE.read_text()


def test_key_events_become_annotations_with_fixed_text_and_no_mail_content(env):
    appm, client, bridge = env
    fake = FakeGrafana()
    try:
        with allow_loopback(fake.port):
            put(client, grafana=graf(fake))
            appm.reporter.event("vault_locked")
            appm.reporter.event("ai_prompt_changed", actor="u1")
            appm.reporter.event("sync_failed", mailbox="acc-1", code="auth_failed")
            appm.reporter.event("sync_failed", mailbox="acc-1", code="auth_failed")          # a second failure is not a new marker
            appm.reporter.event("sync_completed", mailbox="acc-1", added=0)
            appm.reporter.flush()
        notes = [c[3] for c in fake.calls if c[1] == "/api/annotations"]
        texts = [n["text"] for n in notes]
        assert texts[0] == "Vault locked" and "AI prompt changed" in texts
        assert sum(t.startswith("Sync started failing") for t in texts) == 1 and sum(t.startswith("Sync is working again") for t in texts) == 1
        assert all(n["tags"][0] == "enveliq" and n["tags"][2] == "home" and isinstance(n["time"], int) for n in notes)
        assert appm.reporter.sinks["grafana"].sent == len(notes)
        for word in MAIL_WORDS:
            assert word not in json.dumps(notes)
    finally:
        fake.close()


def test_annotations_can_be_switched_off(env):
    appm, client, _ = env
    fake = FakeGrafana()
    try:
        with allow_loopback(fake.port):
            put(client, grafana=graf(fake, annotations=False))
            appm.reporter.event("vault_locked")
            appm.reporter.flush()
        assert not any(c[1] == "/api/annotations" for c in fake.calls)
    finally:
        fake.close()


def test_the_new_settings_are_kept_and_the_secrets_can_be_kept_or_removed(env):
    appm, client, _ = env
    fake = FakeGrafana()
    try:
        with allow_loopback(fake.port):
            put(client, grafana=graf(fake), otlp={"enabled": True, "url": fake.url, "auth": "basic", "username": "u", "secret": "pw-1"})
            put(client, grafana=graf(fake, secret=None), otlp={"enabled": True, "url": fake.url, "auth": "basic", "username": "u", "secret": None})
            saved = appm.vault.get_global("reporting_config")
            assert saved["grafana"]["secret"] == TOKEN and saved["otlp"]["secret"] == "pw-1"
            put(client, grafana=graf(fake, secret="", enabled=False), otlp={"enabled": True, "url": fake.url, "auth": "none"})
            saved = appm.vault.get_global("reporting_config")
            assert saved["grafana"]["secret"] == "" and saved["otlp"]["secret"] == ""
        assert not any(w in json.dumps(client.get("/api/v1/admin/reporting").json()) for w in (TOKEN, "pw-1"))
    finally:
        fake.close()
