"""Endpoints for mailboxes (Proton Bridge and app-password IMAP services)."""
from __future__ import annotations

import base64
import time
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi import Path as PathParam
from pydantic import Field, StrictBool, field_validator

from ..models import StrictModel, header_safe
from ..security import Session
from .errors import HTTP_STATUS, BridgeError
from .limits import SlidingWindowLimiter
from . import attach_service, llm_providers, providers, review
from . import microsoft as ms
from .llm import LlmConfig, Summariser, run_sample
from .service import AI_CONFIG_RECORD, MailService, target_for


UUID_PATTERN = r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
AccountId = Annotated[str, PathParam(pattern=UUID_PATTERN)]
MessageId = Annotated[str, PathParam(pattern=UUID_PATTERN)]
OutboxId = Annotated[str, PathParam(pattern=r"^[0-9a-f]{32}$")]


class SyncBody(StrictModel):
    since_days: int = Field(default=14, ge=1, le=60)
    limit: int = Field(default=50, ge=1, le=200)


class SummariseBody(StrictModel):
    limit: int = Field(default=10, ge=1, le=20)


class SyncConfigBody(StrictModel):
    minutes: int = Field(ge=0, le=1440)       # 0 = off; 1 is raised to the 2 minute minimum


class PrefsBody(StrictModel):
    keep_reviewed: bool
    keep_archived: bool
    keep_days: int = Field(ge=1, le=review.ABSOLUTE_MAX_DAYS)
    instructions: str = Field(default="", max_length=review.USER_INSTRUCTIONS_MAX)
    undo_send_seconds: int | None = Field(default=None, ge=0, le=60)    # None keeps what is saved


class ReviewSettingsBody(StrictModel):
    max_days: int = Field(ge=1, le=review.ABSOLUTE_MAX_DAYS)
    instructions: str = Field(default="", max_length=review.ADMIN_INSTRUCTIONS_MAX)


class PromptBody(StrictModel):
    prompt: str = Field(default="", max_length=review.PROMPT_MAX)
    acknowledged: bool = False


class AttachmentAiBody(StrictModel):
    """Whether attached files are read and summarised. For a cloud AI service, `acknowledged` says the administrator understands the text of the files leaves the network."""
    enabled: StrictBool
    acknowledged: StrictBool = False


class AiModelsBody(StrictModel):
    """Which AI server to ask for its model list. `api_key` None reuses the saved key for the same address."""
    url: str = Field(default="", max_length=2048)
    api_key: str | None = Field(default=None, max_length=4096)
    provider: str = Field(default="custom", max_length=40)

    @field_validator("url", "api_key")
    @classmethod
    def no_control(cls, value: str | None) -> str | None:
        return header_safe(value.strip()) if value is not None else None


class AiConfigBody(StrictModel):
    """AI server settings. `api_key` None keeps the saved key; "" removes it."""
    url: str = Field(default="", max_length=2048)      # not needed for a cloud service: it has one fixed address
    model: str = Field(min_length=1, max_length=200)
    api_key: str | None = Field(default=None, max_length=4096)
    provider: str = Field(default="custom", max_length=40)
    cloud_consent: bool = False

    @field_validator("url", "model", "api_key")
    @classmethod
    def no_control(cls, value: str | None) -> str | None:
        return header_safe(value.strip()) if value is not None else None


class ReplyBody(StrictModel):
    body: str = Field(min_length=1, max_length=100_000)
    from_address: str | None = Field(default=None, max_length=320)
    # Who it goes to. Left out, a reply goes to the sender and a Reply all also to the other people on the email.
    kind: Literal["reply", "reply_all"] = "reply"
    to: list[str] | None = Field(default=None, max_length=50)
    cc: list[str] | None = Field(default=None, max_length=50)
    bcc: list[str] | None = Field(default=None, max_length=50)
    # The whole original email is quoted under the reply unless the person already put it into their own message.
    add_original: bool = True

    @field_validator("from_address")
    @classmethod
    def from_address_safe(cls, value: str | None) -> str | None:
        return header_safe(value)

    @field_validator("to", "cc", "bcc")
    @classmethod
    def short_addresses(cls, values: list[str] | None) -> list[str] | None:
        for v in values or []:
            if len(v) > 320:
                raise ValueError("address too long")
        return values


class ForwardBody(StrictModel):
    to: list[str] = Field(default_factory=list, max_length=50)
    cc: list[str] = Field(default_factory=list, max_length=50)
    bcc: list[str] = Field(default_factory=list, max_length=50)
    body: str = Field(default="", max_length=100_000)
    from_address: str | None = Field(default=None, max_length=320)
    keep_files: list[int] | None = Field(default=None, max_length=50)    # numbers of the original's files to send; left out sends them all

    @field_validator("from_address")
    @classmethod
    def from_address_safe(cls, value: str | None) -> str | None:
        return header_safe(value)

    @field_validator("to", "cc", "bcc")
    @classmethod
    def short_addresses(cls, values: list[str]) -> list[str]:
        for v in values:
            if len(v) > 320:
                raise ValueError("address too long")
        return values


MAX_SNOOZE_DAYS = 366


class SnoozeBody(StrictModel):
    until: float | None = Field(default=None, ge=0, le=4_102_444_800)


def fail(err: BridgeError) -> HTTPException:
    return HTTPException(status_code=HTTP_STATUS.get(err.code, 502), detail={"code": err.code, "message": err.message})


def build_mail_router(ctx: Any) -> APIRouter:
    router = APIRouter(prefix="/api/v1")
    service: MailService = ctx.mail
    vault = ctx.vault
    outbox = ctx.outbox
    session_dep = ctx.full_session
    admin_dep = ctx.admin_session
    sync_limit = SlidingWindowLimiter(max_events=6, window=60)
    view_limit = SlidingWindowLimiter(max_events=60, window=60)
    ai_limit = SlidingWindowLimiter(max_events=12, window=60)
    send_limit = SlidingWindowLimiter(max_events=20, window=600)
    snooze_limit = SlidingWindowLimiter(max_events=120, window=60)
    send_total = SlidingWindowLimiter(max_events=200, window=3600, max_keys=1)
    ctx.send_limit, ctx.send_total = send_limit, send_total          # new email shares these limits with replies

    def owned(account_id: str, session: Session, action: str) -> dict[str, Any]:
        return ctx.load_account(account_id, session.principal, owner_only=True, action=action)

    def message_of(account_id: str, message_id: str) -> dict[str, Any]:
        try:
            return vault.get_message(account_id, message_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Message not found") from exc

    @router.get("/sync/status")
    def sync_status(session: Session = Depends(session_dep)):
        """Whether mail is fetched automatically, and how the last automatic pass went for your mailboxes."""
        mine = {a["id"] for a in vault.list_accounts() if a.get("owner_user_id") == session.principal.user_id}
        ctx.auto_sync.refresh()
        return {**ctx.auto_sync.status_for(mine), "now": time.time(), "editable": ctx.auto_sync.env_minutes is None}

    @router.put("/sync/config")
    def sync_config(body: SyncConfigBody, session: Session = Depends(admin_dep)):
        if ctx.auto_sync.env_minutes is not None:
            raise HTTPException(status_code=409, detail="The interval comes from the server's environment (ENVELIQ_SYNC_MINUTES) and can only be changed there.")
        ctx.auto_sync.save(body.minutes)
        vault.audit({"event": "sync_interval_saved", "actor_user_id": session.principal.user_id, "minutes": ctx.auto_sync.minutes, "at": time.time()})
        return {"ok": True, "minutes": ctx.auto_sync.minutes}

    @router.get("/me/preferences")
    def my_preferences(session: Session = Depends(session_dep)):
        """Whether to keep Reviewed and Archived cards, for how many days (never more than the administrator's maximum), and the person's own AI instructions."""
        return review.user_prefs(vault, session.principal.user_id)

    @router.put("/me/preferences")
    def save_my_preferences(body: PrefsBody, session: Session = Depends(session_dep)):
        saved = review.save_user_prefs(vault, ctx.users, session.principal.user_id, keep_reviewed=body.keep_reviewed,
                                       keep_archived=body.keep_archived, keep_days=body.keep_days, instructions=body.instructions,
                                       undo_send_seconds=body.undo_send_seconds)
        vault.audit({"event": "preferences_saved", "actor_user_id": session.principal.user_id, "at": time.time()})
        return saved

    @router.get("/admin/review-settings")
    def review_settings(session: Session = Depends(admin_dep)):
        return review.admin_config(vault)

    @router.put("/admin/review-settings")
    def save_review_settings(body: ReviewSettingsBody, session: Session = Depends(admin_dep)):
        saved = review.save_admin_config(vault, body.max_days, body.instructions)
        vault.audit({"event": "review_settings_saved", "actor_user_id": session.principal.user_id, "max_days": saved["max_days"], "at": time.time()})
        return saved

    @router.get("/admin/ai-prompt")
    def ai_prompt(session: Session = Depends(admin_dep)):
        """The built-in prompt: the part an administrator may replace, the part that is always added, and any replacement in use."""
        return review.prompt_state(vault)

    @router.put("/admin/ai-prompt")
    def save_ai_prompt(body: PromptBody, session: Session = Depends(admin_dep)):
        """Replace the built-in prompt (needs `acknowledged`), or restore it by sending an empty prompt."""
        if body.prompt.strip() and not body.acknowledged:
            raise HTTPException(status_code=400, detail="Confirm that you understand the risk before changing the built-in prompt.")
        try:
            state = review.save_prompt(vault, body.prompt)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"The prompt must be at least {review.PROMPT_MIN} characters. To go back to the built-in prompt, clear it and save.") from None
        vault.audit({"event": "ai_prompt_changed" if state["in_use"] else "ai_prompt_reset", "actor_user_id": session.principal.user_id, "at": time.time()})
        return state

    @router.get("/mail/providers")
    def mail_providers(session: Session = Depends(session_dep)):
        """The email services the setup guide offers, with their server settings and instructions."""
        out = []
        for p in providers.PROVIDERS:
            item = p.public()
            if p.oauth == "microsoft" and not ms.ready(ctx.microsoft.config()):
                item["status"] = "unavailable"
                item["unavailable_reason"] = ("Microsoft sign-in has not been set up in Enveliq yet. An administrator does this once, in a few minutes, under Administration, Microsoft sign-in, "
                                              "where every step is explained. Until then, mail forwarded to one of the other services works instead." if session.principal.is_admin else
                                              "Microsoft sign-in has not been set up in Enveliq yet. Ask an administrator to set it up (Administration, Microsoft sign-in). Until then, mail forwarded to one of the other services works instead.")
            out.append(item)
        return out

    @router.post("/accounts/{account_id}/bridge/check")
    def check(account_id: AccountId, session: Session = Depends(session_dep)):
        account = owned(account_id, session, "test this mailbox connection")
        if not sync_limit.allow(f"check:{session.principal.user_id}"):
            raise HTTPException(status_code=429, detail="Too many attempts. Wait a minute.")
        try:
            target = service.target(account)
            return ctx.bridge.check(target)
        except BridgeError as err:
            raise fail(err) from None

    @router.post("/accounts/{account_id}/sync")
    def sync(body: SyncBody, account_id: AccountId, session: Session = Depends(session_dep)):
        account = owned(account_id, session, "sync this mailbox")
        if not sync_limit.allow(f"sync:{session.principal.user_id}"):
            raise HTTPException(status_code=429, detail="Too many syncs. Wait a minute.")
        try:
            result = service.sync(vault, account, since_days=body.since_days, limit=body.limit)
        except BridgeError as err:
            raise fail(err) from None
        vault.audit({"event": "mailbox_synced", "actor_user_id": session.principal.user_id, "account_id": account_id,
                     "added": result["added"], "removed": result["removed"], "at": time.time()})
        return result

    @router.get("/ai/status")
    def ai_status(session: Session = Depends(session_dep)):
        # Whether a model is set up; never the address or key.
        service.refresh_ai(vault)
        known = llm_providers.get(service.summariser.config.provider)
        out = {"configured": service.summariser.enabled, "model": service.summariser.config.model or None, "source": service.ai_source}
        if service.summariser.enabled and known.cloud:
            out["cloud"] = known.label
        return out

    @router.get("/ai/config")
    def ai_config(session: Session = Depends(admin_dep)):
        service.refresh_ai(vault)
        cfg = service.summariser.config
        return {"source": service.ai_source, "url": cfg.url, "model": cfg.model, "has_key": bool(cfg.api_key), "provider": llm_providers.get(cfg.provider).id, "editable": service.ai_source != "environment",
                "env_vars": ([name for name, on in (("ENVELIQ_LLM_URL", cfg.url), ("ENVELIQ_LLM_MODEL", cfg.model), ("ENVELIQ_LLM_API_KEY", cfg.api_key), ("ENVELIQ_LLM_PROVIDER", cfg.provider)) if on]
                             if service.ai_source == "environment" else [])}

    def ai_trial_config(body: AiConfigBody, current: LlmConfig) -> LlmConfig:
        """The settings in the request as a config. A cloud service always uses its own fixed address, and a key already in use is only reused for the same address and service."""
        known = llm_providers.get(body.provider)
        url = known.url if known.cloud else body.url
        same = current.url == url and llm_providers.get(current.provider).id == known.id
        key = (current.api_key if same else "") if body.api_key is None else body.api_key
        if known.cloud and not key:
            raise HTTPException(status_code=400, detail=f"{known.label} needs an access key.")
        return LlmConfig(url=url, model=body.model, api_key=key, allowed_hosts=service.env_ai.allowed_hosts, provider=known.id)

    @router.get("/ai/providers")
    def ai_providers(session: Session = Depends(session_dep)):
        """The AI services the setup page offers: local servers and cloud services (which send mail text outside your network)."""
        return [p.public() for p in llm_providers.PROVIDERS]

    @router.put("/ai/config")
    def ai_config_save(body: AiConfigBody, session: Session = Depends(admin_dep)):
        service.refresh_ai(vault)
        if service.ai_source == "environment":
            raise HTTPException(status_code=409, detail="The AI settings come from the server's environment (ENVELIQ_LLM_URL) and can only be changed there.")
        known = llm_providers.get(body.provider)
        if known.cloud and not body.cloud_consent:
            raise HTTPException(status_code=400, detail=f"Confirm that you understand the text of your email will be sent to {known.company or known.label} before using {known.label}.")
        config = ai_trial_config(body, service.summariser.config)
        try:
            Summariser(config).check_url()
        except BridgeError as err:
            raise fail(err) from None
        vault.set_global(AI_CONFIG_RECORD, {"url": config.url, "model": config.model, "api_key": config.api_key, "provider": config.provider})
        vault.audit({"event": "ai_config_saved", "actor_user_id": session.principal.user_id, "provider": config.provider, "cloud": known.cloud, "at": time.time()})
        service.refresh_ai(vault)
        return {"ok": True}

    @router.delete("/ai/config", status_code=204)
    def ai_config_clear(session: Session = Depends(admin_dep)):
        service.refresh_ai(vault)
        if service.ai_source == "environment":
            raise HTTPException(status_code=409, detail="The AI settings come from the server's environment and can only be changed there.")
        vault.set_global(AI_CONFIG_RECORD, {})
        vault.audit({"event": "ai_config_cleared", "actor_user_id": session.principal.user_id, "at": time.time()})
        service.refresh_ai(vault)
        return Response(status_code=204)

    @router.post("/ai/models")
    def ai_models(body: AiModelsBody, session: Session = Depends(admin_dep)):
        """The models an AI server offers, so an administrator can pick one instead of typing its name. Same address rules as the test."""
        if not ai_limit.allow(f"aimodels:{session.principal.user_id}"):
            raise HTTPException(status_code=429, detail="Too many requests. Wait a minute.")
        service.refresh_ai(vault)
        known = llm_providers.get(body.provider)
        url = known.url if known.cloud else body.url
        if not url:
            raise HTTPException(status_code=400, detail="Type the AI server's address first.")
        current = service.summariser.config
        same = current.url == url and llm_providers.get(current.provider).id == known.id
        key = (current.api_key if same else "") if body.api_key is None else body.api_key
        if known.cloud and not key:
            raise HTTPException(status_code=400, detail=f"{known.label} needs an access key first.")
        try:
            return {"models": Summariser(LlmConfig(url=url, model="models", api_key=key, allowed_hosts=service.env_ai.allowed_hosts, provider=known.id)).list_models()}
        except BridgeError as err:
            raise fail(err) from None

    @router.post("/ai/test")
    def ai_test(body: AiConfigBody | None = None, session: Session = Depends(session_dep)):
        """Ask the model to summarise a made-up email. With a body (administrators
        only) it tries those settings before they are saved."""
        if not ai_limit.allow(f"aitest:{session.principal.user_id}"):
            raise HTTPException(status_code=429, detail="Too many tests. Wait a minute.")
        service.refresh_ai(vault)
        if body is not None:
            if not session.principal.is_admin:
                raise HTTPException(status_code=403, detail="Only an administrator can try new AI settings.")
            trial = Summariser(ai_trial_config(body, service.summariser.config))
        else:
            trial = service.summariser
        try:
            return {"ok": True, "result": run_sample(trial, review.instructions_for(vault, session.principal.user_id), review.active_prompt(vault))}
        except BridgeError as err:
            raise fail(err) from None

    @router.post("/accounts/{account_id}/summarise")
    def summarise(body: SummariseBody, account_id: AccountId, session: Session = Depends(session_dep)):
        account = owned(account_id, session, "summarise this mailbox")
        if not ai_limit.allow(f"ai:{session.principal.user_id}"):
            raise HTTPException(status_code=429, detail="Too many requests. Wait a minute.")
        try:
            result = service.summarise_pending(vault, account, limit=body.limit)
        except BridgeError as err:
            raise fail(err) from None
        vault.audit({"event": "mailbox_summarised", "actor_user_id": session.principal.user_id, "account_id": account_id,
                     "summarised": result["summarised"], "failed": result["failed"], "at": time.time()})
        return result

    @router.get("/admin/attachment-ai")
    def attachment_ai(session: Session = Depends(admin_dep)):
        service.refresh_ai(vault)
        return attach_service.status(vault, service.summariser)

    @router.put("/admin/attachment-ai")
    def attachment_ai_save(body: AttachmentAiBody, session: Session = Depends(admin_dep)):
        service.refresh_ai(vault)
        known = llm_providers.get(service.summariser.config.provider)
        if body.enabled and known.cloud and service.summariser.enabled and not body.acknowledged:
            raise HTTPException(status_code=400, detail=f"Confirm that you understand the text of attached files will be sent to {known.company or known.label}.")
        vault.set_global(attach_service.RECORD, {"enabled": body.enabled})
        vault.audit({"event": "attachment_ai_changed", "actor_user_id": session.principal.user_id, "enabled": body.enabled, "cloud": bool(known.cloud and service.summariser.enabled), "at": time.time()})
        return attach_service.status(vault, service.summariser)

    @router.post("/accounts/{account_id}/messages/{message_id}/attachments/summarise", status_code=202)
    def attachments_summarise(account_id: AccountId, message_id: MessageId, session: Session = Depends(session_dep)):
        """Try again for the files of one email whose summaries did not finish. The work goes on in the background."""
        account = owned(account_id, session, "summarise attached files")
        message = message_of(account_id, message_id)
        if not view_limit.allow(f"attsum:{session.principal.user_id}"):
            raise HTTPException(status_code=429, detail="Too many requests. Wait a minute.")
        service.refresh_ai(vault)
        if not service.summariser.enabled:
            raise HTTPException(status_code=409, detail={"code": "ai_not_configured", "message": "No AI model is set up yet. An administrator can add one under Administration, AI model."})
        if not (account.get("settings") or {}).get("ai_summaries"):
            raise HTTPException(status_code=400, detail={"code": "ai_disabled", "message": "AI summaries are switched off for this mailbox."})
        if not attach_service.allowed(vault, service.summariser):
            raise HTTPException(status_code=409, detail={"code": "attachments_off", "message": "Summarising attached files is switched off. An administrator can turn it on under Administration, AI model."})
        try:
            raw = service.original_raw(account, message)
        except BridgeError as err:
            raise fail(err) from None
        if len(raw) > attach_service.MAX_RAW:
            raise HTTPException(status_code=413, detail="This email is too large to read the files of.")
        instructions = review.instructions_for(vault, account.get("owner_user_id"))
        if not attach_service.run_in_background(vault, account_id, message_id, raw, service.summariser, instructions):
            raise HTTPException(status_code=409, detail="This email's files are already being read.")
        return {"started": True}

    @router.get("/accounts/{account_id}/messages/{message_id}/original")
    def original(account_id: AccountId, message_id: MessageId, response: Response, session: Session = Depends(session_dep)):
        account = owned(account_id, session, "view original emails")
        message = message_of(account_id, message_id)
        if not view_limit.allow(f"view:{session.principal.user_id}"):
            raise HTTPException(status_code=429, detail="Too many requests. Wait a minute.")
        try:
            result = service.view(account, message)
        except BridgeError as err:
            raise fail(err) from None
        response.headers["Cache-Control"] = "no-store"
        return result

    @router.post("/accounts/{account_id}/messages/{message_id}/reply")
    def reply(body: ReplyBody, account_id: AccountId, message_id: MessageId, session: Session = Depends(session_dep)):
        account = owned(account_id, session, "send replies")
        message = message_of(account_id, message_id)
        user = session.principal.user_id
        if not send_limit.allow(f"send:{user}") or not send_total.allow("all"):
            raise HTTPException(status_code=429, detail="Too many replies sent recently. Wait a few minutes.")
        delay = review.user_prefs(vault, user)["undo_send_seconds"]
        try:
            if delay > 0:
                # Undo send: check everything now, then hold the reply for the person's chosen time.
                built = service.build_reply(account, message, body.body, body.from_address, body.to, body.cc, body.bcc, body.kind, body.add_original)
                item = outbox.enqueue(user, account_id, message_id, built, body.body, delay, kind=body.kind)
                return {"queued": True, "id": item.id, "send_at": item.send_at, "now": time.time(), "from": item.chosen,
                        "to": item.recipients[0] if item.recipients else "", "people": len(item.recipients)}
            built = service.build_reply(account, message, body.body, body.from_address, body.to, body.cc, body.bcc, body.kind, body.add_original)
            sent_from = service.reply(account, message, body.body, body.from_address, built)
        except BridgeError as err:
            raise fail(err) from None
        service.mark_replied(vault, account_id, message_id)
        vault.audit({"event": "reply_sent", "actor_user_id": user, "account_id": account_id, "kind": body.kind, "people": len(built[2]),
                     "message_id": message_id, "at": time.time()})
        return {"sent": True, "from": sent_from}

    @router.post("/accounts/{account_id}/messages/{message_id}/forward")
    def forward(body: ForwardBody, account_id: AccountId, message_id: MessageId, session: Session = Depends(session_dep)):
        """Forward an email. The original is fetched from the mailbox now and never kept; the forward is built here, not by the page."""
        account = owned(account_id, session, "forward emails")
        message = message_of(account_id, message_id)
        user = session.principal.user_id
        if not send_limit.allow(f"send:{user}") or not send_total.allow("all"):
            raise HTTPException(status_code=429, detail="Too many emails sent recently. Wait a few minutes.")
        delay = review.user_prefs(vault, user)["undo_send_seconds"]
        try:
            built = service.build_forward(account, message, body.body, body.from_address, body.to, body.cc, body.bcc, body.keep_files)
            if delay > 0:
                item = outbox.enqueue(user, account_id, message_id, built, body.body, delay, kind="forward")
                return {"queued": True, "id": item.id, "send_at": item.send_at, "now": time.time(), "from": item.chosen,
                        "to": item.recipients[0] if item.recipients else "", "people": len(item.recipients)}
            service.bridge.send(service.target(account), built[0], built[1], built[2])
        except BridgeError as err:
            raise fail(err) from None
        vault.audit({"event": "email_forwarded", "actor_user_id": user, "account_id": account_id, "people": len(built[2]),
                     "message_id": message_id, "at": time.time()})
        return {"sent": True, "from": built[1]}

    @router.post("/accounts/{account_id}/messages/{message_id}/snooze")
    def snooze(body: SnoozeBody, account_id: AccountId, message_id: MessageId, response: Response, session: Session = Depends(session_dep)):
        """Keep an email out of the inbox list until a time the person picked (or bring it back now). The mailbox itself is not touched."""
        response.headers["Cache-Control"] = "no-store"
        user = session.principal.user_id
        owned(account_id, session, "snooze this email")
        stored = message_of(account_id, message_id)
        if not snooze_limit.allow(f"snooze:{user}"):
            raise HTTPException(status_code=429, detail="Too many changes. Wait a minute.")
        now = time.time()
        until = body.until
        if until is not None:
            if until < now + 30 or until > now + MAX_SNOOZE_DAYS * 86400:
                raise HTTPException(status_code=422, detail=f"Pick a time between now and {MAX_SNOOZE_DAYS} days away.")
            if stored.get("state", "unread") != "unread" or stored.get("from_all_mail"):
                raise HTTPException(status_code=409, detail="Only emails in your inbox can be snoozed.")
        out = service.mark_snoozed(vault, account_id, message_id, until)
        vault.audit({"event": "message_snoozed" if until is not None else "message_unsnoozed", "actor_user_id": user, "account_id": account_id,
                     "message_id": message_id, "at": now})
        return out

    @router.get("/me/outbox")
    def my_outbox(response: Response, session: Session = Depends(session_dep)):
        """Replies waiting to send (undo send) and how recent ones ended, for the signed-in person."""
        response.headers["Cache-Control"] = "no-store"
        return {"now": time.time(), "items": outbox.listing(session.principal.user_id)}

    @router.delete("/me/outbox/{item_id}")
    def cancel_outbox(item_id: OutboxId, response: Response, session: Session = Depends(session_dep)):
        """Undo send: take a waiting reply back. The text comes back so the reply can be edited."""
        response.headers["Cache-Control"] = "no-store"
        try:
            item = outbox.cancel(session.principal.user_id, item_id)
        except BridgeError as err:
            raise fail(err) from None
        if item is None:
            raise HTTPException(status_code=404, detail="That reply is not waiting any more.")
        vault.audit({"event": "reply_cancelled", "actor_user_id": session.principal.user_id, "account_id": item.account_id,
                     "message_id": item.message_id, "at": time.time()})
        files: list[dict[str, Any]] = []
        if item.draft:
            # A new email's attachments are still only in the server's memory; hand them back so Undo keeps them.
            for part in item.msg.iter_attachments():
                data = part.get_payload(decode=True) or b""
                files.append({"name": part.get_filename() or "attachment", "type": part.get_content_type(),
                              "data": base64.b64encode(data).decode("ascii")})
        def listed(name: str) -> list[str]:
            return [a.addr_spec for h in item.msg.get_all(name, []) for a in getattr(h, "addresses", ())]
        to_list, cc_list = listed("To"), listed("Cc")
        shown = {x.lower() for x in to_list + cc_list}
        people = {"kind": item.kind, "to_list": to_list, "cc_list": cc_list, "bcc_list": [r for r in item.recipients if r.lower() not in shown]}
        return {**people, "cancelled": True, "body": item.body, "from": item.chosen, "to": item.recipients[0] if item.recipients else "",
                "account_id": item.account_id, "message_id": item.message_id, "draft": item.draft, "files": files}

    return router
