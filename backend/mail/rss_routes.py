"""News feeds: each person's own list, and the few things they can do with it."""
from __future__ import annotations

import time
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi import Path as PathParam
from pydantic import Field

from ..models import StrictModel
from ..security import Session
from . import rss as R
from .limits import SlidingWindowLimiter

FeedId = Annotated[str, PathParam(pattern=r"^r[0-9a-f]{16}$")]


class NewFeedBody(StrictModel):
    url: str = Field(max_length=R.MAX_URL)


def build_rss_router(ctx: Any) -> APIRouter:
    router = APIRouter(prefix="/api/v1")
    book = ctx.rss
    session_dep = ctx.full_session
    limit = SlidingWindowLimiter(max_events=240, window=60)
    slow = SlidingWindowLimiter(max_events=10, window=60)          # anything that contacts another site

    def person(session: Session, *, contacts: bool = False) -> str:
        user = session.principal.user_id
        if not limit.allow(f"rss:{user}") or (contacts and not slow.allow(f"rss-net:{user}")):
            raise HTTPException(status_code=429, detail="Too many requests. Wait a minute.")
        return user

    def on(user: str) -> None:
        if not book.enabled(user):
            raise HTTPException(status_code=403, detail="News feeds are switched off.")

    @router.get("/me/rss")
    def my_feeds(response: Response, session: Session = Depends(session_dep)):
        user = person(session)
        response.headers["Cache-Control"] = "no-store"
        return book.view(user)

    @router.post("/me/rss/feeds", status_code=201)
    def add_feed(body: NewFeedBody, response: Response, session: Session = Depends(session_dep)):
        user = person(session, contacts=True)
        on(user)
        response.headers["Cache-Control"] = "no-store"
        try:
            view = book.add_feed(user, body.url)
        except R.FeedError as err:
            raise HTTPException(status_code=422, detail=str(err)) from None
        ctx.vault.audit({"event": "rss_feed_added", "actor_user_id": user, "at": time.time()})        # that one was added, never which
        return view

    @router.delete("/me/rss/feeds/{feed_id}")
    def remove_feed(feed_id: FeedId, response: Response, session: Session = Depends(session_dep)):
        user = person(session)
        response.headers["Cache-Control"] = "no-store"
        try:
            return book.remove_feed(user, feed_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="That feed is no longer on your list.") from None

    @router.post("/me/rss/refresh")
    def refresh(response: Response, session: Session = Depends(session_dep)):
        user = person(session, contacts=True)
        on(user)
        response.headers["Cache-Control"] = "no-store"
        return book.refresh(user, force=True)

    @router.post("/me/rss/seen")
    def seen(response: Response, session: Session = Depends(session_dep)):
        user = person(session)
        response.headers["Cache-Control"] = "no-store"
        return book.mark_seen(user)

    return router
