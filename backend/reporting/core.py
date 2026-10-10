"""Reporting: counts, timings and security events for Grafana (or anything else).

What is reported is limited by construction. An event carries only fields from a
fixed list, and a text field is kept only if it looks like a plain code word
(letters, digits, dots, dashes, underscores, up to 64). Email text, subjects,
senders, addresses, summaries, names and anything a server sent back can never
get through, because they never pass those two filters.

Outputs (each off until an administrator switches it on):
* Prometheus: GET /metrics, read with a token.
* Logs: one JSON line per event on the container's output.
* Loki: events pushed to a Loki, Grafana Alloy (loki.source.api) or Grafana Cloud address.
* Webhook: batches of events posted as signed JSON.
* OpenTelemetry: the numbers pushed on a timer (OTLP over HTTP) to Grafana Alloy or any collector.
* Grafana: markers ("annotations") for key events, through a service-account token.

Sending never blocks a request: events wait in a small queue and a background
thread delivers them, dropping the oldest if the queue is full.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import math
import re
import sys
import threading
import time
from collections import deque
from typing import Any, Callable

from ..version import VERSION
from . import config as cfgmod
from . import grafana, net

TOKEN = re.compile(r"^[A-Za-z0-9_.:-]{1,64}$")
NUMBER_FIELDS = {"count", "added", "removed", "summarised", "failed", "duration_ms", "left", "minutes", "max_days", "unread_seen", "skipped"}
BOOL_FIELDS = {"ok", "cloud", "kept"}
TOKEN_FIELDS = {"outcome", "code", "provider", "method", "role", "reason"}
ID_FIELDS = {"actor", "user"}             # opaque ids of people, never names
SECURITY_EVENTS = {
    "signed_in", "sign_in_failed", "setup_completed", "recovery_code_used", "recovery_codes_regenerated", "passkey_failed",
    "passkey_added", "passkey_removed", "password_changed", "totp_enabled", "totp_disabled", "sso_failed", "sso_denied_group",
    "sso_linked", "sso_unlinked", "sso_settings_updated", "user_created", "user_created_by_sso", "user_updated", "user_deleted",
    "mfa_reset", "password_reset_by_admin", "auth_policy_updated", "vault_unlocked", "vault_locked", "ai_config_saved",
    "ai_config_cleared", "ai_prompt_changed", "ai_prompt_reset", "attachment_policy_updated", "global_settings_updated",
    "account_created", "account_updated", "account_disconnected", "reporting_config_saved", "reporting_token_created", "reporting_dashboard_installed", "microsoft_settings_saved", "microsoft_signin_failed", "microsoft_mailbox_connected",
    "sync_interval_saved", "review_settings_saved", "preferences_saved",
}
ERROR_EVENTS = {"sign_in_failed", "passkey_failed", "sso_failed", "sso_denied_group", "sync_failed", "ai_request_failed"}
BUCKETS = (0.5, 1, 2, 5, 10, 30, 60, 120)
QUEUE_MAX = 2000
BATCH = 100
NOTES_MAX = 50
NOTE_TEXT = {
    "app_started": "Enveliq started", "vault_unlocked": "Vault unlocked", "vault_locked": "Vault locked",
    "ai_config_saved": "AI settings changed", "ai_config_cleared": "AI settings removed",
    "ai_prompt_changed": "AI prompt changed", "ai_prompt_reset": "AI prompt reset to the built-in one",
    "sync_failing": "Sync started failing", "sync_recovered": "Sync is working again",
}
FLUSH_SECONDS = 5.0


def clean_fields(raw: dict[str, Any]) -> dict[str, Any]:
    """Keep only allowed fields with safe values."""
    out: dict[str, Any] = {}
    for key, value in raw.items():
        if key in NUMBER_FIELDS:
            if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
                out[key] = value if isinstance(value, int) else round(float(value), 3)
        elif key in BOOL_FIELDS:
            if isinstance(value, bool):
                out[key] = value
        elif key in TOKEN_FIELDS or key in ID_FIELDS:
            if isinstance(value, str) and TOKEN.match(value):
                out[key] = value
        elif key == "mailbox":
            if isinstance(value, str) and value:
                out[key] = value[:60]
    return out


class Registry:
    """A tiny Prometheus-style registry (counters, histograms, gauges set from events)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.counters: dict[str, dict[tuple, float]] = {}
        self.hist: dict[str, dict[tuple, list[float]]] = {}      # labels -> [bucket counts..., sum, count]
        self.gauges: dict[str, dict[tuple, float]] = {}
        self.help: dict[str, str] = {}

    def inc(self, name: str, labels: dict[str, str] | None = None, by: float = 1.0, help: str = "") -> None:
        key = tuple(sorted((labels or {}).items()))
        with self._lock:
            self.help.setdefault(name, help)
            series = self.counters.setdefault(name, {})
            series[key] = series.get(key, 0.0) + by

    def observe(self, name: str, seconds: float, labels: dict[str, str] | None = None, help: str = "") -> None:
        key = tuple(sorted((labels or {}).items()))
        with self._lock:
            self.help.setdefault(name, help)
            series = self.hist.setdefault(name, {})
            row = series.setdefault(key, [0.0] * (len(BUCKETS) + 2))
            for i, edge in enumerate(BUCKETS):
                if seconds <= edge:
                    row[i] += 1
            row[-2] += seconds
            row[-1] += 1

    def set(self, name: str, value: float, labels: dict[str, str] | None = None, help: str = "") -> None:
        key = tuple(sorted((labels or {}).items()))
        with self._lock:
            self.help.setdefault(name, help)
            self.gauges.setdefault(name, {})[key] = value

    def snapshot(self) -> tuple[dict, dict, dict, dict]:
        """Copies of (counters, histograms, gauges, help) that are safe to read while events keep arriving."""
        with self._lock:
            return ({n: dict(s) for n, s in self.counters.items()}, {n: {k: list(r) for k, r in s.items()} for n, s in self.hist.items()},
                    {n: dict(s) for n, s in self.gauges.items()}, dict(self.help))

    @staticmethod
    def _labels(key: tuple, extra: tuple = ()) -> str:
        pairs = list(key) + list(extra)
        if not pairs:
            return ""
        esc = lambda v: str(v).replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')
        return "{" + ",".join(f'{k}="{esc(v)}"' for k, v in pairs) + "}"

    def render(self, extra_gauges: list[tuple[str, str, dict[str, str], float]] = ()) -> str:
        lines: list[str] = []
        with self._lock:
            for name, series in sorted(self.counters.items()):
                lines += [f"# HELP {name} {self.help.get(name, '')}", f"# TYPE {name} counter"]
                lines += [f"{name}{self._labels(k)} {v:g}" for k, v in sorted(series.items())]
            for name, series in sorted(self.hist.items()):
                lines += [f"# HELP {name} {self.help.get(name, '')}", f"# TYPE {name} histogram"]
                for k, row in sorted(series.items()):
                    for i, edge in enumerate(BUCKETS):
                        lines.append(f"{name}_bucket{self._labels(k, (('le', str(edge)),))} {row[i]:g}")
                    lines.append(f"{name}_bucket{self._labels(k, (('le', '+Inf'),))} {row[-1]:g}")
                    lines += [f"{name}_sum{self._labels(k)} {row[-2]:g}", f"{name}_count{self._labels(k)} {row[-1]:g}"]
            for name, series in sorted(self.gauges.items()):
                lines += [f"# HELP {name} {self.help.get(name, '')}", f"# TYPE {name} gauge"]
                lines += [f"{name}{self._labels(k)} {v:g}" for k, v in sorted(series.items())]
        seen: set[str] = set()
        for name, help_text, labels, value in extra_gauges:
            if name not in seen:
                lines += [f"# HELP {name} {help_text}", f"# TYPE {name} gauge"]
                seen.add(name)
            lines.append(f"{name}{self._labels(tuple(sorted(labels.items())))} {value:g}")
        return "\n".join(lines) + "\n"


class SinkState:
    def __init__(self) -> None:
        self.sent = 0
        self.failed = 0
        self.dropped = 0
        self.last_ok: float | None = None
        self.last_error: str | None = None

    def public(self) -> dict[str, Any]:
        return {"sent": self.sent, "failed": self.failed, "dropped": self.dropped, "last_ok": self.last_ok, "last_error": self.last_error}


class Reporter:
    def __init__(self, vault: Any = None, clock: Callable[[], float] = time.time):
        self.vault = vault
        self.clock = clock
        self.registry = Registry()
        self.sinks = {name: SinkState() for name in ("logs", "loki", "webhook", "otlp", "grafana")}
        self._queue: deque[dict[str, Any]] = deque()
        self._notes: deque[tuple[float, str, str]] = deque()
        self._failing: set[str] = set()
        self._started = clock()
        self._last_otlp = 0.0
        self._lock = threading.Lock()
        self._cfg: dict[str, Any] | None = None
        self._labels: dict[str, tuple[str, float]] = {}
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.out = sys.stdout
        if vault is not None:
            vault.add_lock_listener(self.forget)
            vault.audit_hooks.append(self.from_audit)

    # ---------- settings ----------

    def forget(self) -> None:
        """The vault locked: drop the decrypted settings (and anything waiting to be sent)."""
        with self._lock:
            self._cfg = None
            self._labels = {}
            self._queue.clear()
            self._notes.clear()

    def config(self) -> dict[str, Any] | None:
        """The settings, or None while the vault is locked."""
        if self.vault is None or not self.vault.is_unlocked():
            return None
        with self._lock:
            if self._cfg is not None:
                return self._cfg
        try:
            loaded = cfgmod.load(self.vault)
        except Exception:
            return None
        with self._lock:
            self._cfg = loaded
        return loaded

    def reload(self) -> None:
        with self._lock:
            self._cfg = None

    # ---------- naming mailboxes ----------

    def mailbox_label(self, account_id: str, cfg: dict[str, Any] | None = None) -> str:
        cfg = cfg or self.config() or cfgmod.DEFAULT
        anon = "mb_" + hashlib.sha256(str(account_id).encode()).hexdigest()[:6]
        if cfg["label_mode"] != "name" or self.vault is None:
            return anon
        now = self.clock()
        cached = self._labels.get(account_id)
        if cached and now - cached[1] < 60:
            return cached[0]
        name = anon
        try:
            for account in self.vault.list_accounts():
                if account["id"] == account_id:
                    name = re.sub(r"[\x00-\x1f\x7f]", "", str(account.get("display_name") or "")).strip()[:60] or anon
        except Exception:
            pass
        self._labels[account_id] = (name, now)
        return name

    # ---------- events ----------

    def from_audit(self, payload: dict[str, Any]) -> None:
        """Called for every audit-log entry: turns it into a report event (allowed fields only)."""
        try:
            name = str(payload.get("event") or "")
            if not TOKEN.match(name) or name in ("mailbox_synced", "mailbox_summarised"):
                return                                    # the sync and AI events are reported with timings elsewhere
            fields: dict[str, Any] = {}
            for src, dst in (("user_id", "user"), ("actor_user_id", "actor"), ("by", "actor")):
                if payload.get(src):
                    fields.setdefault(dst, str(payload[src]))
            for key in ("outcome", "method", "reason", "role", "provider", "cloud", "kept", "minutes", "max_days", "left"):
                if key in payload:
                    fields[key] = payload[key]
            if payload.get("account_id"):
                fields["mailbox"] = str(payload["account_id"])
            if name == "message_resolved":
                name = "message_action"
            self.event(name, **fields)
        except Exception:
            pass

    def event(self, name: str, **raw: Any) -> None:
        """Record an event: update the counters and, if an output is on, queue it."""
        try:
            cfg = self.config()
            account = raw.pop("mailbox", None)
            fields = clean_fields(raw)
            if account:
                fields["mailbox"] = self.mailbox_label(str(account), cfg)
            category = "security" if name in SECURITY_EVENTS else "activity"
            level = "error" if name in ERROR_EVENTS or fields.get("ok") is False else "info"
            self._count(name, category, fields)
            self._note(name, fields, cfg)
            if cfg is None or not cfg["categories"].get(category):
                return
            if not (cfg["logs"]["enabled"] or cfg["loki"]["enabled"] or cfg["webhook"]["enabled"]):
                return
            record = {"ts": round(self.clock(), 3), "event": name, "category": category, "level": level, **fields}
            with self._lock:
                if len(self._queue) >= QUEUE_MAX:
                    self._queue.popleft()
                    for sink in ("logs", "loki", "webhook"):
                        self.sinks[sink].dropped += 1
                self._queue.append(record)
                full = len(self._queue) >= BATCH
            if full:
                self._wake.set()
        except Exception:
            pass                                           # reporting must never break the app

    def _note(self, name: str, f: dict[str, Any], cfg: dict[str, Any] | None) -> None:
        """Queue a Grafana marker for the few events worth seeing on a chart."""
        if name == "sync_failed" and f.get("mailbox") not in self._failing:
            self._failing.add(f.get("mailbox", ""))
            name = "sync_failing"
        elif name == "sync_completed" and f.get("mailbox", "") in self._failing:
            self._failing.discard(f.get("mailbox", ""))
            name = "sync_recovered"
        if name not in NOTE_TEXT or cfg is None or not (cfg["grafana"]["enabled"] and cfg["grafana"]["annotations"]):
            return
        text = NOTE_TEXT[name] + (f" ({f['mailbox']})" if name.startswith("sync_") and f.get("mailbox") else "")
        with self._lock:
            if len(self._notes) >= NOTES_MAX:
                self._notes.popleft()
            self._notes.append((self.clock(), name, text))

    def _count(self, name: str, category: str, f: dict[str, Any]) -> None:
        r = self.registry
        r.inc("enveliq_events_total", {"event": name, "category": category}, help="Events by type")
        mb = f.get("mailbox", "")
        secs = (f.get("duration_ms") or 0) / 1000.0
        if name == "sync_completed":
            r.inc("enveliq_sync_runs_total", {"mailbox": mb, "result": "ok"}, help="Mailbox syncs")
            r.observe("enveliq_sync_duration_seconds", secs, {"mailbox": mb}, help="How long a mailbox sync took")
            r.inc("enveliq_sync_items_total", {"mailbox": mb, "kind": "added"}, f.get("added", 0), help="Emails added or removed by sync")
            r.inc("enveliq_sync_items_total", {"mailbox": mb, "kind": "removed"}, f.get("removed", 0))
            r.set("enveliq_last_sync_success_timestamp_seconds", self.clock(), {"mailbox": mb}, help="Unix time of the last good sync")
        elif name == "sync_failed":
            r.inc("enveliq_sync_runs_total", {"mailbox": mb, "result": "error"})
            r.inc("enveliq_sync_errors_total", {"mailbox": mb, "code": f.get("code", "failed")}, help="Failed syncs by error code")
        elif name == "summaries_completed":
            r.inc("enveliq_summaries_total", {"result": "ok"}, f.get("summarised", 0), help="AI summaries written or failed")
            r.inc("enveliq_summaries_total", {"result": "failed"}, f.get("failed", 0))
        elif name in ("ai_request", "ai_request_failed"):
            provider = f.get("provider", "custom")
            ok = name == "ai_request"
            r.inc("enveliq_ai_requests_total", {"provider": provider, "result": "ok" if ok else "error"}, help="Requests to the AI service")
            r.observe("enveliq_ai_request_duration_seconds", secs, {"provider": provider}, help="How long the AI service took to answer")
            if not ok:
                r.inc("enveliq_ai_errors_total", {"provider": provider, "code": f.get("code", "failed")}, help="AI failures by error code")
        elif name == "message_action":
            r.inc("enveliq_message_actions_total", {"outcome": f.get("outcome", "other")}, help="Reviewed, archived and binned emails")
        elif name == "signed_in":
            r.inc("enveliq_signins_total", {"result": "ok", "method": f.get("method", "password")}, help="Sign-ins")
        elif name == "sign_in_failed":
            r.inc("enveliq_signins_total", {"result": "failed", "method": "password"})
        elif name == "reply_sent":
            r.inc("enveliq_replies_total", help="Replies sent")

    # ---------- state gauges for /metrics ----------

    def state_gauges(self, version: str = VERSION) -> list[tuple[str, str, dict[str, str], float]]:
        out: list[tuple[str, str, dict[str, str], float]] = [
            ("enveliq_up", "1 while Enveliq is running", {}, 1.0),
            ("enveliq_info", "Version", {"version": version}, 1.0),
        ]
        vault = self.vault
        if vault is None or not vault.is_unlocked():
            out.append(("enveliq_vault_unlocked", "1 when the vault is unlocked", {}, 0.0))
            return out
        cfg = self.config() or cfgmod.DEFAULT
        out.append(("enveliq_vault_unlocked", "1 when the vault is unlocked", {}, 1.0))
        try:
            out.append(("enveliq_users", "People with an account", {}, float(vault.count_users())))
            accounts = vault.list_accounts()
            out.append(("enveliq_mailboxes", "Connected mailboxes", {}, float(len(accounts))))
            totals: dict[tuple, int] = {}
            for account in accounts:
                mb = self.mailbox_label(account["id"], cfg)
                for m in vault.list_messages(account["id"]):
                    state = m.get("state", "unread")
                    for labels in ({"mailbox": mb, "state": state},):
                        key = tuple(sorted(labels.items()))
                        totals[key] = totals.get(key, 0) + 1
                    if state == "unread":
                        for dim, val in (("priority", m.get("priority") or "normal"), ("category", m.get("category") or "other")):
                            key = tuple(sorted({"mailbox": mb, dim: str(val)[:40]}.items()))
                            totals[key] = totals.get(key, 0) + 1
                        if m.get("action_required"):
                            key = (("mailbox", mb),)
                            totals[key] = totals.get(key, 0) + 1
            for key, n in sorted(totals.items()):
                labels = dict(key)
                if "state" in labels:
                    out.append(("enveliq_messages", "Emails held, by state", labels, float(n)))
                elif "priority" in labels:
                    out.append(("enveliq_unread_by_priority", "Unread emails by priority", labels, float(n)))
                elif "category" in labels:
                    out.append(("enveliq_unread_by_category", "Unread emails by category", labels, float(n)))
                else:
                    out.append(("enveliq_unread_action_required", "Unread emails that need action", labels, float(n)))
        except Exception:
            pass
        out.append(("enveliq_report_queue", "Events waiting to be sent", {}, float(len(self._queue))))
        return out

    def _report_gauges(self) -> None:
        for name, state in self.sinks.items():
            self.registry.set("enveliq_report_sent_total", float(state.sent), {"sink": name}, help="Report batches delivered")
            self.registry.set("enveliq_report_failed_total", float(state.failed), {"sink": name}, help="Report batches that failed")
            self.registry.set("enveliq_report_dropped_total", float(state.dropped), {"sink": name}, help="Events dropped because the queue was full")

    def metrics_text(self) -> str:
        self._report_gauges()
        return self.registry.render(self.state_gauges())

    def otlp_payload(self, cfg: dict[str, Any]) -> bytes:
        """The same numbers as /metrics, as OpenTelemetry JSON (OTLP over HTTP)."""
        self._report_gauges()
        counters, hists, gauges, helps = self.registry.snapshot()
        now = self.clock()
        t, start = str(int(now * 1e9)), str(int(self._started * 1e9))
        attrs = lambda key: [{"key": k, "value": {"stringValue": str(v)}} for k, v in key]
        metrics: list[dict[str, Any]] = []
        for name, series in sorted(counters.items()):
            metrics.append({"name": name[:-6] if name.endswith("_total") else name, "description": helps.get(name, ""),
                            "sum": {"aggregationTemporality": 2, "isMonotonic": True,
                                    "dataPoints": [{"attributes": attrs(k), "startTimeUnixNano": start, "timeUnixNano": t, "asDouble": v} for k, v in sorted(series.items())]}})
        for name, series in sorted(hists.items()):
            points = []
            for k, row in sorted(series.items()):
                cumulative, total = row[:len(BUCKETS)], row[-1]
                counts = [cumulative[0]] + [cumulative[i] - cumulative[i - 1] for i in range(1, len(BUCKETS))] + [total - cumulative[-1]]
                points.append({"attributes": attrs(k), "startTimeUnixNano": start, "timeUnixNano": t, "count": str(int(total)), "sum": row[-2],
                               "bucketCounts": [str(int(c)) for c in counts], "explicitBounds": list(BUCKETS)})
            metrics.append({"name": name, "description": helps.get(name, ""), "histogram": {"aggregationTemporality": 2, "dataPoints": points}})
        for name, series in sorted(gauges.items()):
            metrics.append({"name": name, "description": helps.get(name, ""),
                            "gauge": {"dataPoints": [{"attributes": attrs(k), "timeUnixNano": t, "asDouble": v} for k, v in sorted(series.items())]}})
        by_name: dict[str, dict[str, Any]] = {}
        for name, help_text, labels, value in self.state_gauges():
            m = by_name.setdefault(name, {"name": name, "description": help_text, "gauge": {"dataPoints": []}})
            m["gauge"]["dataPoints"].append({"attributes": attrs(sorted(labels.items())), "timeUnixNano": t, "asDouble": value})
        metrics += list(by_name.values())
        resource = [{"key": "service.name", "value": {"stringValue": "enveliq"}}, {"key": "service.instance.id", "value": {"stringValue": cfg["instance"]}},
                    {"key": "service.version", "value": {"stringValue": VERSION}}]
        return json.dumps({"resourceMetrics": [{"resource": {"attributes": resource}, "scopeMetrics": [{"scope": {"name": "enveliq", "version": VERSION}, "metrics": metrics}]}]},
                          separators=(",", ":")).encode()

    # ---------- delivery ----------

    def start(self) -> None:
        if self._thread is None:
            self._stop.clear()
            self._thread = threading.Thread(target=self._run, name="reporting", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        if self._thread:
            self._thread.join(timeout=3)
            self._thread = None

    def _run(self) -> None:
        while not self._stop.is_set():
            self._wake.wait(FLUSH_SECONDS)
            self._wake.clear()
            try:
                self.flush()
            except Exception:
                pass

    def flush(self) -> None:
        """Deliver what is waiting to every output that is on."""
        cfg = self.config()
        if cfg is None:
            return
        with self._lock:
            batch = [self._queue.popleft() for _ in range(min(len(self._queue), BATCH * 5))]
            notes = [self._notes.popleft() for _ in range(len(self._notes))]
        if batch:
            for sink in ("logs", "loki", "webhook"):
                if cfg[sink]["enabled"]:
                    self._deliver(sink, cfg, batch)
        if notes and cfg["grafana"]["enabled"]:
            for when, name, text in notes:
                self._record("grafana", self._annotate(cfg, name, when, text))
        now = self.clock()
        if cfg["otlp"]["enabled"] and now - self._last_otlp >= cfg["otlp"]["interval"] - 1:
            self._last_otlp = now
            self._deliver("otlp", cfg, [])

    def _annotate(self, cfg: dict[str, Any], name: str, when: float, text: str) -> tuple[bool, str]:
        try:
            grafana.annotate(cfg["grafana"], name, cfg["instance"], when, text)
            return True, "ok"
        except grafana.GrafanaError as err:
            return False, err.code
        except Exception:
            return False, "failed"

    def _record(self, sink: str, result: tuple[bool, str]) -> tuple[bool, str]:
        state = self.sinks[sink]
        ok, code = result
        if ok:
            state.sent += 1
            state.last_ok, state.last_error = self.clock(), None
        else:
            state.failed += 1
            state.last_error = code
        return ok, code

    def _deliver(self, sink: str, cfg: dict[str, Any], events: list[dict[str, Any]]) -> tuple[bool, str]:
        return self._record(sink, self.send(sink, cfg, events))

    def send(self, sink: str, cfg: dict[str, Any], events: list[dict[str, Any]]) -> tuple[bool, str]:
        """Send events to one output. Returns (ok, fixed code)."""
        try:
            if sink == "logs":
                for e in events:
                    self.out.write(json.dumps({"app": "enveliq", "instance": cfg["instance"], **e}, separators=(",", ":")) + "\n")
                self.out.flush()
                return True, "ok"
            if sink == "loki":
                c = cfg["loki"]
                dest = net.check_destination(loki_url(c["url"]))
                headers = {"Content-Type": "application/json", **auth_headers(c)}
                if c["tenant"]:
                    headers["X-Scope-OrgID"] = c["tenant"]
                status = net.post(dest, loki_body(cfg, events), headers)
            elif sink == "otlp":
                c = cfg["otlp"]
                dest = net.check_destination(otlp_url(c["url"]))
                status = net.post(dest, self.otlp_payload(cfg), {"Content-Type": "application/json", "User-Agent": "enveliq-reporting", **auth_headers(c)})
            elif sink == "webhook":
                c = cfg["webhook"]
                dest = net.check_destination(c["url"])
                body = json.dumps({"source": "enveliq", "version": VERSION, "instance": cfg["instance"], "events": events}, separators=(",", ":")).encode()
                headers = {"Content-Type": "application/json", "User-Agent": "enveliq-reporting"}
                if c["secret"]:
                    headers["X-Enveliq-Signature"] = "sha256=" + hmac.new(c["secret"].encode(), body, hashlib.sha256).hexdigest()
                status = net.post(dest, body, headers)
            else:
                return False, "unknown"
        except net.DestinationError as err:
            return False, err.code
        except Exception:
            return False, "failed"
        if 200 <= status < 300:
            return True, "ok"
        return False, f"http_{status}" if status in (400, 401, 403, 404, 413, 429, 500, 502, 503) else "http_error"

    def send_test(self, sink: str, cfg: dict[str, Any]) -> tuple[bool, str]:
        """Send one test event to one output now (even if it is switched off)."""
        if sink == "grafana":
            try:
                grafana.check(cfg["grafana"])
                return True, "ok"
            except grafana.GrafanaError as err:
                return False, err.code
        record = {"ts": round(self.clock(), 3), "event": "report_test", "category": "activity", "level": "info"}
        return self.send(sink, cfg, [record])


def loki_url(url: str) -> str:
    url = url.strip()
    return url if url.rstrip("/").endswith("/loki/api/v1/push") else url.rstrip("/") + "/loki/api/v1/push"


def otlp_url(url: str) -> str:
    url = url.strip()
    return url if url.rstrip("/").endswith("/v1/metrics") else url.rstrip("/") + "/v1/metrics"


def auth_headers(c: dict[str, Any]) -> dict[str, str]:
    if c["auth"] == "bearer" and c["secret"]:
        return {"Authorization": "Bearer " + c["secret"]}
    if c["auth"] == "basic":
        import base64
        return {"Authorization": "Basic " + base64.b64encode(f'{c["username"]}:{c["secret"]}'.encode()).decode()}
    return {}


def loki_body(cfg: dict[str, Any], events: list[dict[str, Any]]) -> bytes:
    streams: dict[tuple, list[list[str]]] = {}
    for e in events:
        key = (e["level"], e["event"], e["category"])
        line = json.dumps({k: v for k, v in e.items() if k not in ("ts",)}, separators=(",", ":"))
        streams.setdefault(key, []).append([str(int(e["ts"] * 1e9)), line])
    out = []
    for (level, event, category), values in streams.items():
        labels = {"job": "enveliq", "instance": cfg["instance"], "level": level, "event": event, "category": category, **cfg["loki"]["labels"]}
        out.append({"stream": labels, "values": values})
    return json.dumps({"streams": out}, separators=(",", ":")).encode()


NULL = Reporter(None)
