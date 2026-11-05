"""Folders: list, make one, look inside one, open an email in one, and move an email from the Inbox into one."""
from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from ..models import StrictModel
from ..security import Session
from .errors import BridgeError
from .folders import Folders
from .limits import SlidingWindowLimiter
from .parse import render_original
from .routes import AccountId, fail
from .service import MAIL_METHODS


class NewFolderBody(StrictModel):
    name: str


class MoveBody(StrictModel):
    folder: str


def build_folder_router(ctx: Any) -> APIRouter:
    router = APIRouter(prefix="/api/v1")
    vault, service = ctx.vault, ctx.mail
    session_dep = ctx.full_session
    folders = Folders(service.bridge, lambda aid: vault.get_account(aid), service.target)
    ctx.folders = folders
    limit = SlidingWindowLimiter(max_events=120, window=60)
    make_limit = SlidingWindowLimiter(max_events=10, window=60)

    def mailbox(account_id: str, session: Session, action: str) -> dict[str, Any]:
        account = ctx.load_account(account_id, session.principal, owner_only=True, action=action)
        if account.get("auth_method") not in MAIL_METHODS:
            raise HTTPException(status_code=404, detail="Not found.")
        return account

    def allow(session: Session, bucket: SlidingWindowLimiter = limit) -> None:
        if not bucket.allow(f"folders:{session.principal.user_id}"):
            raise HTTPException(status_code=429, detail="Too many requests. Wait a minute.")

    @router.get("/accounts/{account_id}/folders")
    def list_folders(account_id: AccountId, response: Response, session: Session = Depends(session_dep)):
        account = mailbox(account_id, session, "see folders")
        allow(session)
        response.headers["Cache-Control"] = "no-store"
        try:
            return {"folders": folders.list(account)}
        except BridgeError as err:
            raise fail(err) from None

    @router.post("/accounts/{account_id}/folders", status_code=201)
    def make_folder(account_id: AccountId, body: NewFolderBody, response: Response, session: Session = Depends(session_dep)):
        account = mailbox(account_id, session, "make a folder")
        allow(session, make_limit)
        response.headers["Cache-Control"] = "no-store"
        try:
            row = folders.create(account, body.name)
        except ValueError:
            raise HTTPException(status_code=422, detail="Use a short name without slashes or special marks.") from None
        except BridgeError as err:
            raise (HTTPException(status_code=409, detail=err.message) if err.code == "already_listed" else fail(err)) from None
        vault.audit({"event": "folder_made", "actor_user_id": session.principal.user_id, "account_id": account_id, "at": time.time()})
        return row

    @router.get("/accounts/{account_id}/folder-mail")
    def inside(account_id: AccountId, response: Response, folder: str = Query(min_length=1, max_length=300), offset: int = Query(default=0, ge=0, le=1_000_000),
               session: Session = Depends(session_dep)):
        account = mailbox(account_id, session, "open a folder")
        allow(session)
        response.headers["Cache-Control"] = "no-store"
        try:
            return folders.page(session.principal.user_id, account, folder, offset)
        except BridgeError as err:
            raise fail(err) from None

    @router.get("/folder-mail/{token}/original")
    def original(token: str, response: Response, session: Session = Depends(session_dep)):
        user = session.principal.user_id
        allow(session)
        try:
            account_id, folder, validity, uid = folders.open_token(user, token)
            account = mailbox(account_id, session, "open an email")
            raw = folders.original(account, folder, validity, uid)
        except BridgeError as err:
            raise (HTTPException(status_code=404, detail="Not found.") if err.code == "not_found" else fail(err)) from None
        response.headers["Cache-Control"] = "no-store"
        return render_original(raw)

    return router
