"""Administration API for reporting, and the /metrics endpoint."""
from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from ..mail.limits import SlidingWindowLimiter
from . import config as cfgmod
from . import grafana, net
from .core import Reporter, loki_url, otlp_url


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Categories(Strict):
    activity: bool = True
    security: bool = True


class Enabled(Strict):
    enabled: bool = False


class LokiBody(Strict):
    enabled: bool = False
    url: str = Field(default="", max_length=2048)
    auth: str = "none"
    username: str = Field(default="", max_length=200)
    secret: str | None = Field(default=None, max_length=4096)       # None keeps the saved one, "" removes it
    tenant: str = Field(default="", max_length=100)
    labels: dict[str, str] = Field(default_factory=dict, max_length=10)


class WebhookBody(Strict):
    enabled: bool = False
    url: str = Field(default="", max_length=2048)
    secret: str | None = Field(default=None, max_length=4096)


class OtlpBody(Strict):
    enabled: bool = False
    url: str = Field(default="", max_length=2048)
    auth: str = "none"
    username: str = Field(default="", max_length=200)
    secret: str | None = Field(default=None, max_length=4096)
    interval: int = 60


class GrafanaBody(Strict):
    enabled: bool = False
    url: str = Field(default="", max_length=2048)
    secret: str | None = Field(default=None, max_length=4096)
    folder: str = Field(default="Enveliq", max_length=60)
    prometheus_uid: str = Field(default="", max_length=64)
    loki_uid: str = Field(default="", max_length=64)
    annotations: bool = True


class ReportingBody(Strict):
    instance: str = Field(default="enveliq", max_length=40)
    label_mode: str = "id"
    categories: Categories = Categories()
    prometheus: Enabled = Enabled()
    logs: Enabled = Enabled()
    loki: LokiBody = LokiBody()
    webhook: WebhookBody = WebhookBody()
    otlp: OtlpBody = OtlpBody()
    grafana: GrafanaBody = GrafanaBody()


class TestBody(Strict):
    sink: str


def build_reporting_router(ctx: Any) -> APIRouter:
    router = APIRouter()
    reporter: Reporter = ctx.reporter
    vault = ctx.vault
    admin_dep = ctx.admin_session
    scrape_failures = SlidingWindowLimiter(max_events=30, window=60, max_keys=1)

    def mailboxes(cfg: dict[str, Any]) -> list[dict[str, str]]:
        return [{"label": reporter.mailbox_label(a["id"], cfg), "name": str(a.get("display_name") or "")[:60]} for a in vault.list_accounts()]

    def view() -> dict[str, Any]:
        cfg = cfgmod.load(vault)
        return {"config": cfgmod.public(cfg), "status": {k: v.public() for k, v in reporter.sinks.items()},
                "mailboxes": mailboxes({**cfg, "label_mode": cfg["label_mode"]}), "metrics_path": "/metrics",
                "allowed_hosts_set": bool(net.allowed_hosts())}

    @router.get("/api/v1/admin/reporting")
    def get_reporting(session=Depends(admin_dep)):
        return view()

    @router.put("/api/v1/admin/reporting")
    def put_reporting(body: ReportingBody, session=Depends(admin_dep)):
        try:
            new = cfgmod.apply(cfgmod.load(vault), body.model_dump())
            for sink, c in (("loki", new["loki"]), ("webhook", new["webhook"]), ("otlp", new["otlp"]), ("grafana", new["grafana"])):
                if c["enabled"] or c["url"]:
                    if not c["url"]:
                        raise cfgmod.ConfigError("Enter the address to send to, or switch it off.")
                    net.check_destination({"loki": loki_url, "otlp": otlp_url, "grafana": grafana.base_url}.get(sink, str)(c["url"]))
            if new["grafana"]["enabled"] and not new["grafana"]["secret"]:
                raise cfgmod.ConfigError("Paste the Grafana service-account token, or switch Grafana off.")
        except cfgmod.ConfigError as err:
            raise HTTPException(status_code=400, detail=str(err)) from None
        except net.DestinationError as err:
            raise HTTPException(status_code=400, detail=err.message) from None
        if new["prometheus"]["enabled"] and not new["prometheus"]["token_hash"]:
            raise HTTPException(status_code=400, detail="Create an access token for the metrics address before switching it on.")
        vault.set_global(cfgmod.RECORD, new)
        reporter.reload()
        vault.audit({"event": "reporting_config_saved", "actor_user_id": session.principal.user_id,
                     "prometheus": new["prometheus"]["enabled"], "logs": new["logs"]["enabled"], "loki": new["loki"]["enabled"], "webhook": new["webhook"]["enabled"],
                     "otlp": new["otlp"]["enabled"], "grafana": new["grafana"]["enabled"], "at": time.time()})
        return view()

    @router.post("/api/v1/admin/reporting/token")
    def new_token(session=Depends(admin_dep)):
        """Make a new access token for /metrics. It is shown once; only its hash is kept. The old token stops working."""
        cfg = cfgmod.load(vault)
        token, digest = cfgmod.new_token()
        cfg["prometheus"]["token_hash"] = digest
        vault.set_global(cfgmod.RECORD, cfg)
        reporter.reload()
        vault.audit({"event": "reporting_token_created", "actor_user_id": session.principal.user_id, "at": time.time()})
        return {"token": token}

    @router.post("/api/v1/admin/reporting/test")
    def test(body: TestBody, session=Depends(admin_dep)):
        if body.sink not in ("logs", "loki", "webhook", "otlp", "grafana"):
            raise HTTPException(status_code=400, detail="Unknown output.")
        cfg = cfgmod.load(vault)
        ok, code = reporter.send_test(body.sink, cfg)
        messages = {"ok": "Sent. Look for an event called report_test.", "bad_address": "That address is not valid.", "host_not_allowed": "That address is not allowed (this machine itself, a reserved range, or not on the administrator's list).",
                    "unresolvable": "That server name could not be found.", "needs_https": "A server outside your own network must use https.", "tls_failed": "The secure connection failed: check the certificate and the address.",
                    "unreachable": "The server could not be reached or took too long to answer.", "http_401": "The server refused the sign-in details (HTTP 401).", "http_403": "The server refused access (HTTP 403).",
                    "http_404": "The server does not have that path (HTTP 404). Check the address.", "http_429": "The server says too many requests (HTTP 429).", "not_set_up": "Enter the address and the token first.",
                    "bad_answer": "That address answered, but it does not look like the right kind of server. Check the address.",
                    "http_412": "Grafana refused the change (HTTP 412)."}
        if body.sink == "grafana":
            messages["http_401"] = "Grafana did not accept the token (HTTP 401). Make a new service-account token and paste it again."
            messages["http_403"] = "The token is valid but its role is not allowed to do this (HTTP 403). Give the service account the Editor role."
        return {"ok": ok, "code": code, "message": messages.get(code, "The server answered with an error." if code.startswith("http") else "It did not work.")}

    def grafana_settings() -> dict[str, Any]:
        return cfgmod.load(vault)["grafana"]

    def grafana_failure(err: grafana.GrafanaError) -> HTTPException:
        text = {"http_401": "Grafana did not accept the token (HTTP 401). Make a new service-account token and paste it again.",
                "http_403": "The token is valid but its role is not allowed to do this (HTTP 403). Give the service account the Editor role, or enter the data source IDs by hand.",
                "http_404": "Grafana does not have that path (HTTP 404). Check the address.", "http_429": "Grafana says too many requests (HTTP 429).",
                "http_error": "Grafana answered with an error.", "unreachable": "Grafana could not be reached or took too long to answer.",
                "tls_failed": "The secure connection failed: check the certificate and the address."}
        return HTTPException(status_code=502, detail={"code": err.code, "message": text.get(err.code) or err.message})

    @router.get("/api/v1/admin/reporting/grafana/datasources")
    def grafana_datasources(session=Depends(admin_dep)):
        """The Prometheus and Loki data sources the token can see (may be refused for a low role: then type the IDs by hand)."""
        try:
            return {"datasources": grafana.datasources(grafana_settings())}
        except grafana.GrafanaError as err:
            raise grafana_failure(err) from None

    @router.post("/api/v1/admin/reporting/grafana/dashboard")
    def grafana_dashboard(session=Depends(admin_dep)):
        """Install or update the Enveliq dashboard in the chosen folder, using the saved settings."""
        cfg = cfgmod.load(vault)
        try:
            link = grafana.install_dashboard(cfg["grafana"])
        except grafana.GrafanaError as err:
            raise grafana_failure(err) from None
        cfg["grafana"]["dashboard_url"] = link
        vault.set_global(cfgmod.RECORD, cfg)
        reporter.reload()
        vault.audit({"event": "reporting_dashboard_installed", "actor_user_id": session.principal.user_id, "at": time.time()})
        return {"url": link}

    @router.get("/metrics")
    def metrics(request: Request):
        """Prometheus text format. Needs `Authorization: Bearer <token>` made under Administration, Reporting."""
        def deny(status: int, detail: str) -> Response:
            return Response(content=detail + "\n", status_code=status, media_type="text/plain", headers={"WWW-Authenticate": "Bearer"} if status == 401 else {})
        if not vault.is_unlocked():
            return deny(503, "The vault is locked.")
        cfg = reporter.config()
        presented = request.headers.get("authorization", "")
        presented = presented[7:].strip() if presented.lower().startswith("bearer ") else ""
        if cfg is None or not cfg["prometheus"]["enabled"] or not cfgmod.token_matches(cfg, presented):
            if not scrape_failures.allow("fail"):
                return deny(429, "Too many failed attempts.")
            return deny(401, "Not authorised.")
        return Response(content=reporter.metrics_text(), media_type="text/plain; version=0.0.4; charset=utf-8", headers={"Cache-Control": "no-store"})

    return router
