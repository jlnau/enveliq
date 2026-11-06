"""Find any email: start a search, watch it, cancel it, open a result, keep one in Found emails."""
from __future__ import annotations

import re
import time
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi import Path as PathParam
from pydantic import Field

from ..security import Session
from ..models import StrictModel
from . import features
from .errors import BridgeError
from .find import FindError, FindJobs, make_filters, parse_query
from .find_index import FindIndex
from .limits import SlidingWindowLimiter
from .parse import render_original
from .routes import AccountId, fail
from .saved_searches import SearchBookError
from .service import MAIL_METHODS, target_for

JobId = Annotated[str, PathParam(pattern=r"^[A-Za-z0-9_-]{8,16}$")]
TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{8,16}\.\d{1,6}\.[0-9a-f]{24}$")
Token = Annotated[str, PathParam(pattern=TOKEN_RE.pattern)]
MAX_KEEP_MANY = 100


class FastBody(StrictModel):
    enabled: bool
    agree: bool = False


class StartBody(StrictModel):
    query: str = Field(default="", max_length=400)
    include_junk: bool = False
    sender: str = Field(default="", max_length=200)
    to: str = Field(default="", max_length=200)
    since: str = Field(default="", max_length=10)
    until: str = Field(default="", max_length=10)
    unread: bool = False
    starred: bool = False
    files: bool = False
    account_id: str = Field(default="", max_length=64)
    folder: str = Field(default="", max_length=300)


class SaveBody(StartBody):
    name: str = Field(max_length=100)


class FoundStarBody(StrictModel):
    starred: bool


class FoundMoveBody(StrictModel):
    folder: str | None = None   # a listed folder name; left out means the Inbox


class KeepManyBody(StrictModel):
    tokens: list[str]


def build_find_router(ctx: Any) -> APIRouter:
    router = APIRouter(prefix="/api/v1/find")
    service = ctx.mail
    vault = ctx.vault
    session_dep = ctx.full_session
    start_limit = SlidingWindowLimiter(max_events=6, window=60)
    page_limit = SlidingWindowLimiter(max_events=120, window=60)
    view_limit = SlidingWindowLimiter(max_events=60, window=60)
    keep_limit = SlidingWindowLimiter(max_events=60, window=60)
    keep_many_limit = SlidingWindowLimiter(max_events=6, window=60)
    index = FindIndex(vault, service.bridge, lambda account_id: vault.get_account(account_id), service.target, vault.db_path.parent / "find-index")
    ctx.find_index = index
    index.watch()
    jobs = FindJobs(service.bridge, lambda account_id: vault.get_account(account_id), service.target, fast=index)
    ctx.find_jobs = jobs
    fast_limit = SlidingWindowLimiter(max_events=30, window=60)
    searches = ctx.searches
    hist_limit = SlidingWindowLimiter(max_events=60, window=60)

    def need(session: Session) -> str:
        user = session.principal.user_id
        if not features.effective(vault, user)["find_mail"]:
            raise HTTPException(status_code=403, detail="Find any email is switched off.")
        return user

    def job_of(user: str, job_id: str):
        try:
            return jobs.job(user, job_id)
        except FindError as err:
            raise HTTPException(status_code=err.status, detail=err.message) from None

    def no_store(response: Response) -> None:
        response.headers["Cache-Control"] = "no-store"

    def mine(user: str) -> list[dict[str, Any]]:
        return [a for a in vault.list_accounts() if a.get("owner_user_id") == user and a.get("auth_method") in MAIL_METHODS]

    def mailbox(user: str, account_id: str) -> dict[str, Any]:
        for a in mine(user):
            if a["id"] == account_id:
                return a
        raise HTTPException(status_code=404, detail="Not found.")

    @router.get("/fast")
    def fast_status(response: Response, session: Session = Depends(session_dep)):
        user = need(session)
        no_store(response)
        return {"mailboxes": [{**index.status(user, a["id"]), "label": str(a.get("email_address") or a.get("name") or "Mailbox"), "recommended": a.get("auth_method") == "proton_bridge"} for a in mine(user)]}

    @router.put("/fast/{account_id}")
    def fast_set(account_id: AccountId, body: FastBody, session: Session = Depends(session_dep)):
        user = need(session)
        mailbox(user, account_id)
        if not fast_limit.allow(f"findfast:{user}"):
            raise HTTPException(status_code=429, detail="Too many requests. Wait a minute.")
        if body.enabled:
            if not body.agree:
                raise HTTPException(status_code=400, detail="Tick the box to say you understand, then turn Fast search on.")
            index.enable(user, account_id)
        else:
            index.disable(user, account_id)
        vault.audit({"event": "find_fast_on" if body.enabled else "find_fast_off", "actor_user_id": user, "account_id": account_id, "at": time.time()})
        return index.status(user, account_id)

    @router.post("/fast/{account_id}/rebuild", status_code=202)
    def fast_rebuild(account_id: AccountId, session: Session = Depends(session_dep)):
        user = need(session)
        mailbox(user, account_id)
        if not index.is_enabled(user, account_id):
            raise HTTPException(status_code=409, detail="Fast search is off for this mailbox.")
        if not fast_limit.allow(f"findfast:{user}"):
            raise HTTPException(status_code=429, detail="Too many requests. Wait a minute.")
        index.rebuild(user, account_id)
        return index.status(user, account_id)

    @router.post("/searches", status_code=201)
    def start(body: StartBody, response: Response, session: Session = Depends(session_dep)):
        user = need(session)
        if not start_limit.allow(f"find:{user}"):
            raise HTTPException(status_code=429, detail="Too many searches. Wait a minute.")
        no_store(response)
        try:
            filters = make_filters(body.sender, body.to, body.since, body.until, body.unread, body.starred, body.files, body.folder if body.account_id else "")
            terms = parse_query(body.query, optional=filters.any)
            accounts = [(a["id"], str(a.get("email_address") or a.get("name") or "Mailbox"))
                        for a in vault.list_accounts() if a.get("owner_user_id") == user and a.get("auth_method") in MAIL_METHODS]
            if body.account_id:
                accounts = [x for x in accounts if x[0] == body.account_id]
                if not accounts:
                    raise HTTPException(status_code=404, detail="Not found.")
            job = jobs.start(user, accounts, terms, body.include_junk, filters)
        except FindError as err:
            raise HTTPException(status_code=err.status, detail=err.message) from None
        searches.remember(user, body.model_dump())
        vault.audit({"event": "mail_search_started", "actor_user_id": user, "at": time.time()})   # that a search happened; never the words
        return jobs.progress(job)

    @router.get("/history")
    def history(response: Response, session: Session = Depends(session_dep)):
        user = need(session)
        no_store(response)
        return searches.listing(user)

    @router.delete("/history/recent", status_code=204)
    def clear_recent(session: Session = Depends(session_dep)):
        searches.clear_recent(need(session))
        return Response(status_code=204)

    @router.post("/saved", status_code=201)
    def save_search(body: SaveBody, response: Response, session: Session = Depends(session_dep)):
        user = need(session)
        if not hist_limit.allow(f"findsave:{user}"):
            raise HTTPException(status_code=429, detail="Too many requests. Wait a minute.")
        no_store(response)
        try:
            return searches.add(user, body.name, body.model_dump())
        except SearchBookError as err:
            raise HTTPException(status_code=400, detail=str(err)) from None

    @router.delete("/saved/{saved_id}", status_code=204)
    def forget_search(saved_id: Annotated[str, PathParam(pattern=r"^s[0-9a-f]{16}$")], session: Session = Depends(session_dep)):
        user = need(session)
        if not searches.remove(user, saved_id):
            raise HTTPException(status_code=404, detail="Not found.")
        return Response(status_code=204)

    @router.get("/searches/{job_id}")
    def progress(job_id: JobId, response: Response, session: Session = Depends(session_dep)):
        user = need(session)
        no_store(response)
        return jobs.progress(job_of(user, job_id))

    @router.get("/searches/{job_id}/results")
    def results(job_id: JobId, response: Response, offset: int = Query(default=0, ge=0, le=100000), session: Session = Depends(session_dep)):
        user = need(session)
        if not page_limit.allow(f"findpage:{user}"):
            raise HTTPException(status_code=429, detail="Too many requests. Wait a minute.")
        job = job_of(user, job_id)
        no_store(response)
        rows = jobs.page(job, offset)
        return {**jobs.progress(job), "offset": offset, "rows": rows, "more": offset + 25 < len(job.refs)}

    @router.delete("/searches/{job_id}", status_code=204)
    def cancel(job_id: JobId, session: Session = Depends(session_dep)):
        user = need(session)
        jobs.cancel(job_of(user, job_id))
        return Response(status_code=204)

    @router.get("/results/{token}/original")
    def original(token: Token, response: Response, session: Session = Depends(session_dep)):
        user = need(session)
        if not view_limit.allow(f"findview:{user}"):
            raise HTTPException(status_code=429, detail="Too many requests. Wait a minute.")
        try:
            raw, _ref = jobs.original(user, token)
        except FindError as err:
            raise HTTPException(status_code=err.status, detail=err.message) from None
        except BridgeError as err:
            raise fail(err) from None
        no_store(response)
        return render_original(raw)

    def keep_one(user: str, token: str) -> dict[str, Any]:
        """Keep one found email in Found emails and queue its summary. Raises HTTPException on a problem."""
        try:
            raw, ref = jobs.headers_of(user, token)
            account = vault.get_account(ref.account_id)
            if account.get("owner_user_id") != user:
                raise HTTPException(status_code=404, detail="Not found.")
            try:
                message_id = service.keep_found(vault, account, raw, ref.folder, ref.validity, ref.uid)
            except BridgeError as err:
                if err.code == "already_listed":
                    return {"already": True, "message": err.message, "account_id": ref.account_id, "message_id": service.stored_id_at(vault, ref.account_id, ref.folder, ref.validity, ref.uid)}
                raise
        except FindError as err:
            raise HTTPException(status_code=err.status, detail=err.message) from None
        except BridgeError as err:
            raise fail(err) from None
        queued = False
        queue = getattr(ctx, "summary_queue", None)
        service.refresh_ai(vault)
        if queue is not None and service.summariser.enabled:
            try:
                queue.add(user, ref.account_id, message_id)
                queued = True
            except BridgeError:
                queued = False
        stored = vault.get_message(ref.account_id, message_id)
        vault.audit({"event": "found_email_kept", "actor_user_id": user, "account_id": ref.account_id, "message_id": message_id, "at": time.time()})
        return {"already": False, "account_id": ref.account_id, "message_id": message_id, "found_until": stored.get("found_until"), "summary_queued": queued}

    move_limit = SlidingWindowLimiter(max_events=120, window=60)

    def relocate(token: str, session: Session, dest: str | None, event: str) -> Response:
        """Move one found email (wherever it sits in the mailbox) to a folder, the Inbox or the Bin. Nothing is stored."""
        user = need(session)
        if not move_limit.allow(f"findmove:{user}"):
            raise HTTPException(status_code=429, detail="Too many requests. Wait a minute.")
        try:
            _job, ref = jobs.resolve(user, token)
            account = vault.get_account(ref.account_id)
            if account.get("owner_user_id") != user:
                raise HTTPException(status_code=404, detail="Not found.")
            if dest is None and ref.folder.upper() == "INBOX":
                raise HTTPException(status_code=409, detail="That email is already in your Inbox.")
            ctx.folders.move_from_folder(account, ref.folder, ref.validity, ref.uid, dest)
        except FindError as err:
            raise HTTPException(status_code=err.status, detail=err.message) from None
        except BridgeError as err:
            raise (HTTPException(status_code=404, detail="Not found.") if err.code == "not_found" else fail(err)) from None
        vault.audit({"event": event, "actor_user_id": user, "account_id": ref.account_id, "at": time.time()})
        return Response(status_code=204, headers={"Cache-Control": "no-store"})

    @router.post("/results/{token}/move", status_code=204)
    def move_found(token: Token, body: FoundMoveBody, session: Session = Depends(session_dep)):
        return relocate(token, session, body.folder, "found_email_moved")

    @router.post("/results/{token}/bin", status_code=204)
    def bin_found(token: Token, session: Session = Depends(session_dep)):
        return relocate(token, session, "\\trash", "found_email_binned")

    summary_limit = SlidingWindowLimiter(max_events=20, window=60)

    @router.post("/results/{token}/summary")
    def summary_found(token: Token, response: Response, session: Session = Depends(session_dep)):
        """A short summary of one found email, written when the person presses the button. Nothing is kept."""
        user = need(session)
        if not summary_limit.allow(f"findsum:{user}"):
            raise HTTPException(status_code=429, detail="Too many requests. Wait a minute.")
        no_store(response)
        try:
            raw, ref = jobs.original(user, token)
        except FindError as err:
            raise HTTPException(status_code=err.status, detail=err.message) from None
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
        vault.audit({"event": "found_mail_summarised", "actor_user_id": user, "account_id": ref.account_id, "at": time.time()})
        return {"summary": out["summary"]}

    summary_limit = SlidingWindowLimiter(max_events=20, window=60)

    @router.post("/results/{token}/summary")
    def summary_found(token: Token, response: Response, session: Session = Depends(session_dep)):
        """A short summary of one found email, written when the person presses the button. Nothing is kept."""
        user = need(session)
        if not summary_limit.allow(f"findsum:{user}"):
            raise HTTPException(status_code=429, detail="Too many requests. Wait a minute.")
        no_store(response)
        try:
            raw, ref = jobs.original(user, token)
        except FindError as err:
            raise HTTPException(status_code=err.status, detail=err.message) from None
        except BridgeError as err:
            raise fail(err) from None
        service.refresh_ai(vault)
        if not service.summariser.enabled:
            raise HTTPException(status_code=409, detail={"code": "ai_not_configured", "message": "No AI model is set up yet. An administrator can add one under Administration, AI model."})
        mail = render_original(raw)
        sender = f"{mail['from']['name']} <{mail['from']['address']}>".strip()
        try:
            out = service.summariser.summarise(mail["subject"], sender, mail["text"])
        except BridgeError as err:
            raise fail(err) from None
        vault.audit({"event": "found_email_summarised", "actor_user_id": user, "account_id": ref.account_id, "at": time.time()})
        return {"summary": out["summary"]}

    summary_limit = SlidingWindowLimiter(max_events=20, window=60)

    @router.post("/results/{token}/summary")
    def summary_found(token: Token, response: Response, session: Session = Depends(session_dep)):
        """A short summary of one found email, written when the person presses the button. Nothing is kept."""
        user = need(session)
        if not summary_limit.allow(f"findsum:{user}"):
            raise HTTPException(status_code=429, detail="Too many requests. Wait a minute.")
        no_store(response)
        try:
            raw, ref = jobs.original(user, token)
        except FindError as err:
            raise HTTPException(status_code=err.status, detail=err.message) from None
        except BridgeError as err:
            raise fail(err) from None
        service.refresh_ai(vault)
        if not service.summariser.enabled:
            raise HTTPException(status_code=409, detail={"code": "ai_not_configured", "message": "No AI model is set up yet. An administrator can add one under Administration, AI model."})
        mail = render_original(raw)
        sender = f"{mail['from']['name']} <{mail['from']['address']}>".strip()
        try:
            out = service.summariser.summarise(mail["subject"], sender, mail["text"])
        except BridgeError as err:
            raise fail(err) from None
        vault.audit({"event": "found_email_summarised", "actor_user_id": user, "account_id": ref.account_id, "at": time.time()})
        return {"summary": out["summary"]}

    @router.post("/results/{token}/archive", status_code=204)
    def archive_found(token: Token, session: Session = Depends(session_dep)):
        return relocate(token, session, "\\archive", "found_email_archived")

    @router.post("/results/{token}/star", status_code=204)
    def star_found(token: Token, body: FoundStarBody, session: Session = Depends(session_dep)):
        user = need(session)
        if not move_limit.allow(f"findmove:{user}"):
            raise HTTPException(status_code=429, detail="Too many requests. Wait a minute.")
        try:
            _job, ref = jobs.resolve(user, token)
            account = vault.get_account(ref.account_id)
            if account.get("owner_user_id") != user:
                raise HTTPException(status_code=404, detail="Not found.")
            ctx.folders.flag_in_folder(account, ref.folder, ref.validity, ref.uid, body.starred)
        except FindError as err:
            raise HTTPException(status_code=err.status, detail=err.message) from None
        except BridgeError as err:
            raise (HTTPException(status_code=404, detail="Not found.") if err.code == "not_found" else fail(err)) from None
        return Response(status_code=204, headers={"Cache-Control": "no-store"})

    @router.post("/results/{token}/keep")
    def keep(token: Token, response: Response, session: Session = Depends(session_dep)):
        user = need(session)
        if not keep_limit.allow(f"findkeep:{user}"):
            raise HTTPException(status_code=429, detail="Too many requests. Wait a minute.")
        out = keep_one(user, token)
        no_store(response)
        return out

    @router.post("/results/keep")
    def keep_many(body: KeepManyBody, response: Response, session: Session = Depends(session_dep)):
        """Summarise several found emails at once: each is kept in Found emails and put in the same AI summary queue as one."""
        user = need(session)
        tokens = list(dict.fromkeys(body.tokens))
        if not 1 <= len(tokens) <= MAX_KEEP_MANY:
            raise HTTPException(status_code=422, detail=f"Choose between 1 and {MAX_KEEP_MANY} emails.")
        if not keep_many_limit.allow(f"findkeepmany:{user}"):
            raise HTTPException(status_code=429, detail="Too many requests. Wait a minute.")
        results: dict[str, Any] = {}
        for token in tokens:
            if not TOKEN_RE.match(token):
                results[token] = {"ok": False, "detail": "That result is no longer available."}
                continue
            try:
                results[token] = {"ok": True, **keep_one(user, token)}
            except HTTPException as err:
                results[token] = {"ok": False, "detail": str(err.detail)}
        no_store(response)
        return {"results": results}

    return router
