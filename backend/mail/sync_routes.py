"""Settings for the calendar feed, CalDAV and Home Assistant To-do, and the private feed address itself."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Path as PathParam, Response
from pydantic import Field

from ..models import StrictModel
from ..security import Session
from .limits import SlidingWindowLimiter
from .outbound import OutboundError


class TitlesBody(StrictModel):
    titles: bool


class CalDavBody(StrictModel):
    enabled: bool = True
    url: str = Field(max_length=300)
    user: str = Field(max_length=160)
    password: str = Field(default="", max_length=300)


class TodoBody(StrictModel):
    enabled: bool = True
    url: str = Field(max_length=300)
    token: str = Field(default="", max_length=600)
    entity: str = Field(max_length=90)


def build_sync_router(ctx: Any) -> tuple[APIRouter, APIRouter]:
    """(settings router under /api/v1, the private feed at /calendar/<token>.ics)."""
    router = APIRouter(prefix="/api/v1")
    public = APIRouter()
    sync = ctx.sync
    session_dep = ctx.full_session
    change_limit = SlidingWindowLimiter(max_events=60, window=60)
    test_limit = SlidingWindowLimiter(max_events=10, window=60)
    feed_misses = SlidingWindowLimiter(max_events=30, window=60)
    feed_reads = SlidingWindowLimiter(max_events=120, window=60)

    def guard(user: str) -> None:
        if not change_limit.allow(f"s:{user}"):
            raise HTTPException(status_code=429, detail="Too many changes. Wait a minute.")

    @router.get("/me/sync")
    def overview(session: Session = Depends(session_dep)):
        return sync.overview(session.principal.user_id)

    @router.put("/me/sync/titles")
    def titles(body: TitlesBody, session: Session = Depends(session_dep)):
        user = session.principal.user_id
        guard(user)
        sync.set_titles(user, body.titles)
        return sync.overview(user)

    @router.post("/me/sync/feed")
    def feed_new(session: Session = Depends(session_dep)):
        """Make a new private address. It is shown once; making another stops the old one working."""
        user = session.principal.user_id
        guard(user)
        url = sync.feed_new(user)
        return {"url": url, **sync.overview(user)}

    @router.delete("/me/sync/feed")
    def feed_off(session: Session = Depends(session_dep)):
        user = session.principal.user_id
        sync.feed_off(user)
        return sync.overview(user)

    @router.put("/me/sync/caldav")
    def caldav_put(body: CalDavBody, session: Session = Depends(session_dep)):
        user = session.principal.user_id
        guard(user)
        try:
            sync.save_caldav(user, body.enabled, body.url, body.user, body.password)
        except ValueError as err:
            raise HTTPException(status_code=422, detail=str(err)) from None
        return sync.overview(user)

    @router.put("/me/sync/todo")
    def todo_put(body: TodoBody, session: Session = Depends(session_dep)):
        user = session.principal.user_id
        guard(user)
        try:
            sync.save_todo(user, body.enabled, body.url, body.token, body.entity)
        except ValueError as err:
            raise HTTPException(status_code=422, detail=str(err)) from None
        return sync.overview(user)

    @router.delete("/me/sync/{which}")
    def remove(which: str = PathParam(pattern=r"^(caldav|todo|google)$"), session: Session = Depends(session_dep)):
        user = session.principal.user_id
        sync.clear(user, which)
        return sync.overview(user)

    @router.post("/me/sync/{which}/test")
    def test(which: str = PathParam(pattern=r"^(caldav|todo)$"), session: Session = Depends(session_dep)):
        user = session.principal.user_id
        if not test_limit.allow(f"t:{user}"):
            raise HTTPException(status_code=429, detail="Too many tests. Wait a minute.")
        try:
            message = sync.test_caldav(user) if which == "caldav" else sync.test_todo(user)
        except OutboundError as err:
            raise HTTPException(status_code=502, detail=err.message) from None
        return {"ok": True, "message": message}

    @router.post("/me/sync/now")
    def now(session: Session = Depends(session_dep)):
        user = session.principal.user_id
        if not test_limit.allow(f"n:{user}"):
            raise HTTPException(status_code=429, detail="Too many requests. Wait a minute.")
        sync.tasks.reconcile(user)
        return {"results": sync.sync_now(user), **sync.overview(user)}

    @public.get("/calendar/{token}.ics", include_in_schema=False)
    def feed(token: str = PathParam(pattern=r"^[A-Za-z0-9_-]{20,64}$")):
        """The one address that works without signing in: whoever holds the private link can read the task dates."""
        def deny(status: int, text: str) -> Response:
            return Response(content=text + "\n", status_code=status, media_type="text/plain", headers={"Cache-Control": "no-store"})
        if not sync.vault.is_unlocked():
            return deny(503, "Enveliq is locked.")
        if not feed_reads.allow("read"):
            return deny(429, "Too many requests.")
        owner = sync.feed_owner(token)
        if owner is None:
            if not feed_misses.allow("miss"):
                return deny(429, "Too many failed attempts.")
            return deny(404, "Not found.")
        with sync.vault.passive():
            text = sync.feed_text(owner)
        return Response(content=text, media_type="text/calendar; charset=utf-8", headers={"Cache-Control": "private, max-age=300", "Content-Disposition": 'inline; filename="enveliq.ics"', "X-Robots-Tag": "noindex"})

    return router, public
