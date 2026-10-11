"""Subscriptions: the person's renewals and free trials, and the few things they can do with them."""
from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi import Path as PathParam
from pydantic import Field

from ..models import StrictModel
from ..security import Session
from .limits import SlidingWindowLimiter

SubId = Annotated[str, PathParam(pattern=r"^b[0-9a-f]{23}$")]
Action = Annotated[str, PathParam(pattern=r"^(not_subscription|cancelled|keep)$")]


class SettingsBody(StrictModel):
    nudge_days: int = Field(ge=1, le=14)


def build_subscriptions_router(ctx: Any) -> APIRouter:
    router = APIRouter(prefix="/api/v1")
    book = ctx.subscriptions
    session_dep = ctx.full_session
    limit = SlidingWindowLimiter(max_events=240, window=60)

    def mine(session: Session, response: Response) -> str:
        user = session.principal.user_id
        if not limit.allow(f"subs:{user}"):
            raise HTTPException(status_code=429, detail="Too many requests. Wait a minute.")
        response.headers["Cache-Control"] = "no-store"
        return user

    @router.get("/me/subscriptions")
    def my_subscriptions(response: Response, session: Session = Depends(session_dep)):
        return book.view(mine(session, response))

    @router.put("/me/subscriptions/settings")
    def my_settings(body: SettingsBody, response: Response, session: Session = Depends(session_dep)):
        user = mine(session, response)
        if not book.enabled(user):
            raise HTTPException(status_code=403, detail="Subscriptions is switched off.")
        return book.set_nudge_days(user, body.nudge_days)

    @router.post("/me/subscriptions/{sub_id}/{action}")
    def change_subscription(sub_id: SubId, action: Action, response: Response, session: Session = Depends(session_dep)):
        user = mine(session, response)
        if not book.enabled(user):
            raise HTTPException(status_code=403, detail="Subscriptions is switched off.")
        try:
            return book.act(user, sub_id, action)
        except KeyError:
            raise HTTPException(status_code=404, detail="That subscription is no longer on your list.") from None
        except ValueError:
            raise HTTPException(status_code=422, detail="That change is not possible.") from None

    return router
