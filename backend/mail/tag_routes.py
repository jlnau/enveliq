"""Tags: list the mailbox's own tags, make a new one, put one on an email or take it off."""
from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import Field, StrictBool

from ..models import StrictModel
from ..security import Session
from . import features
from . import tags as T
from .errors import HTTP_STATUS, BridgeError
from .limits import SlidingWindowLimiter
from .routes import AccountId, MessageId


class NewTagBody(StrictModel):
    name: str = Field(max_length=200)


class SetTagBody(StrictModel):
    name: str = Field(max_length=200)
    on: StrictBool


def build_tag_router(ctx: Any) -> APIRouter:
    router = APIRouter(prefix="/api/v1")
    service = ctx.tags
    vault = ctx.vault
    session_dep = ctx.full_session
    limit = SlidingWindowLimiter(max_events=60, window=60)

    def start(account_id: str, session: Session) -> tuple[str, dict[str, Any]]:
        user = session.principal.user_id
        account = ctx.load_account(account_id, session.principal, owner_only=True, action="use its tags")
        if not features.effective(vault, user)["tags"]:
            raise HTTPException(status_code=403, detail="Tags are switched off.")
        if not limit.allow(f"tags:{user}"):
            raise HTTPException(status_code=429, detail="Too many changes. Wait a minute.")
        return user, account

    def failed(err: Exception) -> HTTPException:
        if isinstance(err, T.TagError):
            return HTTPException(status_code=422, detail=str(err))
        if isinstance(err, BridgeError):
            return HTTPException(status_code=HTTP_STATUS.get(err.code, 502), detail={"code": err.code, "message": err.message})
        raise err

    @router.get("/accounts/{account_id}/tags")
    def list_tags(account_id: AccountId, response: Response, session: Session = Depends(session_dep)):
        response.headers["Cache-Control"] = "no-store"
        _user, account = start(account_id, session)
        try:
            return service.overview(account)
        except (T.TagError, BridgeError) as err:
            raise failed(err) from None

    @router.post("/accounts/{account_id}/tags", status_code=201)
    def make_tag(body: NewTagBody, account_id: AccountId, response: Response, session: Session = Depends(session_dep)):
        response.headers["Cache-Control"] = "no-store"
        user, account = start(account_id, session)
        try:
            out = service.create(account, body.name)
        except (T.TagError, BridgeError) as err:
            raise failed(err) from None
        vault.audit({"event": "tag_created", "actor_user_id": user, "account_id": account_id, "at": time.time()})      # that one was made, never its name
        return out

    @router.put("/accounts/{account_id}/messages/{message_id}/tags")
    def tag_message(body: SetTagBody, account_id: AccountId, message_id: MessageId, response: Response, session: Session = Depends(session_dep)):
        response.headers["Cache-Control"] = "no-store"
        user, account = start(account_id, session)
        try:
            vault.get_message(account_id, message_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="Message not found") from None
        try:
            tags = service.set_for_message(account, message_id, body.name, body.on)
        except KeyError:
            raise HTTPException(status_code=404, detail="Message not found") from None
        except (T.TagError, BridgeError) as err:
            raise failed(err) from None
        vault.audit({"event": "message_tagged" if body.on else "message_untagged", "actor_user_id": user, "account_id": account_id,
                     "message_id": message_id, "at": time.time()})
        return {"tags": tags}

    return router
