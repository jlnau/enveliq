"""A signature and saved replies: the few things a person can do with their own text."""
from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi import Path as PathParam
from pydantic import Field

from ..models import StrictModel
from ..security import Session
from .limits import SlidingWindowLimiter
from .saved_writing import MAX_SIGNATURE, MAX_TEXT, MAX_TITLE, SavedError

ReplyId = Annotated[str, PathParam(pattern=r"^r[0-9a-f]{16}$")]


class SignatureBody(StrictModel):
    text: str = Field(max_length=MAX_SIGNATURE * 2)


class ReplyBody(StrictModel):
    title: str = Field(max_length=MAX_TITLE * 2)
    text: str = Field(max_length=MAX_TEXT * 2)


def build_saved_writing_router(ctx: Any) -> APIRouter:
    router = APIRouter(prefix="/api/v1")
    book = ctx.saved_writing
    session_dep = ctx.full_session
    limit = SlidingWindowLimiter(max_events=120, window=60)

    def mine(session: Session, response: Response) -> str:
        user = session.principal.user_id
        if not limit.allow(f"saved:{user}"):
            raise HTTPException(status_code=429, detail="Too many requests. Wait a minute.")
        response.headers["Cache-Control"] = "no-store"
        return user

    @router.get("/me/saved")
    def my_saved(response: Response, session: Session = Depends(session_dep)):
        return book.view(mine(session, response))

    @router.put("/me/saved/signature")
    def put_signature(body: SignatureBody, response: Response, session: Session = Depends(session_dep)):
        return book.set_signature(mine(session, response), body.text)

    @router.post("/me/saved/replies")
    def add_reply(body: ReplyBody, response: Response, session: Session = Depends(session_dep)):
        try:
            return book.add_reply(mine(session, response), body.title, body.text)
        except SavedError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from None

    @router.put("/me/saved/replies/{reply_id}")
    def put_reply(reply_id: ReplyId, body: ReplyBody, response: Response, session: Session = Depends(session_dep)):
        try:
            out = book.update_reply(mine(session, response), reply_id, body.title, body.text)
        except SavedError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from None
        if out is None:
            raise HTTPException(status_code=404, detail="That saved reply was not found.")
        return out

    @router.delete("/me/saved/replies/{reply_id}")
    def delete_reply(reply_id: ReplyId, response: Response, session: Session = Depends(session_dep)):
        out = book.remove_reply(mine(session, response), reply_id)
        if out is None:
            raise HTTPException(status_code=404, detail="That saved reply was not found.")
        return out

    return router
