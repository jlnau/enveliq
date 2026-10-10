"""Talking to a Grafana server with a service-account token.

Used for three things only: checking the connection, installing or updating the
Enveliq dashboard in a folder, and adding annotations (small markers on the
charts) for key events. Every address is checked by `net.check_destination` first.
Error codes are fixed words; nothing the server says is passed on.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import net

DASHBOARD_FILE = Path(__file__).with_name("enveliq-dashboard.json")
LOKI_DASHBOARD_FILE = Path(__file__).with_name("enveliq-dashboard-loki.json")
DASHBOARD_UID = "enveliq-overview"
MAX_BODY = 1_000_000


class GrafanaError(Exception):
    def __init__(self, code: str, message: str = ""):
        super().__init__(code)
        self.code = code
        self.message = message or code


def base_url(url: str) -> str:
    url = url.strip().rstrip("/")
    if url.endswith("/api"):
        url = url[:-4]
    return url


def _call(c: dict[str, Any], method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
    if not c["url"] or not c["secret"]:
        raise GrafanaError("not_set_up", "Enter the Grafana address and the service-account token first.")
    try:
        dest = net.check_destination(base_url(c["url"]) + path)
        body = json.dumps(payload, separators=(",", ":")).encode() if payload is not None else None
        headers = {"Authorization": "Bearer " + c["secret"], "Accept": "application/json", "User-Agent": "enveliq-reporting"}
        if body is not None:
            headers["Content-Type"] = "application/json"
        status, answer = net.request(dest, method, body, headers)
    except net.DestinationError as err:
        raise GrafanaError(err.code, err.message) from None
    if 200 <= status < 300:
        try:
            return json.loads(answer.decode("utf-8", "replace")) if answer else {}
        except ValueError:
            raise GrafanaError("bad_answer", "That address answered, but it does not look like Grafana. Check the address.") from None
    known = {401: "http_401", 403: "http_403", 404: "http_404", 412: "http_412", 429: "http_429"}
    raise GrafanaError(known.get(status, "http_error"))


def check(c: dict[str, Any]) -> dict[str, str]:
    org = _call(c, "GET", "/api/org")
    if not isinstance(org, dict) or "name" not in org:
        raise GrafanaError("bad_answer", "That address answered, but it does not look like Grafana. Check the address.")
    return {"org": str(org["name"])[:80]}


def datasources(c: dict[str, Any]) -> list[dict[str, str]]:
    found = _call(c, "GET", "/api/datasources")
    out = []
    for item in found if isinstance(found, list) else []:
        if isinstance(item, dict) and item.get("type") in ("prometheus", "loki") and isinstance(item.get("uid"), str):
            out.append({"uid": item["uid"][:64], "name": str(item.get("name", ""))[:80], "type": item["type"]})
    return out


def dashboard_for(prometheus_uid: str, loki_uid: str) -> dict[str, Any]:
    """The built-in dashboard with the chosen data sources filled in.
    With Prometheus: the full dashboard (the log panel is left out without a Loki).
    With only Loki: a smaller dashboard drawn from the event logs."""
    if not prometheus_uid and loki_uid:
        dash = json.loads(LOKI_DASHBOARD_FILE.read_text(encoding="utf-8"))
        dash.pop("__inputs", None)
        return json.loads(json.dumps(dash).replace("${DS_LOKI}", loki_uid))
    dash = json.loads(DASHBOARD_FILE.read_text(encoding="utf-8"))
    dash.pop("__inputs", None)
    if not loki_uid:
        dash["panels"] = [p for p in dash["panels"] if (p.get("datasource") or {}).get("uid") != "${DS_LOKI}"]
    text = json.dumps(dash).replace("${DS_PROMETHEUS}", prometheus_uid).replace("${DS_LOKI}", loki_uid)
    return json.loads(text)


def _folder_uid(c: dict[str, Any]) -> str:
    wanted = c["folder"]
    folders = _call(c, "GET", "/api/folders?limit=1000")
    for item in folders if isinstance(folders, list) else []:
        if isinstance(item, dict) and item.get("title") == wanted and isinstance(item.get("uid"), str):
            return item["uid"]
    made = _call(c, "POST", "/api/folders", {"title": wanted})
    if not isinstance(made, dict) or not isinstance(made.get("uid"), str):
        raise GrafanaError("bad_answer", "Grafana did not create the folder.")
    return made["uid"]


def install_dashboard(c: dict[str, Any]) -> str:
    """Create or update the dashboard. Returns its address in Grafana."""
    if not c["prometheus_uid"] and not c["loki_uid"]:
        raise GrafanaError("no_datasource", "Choose a data source first: Loki, or Prometheus, or both.")
    folder = _folder_uid(c)
    result = _call(c, "POST", "/api/dashboards/db", {"dashboard": dashboard_for(c["prometheus_uid"], c["loki_uid"]), "folderUid": folder,
                                                       "overwrite": True, "message": "Installed by Enveliq"})
    path = result.get("url") if isinstance(result, dict) else None
    if not isinstance(path, str) or not path.startswith("/d/"):
        path = "/d/" + DASHBOARD_UID
    return base_url(c["url"]) + path


def annotate(c: dict[str, Any], event: str, instance: str, when: float, text: str) -> None:
    _call(c, "POST", "/api/annotations", {"time": int(when * 1000), "tags": ["enveliq", event, instance], "text": text})
