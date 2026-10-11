"""Rules: the few things a person can do with their own list of rules."""
from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi import Path as PathParam
from pydantic import Field

from ..models import StrictModel
from ..security import Session
from .limits import SlidingWindowLimiter
from .rules import ACTIONS, MAX_RULES, MAX_SUBJECT, RuleError

RuleId = Annotated[str, PathParam(pattern=r"^u[0-9a-f]{16}$")]


class RuleBody(StrictModel):
    sender: str = Field(max_length=320)
    subject: str = Field(default="", max_length=MAX_SUBJECT * 4)
    action: str = Field(max_length=20)


def build_rules_router(ctx: Any) -> APIRouter:
    router = APIRouter(prefix="/api/v1")
    book = ctx.rules
    session_dep = ctx.full_session
    limit = SlidingWindowLimiter(max_events=120, window=60)

    def mine(session: Session, response: Response) -> str:
        user = session.principal.user_id
        if not limit.allow(f"rules:{user}"):
            raise HTTPException(status_code=429, detail="Too many requests. Wait a minute.")
        response.headers["Cache-Control"] = "no-store"
        return user

    def view(user: str) -> dict[str, Any]:
        return {"rules": book.listing(user), "actions": ACTIONS, "max": MAX_RULES}

    @router.get("/me/rules")
    def my_rules(response: Response, session: Session = Depends(session_dep)):
        return view(mine(session, response))

    @router.post("/me/rules")
    def add_rule(body: RuleBody, response: Response, session: Session = Depends(session_dep)):
        user = mine(session, response)
        try:
            book.add(user, body.sender, body.subject, body.action)
        except RuleError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from None
        return view(user)

    @router.delete("/me/rules/{rule_id}")
    def delete_rule(rule_id: RuleId, response: Response, session: Session = Depends(session_dep)):
        user = mine(session, response)
        if not book.remove(user, rule_id):
            raise HTTPException(status_code=404, detail="That rule was not found.")
        return view(user)

    return router
