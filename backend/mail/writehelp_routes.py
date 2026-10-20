"""Writing help: settings, and one request that asks the AI to suggest or check a reply. Nothing is stored or logged but a "used" audit line."""
from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import Field

from ..models import StrictModel
from ..security import Session
from . import features, writehelp as W
from .limits import SlidingWindowLimiter
from .llm import BridgeError
from .routes import AccountId, MessageId, fail


class SettingsBody(StrictModel):
    on: bool
    quick: bool | None = None
    instructions: str | None = Field(default=None, max_length=W.INSTRUCTIONS_MAX * 2)


class DraftBody(StrictModel):
    draft: str = Field(default="", max_length=W.DRAFT_MAX * 2)


class NewDraftBody(DraftBody):
    subject: str = Field(default="", max_length=400)


class QuickBody(StrictModel):
    subject: str = Field(default="", max_length=400)
    draft: str = Field(default="", max_length=W.DRAFT_MAX * 2)


def build_writehelp_router(ctx: Any) -> APIRouter:
    router = APIRouter(prefix="/api/v1")
    book: W.WriteHelpBook = ctx.writehelp
    service, vault = ctx.mail, ctx.vault
    session_dep = ctx.full_session
    limit = SlidingWindowLimiter(max_events=12, window=60)

    def available(user: str) -> bool:
        return features.effective(vault, user)["write_help"]

    def ready(session: Session) -> str:
        """The signed-in person, if writing help is allowed for them and they turned it on."""
        user = session.principal.user_id
        if not available(user):
            raise HTTPException(status_code=403, detail="Writing help is switched off.")
        if not book.get(user)["on"]:
            raise HTTPException(status_code=403, detail="Turn on writing help in Settings first.")
        if not limit.allow(f"writehelp:{user}"):
            raise HTTPException(status_code=429, detail="Too many requests. Wait a minute.")
        service.refresh_ai(vault)
        if not service.summariser.enabled:
            raise HTTPException(status_code=409, detail={"code": "ai_not_configured", "message": "No AI model is set up yet. An administrator can add one under Administration, AI model."})
        return user

    def guide_of(user: str) -> str:
        style = getattr(ctx, "style", None)
        return style.guide_for(user) if style is not None else ""

    def answer(user: str, mode: str, draft: str, **context: str) -> dict[str, Any]:
        try:
            result = W.run(service.summariser, book.get(user)["instructions"], mode, draft, guide=guide_of(user), **context)
        except BridgeError as err:
            raise fail(err) from None
        except Exception:
            raise HTTPException(status_code=502, detail={"code": "ai_unreachable", "message": "The AI server could not be reached or took too long to answer."}) from None
        vault.audit({"event": "write_help_used", "actor_user_id": user, "mode": mode, "at": time.time()})   # that it was used, never any words
        return result

    @router.get("/me/write-help")
    def get_settings(response: Response, session: Session = Depends(session_dep)):
        response.headers["Cache-Control"] = "no-store"
        user = session.principal.user_id
        service.refresh_ai(vault)
        return {"available": available(user), "ai_ready": service.summariser.enabled, **book.get(user)}

    @router.put("/me/write-help")
    def put_settings(body: SettingsBody, response: Response, session: Session = Depends(session_dep)):
        response.headers["Cache-Control"] = "no-store"
        user = session.principal.user_id
        if not available(user):
            raise HTTPException(status_code=403, detail="Writing help is switched off.")
        saved = book.save(user, body.on, body.instructions, body.quick)
        vault.audit({"event": "write_help_settings", "actor_user_id": user, "on": saved["on"], "quick": saved["quick"], "at": time.time()})
        service.refresh_ai(vault)
        return {"available": True, "ai_ready": service.summariser.enabled, **saved}

    @router.post("/accounts/{account_id}/messages/{message_id}/write-help")
    def for_reply(body: DraftBody, account_id: AccountId, message_id: MessageId, response: Response, session: Session = Depends(session_dep)):
        response.headers["Cache-Control"] = "no-store"
        user = ready(session)
        account = ctx.load_account(account_id, session.principal, owner_only=True, action="use writing help on this mailbox")
        try:
            message = vault.get_message(account_id, message_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Message not found") from exc
        try:
            original = service.view(account, message)          # fetched from the mailbox now; the page never chooses what the model reads
        except BridgeError as err:
            raise fail(err) from None
        sender = f'{message.get("sender_display") or ""} <{message.get("sender_address") or ""}>' 
        return answer(user, "reply", body.draft, subject=str(original.get("subject") or message.get("subject") or ""),
                      sender=sender, email_text=str(original.get("text") or ""))

    @router.post("/me/write-help/new")
    def for_new(body: NewDraftBody, response: Response, session: Session = Depends(session_dep)):
        response.headers["Cache-Control"] = "no-store"
        user = ready(session)
        return answer(user, "new", body.draft, subject=body.subject)

    @router.post("/me/write-help/quick-fix")
    def quick_fix(body: QuickBody, response: Response, session: Session = Depends(session_dep)):
        """Quick AI Send, step one: a strict proofread of the subject and text. It sends nothing and keeps nothing; the page sends the
        result with the normal send route, and keeps the person's own draft if anything fails."""
        response.headers["Cache-Control"] = "no-store"
        user = session.principal.user_id
        if not available(user):
            raise HTTPException(status_code=403, detail="Writing help is switched off.")
        if not book.get(user)["quick"]:
            raise HTTPException(status_code=403, detail="Turn on Quick AI Send in Settings first.")
        if not limit.allow(f"writehelp:{user}"):
            raise HTTPException(status_code=429, detail="Too many requests. Wait a minute.")
        service.refresh_ai(vault)
        if not service.summariser.enabled:
            raise HTTPException(status_code=409, detail={"code": "ai_not_configured", "message": "No AI model is set up yet. An administrator can add one under Administration, AI model."})
        try:
            result = W.quick_fix(service.summariser, body.subject, body.draft, guide_of(user))
        except BridgeError as err:
            if err.code in ("quick_unsafe", "empty_draft"):
                raise HTTPException(status_code=422, detail={"code": err.code, "message": err.message}) from None
            raise fail(err) from None
        except Exception:
            raise HTTPException(status_code=502, detail={"code": "ai_unreachable", "message": "The AI server could not be reached or took too long to answer."}) from None
        vault.audit({"event": "quick_send_checked", "actor_user_id": user, "at": time.time()})
        return result

    return router
