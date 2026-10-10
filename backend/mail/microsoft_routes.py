"""Endpoints for Microsoft sign-in: the administrator's settings, starting a sign-in, and the return address."""
from __future__ import annotations

import secrets
import time
from typing import Any
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import Field, field_validator

from ..models import StrictModel, header_safe
from . import microsoft as ms
from .limits import SlidingWindowLimiter

FLOW = "msoauth"
SUCCESS = "/welcome"


class MicrosoftBody(StrictModel):
    enabled: bool = False
    client_id: str = Field(default="", max_length=64)
    tenant: str = Field(default="common", max_length=255)
    client_secret: str | None = Field(default=None, max_length=1024)       # None keeps the saved one, "" removes it

    @field_validator("client_id", "tenant", "client_secret")
    @classmethod
    def no_control(cls, value: str | None) -> str | None:
        return header_safe(value.strip()) if value is not None else None


class StartBody(StrictModel):
    display_name: str = Field(min_length=1, max_length=128)
    send_identities: list[str] = Field(default_factory=list, max_length=10)
    ai_summaries: bool = False


def build_microsoft_router(ctx: Any) -> APIRouter:
    router = APIRouter(prefix="/api/v1")
    vault, service, microsoft = ctx.vault, ctx.mail, ctx.microsoft
    flows = ctx.flows
    redirect_uri = ctx.microsoft_redirect_uri
    start_limit = SlidingWindowLimiter(max_events=10, window=60)

    @router.get("/admin/microsoft")
    def get_settings(session=Depends(ctx.admin_session)):
        return ms.public(microsoft.config(), redirect_uri)

    @router.put("/admin/microsoft")
    def put_settings(body: MicrosoftBody, session=Depends(ctx.admin_session)):
        try:
            new = ms.apply(microsoft.config(), body.model_dump())
        except ms.ConfigError as err:
            raise HTTPException(status_code=400, detail=str(err)) from None
        vault.set_global(ms.RECORD, new)
        microsoft.forget()
        vault.audit({"event": "microsoft_settings_saved", "actor_user_id": session.principal.user_id, "enabled": new["enabled"], "at": time.time()})
        return ms.public(new, redirect_uri)

    @router.get("/mail/microsoft/messages")
    def messages(session=Depends(ctx.full_session)):
        """Plain wording for each sign-in result code (the return page shows one of them)."""
        return ms.MESSAGES

    @router.get("/mail/microsoft/status")
    def status(session=Depends(ctx.full_session)):
        return {"ready": ms.ready(microsoft.config())}

    @router.post("/mail/microsoft/start")
    def start(body: StartBody, session=Depends(ctx.full_session)):
        """Begin signing in at Microsoft. Returns the address to send the browser to."""
        if not start_limit.allow(session.principal.user_id):
            raise HTTPException(status_code=429, detail="Too many attempts. Wait a minute.")
        identities = [i.strip() for i in body.send_identities if i.strip()]
        if any(not ms.EMAIL.match(i) for i in identities):
            raise HTTPException(status_code=400, detail="The other addresses must be email addresses.")
        try:
            url, secrets_ = microsoft.authorization_url(redirect_uri)
        except ms.MsError as err:
            raise HTTPException(status_code=400, detail={"code": err.code, "message": err.message}) from None
        response = JSONResponse({"url": url})
        flow_id = flows.create(FLOW, {**secrets_, "user_id": session.principal.user_id, "display_name": body.display_name,
                                      "identities": identities, "ai": bool(body.ai_summaries)}, ttl_seconds=600)
        ctx.set_cookie(response, ctx.flow_cookie, flow_id, max_age=600)
        return response

    @router.get("/mail/microsoft/callback")
    def callback(request: Request, code: str = "", state: str = "", error: str = ""):
        fid = request.cookies.get(ctx.flow_cookie)
        flow = flows.get(fid, FLOW)

        def back(result: str, reason: str = "") -> RedirectResponse:
            query = {"ms": result, **({"code": reason} if reason else {})}
            resp = RedirectResponse(f"{SUCCESS}?{urlencode(query)}", status_code=303)
            ctx.clear_cookie(resp, ctx.flow_cookie)
            return resp

        if flow is None:
            return back("error", "ms_expired")
        flows.pop(fid)
        data = flow["data"]
        session = ctx.peek_full_session(request)
        if session is None or session.principal.user_id != data["user_id"]:
            return back("error", "ms_expired")
        if error:
            return back("error", "ms_denied")
        if not state or not secrets.compare_digest(state, data["state"]) or not code or len(code) > 4096:
            return back("error", "ms_state")
        try:
            tokens = microsoft.exchange(code, redirect_uri, data["verifier"])
        except ms.MsError as err:
            vault.audit({"event": "microsoft_signin_failed", "reason": err.code, "at": time.time()})
            return back("error", err.code)
        record = {
            "provider": "Outlook", "display_name": data["display_name"], "email_address": tokens["email"], "auth_method": "imap",
            "server": ms.IMAP_HOST, "port": ms.IMAP_PORT, "username": tokens["email"], "password": None, "oauth_refresh_token": tokens["refresh_token"],
            "settings": {"provider_id": "outlook", "auth": "microsoft", "imap_security": "ssl", "smtp_host": ms.SMTP_HOST, "smtp_port": ms.SMTP_PORT,
                         "smtp_security": "starttls", "send_identities": data["identities"], "ai_summaries": data["ai"]},
            "owner_user_id": session.principal.user_id, "privacy": {"visibility": "private", "shared_with": []}, "created_at": time.time(),
        }
        account_id = vault.create_account(record)
        account = vault.get_account(account_id)
        microsoft.remember(account_id, tokens)
        try:
            check = ctx.bridge.check(service.target(account))
        except Exception as err:  # a failed sign-in token or a refused mailbox: keep nothing
            check = {"imap": getattr(err, "code", "failed"), "smtp": "failed"}
        if check.get("imap") != "ok" or check.get("smtp") != "ok":
            vault.delete_account(account_id)
            microsoft.forget()
            bad = check.get("imap") if check.get("imap") != "ok" else check.get("smtp")
            vault.audit({"event": "microsoft_signin_failed", "reason": str(bad)[:40] if str(bad).replace("_", "").isalnum() else "failed", "at": time.time()})
            return back("error", bad if bad in ms.MESSAGES else "ms_mailbox_refused")
        vault.audit({"event": "account_created", "actor_user_id": session.principal.user_id, "account_id": account_id, "at": time.time()})
        vault.audit({"event": "microsoft_mailbox_connected", "actor_user_id": session.principal.user_id, "account_id": account_id, "at": time.time()})
        return back("ok")

    return router
