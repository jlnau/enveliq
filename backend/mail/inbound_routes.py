"""The WebSocket door for other services, and the bell: a person's key, their notifications and what they can do with them."""
from __future__ import annotations

import asyncio
import json
import time
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, WebSocket
from fastapi import Path as PathParam
from starlette.concurrency import run_in_threadpool

from ..crypto_vault import VaultLocked
from ..security import Session
from . import inbound as I
from .limits import SlidingWindowLimiter

WS_PATH = "/api/v1/inbound/ws"
WEBHOOK_PATH = "/api/v1/inbound/webhook"      # the same door for services that can only send a plain POST
AUTH_WAIT = 10          # seconds a new connection has to show its key
IDLE_WAIT = 120         # seconds of silence before the door closes (a service keeps it open with "ping")

NoteId = Annotated[str, PathParam(pattern=r"^n[0-9a-f]{16}$")]


def build_inbound_router(ctx: Any) -> APIRouter:
    router = APIRouter()
    book: I.InboundBook = ctx.inbound
    session_dep = ctx.full_session
    page_limit = SlidingWindowLimiter(max_events=240, window=60)
    key_limit = SlidingWindowLimiter(max_events=10, window=60)
    tries = SlidingWindowLimiter(max_events=20, window=60)                     # connection attempts per network address
    hook_tries = SlidingWindowLimiter(max_events=120, window=60)               # POSTs per network address (a busy service sends many)
    per_key = SlidingWindowLimiter(max_events=I.MAX_PER_MINUTE, window=60)
    open_doors: dict[str, int] = {}

    def person(session: Session) -> str:
        user = session.principal.user_id
        if not page_limit.allow(f"inbound:{user}"):
            raise HTTPException(status_code=429, detail="Too many requests. Wait a minute.")
        return user

    # ---- the bell (signed-in person) ----
    @router.get("/api/v1/me/bell")
    def mine(response: Response, session: Session = Depends(session_dep)):
        user = person(session)
        response.headers["Cache-Control"] = "no-store"
        return {**book.view(user), "ws_path": WS_PATH, "webhook_path": WEBHOOK_PATH}

    @router.post("/api/v1/me/bell/read", status_code=204)
    def read_all(session: Session = Depends(session_dep)):
        book.mark_read(person(session))

    @router.post("/api/v1/me/bell/key")
    def make_key(response: Response, session: Session = Depends(session_dep)):
        user = person(session)
        if not key_limit.allow(f"inbound-key:{user}"):
            raise HTTPException(status_code=429, detail="Too many requests. Wait a minute.")
        response.headers["Cache-Control"] = "no-store"
        key = book.make_key(user)
        ctx.vault.audit({"event": "inbound_key_made", "actor_user_id": user, "at": time.time()})       # never the key
        return {"key": key, "ws_path": WS_PATH}

    @router.delete("/api/v1/me/bell/key", status_code=204)
    def remove_key(session: Session = Depends(session_dep)):
        user = person(session)
        book.revoke_key(user)
        ctx.vault.audit({"event": "inbound_key_removed", "actor_user_id": user, "at": time.time()})

    @router.delete("/api/v1/me/bell/{note_id}", status_code=204)
    def dismiss(note_id: NoteId, session: Session = Depends(session_dep)):
        if not book.dismiss(person(session), note_id):
            raise HTTPException(status_code=404, detail="Not found")

    @router.delete("/api/v1/me/bell", status_code=204)
    def clear(session: Session = Depends(session_dep)):
        book.clear(person(session))

    # ---- the door for other services ----
    async def say(ws: WebSocket, payload: dict[str, Any]) -> None:
        await ws.send_text(json.dumps(payload))

    async def refuse(ws: WebSocket, payload: dict[str, Any], code: int) -> None:
        try:
            await say(ws, payload)
            await ws.close(code=code)
        except Exception:
            pass

    def who(token: Any) -> str | None:
        """The person this key belongs to, if they are still allowed in."""
        user = book.user_for(token) if isinstance(token, str) else None
        if not user:
            return None
        try:
            record = ctx.vault.get_user(user)
        except KeyError:
            return None
        return None if record.get("disabled") else user

    @router.post(WEBHOOK_PATH)
    async def webhook(request: Request):
        """A service that cannot hold a WebSocket open sends one note as a POST. Same key, same limits, same bell."""
        peer = request.client.host if request.client else "?"
        if not hook_tries.allow(f"hook:{peer}"):
            raise HTTPException(status_code=429, detail="Too many tries. Wait a minute.")
        header = request.headers.get("authorization", "")
        token = header[7:].strip() if header.lower().startswith("bearer ") else None
        try:
            user = await run_in_threadpool(who, token)
        except VaultLocked:
            raise HTTPException(status_code=503, detail="Enveliq is locked. Unlock it, then try again.")
        if not user:
            raise HTTPException(status_code=401, detail="That key is not accepted.", headers={"WWW-Authenticate": "Bearer"})
        if not per_key.allow(f"ws-key:{user}"):
            raise HTTPException(status_code=429, detail=f"Slow down. At most {I.MAX_PER_MINUTE} notes a minute.")
        raw = await request.body()
        if len(raw) > I.MAX_FRAME:
            raise HTTPException(status_code=413, detail="That message is too big.")
        try:
            msg = json.loads(raw)
        except ValueError:
            msg = None
        if not isinstance(msg, dict):
            raise HTTPException(status_code=400, detail='Send JSON such as {"title": "Washer finished", "message": "Empty it"}.')
        try:
            await run_in_threadpool(book.add, user, msg.get("title"), msg.get("message"), msg.get("source"))
        except I.InboundError as err:
            raise HTTPException(status_code=400, detail=str(err))
        except VaultLocked:
            raise HTTPException(status_code=503, detail="Enveliq is locked. Unlock it, then try again.")
        return Response(content='{"ok":true}', media_type="application/json", headers={"Cache-Control": "no-store"})

    @router.websocket(WS_PATH)
    async def door(ws: WebSocket):
        origin = ws.headers.get("origin")
        if origin and origin not in ctx.allowed_origins:           # a web page on another site has no business here
            await ws.close(code=1008)
            return
        peer = ws.client.host if ws.client else "?"
        await ws.accept()
        if not tries.allow(f"ws:{peer}"):
            await refuse(ws, {"type": "error", "message": "Too many tries. Wait a minute."}, 1008)
            return
        try:
            header = ws.headers.get("authorization", "")
            token: Any = header[7:].strip() if header.lower().startswith("bearer ") else None
            if token is None:
                first = await asyncio.wait_for(ws.receive_text(), AUTH_WAIT)
                msg = json.loads(first) if len(first) <= I.MAX_FRAME else None
                token = msg.get("token") if isinstance(msg, dict) and msg.get("type") == "auth" else None
            user = await run_in_threadpool(who, token)
        except VaultLocked:
            await refuse(ws, {"type": "error", "message": "Enveliq is locked. Unlock it, then connect again."}, 1013)
            return
        except Exception:
            await refuse(ws, {"type": "auth_failed"}, 1008)
            return
        if not user:
            await refuse(ws, {"type": "auth_failed"}, 1008)
            return
        if open_doors.get(user, 0) >= I.MAX_CONNECTIONS:
            await refuse(ws, {"type": "error", "message": "Too many connections are open for this key."}, 1013)
            return
        open_doors[user] = open_doors.get(user, 0) + 1
        try:
            await say(ws, {"type": "auth_ok"})
            while True:
                try:
                    got = await asyncio.wait_for(ws.receive(), IDLE_WAIT)
                except asyncio.TimeoutError:
                    await ws.close(code=1001)
                    return
                if got.get("type") == "websocket.disconnect":
                    return
                raw = got.get("text")
                if raw is None:
                    await refuse(ws, {"type": "error", "message": "Send text, not binary data."}, 1003)
                    return
                if len(raw) > I.MAX_FRAME:
                    await refuse(ws, {"type": "error", "message": "That message is too big."}, 1009)
                    return
                try:
                    msg = json.loads(raw)
                except ValueError:
                    msg = None
                if not isinstance(msg, dict):
                    await say(ws, {"type": "error", "message": "Send JSON such as {\"type\": \"notify\", \"title\": \"...\"}."})
                    continue
                ref = msg.get("id") if isinstance(msg.get("id"), str) and len(msg["id"]) <= 64 else None
                kind = msg.get("type")
                if kind == "ping":
                    await say(ws, {"type": "pong"})
                elif kind == "notify":
                    if await run_in_threadpool(who, token) != user:             # the key was replaced or removed
                        await refuse(ws, {"type": "auth_failed"}, 1008)
                        return
                    if not per_key.allow(f"ws-key:{user}"):
                        await say(ws, {"type": "error", "id": ref, "message": "Slow down. At most "
                                       f"{I.MAX_PER_MINUTE} notes a minute."})
                        continue
                    try:
                        await run_in_threadpool(book.add, user, msg.get("title"), msg.get("message"), msg.get("source"))
                    except I.InboundError as err:
                        await say(ws, {"type": "error", "id": ref, "message": str(err)})
                        continue
                    except VaultLocked:
                        await refuse(ws, {"type": "error", "id": ref, "message": "Enveliq is locked."}, 1013)
                        return
                    await say(ws, {"type": "ok", "id": ref})
                else:
                    await say(ws, {"type": "error", "id": ref, "message": "Unknown type. Use notify or ping."})
        except Exception:
            # the other side went away, or sent something broken: close quietly
            try:
                await ws.close(code=1011)
            except Exception:
                pass
        finally:
            open_doors[user] = max(0, open_doors.get(user, 1) - 1)

    return router
