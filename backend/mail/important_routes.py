"""Important people: the few things a person can do with their own list."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import Field

from ..models import StrictModel
from ..security import Session
from .important import ImportantError
from .limits import SlidingWindowLimiter


class AddBody(StrictModel):
    address: str = Field(max_length=320)
    name: str = Field(default="", max_length=200)


class RemoveBody(StrictModel):
    address: str = Field(max_length=320)


def build_important_router(ctx: Any) -> APIRouter:
    router = APIRouter(prefix="/api/v1")
    book = ctx.important
    session_dep = ctx.full_session
    limit = SlidingWindowLimiter(max_events=120, window=60)

    def mine(session: Session, response: Response) -> str:
        user = session.principal.user_id
        if not limit.allow(f"important:{user}"):
            raise HTTPException(status_code=429, detail="Too many requests. Wait a minute.")
        response.headers["Cache-Control"] = "no-store"
        return user

    @router.get("/me/important")
    def my_important(response: Response, session: Session = Depends(session_dep)):
        return {"items": book.listing(mine(session, response))}

    @router.post("/me/important")
    def add_important(body: AddBody, response: Response, session: Session = Depends(session_dep)):
        user = mine(session, response)
        try:
            return {"items": book.add(user, body.address, body.name)}
        except ImportantError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from None

    @router.post("/me/important/remove")
    def remove_important(body: RemoveBody, response: Response, session: Session = Depends(session_dep)):
        user = mine(session, response)
        if not book.remove(user, body.address):
            raise HTTPException(status_code=404, detail="That person is not on your list.")
        return {"items": book.listing(user)}

    return router
