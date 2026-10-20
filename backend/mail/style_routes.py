"""Settings and actions for the personal writing-style guide (see style.py). The guide is the person's own text: they can read and edit it."""
from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import Field

from ..models import StrictModel
from ..security import Session
from . import features, style as S
from .limits import SlidingWindowLimiter


class StyleBody(StrictModel):
    on: bool | None = None
    guide: str | None = Field(default=None, max_length=S.GUIDE_MAX * 2)
    mode: str | None = Field(default=None, max_length=10)


def build_style_router(ctx: Any) -> APIRouter:
    router = APIRouter(prefix="/api/v1")
    book: S.StyleBook = ctx.style
    service, vault = ctx.mail, ctx.vault
    session_dep = ctx.full_session
    limit = SlidingWindowLimiter(max_events=4, window=3600)

    def available(user: str) -> bool:
        return features.effective(vault, user)["write_help"]

    def view(user: str) -> dict[str, Any]:
        service.refresh_ai(vault)
        return {"available": available(user), "ai_ready": service.summariser.enabled, **book.get(user)}

    @router.get("/me/writing-style")
    def get_style(response: Response, session: Session = Depends(session_dep)):
        response.headers["Cache-Control"] = "no-store"
        return view(session.principal.user_id)

    @router.put("/me/writing-style")
    def put_style(body: StyleBody, response: Response, session: Session = Depends(session_dep)):
        response.headers["Cache-Control"] = "no-store"
        user = session.principal.user_id
        if not available(user):
            raise HTTPException(status_code=403, detail="Writing help is switched off.")
        try:
            book.save(user, on=body.on, guide=body.guide, mode=body.mode)
        except ValueError:
            raise HTTPException(status_code=422, detail="Choose automatic or manual.") from None
        vault.audit({"event": "writing_style_settings", "actor_user_id": user, "at": time.time()})      # never the guide itself
        return view(user)

    @router.post("/me/writing-style/rebuild")
    def rebuild(response: Response, session: Session = Depends(session_dep)):
        """Make the guide again now, from the 20 newest sent emails. It runs in the background; read the guide again to see it finish."""
        response.headers["Cache-Control"] = "no-store"
        user = session.principal.user_id
        if not available(user):
            raise HTTPException(status_code=403, detail="Writing help is switched off.")
        if not book.get(user)["on"]:
            raise HTTPException(status_code=403, detail="Turn on learning your writing style first.")
        service.refresh_ai(vault)
        if not service.summariser.enabled:
            raise HTTPException(status_code=409, detail={"code": "ai_not_configured", "message": "No AI model is set up yet. An administrator can add one under Administration, AI model."})
        if not limit.allow(f"style:{user}"):
            raise HTTPException(status_code=429, detail="That was done a few times already. Try again in an hour.")
        book.start_rebuild(user, service.summariser)
        vault.audit({"event": "writing_style_rebuild", "actor_user_id": user, "at": time.time()})
        return {**view(user), "busy": True}

    return router
