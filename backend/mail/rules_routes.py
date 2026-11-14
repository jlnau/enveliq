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


NEW_ACTIONS = {"starred", "snoozed", "safe"}


class MoveBody(StrictModel):
    direction: str = Field(pattern=r"^(up|down)$")


class RunBody(StrictModel):
    confirm: bool = False


class RuleBody(StrictModel):
    sender: str = Field(default="", max_length=320)
    not_subject: str = Field(default="", max_length=MAX_SUBJECT * 4)
    to: str = Field(default="", max_length=200)
    mailing_list: str = Field(default="", max_length=200)
    files: bool = False
    larger_mb: int = Field(default=0, ge=0, le=100000)
    hours: int = Field(default=0, ge=0, le=100000)
    advanced: bool = False                  # sent by the Mail rules form: any mix of conditions is allowed, even none about the sender
    subject: str = Field(default="", max_length=MAX_SUBJECT * 4)
    action: str = Field(max_length=20)
    tags: list[Annotated[str, Field(max_length=80)]] = Field(default_factory=list, max_length=20)
    folder: str = Field(default="", max_length=300)
    folder_label: str = Field(default="", max_length=80)


def build_rules_router(ctx: Any) -> APIRouter:
    router = APIRouter(prefix="/api/v1")
    book = ctx.rules
    session_dep = ctx.full_session
    limit = SlidingWindowLimiter(max_events=120, window=60)
    run_limit = SlidingWindowLimiter(max_events=3, window=60)

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
            if body.not_subject or body.to or body.mailing_list or body.files or body.larger_mb or body.hours or body.advanced or body.action in NEW_ACTIONS:
                book.save(user, body.model_dump())
            else:                                   # the one-button rules (archive, block, tags, folder) keep their "one per sender" behaviour
                book.add(user, body.sender, body.subject, body.action, body.tags, body.folder, body.folder_label)
        except RuleError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from None
        return view(user)

    @router.put("/me/rules/{rule_id}")
    def edit_rule(rule_id: RuleId, body: RuleBody, response: Response, session: Session = Depends(session_dep)):
        user = mine(session, response)
        try:
            book.save(user, body.model_dump(), rule_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="That rule was not found.") from None
        except RuleError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from None
        return view(user)

    @router.post("/me/rules/{rule_id}/move")
    def move_rule(rule_id: RuleId, body: MoveBody, response: Response, session: Session = Depends(session_dep)):
        user = mine(session, response)
        if not book.move(user, rule_id, -1 if body.direction == "up" else 1):
            raise HTTPException(status_code=404, detail="That rule was not found.")
        return view(user)

    @router.post("/me/rules/preview")
    def preview_rule(body: RuleBody, response: Response, session: Session = Depends(session_dep)):
        """How many of the emails already here a rule would have fitted. Nothing is changed."""
        user = mine(session, response)
        try:
            rule = book.build(body.model_dump())
        except RuleError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from None
        return ctx.rule_tools.preview(user, rule)

    @router.post("/me/rules/run")
    def run_rules(body: RunBody, response: Response, session: Session = Depends(session_dep)):
        """Run the rules on mail that is already in the inbox. Without confirm it only counts; with it, it does it (500 at most)."""
        user = mine(session, response)
        if body.confirm and not run_limit.allow(f"rulesrun:{user}"):
            raise HTTPException(status_code=429, detail="That was just run. Wait a minute before running it again.")
        return ctx.rule_tools.run(user, body.confirm)

    @router.delete("/me/rules/{rule_id}")
    def delete_rule(rule_id: RuleId, response: Response, session: Session = Depends(session_dep)):
        user = mine(session, response)
        if not book.remove(user, rule_id):
            raise HTTPException(status_code=404, detail="That rule was not found.")
        return view(user)

    return router
