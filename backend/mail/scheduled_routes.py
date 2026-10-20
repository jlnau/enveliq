"""Send later: schedule an email, list what is waiting, take one back. Only the signed-in person's own."""
from __future__ import annotations

import time
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi import Path as PathParam
from pydantic import Field

from ..models import StrictModel
from ..security import Session
from . import features
from .errors import BridgeError
from .limits import SlidingWindowLimiter
from .routes import fail
from .scheduled import MAX_AHEAD, MAX_BODY, MAX_PEOPLE, ScheduleError

ItemId = Annotated[str, PathParam(pattern=r"^s[0-9a-f]{16}$")]


class ScheduleBody(StrictModel):
    kind: Literal["new", "reply", "reply_all", "forward"]
    account_id: str = Field(min_length=1, max_length=64)
    message_id: str | None = Field(default=None, max_length=64)       # the email being answered or forwarded
    from_address: str | None = Field(default=None, max_length=320)
    to: list[str] = Field(default_factory=list, max_length=MAX_PEOPLE)
    cc: list[str] = Field(default_factory=list, max_length=MAX_PEOPLE)
    bcc: list[str] = Field(default_factory=list, max_length=MAX_PEOPLE)
    subject: str = Field(default="", max_length=900)
    body: str = Field(default="", max_length=MAX_BODY)
    send_at: float                                                    # a Unix time in seconds


def build_scheduled_router(ctx: Any) -> APIRouter:
    router = APIRouter(prefix="/api/v1")
    book = ctx.scheduled
    service = ctx.mail
    vault = ctx.vault
    session_dep = ctx.full_session
    limit = SlidingWindowLimiter(max_events=120, window=60)

    def mine(session: Session, response: Response) -> str:
        user = session.principal.user_id
        if not limit.allow(f"scheduled:{user}"):
            raise HTTPException(status_code=429, detail="Too many requests. Wait a minute.")
        response.headers["Cache-Control"] = "no-store"
        return user

    @router.get("/me/scheduled")
    def my_scheduled(response: Response, session: Session = Depends(session_dep)):
        return {"now": time.time(), "max_days": MAX_AHEAD // 86400, "items": book.listing(mine(session, response))}

    @router.post("/me/scheduled", status_code=201)
    def schedule(body: ScheduleBody, response: Response, session: Session = Depends(session_dep)):
        user = mine(session, response)
        if not features.effective(vault, user)["compose"]:
            raise HTTPException(status_code=403, detail="Writing email is switched off.")
        account = ctx.load_account(body.account_id, session.principal, owner_only=True, action="send email")
        try:
            # Check now what can be checked, so a mistake is found while the person is still here.
            if body.kind == "new":
                service.build_new(account, body.to, body.cc, body.bcc, body.subject, body.body, body.from_address, [])
            else:
                if not body.message_id:
                    raise HTTPException(status_code=422, detail="Say which email this answers.")
                try:
                    message = vault.get_message(body.account_id, body.message_id)
                except KeyError:
                    raise HTTPException(status_code=404, detail="Message not found") from None
                if body.kind == "forward":
                    service._people(body.to, body.cc, body.bcc)
                    service._pick_from(account, body.from_address, (message.get("reply_context") or {}).get("delivered_to"))
                else:
                    service.build_reply(account, message, body.body, body.from_address, body.to or None, body.cc or None, body.bcc or None, body.kind, False, None, body.subject or None)
            return book.add(user, body.model_dump())
        except BridgeError as err:
            raise fail(err) from None
        except ScheduleError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from None

    @router.delete("/me/scheduled/{item_id}")
    def take_back(item_id: ItemId, response: Response, session: Session = Depends(session_dep)):
        out = book.cancel(mine(session, response), item_id)
        if out is None:
            raise HTTPException(status_code=404, detail="That email is not waiting any more.")
        return out

    return router
