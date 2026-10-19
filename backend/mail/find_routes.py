"""Find any email: start a search, watch it, cancel it, open a result, keep one in Found emails."""
from __future__ import annotations

import re
import time
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi import Path as PathParam

from ..security import Session
from ..models import StrictModel
from . import features
from .errors import BridgeError
from .find import FindError, FindJobs, parse_query
from .find_index import FindIndex
from .limits import SlidingWindowLimiter
from .parse import render_original
from .routes import AccountId, fail
from .service import MAIL_METHODS, target_for

JobId = Annotated[str, PathParam(pattern=r"^[A-Za-z0-9_-]{8,16}$")]
TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{8,16}\.\d{1,6}\.[0-9a-f]{24}$")
Token = Annotated[str, PathParam(pattern=TOKEN_RE.pattern)]
MAX_KEEP_MANY = 100


class FastBody(StrictModel):
    enabled: bool
    agree: bool = False


class StartBody(StrictModel):
    query: str
    include_junk: bool = False


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
            terms = parse_query(body.query)
            accounts = [(a["id"], str(a.get("email_address") or a.get("name") or "Mailbox"))
                        for a in vault.list_accounts() if a.get("owner_user_id") == user and a.get("auth_method") in MAIL_METHODS]
            job = jobs.start(user, accounts, terms, body.include_junk)
        except FindError as err:
            raise HTTPException(status_code=err.status, detail=err.message) from None
        vault.audit({"event": "mail_search_started", "actor_user_id": user, "at": time.time()})   # that a search happened; never the words
        return jobs.progress(job)

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
                    return {"already": True, "message": err.message}
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
