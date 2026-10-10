"""Messages between people: every call is checked against the signed-in session, and a conversation you are not in is "not found"."""
from __future__ import annotations

import time
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi import Path as PathParam
from pydantic import Field

from ..models import StrictModel
from ..security import Session
from . import messages as M
from .limits import SlidingWindowLimiter

ThreadId = Annotated[str, PathParam(pattern=M.THREAD_ID)]
MessageId = Annotated[str, PathParam(pattern=M.MESSAGE_ID)]
NOT_FOUND = "Not found."


class StartBody(StrictModel):
    to: list[str] = Field(min_length=1, max_length=M.MAX_MEMBERS - 1)
    text: str = Field(max_length=M.MAX_TEXT * 2)


class TextBody(StrictModel):
    text: str = Field(max_length=M.MAX_TEXT * 2)


class MuteBody(StrictModel):
    muted: bool


def build_messages_router(ctx: Any) -> APIRouter:
    router = APIRouter(prefix="/api/v1/messages")
    book = ctx.messages
    session_dep = ctx.full_session
    read_limit = SlidingWindowLimiter(max_events=600, window=60)
    send_limit = SlidingWindowLimiter(max_events=30, window=60)

    def me(session: Session) -> str:
        user = session.principal.user_id
        if not book.enabled(user):
            raise HTTPException(status_code=403, detail="Messages is switched off.")
        return user

    def reading(user: str) -> None:
        if not read_limit.allow(f"msg-read:{user}"):
            raise HTTPException(status_code=429, detail="Too many requests. Wait a minute.")

    def sending(user: str) -> None:
        if not send_limit.allow(f"msg-send:{user}"):
            raise HTTPException(status_code=429, detail="That is a lot of messages. Wait a minute, then try again.")

    def nothing(response: Response) -> None:
        response.headers["Cache-Control"] = "no-store"

    @router.get("/summary")
    def summary(response: Response, session: Session = Depends(session_dep)):
        nothing(response)
        user = session.principal.user_id
        if not book.enabled(user):
            return {"enabled": False, "unread": 0, "latest": []}
        reading(user)
        return book.summary(user)

    @router.get("/people")
    def people(response: Response, session: Session = Depends(session_dep)):
        nothing(response)
        user = me(session)
        reading(user)
        return {"people": book.people(user)}

    @router.get("/threads")
    def threads(response: Response, session: Session = Depends(session_dep)):
        nothing(response)
        user = me(session)
        reading(user)
        return {"threads": book.threads(user)}

    @router.post("/threads", status_code=201)
    def start(body: StartBody, response: Response, session: Session = Depends(session_dep)):
        nothing(response)
        user = me(session)
        sending(user)
        try:
            return book.start(user, body.to, body.text)
        except M.MessageError as err:
            raise HTTPException(status_code=422, detail=str(err)) from None
        except KeyError:
            raise HTTPException(status_code=404, detail="One of those people can't be written to.") from None

    @router.get("/threads/{thread_id}")
    def open_thread(thread_id: ThreadId, response: Response, session: Session = Depends(session_dep)):
        nothing(response)
        user = me(session)
        reading(user)
        try:
            return book.open(user, thread_id)
        except KeyError:
            raise HTTPException(status_code=404, detail=NOT_FOUND) from None

    @router.post("/threads/{thread_id}/messages", status_code=201)
    def post(thread_id: ThreadId, body: TextBody, response: Response, session: Session = Depends(session_dep)):
        nothing(response)
        user = me(session)
        sending(user)
        try:
            return book.post(user, thread_id, body.text)
        except M.MessageError as err:
            raise HTTPException(status_code=422, detail=str(err)) from None
        except KeyError:
            raise HTTPException(status_code=404, detail=NOT_FOUND) from None

    @router.post("/threads/{thread_id}/read", status_code=204)
    def read(thread_id: ThreadId, session: Session = Depends(session_dep)):
        user = me(session)
        reading(user)
        try:
            book.mark_read(user, thread_id)
        except KeyError:
            raise HTTPException(status_code=404, detail=NOT_FOUND) from None
        return Response(status_code=204)

    @router.delete("/threads/{thread_id}/messages/{message_id}", status_code=204)
    def unsend(thread_id: ThreadId, message_id: MessageId, session: Session = Depends(session_dep)):
        user = me(session)
        reading(user)
        try:
            book.unsend(user, thread_id, message_id)
        except KeyError:
            raise HTTPException(status_code=404, detail=NOT_FOUND) from None
        return Response(status_code=204)

    @router.put("/threads/{thread_id}/mute", status_code=204)
    def mute(thread_id: ThreadId, body: MuteBody, session: Session = Depends(session_dep)):
        user = me(session)
        reading(user)
        try:
            book.mute(user, thread_id, body.muted)
        except KeyError:
            raise HTTPException(status_code=404, detail=NOT_FOUND) from None
        return Response(status_code=204)

    return router
