"""Muted conversations: the list, and Unmute. (Muting itself is on the email: POST /accounts/{id}/messages/{id}/mute.)"""
from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi import Path as PathParam

from ..security import Session
from .limits import SlidingWindowLimiter

MuteId = Annotated[str, PathParam(pattern=r"^q[0-9a-f]{16}$")]


def build_muted_router(ctx: Any) -> APIRouter:
    router = APIRouter(prefix="/api/v1")
    book = ctx.muted
    session_dep = ctx.full_session
    limit = SlidingWindowLimiter(max_events=120, window=60)

    def mine(session: Session, response: Response) -> str:
        user = session.principal.user_id
        if not limit.allow(f"muted:{user}"):
            raise HTTPException(status_code=429, detail="Too many requests. Wait a minute.")
        response.headers["Cache-Control"] = "no-store"
        return user

    @router.get("/me/muted")
    def my_muted(response: Response, session: Session = Depends(session_dep)):
        return book.listing(mine(session, response))

    @router.delete("/me/muted/{entry_id}")
    def unmute(entry_id: MuteId, response: Response, session: Session = Depends(session_dep)):
        user = mine(session, response)
        if not book.remove(user, entry_id):
            raise HTTPException(status_code=404, detail="That conversation is not muted.")
        return book.listing(user)

    return router
