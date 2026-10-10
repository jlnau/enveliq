"""Google Calendar: the administrator's client settings, starting the connection, and Google's return address."""
from __future__ import annotations

import secrets
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import Field

from ..models import StrictModel, header_safe
from . import gcal
from .limits import SlidingWindowLimiter
from .outbound import OutboundError

FLOW = "gcal"
BACK = "/#google-calendar="


class GoogleBody(StrictModel):
    enabled: bool = False
    client_id: str = Field(default="", max_length=200)
    client_secret: str | None = Field(default=None, max_length=300)       # None keeps the saved one, "" removes it


class EnabledBody(StrictModel):
    enabled: bool


def build_gcal_router(ctx: Any) -> APIRouter:
    router = APIRouter(prefix="/api/v1")
    vault, sync, flows, redirect_uri = ctx.vault, ctx.sync, ctx.flows, ctx.google_redirect_uri
    start_limit = SlidingWindowLimiter(max_events=10, window=60)

    @router.get("/admin/google")
    def get_settings(session=Depends(ctx.admin_session)):
        return gcal.public(sync.google.config(), redirect_uri)

    @router.put("/admin/google")
    def put_settings(body: GoogleBody, session=Depends(ctx.admin_session)):
        try:
            new = gcal.apply(sync.google.config(), {"enabled": body.enabled, "client_id": header_safe(body.client_id.strip()),
                                                    "client_secret": None if body.client_secret is None else header_safe(body.client_secret.strip())})
        except gcal.ConfigError as err:
            raise HTTPException(status_code=400, detail=str(err)) from None
        vault.set_global(gcal.RECORD, new)
        vault.audit({"event": "google_calendar_settings_saved", "actor_user_id": session.principal.user_id, "enabled": new["enabled"], "at": time.time()})
        return gcal.public(new, redirect_uri)

    @router.post("/me/sync/google/start")
    def start(session=Depends(ctx.full_session)):
        """Begin connecting. Returns Google's address for the browser to open."""
        if not start_limit.allow(session.principal.user_id):
            raise HTTPException(status_code=429, detail="Too many attempts. Wait a minute.")
        try:
            url, secrets_ = sync.google.authorization_url(redirect_uri)
        except OutboundError as err:
            raise HTTPException(status_code=400, detail=err.message) from None
        response = JSONResponse({"url": url})
        flow_id = flows.create(FLOW, {**secrets_, "user_id": session.principal.user_id}, ttl_seconds=600)
        ctx.set_cookie(response, ctx.flow_cookie, flow_id, max_age=600)
        return response

    @router.put("/me/sync/google")
    def toggle(body: EnabledBody, session=Depends(ctx.full_session)):
        try:
            sync.set_google_enabled(session.principal.user_id, body.enabled)
        except ValueError as err:
            raise HTTPException(status_code=422, detail=str(err)) from None
        return sync.overview(session.principal.user_id)

    @router.get("/sync/google/callback", include_in_schema=False)
    def callback(request: Request, code: str = "", state: str = "", error: str = ""):
        fid = request.cookies.get(ctx.flow_cookie)
        flow = flows.get(fid, FLOW)

        def back(result: str) -> RedirectResponse:
            resp = RedirectResponse(BACK + result, status_code=303)
            ctx.clear_cookie(resp, ctx.flow_cookie)
            return resp

        if flow is None:
            return back("expired")
        flows.pop(fid)
        data = flow["data"]
        session = ctx.peek_full_session(request)
        if session is None or session.principal.user_id != data["user_id"]:
            return back("expired")
        if error:
            return back("denied")
        if not state or not secrets.compare_digest(state, data["state"]) or not code or len(code) > 4096:
            return back("state")
        try:
            tokens = sync.google.exchange(code, redirect_uri, data["verifier"])
            sync.connect_google(session.principal.user_id, tokens["refresh_token"])
        except OutboundError as err:
            vault.audit({"event": "google_calendar_connect_failed", "reason": err.code, "at": time.time()})
            return back("failed")
        vault.audit({"event": "google_calendar_connected", "actor_user_id": session.principal.user_id, "at": time.time()})
        return back("ok")

    return router
