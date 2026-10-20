"""Clean up: the senders that fill the inbox, and what the person can do about each (see mail/senders.py)."""
from __future__ import annotations

import logging
import time
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi import Path as PathParam
from pydantic import Field

from ..models import StrictModel
from ..security import Session
from . import features
from .errors import BridgeError
from .limits import SlidingWindowLimiter
from .routes import fail
from .senders import SenderError

log = logging.getLogger(__name__)
SenderId = Annotated[str, PathParam(pattern=r"^s[0-9a-f]{20}$")]


class UndoBody(StrictModel):
    token: str = Field(min_length=8, max_length=64)


def build_senders_router(ctx: Any) -> APIRouter:
    router = APIRouter(prefix="/api/v1/me/senders")
    book = ctx.senders
    vault = ctx.vault
    session_dep = ctx.full_session
    read_limit = SlidingWindowLimiter(max_events=60, window=60)
    scan_limit = SlidingWindowLimiter(max_events=6, window=60)
    act_limit = SlidingWindowLimiter(max_events=30, window=60)

    def need(session: Session, response: Response, limit: SlidingWindowLimiter, name: str) -> str:
        user = session.principal.user_id
        if not features.effective(vault, user)["clean_up"]:
            raise HTTPException(status_code=403, detail="Clean up is switched off.")
        if not limit.allow(f"{name}:{user}"):
            raise HTTPException(status_code=429, detail="Too many requests. Wait a minute.")
        response.headers["Cache-Control"] = "no-store"
        return user

    def gone() -> HTTPException:
        return HTTPException(status_code=404, detail="That sender is not on the list any more. Look again.")

    @router.get("")
    def listing(response: Response, refresh: bool = False, session: Session = Depends(session_dep)):
        user = need(session, response, scan_limit if refresh else read_limit, "sendersscan" if refresh else "sendersread")
        try:
            return book.scan(user, refresh=refresh)
        except Exception as exc:
            log.exception("clean up: listing failed")
            raise HTTPException(status_code=502, detail=f"Your mail could not be read just now ({type(exc).__name__}). Try again in a moment.") from None

    @router.post("/{sender_id}/archive")
    def archive(sender_id: SenderId, response: Response, session: Session = Depends(session_dep)):
        user = need(session, response, act_limit, "sendersact")
        try:
            result = book.archive(user, sender_id)
        except KeyError:
            raise gone() from None
        except SenderError as err:
            raise HTTPException(status_code=400, detail=str(err)) from None
        except BridgeError as err:
            raise fail(err) from None
        vault.audit({"event": "clean_up_archived", "actor_user_id": user, "count": result["archived"], "at": time.time()})
        return {**result, **book.scan(user)}

    @router.post("/{sender_id}/always")
    def always(sender_id: SenderId, response: Response, session: Session = Depends(session_dep)):
        user = need(session, response, act_limit, "sendersact")
        try:
            return book.always_archive(user, sender_id)
        except KeyError:
            raise gone() from None
        except SenderError as err:
            raise HTTPException(status_code=400, detail=str(err)) from None

    @router.post("/{sender_id}/keep")
    def keep(sender_id: SenderId, response: Response, session: Session = Depends(session_dep)):
        user = need(session, response, act_limit, "sendersact")
        try:
            return book.keep(user, sender_id)
        except KeyError:
            raise gone() from None
        except SenderError as err:
            raise HTTPException(status_code=400, detail=str(err)) from None

    @router.delete("/keep")
    def show_again(response: Response, session: Session = Depends(session_dep)):
        user = need(session, response, act_limit, "sendersact")
        return book.show_kept_again(user)

    @router.post("/undo")
    def undo(body: UndoBody, response: Response, session: Session = Depends(session_dep)):
        user = need(session, response, act_limit, "sendersact")
        try:
            result = book.undo(user, body.token)
        except KeyError:
            raise HTTPException(status_code=404, detail="There is nothing to undo any more.") from None
        except BridgeError as err:
            raise fail(err) from None
        vault.audit({"event": "clean_up_undone", "actor_user_id": user, "count": result["restored"], "at": time.time()})
        return {**result, **book.scan(user, refresh=True)}

    return router
