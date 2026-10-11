"""Administration: backups and restore. Export my data: every person, their own data only."""
from __future__ import annotations

import json
import time
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import FileResponse
from pydantic import Field, SecretStr

from .auth import passwords
from .backup import BackupError, MAX_KEEP_DAYS, MIN_KEEP_DAYS
from .mail.limits import SlidingWindowLimiter
from .models import StrictModel
from .security import Session

NAME_PATTERN = r"^enveliq-\d{8}-\d{6}-(manual|auto|before-restore)\.sqlite3$"
CONFIRM_WORD = "RESTORE"


class SettingsBody(StrictModel):
    daily: bool
    keep_days: Annotated[int, Field(ge=MIN_KEEP_DAYS, le=MAX_KEEP_DAYS)]


class RestoreBody(StrictModel):
    password: SecretStr = Field(max_length=1024)
    confirm: Annotated[str, Field(max_length=40)]


def _fail(err: BackupError) -> HTTPException:
    code = 404 if err.code == "not_found" else 409 if err.code in ("too_many", "other_vault", "not_in_backup") else 500 if err.code in ("failed", "corrupt") else 400
    return HTTPException(status_code=code, detail=err.message)


def build_backup_router(ctx: Any) -> APIRouter:
    router = APIRouter(prefix="/api/v1")
    mgr, vault, users, sessions = ctx.backups, ctx.vault, ctx.users, ctx.sessions
    admin_dep, full_dep = ctx.admin_session, ctx.full_session
    limit = SlidingWindowLimiter(max_events=20, window=60)
    pw_limit = ctx.login_limiter
    export_limit = SlidingWindowLimiter(max_events=6, window=300)

    def view() -> dict[str, Any]:
        return {"backups": mgr.list(), "settings": mgr.settings(), "folder": "backups", "last_error": mgr.last_error,
                "max_keep_days": MAX_KEEP_DAYS, "confirm_word": CONFIRM_WORD}

    def throttle(user: str) -> None:
        if not limit.allow(f"bk:{user}"):
            raise HTTPException(status_code=429, detail="Too many requests. Wait a minute.")

    @router.get("/admin/backups")
    def get(response: Response, session: Session = Depends(admin_dep)):
        response.headers["Cache-Control"] = "no-store"
        return view()

    @router.put("/admin/backups/settings")
    def put_settings(body: SettingsBody, response: Response, session: Session = Depends(admin_dep)):
        response.headers["Cache-Control"] = "no-store"
        throttle(session.principal.user_id)
        mgr.save_settings(body.daily, body.keep_days)
        vault.audit({"event": "backup_settings_saved", "actor_user_id": session.principal.user_id, "daily": body.daily, "at": time.time()})
        return view()

    @router.post("/admin/backups")
    def make(response: Response, session: Session = Depends(admin_dep)):
        response.headers["Cache-Control"] = "no-store"
        throttle(session.principal.user_id)
        try:
            made = mgr.create("manual")
        except BackupError as err:
            raise _fail(err) from None
        vault.audit({"event": "backup_created", "actor_user_id": session.principal.user_id, "at": time.time()})
        return {**view(), "made": made["name"]}

    @router.get("/admin/backups/{name}/download")
    def download(name: Annotated[str, Field(pattern=NAME_PATTERN)], session: Session = Depends(admin_dep)):
        throttle(session.principal.user_id)
        try:
            path = mgr.path_of(name)
        except BackupError as err:
            raise _fail(err) from None
        vault.audit({"event": "backup_downloaded", "actor_user_id": session.principal.user_id, "at": time.time()})
        return FileResponse(path, media_type="application/octet-stream", filename=name,
                            headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})

    @router.delete("/admin/backups/{name}")
    def remove(name: Annotated[str, Field(pattern=NAME_PATTERN)], response: Response, session: Session = Depends(admin_dep)):
        response.headers["Cache-Control"] = "no-store"
        throttle(session.principal.user_id)
        try:
            mgr.delete(name)
        except BackupError as err:
            raise _fail(err) from None
        vault.audit({"event": "backup_deleted", "actor_user_id": session.principal.user_id, "at": time.time()})
        return view()

    @router.post("/admin/backups/{name}/restore")
    def restore(name: Annotated[str, Field(pattern=NAME_PATTERN)], body: RestoreBody, response: Response, session: Session = Depends(admin_dep)):
        response.headers["Cache-Control"] = "no-store"
        uid = session.principal.user_id
        throttle(uid)
        pw_limit.acquire("restore:" + uid)
        user = users.get(uid)
        if not user.get("password"):
            raise HTTPException(status_code=409, detail="Set a password in Settings first. Restoring asks for it again.")
        if not passwords.verify_password(body.password.get_secret_value(), user["password"]):
            vault.audit({"event": "restore_refused", "actor_user_id": uid, "at": time.time()})
            raise HTTPException(status_code=401, detail="Your password is not correct")
        if body.confirm.strip() != CONFIRM_WORD:
            raise HTTPException(status_code=400, detail=f"Type {CONFIRM_WORD} to confirm")
        try:
            result = mgr.restore(name, uid)
        except BackupError as err:
            raise _fail(err) from None
        vault.audit({"event": "vault_restored", "actor_user_id": uid, "at": time.time()})
        sessions.revoke_all()                      # what people were signed in as may no longer be the same
        return {"restored": True, "safety_copy": result["safety_copy"], "counts": result["counts"]}

    @router.get("/me/export")
    def export(session: Session = Depends(full_dep)):
        uid = session.principal.user_id
        if not export_limit.allow(f"exp:{uid}"):
            raise HTTPException(status_code=429, detail="You just did this. Wait a few minutes and try again.")
        data = ctx.exporter(uid)
        vault.audit({"event": "data_exported", "actor_user_id": uid, "at": time.time()})
        stamp = time.strftime("%Y-%m-%d", time.localtime())
        body = json.dumps(data, indent=2, ensure_ascii=False, default=str)
        return Response(content=body, media_type="application/json",
                        headers={"Content-Disposition": f'attachment; filename="enveliq-my-data-{stamp}.json"', "Cache-Control": "no-store",
                                 "X-Content-Type-Options": "nosniff"})

    return router
