"""Folders: list, make one, look inside one, open an email in one, and move an email from the Inbox into one."""
from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from ..models import StrictModel
from ..security import Session
from .errors import BridgeError
from .find import FindError
from .folders import Folders
from .limits import SlidingWindowLimiter
from .parse import render_original
from .routes import AccountId, fail
from .service import MAIL_METHODS


class NewFolderBody(StrictModel):
    name: str


class MoveBody(StrictModel):
    folder: str


class StarBody(StrictModel):
    starred: bool


class FolderMoveBody(StrictModel):
    folder: str | None = None   # a listed folder name; left out means the Inbox


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
               q: str = Query(default="", max_length=200), session: Session = Depends(session_dep)):
        account = mailbox(account_id, session, "open a folder")
        allow(session)
        response.headers["Cache-Control"] = "no-store"
        try:
            return folders.page(session.principal.user_id, account, folder, offset, q)
        except FindError as err:
            raise HTTPException(status_code=422, detail=err.message) from None
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

    def relocate(token: str, session: Session, dest: str | None, event: str) -> Response:
        user = session.principal.user_id
        allow(session)
        try:
            account_id, folder, validity, uid = folders.open_token(user, token)
            account = mailbox(account_id, session, "move an email")
            folders.move_from_folder(account, folder, validity, uid, dest)
        except BridgeError as err:
            raise (HTTPException(status_code=404, detail="Not found.") if err.code == "not_found" else fail(err)) from None
        vault.audit({"event": event, "actor_user_id": user, "account_id": account_id, "at": time.time()})
        return Response(status_code=204, headers={"Cache-Control": "no-store"})

    @router.post("/folder-mail/{token}/move", status_code=204)
    def move_folder_mail(token: str, body: FolderMoveBody, session: Session = Depends(session_dep)):
        """Move an email that is in a folder to another folder, or to the Inbox when no folder is given."""
        return relocate(token, session, body.folder, "folder_mail_moved")

    @router.post("/folder-mail/{token}/bin", status_code=204)
    def bin_folder_mail(token: str, session: Session = Depends(session_dep)):
        return relocate(token, session, "\\trash", "folder_mail_binned")

    @router.post("/folder-mail/{token}/archive", status_code=204)
    def archive_folder_mail(token: str, session: Session = Depends(session_dep)):
        return relocate(token, session, "\\archive", "folder_mail_archived")

    @router.post("/folder-mail/{token}/star", status_code=204)
    def star_folder_mail(token: str, body: StarBody, session: Session = Depends(session_dep)):
        user = session.principal.user_id
        allow(session)
        try:
            account_id, folder, validity, uid = folders.open_token(user, token)
            account = mailbox(account_id, session, "star an email")
            folders.flag_in_folder(account, folder, validity, uid, body.starred)
        except BridgeError as err:
            raise (HTTPException(status_code=404, detail="Not found.") if err.code == "not_found" else fail(err)) from None
        return Response(status_code=204, headers={"Cache-Control": "no-store"})

    @router.post("/folder-mail/{token}/keep")
    def keep_folder_mail(token: str, response: Response, session: Session = Depends(session_dep)):
        """Add one folder email to the person's lists quietly (headers and an encrypted summary only, for 60 days) so it can be tagged, snoozed and so on."""
        user = session.principal.user_id
        allow(session)
        response.headers["Cache-Control"] = "no-store"
        try:
            account_id, folder, validity, uid = folders.open_token(user, token)
            account = mailbox(account_id, session, "keep an email")
            raw = folders.headers(account, folder, validity, uid)
            try:
                message_id = service.keep_found(vault, account, raw, folder, validity, uid)
            except BridgeError as err:
                if err.code == "already_listed":
                    return {"already": True, "message": err.message, "account_id": account_id, "message_id": service.stored_id_at(vault, account_id, folder, validity, uid)}
                raise
        except BridgeError as err:
            raise (HTTPException(status_code=404, detail="Not found.") if err.code == "not_found" else fail(err)) from None
        queue = getattr(ctx, "summary_queue", None)
        service.refresh_ai(vault)
        if queue is not None and service.summariser.enabled:
            try:
                queue.add(user, account_id, message_id)
            except BridgeError:
                pass
        vault.audit({"event": "folder_mail_kept", "actor_user_id": user, "account_id": account_id, "message_id": message_id, "at": time.time()})
        return {"already": False, "account_id": account_id, "message_id": message_id}

    ask_limit = SlidingWindowLimiter(max_events=20, window=60)

    @router.post("/folder-mail/{token}/summary")
    def summary(token: str, response: Response, session: Session = Depends(session_dep)):
        """A short summary of one email in a folder, written when the person presses the button. Nothing is kept."""
        user = session.principal.user_id
        allow(session, ask_limit)
        response.headers["Cache-Control"] = "no-store"
        try:
            account_id, folder, validity, uid = folders.open_token(user, token)
            account = mailbox(account_id, session, "summarise an email")
            raw = folders.original(account, folder, validity, uid)
        except BridgeError as err:
            raise (HTTPException(status_code=404, detail="Not found.") if err.code == "not_found" else fail(err)) from None
        service.refresh_ai(vault)
        if not service.summariser.enabled:
            raise HTTPException(status_code=409, detail={"code": "ai_not_configured", "message": "No AI model is set up yet. An administrator can add one under Administration, AI model."})
        mail = render_original(raw)
        sender = f"{mail['from']['name']} <{mail['from']['address']}>".strip()
        try:
            out = service.summariser.summarise(mail["subject"], sender, mail["text"])
        except BridgeError as err:
            raise fail(err) from None
        vault.audit({"event": "folder_mail_summarised", "actor_user_id": user, "account_id": account_id, "at": time.time()})
        return {"summary": out["summary"]}

    return router
