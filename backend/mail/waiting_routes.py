"""Waiting for a reply: the person's sent emails that are waiting on an answer, and the few things they can do with them."""
from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi import Path as PathParam
from pydantic import Field

from ..models import StrictModel
from ..security import Session
from .errors import BridgeError
from .limits import SlidingWindowLimiter
from .service import MAIL_METHODS

NoteId = Annotated[str, PathParam(pattern=r"^w[0-9a-f]{23}$")]
Action = Annotated[str, PathParam(pattern=r"^(got_reply|later|not_needed|undo)$")]


class DaysBody(StrictModel):
    days: int = Field(ge=1, le=14)


def build_waiting_router(ctx: Any) -> APIRouter:
    router = APIRouter(prefix="/api/v1")
    book = ctx.waiting
    session_dep = ctx.full_session
    limit = SlidingWindowLimiter(max_events=240, window=60)
    check_limit = SlidingWindowLimiter(max_events=6, window=60)

    def guard(user: str, response: Response) -> None:
        if not limit.allow(f"wait:{user}"):
            raise HTTPException(status_code=429, detail="Too many requests. Wait a minute.")
        response.headers["Cache-Control"] = "no-store"

    @router.get("/me/waiting")
    def my_notes(response: Response, session: Session = Depends(session_dep)):
        user = session.principal.user_id
        guard(user, response)
        return book.view(user)

    @router.put("/me/waiting/settings")
    def settings(body: DaysBody, response: Response, session: Session = Depends(session_dep)):
        user = session.principal.user_id
        guard(user, response)
        return book.set_days(user, body.days)

    @router.post("/me/waiting/check")
    def check_now(response: Response, session: Session = Depends(session_dep)):
        """Look at the Sent folder of each of the person's mailboxes that has this switched on, right now."""
        user = session.principal.user_id
        guard(user, response)
        if not check_limit.allow(f"waitcheck:{user}"):
            raise HTTPException(status_code=429, detail="Checked a moment ago. Wait a minute.")
        if book.enabled(user):
            for account in ctx.vault.list_accounts():
                if account.get("owner_user_id") != user or account.get("auth_method") not in MAIL_METHODS:
                    continue
                try:
                    ctx.mail.waiting_scan(ctx.vault, account, judge=10)
                except BridgeError as err:
                    raise HTTPException(status_code=502, detail=err.message) from None
        return book.view(user)

    @router.post("/me/waiting/{note_id}/{action}")
    def change_note(note_id: NoteId, action: Action, response: Response, session: Session = Depends(session_dep)):
        user = session.principal.user_id
        guard(user, response)
        try:
            return book.act(user, note_id, action)
        except KeyError:
            raise HTTPException(status_code=404, detail="That note is no longer on your list.") from None
        except ValueError:
            raise HTTPException(status_code=422, detail="That change is not possible.") from None

    return router
