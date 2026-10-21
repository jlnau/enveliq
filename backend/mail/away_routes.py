"""Away reply: read and change the person's own away reply."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import Field

from ..models import StrictModel
from ..security import Session
from .awayreply import MAX_BODY, AwayError
from .limits import SlidingWindowLimiter


class AwayBody(StrictModel):
    enabled: bool
    start: str = Field(default="", max_length=10)
    end: str = Field(default="", max_length=10)
    body: str = Field(default="", max_length=MAX_BODY * 2)


def build_away_router(ctx: Any) -> APIRouter:
    router = APIRouter(prefix="/api/v1")
    book = ctx.away
    session_dep = ctx.full_session
    limit = SlidingWindowLimiter(max_events=60, window=60)

    def mine(session: Session, response: Response) -> str:
        user = session.principal.user_id
        if not limit.allow(f"away:{user}"):
            raise HTTPException(status_code=429, detail="Too many requests. Wait a minute.")
        response.headers["Cache-Control"] = "no-store"
        return user

    @router.get("/me/away")
    def my_away(response: Response, session: Session = Depends(session_dep)):
        return book.view(mine(session, response))

    @router.put("/me/away")
    def put_away(body: AwayBody, response: Response, session: Session = Depends(session_dep)):
        user = mine(session, response)
        try:
            out = book.save(user, body.enabled, body.start, body.end, body.body)
        except AwayError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from None
        ctx.vault.audit({"event": "away_reply_on" if body.enabled else "away_reply_off", "actor_user_id": user})
        return out

    return router
