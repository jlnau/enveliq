"""The daily summary and the email held for it (see digest.py): read it, take one email out, or finish with it.

Everything is the signed-in person's own. An email that is not theirs answers "not found". Reviewed, Archive and Bin on a line in the
summary are the normal email actions (the existing resolve route), so the same rules apply.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import Field

from ..models import StrictModel
from ..security import Session
from .digest import DigestBook


class OneMail(StrictModel):
    account_id: str = Field(min_length=1, max_length=128)
    message_id: str = Field(min_length=1, max_length=512)


def build_digest_router(ctx: Any) -> APIRouter:
    router = APIRouter(prefix="/api/v1")
    book: DigestBook = ctx.digest
    session_dep = ctx.full_session

    @router.get("/me/summary")
    def summary(response: Response, session: Session = Depends(session_dep)):
        response.headers["Cache-Control"] = "no-store"
        return book.view(session.principal.user_id)

    @router.post("/me/summary/seen")
    def seen(response: Response, session: Session = Depends(session_dep)):
        response.headers["Cache-Control"] = "no-store"
        book.mark_seen(session.principal.user_id)
        return {"ok": True}

    @router.post("/me/summary/complete")
    def complete(response: Response, session: Session = Depends(session_dep)):
        """Done with the summary: whatever is still in it goes back in the inbox, unchanged."""
        response.headers["Cache-Control"] = "no-store"
        return {"returned": book.release(session.principal.user_id)}

    @router.post("/me/summary/remove")
    def remove(body: OneMail, response: Response, session: Session = Depends(session_dep)):
        """Take one email out of the summary: it goes back in the inbox."""
        response.headers["Cache-Control"] = "no-store"
        user = session.principal.user_id
        account = ctx.vault.get_account(body.account_id)
        if not account or account.get("owner_user_id") != user:
            raise HTTPException(status_code=404, detail="Not found")
        try:
            message = ctx.vault.get_message(body.account_id, body.message_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="Not found") from None
        if message.get("held_for_summary") is not True:
            raise HTTPException(status_code=404, detail="Not found")
        book.release(user, only=(body.account_id, body.message_id))
        return {"ok": True}

    return router
