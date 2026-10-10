"""The Hermes chats: list them, open one, add to one, rename, delete. Every request needs a signed-in, unlocked session."""
from __future__ import annotations

import time
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Path as PathParam, Query, Response
from pydantic import Field

from ..models import StrictModel
from ..security import Session
from .agent import CHAT_ID, MAX_TEXT, TITLE_MAX, Agent, ChatError
from .limits import SlidingWindowLimiter
from .llm import BridgeError
from .routes import fail

ChatId = Annotated[str, PathParam(pattern=CHAT_ID.pattern)]


class MessageBody(StrictModel):
    text: str = Field(min_length=1, max_length=MAX_TEXT)
    chat: str | None = Field(default=None, pattern=CHAT_ID.pattern)


class SettingsBody(StrictModel):
    mode: str = Field(pattern=r"^(plain|own)$")
    who: str = Field(pattern=r"^(all|admins)$")
    name: str = Field(default="", max_length=40)
    url: str | None = Field(default=None, max_length=300)       # None: keep what is saved
    model: str | None = Field(default=None, max_length=80)
    key: str | None = Field(default=None, max_length=300)
    clear_key: bool = False


class RenameBody(StrictModel):
    title: str = Field(min_length=1, max_length=TITLE_MAX)


def build_agent_router(ctx: Any) -> APIRouter:
    router = APIRouter(prefix="/api/v1")
    agent: Agent = ctx.agent
    service, vault = ctx.mail, ctx.vault
    session_dep, admin_dep = ctx.full_session, ctx.admin_session
    limit = SlidingWindowLimiter(max_events=20, window=60)
    edit_limit = SlidingWindowLimiter(max_events=60, window=60)

    def ready() -> dict[str, Any]:
        service.refresh_ai(vault)
        conf = agent.settings()
        return {"name": conf["name"], "mode": conf["mode"], "ready": service.summariser.enabled or (conf["mode"] == "own" and agent.own_connection() is not None)}

    def allowed(session: Session) -> None:
        """The administrator can keep the chat to administrators; the server checks every request."""
        if agent.settings()["who"] == "admins" and not session.principal.is_admin:
            raise HTTPException(status_code=403, detail="Your administrator has kept this chat for administrators only.")

    def wrong(err: ChatError) -> HTTPException:
        return HTTPException(status_code=err.status, detail=str(err))

    @router.get("/me/agent")
    def get_chats(response: Response, chat: Annotated[str | None, Query(pattern=CHAT_ID.pattern)] = None, session: Session = Depends(session_dep)):
        response.headers["Cache-Control"] = "no-store"
        allowed(session)
        return {**ready(), **agent.view(session.principal.user_id, chat, latest=chat is None)}

    @router.post("/me/agent/messages")
    def post_message(body: MessageBody, response: Response, session: Session = Depends(session_dep)):
        user = session.principal.user_id
        response.headers["Cache-Control"] = "no-store"
        allowed(session)
        if not limit.allow(f"agent:{user}"):
            raise HTTPException(status_code=429, detail="Too many messages. Wait a minute.")
        state = ready()
        if not state["ready"]:
            raise HTTPException(status_code=409, detail={"code": "ai_not_configured", "message": "No AI model is set up yet. An administrator can add one under Administration, AI model."})
        try:
            return {**state, **agent.send(user, body.text, body.chat)}
        except ChatError as err:
            raise wrong(err) from None
        except BridgeError as err:
            raise fail(err) from None

    @router.patch("/me/agent/chats/{chat_id}")
    def rename_chat(chat_id: ChatId, body: RenameBody, response: Response, session: Session = Depends(session_dep)):
        user = session.principal.user_id
        response.headers["Cache-Control"] = "no-store"
        allowed(session)
        if not edit_limit.allow(f"agentedit:{user}"):
            raise HTTPException(status_code=429, detail="Too many changes. Wait a minute.")
        try:
            agent.rename(user, chat_id, body.title)
        except ChatError as err:
            raise wrong(err) from None
        return {**ready(), **agent.view(user)}

    @router.delete("/me/agent/chats/{chat_id}")
    def delete_chat(chat_id: ChatId, response: Response, session: Session = Depends(session_dep)):
        user = session.principal.user_id
        response.headers["Cache-Control"] = "no-store"
        allowed(session)
        if not edit_limit.allow(f"agentedit:{user}"):
            raise HTTPException(status_code=429, detail="Too many changes. Wait a minute.")
        agent.delete(user, chat_id)
        return {**ready(), **agent.view(user)}

    @router.get("/admin/agent")
    def admin_get(response: Response, session: Session = Depends(admin_dep)):
        response.headers["Cache-Control"] = "no-store"
        return agent.settings()

    @router.put("/admin/agent")
    def admin_put(body: SettingsBody, response: Response, session: Session = Depends(admin_dep)):
        response.headers["Cache-Control"] = "no-store"
        try:
            saved = agent.save_settings(body.mode, body.who, body.name, body.url, body.model, body.key, body.clear_key)
        except ChatError as err:
            raise wrong(err) from None
        vault.audit({"event": "agent_chat_settings_saved", "actor_user_id": session.principal.user_id, "mode": saved["mode"], "who": saved["who"], "own_address": bool(saved["url"]), "at": time.time()})
        return saved

    test_limit = SlidingWindowLimiter(max_events=6, window=60)

    @router.post("/admin/agent/test")
    def admin_test(response: Response, session: Session = Depends(admin_dep)):
        response.headers["Cache-Control"] = "no-store"
        if not test_limit.allow(f"agenttest:{session.principal.user_id}"):
            raise HTTPException(status_code=429, detail="Too many tests. Wait a minute.")
        try:
            return agent.test()
        except ChatError as err:
            raise wrong(err) from None

    @router.get("/admin/agent/test")
    def admin_test_state(response: Response, session: Session = Depends(admin_dep)):
        response.headers["Cache-Control"] = "no-store"
        return agent.test_state()

    return router
