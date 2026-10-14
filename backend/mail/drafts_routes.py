"""Drafts: save an unfinished email, list it, open it again, delete it. Only the signed-in person's own."""
from __future__ import annotations

import time
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi import Path as PathParam
from pydantic import Field

from ..models import StrictModel
from ..security import Session
from .drafts import KEEP_SECONDS, MAX_BODY, MAX_PEOPLE, DraftError
from .limits import SlidingWindowLimiter

DraftId = Annotated[str, PathParam(pattern=r"^d[0-9a-f]{16}$")]


class DraftBody(StrictModel):
    kind: Literal["new", "reply", "reply_all", "forward"]
    account_id: str | None = Field(default=None, max_length=64)
    message_id: str | None = Field(default=None, max_length=64)     # the email being answered or forwarded
    from_address: str | None = Field(default=None, max_length=320)
    to: list[str] = Field(default_factory=list, max_length=MAX_PEOPLE)
    cc: list[str] = Field(default_factory=list, max_length=MAX_PEOPLE)
    bcc: list[str] = Field(default_factory=list, max_length=MAX_PEOPLE)
    subject: str = Field(default="", max_length=900)
    body: str = Field(default="", max_length=MAX_BODY)


def build_drafts_router(ctx: Any) -> APIRouter:
    router = APIRouter(prefix="/api/v1")
    book = ctx.drafts
    session_dep = ctx.full_session
    limit = SlidingWindowLimiter(max_events=240, window=60)

    def mine(session: Session, response: Response) -> str:
        user = session.principal.user_id
        if not limit.allow(f"drafts:{user}"):
            raise HTTPException(status_code=429, detail="Too many requests. Wait a minute.")
        response.headers["Cache-Control"] = "no-store"
        return user

    @router.get("/me/drafts")
    def my_drafts(response: Response, session: Session = Depends(session_dep)):
        return {"now": time.time(), "keep_days": KEEP_SECONDS // 86400, "items": book.listing(mine(session, response))}

    @router.post("/me/drafts", status_code=201)
    def create_draft(body: DraftBody, response: Response, session: Session = Depends(session_dep)):
        try:
            return book.save(mine(session, response), None, body.model_dump())
        except DraftError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from None

    @router.put("/me/drafts/{draft_id}")
    def replace_draft(draft_id: DraftId, body: DraftBody, response: Response, session: Session = Depends(session_dep)):
        try:
            out = book.save(mine(session, response), draft_id, body.model_dump())
        except DraftError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from None
        if out is None:
            raise HTTPException(status_code=404, detail="That draft is not there any more.")
        return out

    @router.delete("/me/drafts/{draft_id}", status_code=204)
    def delete_draft(draft_id: DraftId, response: Response, session: Session = Depends(session_dep)):
        if not book.remove(mine(session, response), draft_id):
            raise HTTPException(status_code=404, detail="That draft is not there any more.")
        return Response(status_code=204)

    return router
