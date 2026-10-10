"""Reporting settings: stored encrypted in the vault, secrets never returned."""
from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from typing import Any

RECORD = "reporting_config"
INSTANCE = re.compile(r"^[A-Za-z0-9_.-]{1,40}$")
LABEL_KEY = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]{0,30}$")
LABEL_VALUE = re.compile(r"^[A-Za-z0-9_.:/ -]{0,60}$")
TENANT = re.compile(r"^[A-Za-z0-9_.-]{0,100}$")
RESERVED_LABELS = {"job", "instance", "level", "event", "category", "mailbox"}
MAX_LABELS = 5

DEFAULT: dict[str, Any] = {
    "instance": "enveliq",
    "label_mode": "id",                      # how mailboxes are named in reports: "id" (anonymous) or "name"
    "categories": {"activity": True, "security": True},
    "prometheus": {"enabled": False, "token_hash": ""},
    "logs": {"enabled": False},
    "loki": {"enabled": False, "url": "", "auth": "none", "username": "", "secret": "", "tenant": "", "labels": {}},
    "webhook": {"enabled": False, "url": "", "secret": ""},
    "otlp": {"enabled": False, "url": "", "auth": "none", "username": "", "secret": "", "interval": 60},
    "grafana": {"enabled": False, "url": "", "secret": "", "folder": "Enveliq", "prometheus_uid": "", "loki_uid": "", "annotations": True, "dashboard_url": ""},
}
UID = re.compile(r"^[A-Za-z0-9_-]{0,64}$")
FOLDER = re.compile(r"^[A-Za-z0-9 _.-]{1,60}$")
INTERVALS = (30, 60, 300)


class ConfigError(ValueError):
    pass


def load(vault: Any) -> dict[str, Any]:
    """The saved settings merged over the defaults (unknown or malformed values fall back)."""
    saved = vault.get_global(RECORD) or {}
    out = {k: (dict(v) if isinstance(v, dict) else v) for k, v in DEFAULT.items()}
    if isinstance(saved.get("instance"), str) and INSTANCE.match(saved["instance"]):
        out["instance"] = saved["instance"]
    if saved.get("label_mode") in ("id", "name"):
        out["label_mode"] = saved["label_mode"]
    cats = saved.get("categories") if isinstance(saved.get("categories"), dict) else {}
    out["categories"] = {k: cats.get(k) is not False for k in ("activity", "security")}
    for sink in ("prometheus", "logs", "loki", "webhook", "otlp", "grafana"):
        got = saved.get(sink) if isinstance(saved.get(sink), dict) else {}
        for key, default in DEFAULT[sink].items():
            value = got.get(key, default)
            out[sink][key] = value if isinstance(value, type(default)) else default
        out[sink]["enabled"] = got.get("enabled") is True
    return out


def public(cfg: dict[str, Any]) -> dict[str, Any]:
    """What an administrator may see: the secrets only as yes/no."""
    loki, hook = cfg["loki"], cfg["webhook"]
    return {
        "instance": cfg["instance"], "label_mode": cfg["label_mode"], "categories": cfg["categories"],
        "prometheus": {"enabled": cfg["prometheus"]["enabled"], "has_token": bool(cfg["prometheus"]["token_hash"])},
        "logs": {"enabled": cfg["logs"]["enabled"]},
        "loki": {"enabled": loki["enabled"], "url": loki["url"], "auth": loki["auth"], "username": loki["username"],
                 "has_secret": bool(loki["secret"]), "tenant": loki["tenant"], "labels": loki["labels"]},
        "webhook": {"enabled": hook["enabled"], "url": hook["url"], "has_secret": bool(hook["secret"])},
        "otlp": {"enabled": cfg["otlp"]["enabled"], "url": cfg["otlp"]["url"], "auth": cfg["otlp"]["auth"], "username": cfg["otlp"]["username"],
                 "has_secret": bool(cfg["otlp"]["secret"]), "interval": cfg["otlp"]["interval"]},
        "grafana": {"enabled": cfg["grafana"]["enabled"], "url": cfg["grafana"]["url"], "has_secret": bool(cfg["grafana"]["secret"]),
                    "folder": cfg["grafana"]["folder"], "prometheus_uid": cfg["grafana"]["prometheus_uid"], "loki_uid": cfg["grafana"]["loki_uid"],
                    "annotations": cfg["grafana"]["annotations"], "dashboard_url": cfg["grafana"]["dashboard_url"]},
    }


def _secret(new: str | None, old: str) -> str:
    return old if new is None else new.strip()


def apply(cfg: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
    """Settings after applying a request. Raises ConfigError with a plain message."""
    out = load_like(cfg)
    instance = str(body.get("instance", out["instance"])).strip()
    if not INSTANCE.match(instance):
        raise ConfigError("The name can use letters, numbers, dots, dashes and underscores (up to 40).")
    out["instance"] = instance
    if body.get("label_mode") not in ("id", "name"):
        raise ConfigError("Choose how mailboxes are named in reports.")
    out["label_mode"] = body["label_mode"]
    out["categories"] = {"activity": bool(body["categories"]["activity"]), "security": bool(body["categories"]["security"])}
    out["prometheus"]["enabled"] = bool(body["prometheus"]["enabled"])
    out["logs"]["enabled"] = bool(body["logs"]["enabled"])
    lk, old = body["loki"], out["loki"]
    if lk["auth"] not in ("none", "basic", "bearer"):
        raise ConfigError("Choose how to sign in to Loki: none, user name and password, or a token.")
    labels = {}
    for key, value in (lk.get("labels") or {}).items():
        key, value = str(key).strip(), str(value).strip()
        if not LABEL_KEY.match(key) or key in RESERVED_LABELS or not LABEL_VALUE.match(value):
            raise ConfigError(f"Extra label \"{key}\" is not allowed. Use letters, numbers and underscores; these names are taken: {', '.join(sorted(RESERVED_LABELS))}.")
        labels[key] = value
    if len(labels) > MAX_LABELS:
        raise ConfigError(f"At most {MAX_LABELS} extra labels.")
    tenant = str(lk.get("tenant", "")).strip()
    if not TENANT.match(tenant):
        raise ConfigError("The tenant ID can use letters, numbers, dots, dashes and underscores.")
    out["loki"] = {"enabled": bool(lk["enabled"]), "url": str(lk.get("url", "")).strip(), "auth": lk["auth"],
                   "username": str(lk.get("username", "")).strip()[:200], "secret": _secret(lk.get("secret"), old["secret"]),
                   "tenant": tenant, "labels": labels}
    if out["loki"]["auth"] == "none":
        out["loki"]["secret"] = ""
    wh = body["webhook"]
    out["webhook"] = {"enabled": bool(wh["enabled"]), "url": str(wh.get("url", "")).strip(), "secret": _secret(wh.get("secret"), out["webhook"]["secret"])}
    ot, old_ot = body["otlp"], out["otlp"]
    if ot["auth"] not in ("none", "basic", "bearer"):
        raise ConfigError("Choose how to sign in to the OpenTelemetry receiver: none, user name and password, or a token.")
    if ot["interval"] not in INTERVALS:
        raise ConfigError("Choose how often to send metrics: every 30 seconds, 1 minute or 5 minutes.")
    out["otlp"] = {"enabled": bool(ot["enabled"]), "url": str(ot.get("url", "")).strip(), "auth": ot["auth"], "username": str(ot.get("username", "")).strip()[:200],
                   "secret": _secret(ot.get("secret"), old_ot["secret"]), "interval": ot["interval"]}
    if out["otlp"]["auth"] == "none":
        out["otlp"]["secret"] = ""
    gr, old_gr = body["grafana"], out["grafana"]
    folder = str(gr.get("folder", "")).strip() or "Enveliq"
    if not FOLDER.match(folder):
        raise ConfigError("The folder name can use letters, numbers, spaces, dots, dashes and underscores (up to 60).")
    uids = {k: str(gr.get(k, "")).strip() for k in ("prometheus_uid", "loki_uid")}
    for k, v in uids.items():
        if not UID.match(v):
            raise ConfigError("A data source ID can use letters, numbers, dashes and underscores. Pick it from the list or copy it from the data source's address in Grafana.")
    out["grafana"] = {"enabled": bool(gr["enabled"]), "url": str(gr.get("url", "")).strip(), "secret": _secret(gr.get("secret"), old_gr["secret"]),
                      "folder": folder, "prometheus_uid": uids["prometheus_uid"], "loki_uid": uids["loki_uid"], "annotations": bool(gr["annotations"]),
                      "dashboard_url": old_gr["dashboard_url"]}
    return out


def load_like(cfg: dict[str, Any]) -> dict[str, Any]:
    return {k: (dict(v) if isinstance(v, dict) else v) for k, v in cfg.items()}


def new_token() -> tuple[str, str]:
    """(token to show once, hash to store)."""
    token = "enq_" + secrets.token_urlsafe(32)
    return token, hash_token(token)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def token_matches(cfg: dict[str, Any], presented: str) -> bool:
    stored = cfg["prometheus"]["token_hash"]
    return bool(stored) and bool(presented) and hmac.compare_digest(stored, hash_token(presented))
