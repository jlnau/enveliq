"""Administration: choose the check address and who may use it (Forward to check). Administrators only."""
from __future__ import annotations

import time
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import Field

from ..models import StrictModel
from ..security import Session
from .checkbox import clean_allowed
from .limits import SlidingWindowLimiter
from .service import MAIL_METHODS


class CheckBody(StrictModel):
    account_id: Annotated[str, Field(pattern=r"^[0-9a-fA-F-]{32,40}$")] | None = None
    allowed: list[str] = Field(default_factory=list, max_length=60)


def _exists(vault: Any, account_id: str) -> bool:
    try:
        vault.get_account(account_id)
        return True
    except KeyError:
        return False


def build_check_router(ctx: Any) -> APIRouter:
    router = APIRouter(prefix="/api/v1")
    box, vault = ctx.checkbox, ctx.vault
    admin_dep = ctx.admin_session
    limit = SlidingWindowLimiter(max_events=30, window=60)

    def mine(user: str) -> list[dict[str, Any]]:
        """The administrator's own mailboxes that can send. Nobody else's mailbox can be chosen."""
        return [{"id": a["id"], "name": a.get("display_name") or a.get("email_address") or "Mailbox", "email": a.get("email_address") or ""}
                for a in vault.list_accounts() if a.get("owner_user_id") == user and a.get("auth_method") in MAIL_METHODS]

    def view(user: str) -> dict[str, Any]:
        cfg = box.config()
        choices = mine(user)
        chosen = cfg["account_id"] if any(c["id"] == cfg["account_id"] for c in choices) else None
        return {"account_id": chosen, "set_elsewhere": bool(cfg["account_id"]) and chosen is None, "allowed": cfg["allowed"], "accounts": choices,
                "last": box.last or None, "automatic_sync_on": bool(ctx.auto_sync.enabled)}

    @router.get("/admin/check-address")
    def get(response: Response, session: Session = Depends(admin_dep)):
        response.headers["Cache-Control"] = "no-store"
        return view(session.principal.user_id)

    @router.put("/admin/check-address")
    def put(body: CheckBody, response: Response, session: Session = Depends(admin_dep)):
        user = session.principal.user_id
        response.headers["Cache-Control"] = "no-store"
        if not limit.allow(f"chk:{user}"):
            raise HTTPException(status_code=429, detail="Too many changes. Wait a minute.")
        try:
            allowed = clean_allowed(body.allowed)
        except ValueError as err:
            raise HTTPException(status_code=422, detail=str(err)) from None
        current = box.config()["account_id"]
        ids = {c["id"] for c in mine(user)}
        if current and current not in ids and _exists(vault, current):
            raise HTTPException(status_code=403, detail="Another administrator chose the check address. Only they can change it.")
        if body.account_id is not None and body.account_id not in ids:
            raise HTTPException(status_code=404, detail="Mailbox not found")          # also what someone else's mailbox answers
        box.save(body.account_id, allowed)
        vault.audit({"event": "check_address_saved", "actor_user_id": user, "on": body.account_id is not None, "people": len(allowed), "at": time.time()})
        return view(user)

    return router
