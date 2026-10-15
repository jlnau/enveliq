"""Reminder channels: setting them up, testing them, and the administrator's rules."""
from __future__ import annotations

from typing import Annotated, Any
from threading import RLock

from fastapi import APIRouter, Depends, HTTPException, Path as PathParam
from pydantic import Field, field_validator

from ..models import StrictModel
from ..security import Session
from .limits import SlidingWindowLimiter
from . import extra_channels
from .notify import CHANNELS, Notifier
from .outbound import OutboundError

ChannelId = Annotated[str, PathParam(pattern=r"^[a-z_]{2,20}$")]


class ChannelBody(StrictModel):
    enabled: bool = True
    values: dict[str, str] = Field(default_factory=dict, max_length=12)

    @field_validator("values")
    @classmethod
    def short(cls, v: dict[str, str]) -> dict[str, str]:
        for k, x in v.items():
            if len(k) > 40 or len(x) > 700:
                raise ValueError("value too long")
        return v


class SettingsBody(StrictModel):
    morning_on: bool | None = None
    morning_time: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    due_on: bool | None = None
    repeat_hours: int | None = Field(default=None, ge=1, le=12)
    repeat_max: int | None = Field(default=None, ge=0, le=5)
    quiet_on: bool | None = None
    quiet_from: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    quiet_to: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    show_titles: bool | None = None
    mail_on: bool | None = None
    mail_details: bool | None = None


class OpenedMessageBody(StrictModel):
    account_id: str = Field(min_length=1, max_length=128)
    message_id: str = Field(min_length=1, max_length=512)


class MailViewBody(StrictModel):
    layout: str = Field(pattern=r"^(list|right|bottom|screen|deck)$")
    density: str = Field(pattern=r"^(compact|standard|roomy)$")
    width: str = Field(pattern=r"^(centered|full)$")
    rows: str = Field(pattern=r"^(collapsed|open)$")
    peek: bool


class MailContextBody(StrictModel):
    account_id: str | None = Field(default=None, max_length=128)
    message_id: str | None = Field(default=None, max_length=512)


class DeviceBody(StrictModel):
    endpoint: str = Field(max_length=800)
    p256dh: str = Field(max_length=200)
    auth: str = Field(max_length=100)
    label: str = Field(default="", max_length=80)


class AdminBody(StrictModel):
    channels: dict[str, bool] | None = Field(default=None, max_length=30)
    local_hosts: list[str] | None = Field(default=None, max_length=50)


def build_notify_router(ctx: Any) -> APIRouter:
    router = APIRouter(prefix="/api/v1")
    notifier: Notifier = ctx.notifier
    session_dep, admin_dep = ctx.full_session, ctx.admin_session
    save_limit = SlidingWindowLimiter(max_events=60, window=60)
    test_limit = SlidingWindowLimiter(max_events=10, window=60)
    click_url = ctx.click_url

    opened_lock = RLock()
    opened_prefix = "enveliq-opened-v1:"

    @router.get("/me/mail-opened")
    def get_mail_opened(session: Session = Depends(session_dep)):
        with opened_lock:
            rec = ctx.vault.get_global(opened_prefix + session.principal.user_id) or {}
        return {"keys": rec.get("keys", []) if isinstance(rec.get("keys"), list) else []}

    @router.post("/me/mail-opened")
    def record_mail_opened(body: OpenedMessageBody, session: Session = Depends(session_dep)):
        user = session.principal.user_id
        account = ctx.vault.get_account(body.account_id)
        if not account or account.get("owner_user_id") != user:
            raise HTTPException(status_code=404, detail="Email not found")
        try:
            message = ctx.vault.get_message(body.account_id, body.message_id)
        except (KeyError, ValueError):
            message = None
        if not message:
            raise HTTPException(status_code=404, detail="Email not found")
        key = body.account_id + ":" + body.message_id
        with opened_lock:
            rec = ctx.vault.get_global(opened_prefix + user) or {}
            keys = rec.get("keys", [])
            keys = keys if isinstance(keys, list) else []
            if key not in keys:
                keys.append(key)
                ctx.vault.set_global(opened_prefix + user, {"keys": keys[-20000:]})
        return {"ok": True}

    # User-owned, encrypted vault preference: survives container restarts and browser changes.
    @router.get("/me/mail-view")
    def get_mail_view(session: Session = Depends(session_dep)):
        saved = ctx.vault.get_global("mail-view-v1:" + session.principal.user_id)
        return {"view": saved if isinstance(saved, dict) and saved else None}

    @router.put("/me/mail-view")
    def put_mail_view(body: MailViewBody, session: Session = Depends(session_dep)):
        view = body.model_dump()
        ctx.vault.set_global("mail-view-v1:" + session.principal.user_id, view)
        return {"view": view}

    @router.get("/me/mail-context")
    def get_mail_context(session: Session = Depends(session_dep)):
        saved = ctx.vault.get_global("mail-context-v1:" + session.principal.user_id)
        return {"selection": saved if isinstance(saved, dict) and saved else None}

    @router.put("/me/mail-context")
    def put_mail_context(body: MailContextBody, session: Session = Depends(session_dep)):
        selection = None
        if body.account_id is not None or body.message_id is not None:
            if not body.account_id or not body.message_id:
                raise HTTPException(status_code=422, detail="Both message identifiers are required")
            account = ctx.vault.get_account(body.account_id)
            if not account or account.get("owner_user_id") != session.principal.user_id:
                raise HTTPException(status_code=404, detail="Email not found")
            try:
                message = ctx.vault.get_message(body.account_id, body.message_id)
            except (KeyError, ValueError):
                message = None
            if not message:
                raise HTTPException(status_code=404, detail="Email not found")
            selection = {"account_id": body.account_id, "message_id": body.message_id}
        ctx.vault.set_global("mail-context-v1:" + session.principal.user_id, selection or {})
        return {"selection": selection}

    @router.get("/me/notifications")
    def overview(session: Session = Depends(session_dep)):
        out = notifier.overview(session.principal.user_id)
        out["tz"] = ctx.tasks.timezone_of(session.principal.user_id)
        return out

    @router.put("/me/notifications/channels/{cid}")
    def save_channel(cid: ChannelId, body: ChannelBody, session: Session = Depends(session_dep)):
        user = session.principal.user_id
        if cid not in CHANNELS:
            raise HTTPException(status_code=404, detail="Unknown channel.")
        if not save_limit.allow(f"n:{user}"):
            raise HTTPException(status_code=429, detail="Too many changes. Wait a minute.")
        if not notifier.admin()["channels"].get(cid, True):
            raise HTTPException(status_code=403, detail="Your administrator has switched this channel off.")
        try:
            notifier.save_channel(user, cid, body.enabled, body.values)
        except ValueError as err:
            raise HTTPException(status_code=422, detail=str(err)) from None
        return notifier.overview(user)

    @router.delete("/me/notifications/channels/{cid}")
    def clear_channel(cid: ChannelId, session: Session = Depends(session_dep)):
        if cid not in CHANNELS:
            raise HTTPException(status_code=404, detail="Unknown channel.")
        notifier.clear_channel(session.principal.user_id, cid)
        return notifier.overview(session.principal.user_id)

    @router.post("/me/notifications/channels/{cid}/test")
    def test_channel(cid: ChannelId, session: Session = Depends(session_dep)):
        user = session.principal.user_id
        if cid not in CHANNELS:
            raise HTTPException(status_code=404, detail="Unknown channel.")
        if not test_limit.allow(f"t:{user}"):
            raise HTTPException(status_code=429, detail="Too many tests. Wait a minute.")
        try:
            notifier.send_one(user, cid, {"title": "Enveliq test", "body": "This is how a reminder will look. You can ignore it.", "url": click_url or None}, force=True)
        except OutboundError as err:
            raise HTTPException(status_code=502, detail=err.message) from None
        return {"ok": True}

    @router.put("/me/notifications/settings")
    def save_settings(body: SettingsBody, session: Session = Depends(session_dep)):
        user = session.principal.user_id
        if not save_limit.allow(f"n:{user}"):
            raise HTTPException(status_code=429, detail="Too many changes. Wait a minute.")
        notifier.save_settings(user, body.model_dump(exclude_none=True))
        return notifier.overview(user)

    @router.get("/me/notifications/browser/key")
    def browser_key(session: Session = Depends(session_dep)):
        return {"public_key": extra_channels.public_key_text(extra_channels.vapid_key(ctx.vault))}

    @router.post("/me/notifications/browser")
    def browser_add(body: DeviceBody, session: Session = Depends(session_dep)):
        user = session.principal.user_id
        if not save_limit.allow(f"n:{user}"):
            raise HTTPException(status_code=429, detail="Too many changes. Wait a minute.")
        if not notifier.admin()["channels"].get("browser", True):
            raise HTTPException(status_code=403, detail="Your administrator has switched this channel off.")
        try:
            extra_channels.add_device(notifier, user, body.endpoint, body.p256dh, body.auth, body.label)
        except ValueError as err:
            raise HTTPException(status_code=422, detail=str(err)) from None
        return notifier.overview(user)

    @router.post("/me/notifications/browser/{device_id}/test")
    def browser_device_test(device_id: Annotated[str, PathParam(pattern=r"^[0-9a-f]{12}$")], session: Session = Depends(session_dep)):
        user = session.principal.user_id
        if not test_limit.allow(f"t:{user}"):
            raise HTTPException(status_code=429, detail="Too many tests. Wait a minute.")
        if not notifier.admin()["channels"].get("browser", True):
            raise HTTPException(status_code=403, detail="Browser notifications have been disabled.")
        try:
            extra_channels.test_browser_device(notifier, user, device_id, click_url)
        except OutboundError as err:
            raise HTTPException(status_code=502 if err.code != "not_found" else 404, detail=err.message) from None
        return {"ok": True}

    @router.delete("/me/notifications/browser/{device_id}")
    def browser_remove(device_id: Annotated[str, PathParam(pattern=r"^[0-9a-f]{12}$")], session: Session = Depends(session_dep)):
        extra_channels.remove_device(notifier, session.principal.user_id, device_id)
        return notifier.overview(session.principal.user_id)

    @router.get("/admin/notifications")
    def admin_get(session: Session = Depends(admin_dep)):
        return {**notifier.admin(), "labels": {c: s["label"] for c, s in CHANNELS.items()}, "local_channels": [c for c, s in CHANNELS.items() if s.get("local_ok")]}

    @router.put("/admin/notifications")
    def admin_put(body: AdminBody, session: Session = Depends(admin_dep)):
        try:
            notifier.save_admin(body.channels, body.local_hosts)
        except ValueError as err:
            raise HTTPException(status_code=422, detail=str(err)) from None
        return admin_get(session)

    return router
