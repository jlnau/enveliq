"""Reminder channels: setting them up, testing them, and the administrator's rules."""
from __future__ import annotations

from typing import Annotated, Any, Literal
import asyncio
import hashlib
import json
import time

from fastapi import Request
from fastapi.responses import StreamingResponse
from threading import RLock

from fastapi import APIRouter, Depends, HTTPException, Path as PathParam
from pydantic import Field, field_validator

from ..models import StrictModel
from ..security import Session
from .limits import SlidingWindowLimiter
from . import extra_channels, fcm
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
    digest_mail: bool | None = None
    digest_inbox: bool | None = None
    mail_filter: Literal["all", "important", "action"] | None = None
    mail_muted_accounts: list[str] | None = Field(default=None, max_length=100)


class OpenedMessageBody(StrictModel):
    account_id: str = Field(min_length=1, max_length=128)
    message_id: str = Field(min_length=1, max_length=512)


class MailViewBody(StrictModel):
    layout: str = Field(pattern=r"^(list|right|bottom|screen|deck)$")
    density: str = Field(pattern=r"^(compact|standard|roomy)$")
    width: str = Field(pattern=r"^(centered|full)$")
    rows: str = Field(pattern=r"^(collapsed|open)$")
    peek: bool
    action_feedback: bool = True
    show_original: bool = False
    conversations: bool = False
    style: str = Field(default="classic", pattern=r"^(classic|rail)$")


class MailContextBody(StrictModel):
    account_id: str | None = Field(default=None, max_length=128)
    message_id: str | None = Field(default=None, max_length=512)


class DeviceBody(StrictModel):
    endpoint: str = Field(max_length=800)
    p256dh: str = Field(max_length=200)
    auth: str = Field(max_length=100)
    label: str = Field(default="", max_length=80)


class AndroidDeviceBody(StrictModel):
    token: str = Field(min_length=20, max_length=400)
    label: str = Field(default="", max_length=60)
    alerts: bool = False                       # true: the person switched on "Tell me when new email arrives" in the app
    replaces: str | None = Field(default=None, pattern=r"^[0-9a-f]{12}$")


class AdminBody(StrictModel):
    channels: dict[str, bool] | None = Field(default=None, max_length=30)
    local_hosts: list[str] | None = Field(default=None, max_length=50)


def ready_mail(vault: Any, user_id: str) -> set[tuple[str, str]]:
    """The (account, message) pairs of this person's unread emails that are ready to be told about: stored, not from All Mail,
    and not still waiting for the AI summary. Only ids are returned, never any text."""
    ready: set[tuple[str, str]] = set()
    for account in vault.list_accounts():
        if account.get("owner_user_id") != user_id:
            continue
        try:
            for m in vault.list_messages(account["id"]):
                if m.get("state", "unread") == "unread" and not m.get("from_all_mail") and not m.get("ai_pending"):
                    ready.add((str(account["id"]), str(m.get("id", ""))))
        except (KeyError, ValueError):
            continue
    return ready


def mail_changes(before: set[tuple[str, str]], now: set[tuple[str, str]]) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    """What changed between two looks at the ready emails: (new ones, ones that are no longer waiting). Only ids."""
    return sorted(now - before), sorted(before - now)


def other_counts(ctx: Any, user_id: str) -> dict[str, int]:
    """How many things of each other kind are waiting for this person. Only numbers, never any text."""
    out: dict[str, int] = {}
    try:
        if ctx.messages.enabled(user_id):
            out["messages"] = int(ctx.messages.summary(user_id).get("unread") or 0)
    except Exception:
        pass
    try:
        out["bell"] = int(ctx.inbound.unread(user_id))
    except Exception:
        pass
    try:
        out["tasks"] = sum(1 for t in ctx.tasks.view(user_id)["tasks"] if t["state"] == "open" and t["days"] <= 0)
    except Exception:
        pass
    try:
        out["shipping"] = sum(1 for o in ctx.shipping.view(user_id).get("orders", []) if o.get("needs_confirm"))
    except Exception:
        pass
    try:
        out["summary"] = int(ctx.notifier.get_state(user_id).get("summary_seq") or 0)       # goes up by one each time the daily summary goes out
    except Exception:
        pass
    return out


def digest_filter(ctx: Any, user_id: str, fresh: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """When the person chose "new email in the daily summary instead", the phone is not told about each new email, except from important people."""
    try:
        st = ctx.notifier.settings(user_id)
        if not ((st.get("digest_mail") and st.get("morning_on", True)) or st.get("digest_inbox")):
            return fresh
        keep: list[tuple[str, str]] = []
        for account_id, message_id in fresh:
            try:
                message = ctx.vault.get_message(account_id, message_id)
            except Exception:
                continue
            if ctx.important.contains(user_id, message.get("sender_address")) or message.get("act_today") is True:      # urgent mail still comes at once
                keep.append((account_id, message_id))
        return keep
    except Exception:
        return fresh


def grown(before: dict[str, int], latest: dict[str, int]) -> list[str]:
    """The kinds that have more waiting than before. A kind that went down (the person dealt with it) is not news."""
    return sorted(k for k, n in latest.items() if n > before.get(k, 0))


def build_notify_router(ctx: Any) -> APIRouter:
    router = APIRouter(prefix="/api/v1")
    notifier: Notifier = ctx.notifier
    session_dep, admin_dep = ctx.full_session, ctx.admin_session
    save_limit = SlidingWindowLimiter(max_events=60, window=60)
    test_limit = SlidingWindowLimiter(max_events=10, window=60)
    click_url = ctx.click_url

    opened_lock = RLock()
    # Share recent fingerprints among the same person's browser connections.
    fingerprint_lock = RLock()
    fingerprint_cache: dict[str, tuple[float, str]] = {}

    opened_prefix = "enveliq-opened-v1:"

    def mail_fingerprint(user_id: str) -> str:
        """Hash metadata only, never expose message content in the event stream."""
        rows = []
        for account in ctx.vault.list_accounts():
            if account.get("owner_user_id") != user_id:
                continue
            aid = account["id"]
            try:
                for m in ctx.vault.list_messages(aid):
                    rows.append((aid, str(m.get("id", "")), str(m.get("state", "")),
                                 str(m.get("folder", "")), str(m.get("mailbox", "")),
                                 str(m.get("snoozed_until", "")), str(m.get("replied_at", "")), str(m.get("held_for_summary", "")),
                                 tuple(sorted(str(t) for t in (m.get("tags") or []))),
                                 str(m.get("summary", "")), str(m.get("ai_pending", ""))))
            except (KeyError, ValueError):
                continue
        rows.sort(key=lambda row: (row[0], row[1]))
        opened = ctx.vault.get_global("enveliq-opened-v1:" + user_id) or {}
        keys = opened.get("keys", []) if isinstance(opened, dict) else []
        rows.append(("opened", tuple(sorted(str(k) for k in keys))))
        return hashlib.sha256(json.dumps(rows, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()

    def cached_mail_fingerprint(user_id: str) -> str:
        # Avoid walking the entire mailbox once per open browser connection.
        import time
        with fingerprint_lock:
            now = time.monotonic()
            cached = fingerprint_cache.get(user_id)
            if cached and now - cached[0] < 3:
                return cached[1]
            value = mail_fingerprint(user_id)
            fingerprint_cache[user_id] = (now, value)
            # Remove expired entries if the cache grows beyond its normal size.
            if len(fingerprint_cache) > 256:
                for uid, (stamp, _) in list(fingerprint_cache.items()):
                    if now - stamp > 60:
                        fingerprint_cache.pop(uid, None)
            return value

    @router.get("/me/mail-events")
    async def mail_events(request: Request, session: Session = Depends(session_dep)):
        """Same-origin one-way change hints; EventSource automatically reconnects."""
        user_id = session.principal.user_id

        async def stream():
            last = await asyncio.to_thread(cached_mail_fingerprint, user_id)
            yield "retry: 3000\nevent: ready\ndata: {}\n\n"
            ticks = 0
            while not await request.is_disconnected():
                await asyncio.sleep(4)
                if await request.is_disconnected():
                    return
                try:
                    fingerprint = await asyncio.to_thread(cached_mail_fingerprint, user_id)
                except Exception:
                    yield "event: reconnect\ndata: {}\n\n"
                    return
                if fingerprint != last:
                    last = fingerprint
                    yield "event: changed\ndata: {}\n\n"
                ticks += 1
                if ticks % 5 == 0:
                    yield ": heartbeat\n\n"

        return StreamingResponse(stream(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no",
                                          "Content-Security-Policy": "default-src 'none'"})


    ready_cache: dict[str, tuple[float, set[tuple[str, str]]]] = {}

    def cached_ready(user_id: str) -> set[tuple[str, str]]:
        import time
        with fingerprint_lock:
            now = time.monotonic()
            hit = ready_cache.get(user_id)
            if hit and now - hit[0] < 4:
                return hit[1]
            value = ready_mail(ctx.vault, user_id)
            ready_cache[user_id] = (now, value)
            if len(ready_cache) > 256:
                for uid, (stamp, _) in list(ready_cache.items()):
                    if now - stamp > 60:
                        ready_cache.pop(uid, None)
            return value

    @router.get("/me/new-mail-events")
    async def new_mail_events(request: Request, session: Session = Depends(session_dep)):
        """For the Android app: one quiet stream that only says "these emails are ready" (their AI summary is done).
        It carries ids, never text. A short heartbeat every minute keeps the connection alive without waking the phone often."""
        user_id = session.principal.user_id

        async def stream():
            seen = set(await asyncio.to_thread(cached_ready, user_id))
            counts = await asyncio.to_thread(other_counts, ctx, user_id)
            yield "retry: 30000\nevent: ready\ndata: {}\n\n"
            ticks = 0
            rounds = 0
            while not await request.is_disconnected():
                await asyncio.sleep(5)
                try:
                    now = await asyncio.to_thread(cached_ready, user_id)
                except Exception:
                    yield "event: reconnect\ndata: {}\n\n"
                    return
                rounds += 1
                if rounds % 6 == 0:                       # every half minute: did more messages, notes, tasks or parcels start waiting?
                    latest = await asyncio.to_thread(other_counts, ctx, user_id)
                    grew = grown(counts, latest)
                    counts = latest
                    if grew:
                        yield "event: other\ndata: " + json.dumps({"kinds": grew}, separators=(",", ":")) + "\n\n"
                        ticks = 0
                fresh, gone = mail_changes(seen, now)
                seen = set(now)
                if fresh:
                    fresh = await asyncio.to_thread(digest_filter, ctx, user_id, fresh)
                if gone:                              # reviewed, archived or moved somewhere else: the phone takes its alert down at once
                    ids = [{"a": a, "m": m} for a, m in gone[:50]]
                    yield "event: gone\ndata: " + json.dumps({"ids": ids}, separators=(",", ":")) + "\n\n"
                    ticks = 0
                if fresh:
                    ids = [{"a": a, "m": m} for a, m in fresh[:50]]
                    yield "event: new\ndata: " + json.dumps({"count": len(fresh), "ids": ids}, separators=(",", ":")) + "\n\n"
                    ticks = 0
                else:
                    ticks += 1
                    if ticks >= 12:                       # a minute of quiet: one tiny line, so the connection is not dropped
                        ticks = 0
                        yield ": heartbeat\n\n"

        return StreamingResponse(stream(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no",
                                          "Content-Security-Policy": "default-src 'none'"})

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
        # Preserve optional preferences when older clients submit their legacy view.
        key = "mail-view-v1:" + session.principal.user_id
        previous = ctx.vault.get_global(key)
        view = {**(previous if isinstance(previous, dict) else {}), **body.model_dump(exclude_unset=True)}
        ctx.vault.set_global(key, view)
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
            try:
                account = ctx.vault.get_account(body.account_id)
            except (KeyError, ValueError):
                account = None
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

    @router.get("/me/summary")
    def daily_summary(session: Session = Depends(session_dep)):
        """The numbers behind the daily summary, for the Android app's note. Counts only: no sender, subject or title."""
        user = session.principal.user_id
        st = notifier.settings(user)
        counts = ctx.summary.counts(user, with_unread=bool(st.get("digest_mail")))
        tasks = sum(1 for t in ctx.tasks.view(user)["tasks"] if t["state"] == "open" and t["days"] <= 0)
        return {"tasks": tasks, "waiting": counts["waiting"], "parcels": counts["parcels"], "coming": counts["coming"], "unread": counts["unread"],
                "digest": bool(st.get("digest_mail") and st.get("morning_on", True))}

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
        changed = body.model_dump(exclude_none=True)
        if "mail_muted_accounts" in changed:
            allowed = {a["id"] for a in ctx.vault.list_accounts() if a.get("owner_user_id") == user}
            if any(not isinstance(aid, str) or aid not in allowed for aid in changed["mail_muted_accounts"]):
                raise HTTPException(status_code=404, detail="Mailbox not found")
        notifier.save_settings(user, changed)
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

    # ---- the Enveliq Android app, through Google's push service ----

    @router.get("/me/notifications/android")
    def android_status(session: Session = Depends(session_dep)):
        """Lets the app know whether Google push can be offered. Says nothing about the key itself."""
        return {"available": bool(fcm.relay_url()) and bool(notifier.admin()["channels"].get("android", True))}

    @router.post("/me/notifications/android")
    def android_add(body: AndroidDeviceBody, session: Session = Depends(session_dep)):
        user = session.principal.user_id
        if not save_limit.allow(f"n:{user}"):
            raise HTTPException(status_code=429, detail="Too many changes. Wait a minute.")
        if not notifier.admin()["channels"].get("android", True):
            raise HTTPException(status_code=403, detail="Your administrator has switched this channel off.")
        try:
            device_id = extra_channels.add_android_device(notifier, user, body.token, body.label, body.replaces)
        except ValueError as err:
            raise HTTPException(status_code=422, detail=str(err)) from None
        if body.alerts:
            notifier.save_settings(user, {"mail_on": True})     # the switch in the app is the same "New email alerts" switch as on the website
        return {"id": device_id}

    @router.post("/me/notifications/android/{device_id}/test")
    def android_test(device_id: Annotated[str, PathParam(pattern=r"^[0-9a-f]{12}$")], session: Session = Depends(session_dep)):
        user = session.principal.user_id
        if not test_limit.allow(f"t:{user}"):
            raise HTTPException(status_code=429, detail="Too many tests. Wait a minute.")
        if not notifier.admin()["channels"].get("android", True):
            raise HTTPException(status_code=403, detail="Your administrator has switched this channel off.")
        try:
            extra_channels.test_android_device(notifier, user, device_id)
        except OutboundError as err:
            raise HTTPException(status_code=502 if err.code != "not_found" else 404, detail=err.message) from None
        return {"ok": True}

    @router.delete("/me/notifications/android/{device_id}")
    def android_remove(device_id: Annotated[str, PathParam(pattern=r"^[0-9a-f]{12}$")], session: Session = Depends(session_dep)):
        extra_channels.remove_android_device(notifier, session.principal.user_id, device_id)
        return {"ok": True}

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
