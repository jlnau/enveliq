"""The daily summary item in the inbox (see digest.py): list it, open it, mark it read, delete it, make today's now.

Everything is the signed-in person's own. A summary that is not theirs answers "not found". Opening one sends no alert.
"""
from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response

from ..security import Session
from .digest import DigestBook
from .limits import SlidingWindowLimiter


def build_digest_router(ctx: Any) -> APIRouter:
    router = APIRouter(prefix="/api/v1")
    book: DigestBook = ctx.digest
    session_dep = ctx.full_session
    limit = SlidingWindowLimiter(max_events=6, window=3600)

    @router.get("/me/digests")
    def list_digests(response: Response, session: Session = Depends(session_dep)):
        response.headers["Cache-Control"] = "no-store"
        user = session.principal.user_id
        return {"enabled": book.enabled(user), "items": book.listing(user)}

    @router.get("/me/digests/{digest_id}")
    def get_digest(digest_id: str, response: Response, session: Session = Depends(session_dep)):
        response.headers["Cache-Control"] = "no-store"
        found = book.get(session.principal.user_id, digest_id[:64])
        if found is None:
            raise HTTPException(status_code=404, detail="Not found")
        return found

    @router.post("/me/digests/{digest_id}/read")
    def read_digest(digest_id: str, response: Response, session: Session = Depends(session_dep)):
        response.headers["Cache-Control"] = "no-store"
        if not book.mark_read(session.principal.user_id, digest_id[:64]):
            raise HTTPException(status_code=404, detail="Not found")
        return {"ok": True}

    @router.delete("/me/digests/{digest_id}")
    def delete_digest(digest_id: str, response: Response, session: Session = Depends(session_dep)):
        response.headers["Cache-Control"] = "no-store"
        if not book.delete(session.principal.user_id, digest_id[:64]):
            raise HTTPException(status_code=404, detail="Not found")
        return {"ok": True}

    @router.post("/me/digests/now")
    def make_now(response: Response, session: Session = Depends(session_dep)):
        """Make (or remake) today's summary right now, so it can be seen without waiting for the morning. Sends no alert."""
        response.headers["Cache-Control"] = "no-store"
        user = session.principal.user_id
        if not book.enabled(user):
            raise HTTPException(status_code=403, detail="Turn on the daily summary in your inbox first.")
        if not limit.allow(f"digest:{user}"):
            raise HTTPException(status_code=429, detail="That was done a few times already. Try again in an hour.")
        made = book.build(user, time.time(), replace_today=True)
        return {"made": made is not None, "id": made["id"] if made else None}

    return router
