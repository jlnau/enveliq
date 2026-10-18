"""Find any email: start a search, watch it, cancel it, open a result, keep one in Found emails."""
from __future__ import annotations

import time
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi import Path as PathParam

from ..security import Session
from ..models import StrictModel
from . import features
from .errors import BridgeError
from .find import FindError, FindJobs, parse_query
from .limits import SlidingWindowLimiter
from .parse import render_original
from .routes import fail
from .service import MAIL_METHODS, target_for

JobId = Annotated[str, PathParam(pattern=r"^[A-Za-z0-9_-]{8,16}$")]
Token = Annotated[str, PathParam(pattern=r"^[A-Za-z0-9_-]{8,16}\.\d{1,6}\.[0-9a-f]{24}$")]


class StartBody(StrictModel):
    query: str
    include_junk: bool = False


def build_find_router(ctx: Any) -> APIRouter:
    router = APIRouter(prefix="/api/v1/find")
    service = ctx.mail
    vault = ctx.vault
    session_dep = ctx.full_session
    start_limit = SlidingWindowLimiter(max_events=6, window=60)
    page_limit = SlidingWindowLimiter(max_events=120, window=60)
    view_limit = SlidingWindowLimiter(max_events=60, window=60)
    keep_limit = SlidingWindowLimiter(max_events=60, window=60)
    jobs = FindJobs(service.bridge, lambda account_id: vault.get_account(account_id), service.target)
    ctx.find_jobs = jobs

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

    @router.post("/results/{token}/keep")
    def keep(token: Token, response: Response, session: Session = Depends(session_dep)):
        user = need(session)
        if not keep_limit.allow(f"findkeep:{user}"):
            raise HTTPException(status_code=429, detail="Too many requests. Wait a minute.")
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
        no_store(response)
        return {"already": False, "account_id": ref.account_id, "message_id": message_id, "found_until": stored.get("found_until"), "summary_queued": queued}

    return router
