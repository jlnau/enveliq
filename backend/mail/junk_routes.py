"""Junk Mail: list, refresh from the mail services, AI check, a safe view of one email, and Not junk."""
from __future__ import annotations

import logging
import time
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi import Path as PathParam

from ..security import Session
from . import features, htmlview
from .errors import BridgeError
from .limits import SlidingWindowLimiter
from .parse import render_original
from .routes import fail

log = logging.getLogger(__name__)
JunkId = Annotated[str, PathParam(pattern=r"^j[0-9a-f]{23}$")]


def build_junk_router(ctx: Any) -> APIRouter:
    router = APIRouter(prefix="/api/v1/junk")
    book = ctx.junk
    vault = ctx.vault
    session_dep = ctx.full_session
    read_limit = SlidingWindowLimiter(max_events=120, window=60)
    refresh_limit = SlidingWindowLimiter(max_events=6, window=60)
    check_limit = SlidingWindowLimiter(max_events=30, window=60)
    view_limit = SlidingWindowLimiter(max_events=60, window=60)
    move_limit = SlidingWindowLimiter(max_events=30, window=60)

    def need(session: Session, response: Response, limit: SlidingWindowLimiter, name: str) -> str:
        user = session.principal.user_id
        if not features.effective(vault, user)["junk_mail"]:
            raise HTTPException(status_code=403, detail="Junk Mail is switched off.")
        if not limit.allow(f"{name}:{user}"):
            raise HTTPException(status_code=429, detail="Too many requests. Wait a minute.")
        response.headers["Cache-Control"] = "no-store"
        return user

    def gone() -> HTTPException:
        return HTTPException(status_code=404, detail="That email is no longer in Junk Mail.")

    @router.get("")
    def listing(response: Response, session: Session = Depends(session_dep)):
        return book.view(need(session, response, read_limit, "junkread"))

    @router.post("/refresh")
    def refresh(response: Response, session: Session = Depends(session_dep)):
        user = need(session, response, refresh_limit, "junkrefresh")
        try:
            return book.refresh(user)
        except HTTPException:
            raise
        except Exception as exc:
            log.exception("junk mail: refresh failed")
            raise HTTPException(status_code=502, detail=f"Junk Mail could not be read just now ({type(exc).__name__}). Try again in a moment.") from None

    @router.post("/check")
    def check(response: Response, session: Session = Depends(session_dep)):
        """Ask the AI about a few emails that have no answer yet. The page repeats this while some are left."""
        user = need(session, response, check_limit, "junkcheck")
        try:
            return book.classify(user)
        except BridgeError as err:
            raise fail(err) from None
        except Exception as exc:
            log.exception("junk mail: check failed")
            raise HTTPException(status_code=502, detail=f"The AI check could not run just now ({type(exc).__name__}). Try again in a moment.") from None

    @router.get("/{junk_id}/original")
    def original(junk_id: JunkId, response: Response, session: Session = Depends(session_dep)):
        user = need(session, response, view_limit, "junkview")
        try:
            raw = book.original(user, junk_id)
        except KeyError:
            raise gone() from None
        except BridgeError as err:
            if err.code == "not_found":
                book.forget(user, junk_id)                  # it is not in the Junk folder any more: take it off the list too
                raise gone() from None
            raise fail(err) from None
        view = render_original(raw)
        # Junk is shown switched off: no links to press, no pictures from the internet, no files to open, no unsubscribe.
        view.update(links=[], remote_images=0, attachments=[], unsubscribe=None)
        return view

    @router.get("/{junk_id}/original/html")
    def original_html(junk_id: JunkId, session: Session = Depends(session_dep)):
        user = session.principal.user_id
        if not features.effective(vault, user)["junk_mail"]:
            raise HTTPException(status_code=403, detail="Junk Mail is switched off.")
        if not view_limit.allow(f"junkview:{user}"):
            raise HTTPException(status_code=429, detail="Too many requests. Wait a minute.")
        try:
            raw = book.original(user, junk_id)
        except KeyError:
            raise gone() from None
        except BridgeError as err:
            if err.code == "not_found":
                book.forget(user, junk_id)                  # it is not in the Junk folder any more: take it off the list too
                raise gone() from None
            raise fail(err) from None
        built = htmlview.render(raw, False, no_links=True)
        if built is None:
            raise HTTPException(status_code=404, detail="This email has no formatted version.")
        return Response(built.page, media_type="text/html; charset=utf-8",
                        headers={"Content-Security-Policy": htmlview.policy_header(False), "Cache-Control": "no-store", "X-Frame-Options": "SAMEORIGIN",
                                 "Referrer-Policy": "no-referrer"})

    @router.post("/{junk_id}/not-junk")
    def not_junk(junk_id: JunkId, response: Response, session: Session = Depends(session_dep)):
        user = need(session, response, move_limit, "junkmove")
        try:
            book.not_junk(user, junk_id)
        except KeyError:
            raise gone() from None
        except BridgeError as err:
            if err.code == "not_found":
                book.forget(user, junk_id)                  # it is not in the Junk folder any more: take it off the list too
                raise gone() from None
            raise fail(err) from None
        vault.audit({"event": "junk_marked_not_junk", "actor_user_id": user, "at": time.time()})
        return book.view(user)

    return router
