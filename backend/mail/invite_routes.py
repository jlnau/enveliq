"""Calendar invites on an open email: the card's data, Accept / Maybe / Decline, Propose a new time, and Add / Remove for the calendar."""
from __future__ import annotations

import logging
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import Field, field_validator

from ..models import StrictModel
from ..security import Session
from . import invites, review
from .errors import BridgeError
from .limits import SlidingWindowLimiter
from .outbound import OutboundError
from .routes import AccountId, MessageId, fail

log = logging.getLogger("enveliq.invites")


class AnswerBody(StrictModel):
    response: str = Field(pattern=r"^(accepted|tentative|declined)$")
    comment: str = Field(default="", max_length=500)
    confirm_organizer: bool = False                       # the person agreed to answer an organiser who is not the sender


class ProposeBody(StrictModel):
    start: float = Field(ge=0, le=4_102_444_800)
    end: float = Field(ge=0, le=4_102_444_800)
    zone: str = Field(default="UTC", max_length=64)
    note: str = Field(default="", max_length=500)
    confirm_organizer: bool = False

    @field_validator("zone")
    @classmethod
    def known_zone(cls, value: str) -> str:
        if invites._zone(value) is None:
            raise ValueError("unknown time zone")
        return value


class CalendarBody(StrictModel):
    action: str = Field(pattern=r"^(add|remove)$")


def build_invite_router(ctx: Any) -> APIRouter:
    router = APIRouter(prefix="/api/v1")
    service, vault, outbox, sync = ctx.mail, ctx.vault, ctx.outbox, ctx.sync
    state = invites.State(vault)
    session_dep = ctx.full_session
    read_limit = SlidingWindowLimiter(max_events=60, window=60)
    act_limit = SlidingWindowLimiter(max_events=20, window=60)

    def owned(account_id: str, session: Session, action: str) -> dict[str, Any]:
        return ctx.load_account(account_id, session.principal, owner_only=True, action=action)

    def message_of(account_id: str, message_id: str) -> dict[str, Any]:
        try:
            return vault.get_message(account_id, message_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="Message not found") from None

    def load(account: dict[str, Any], message: dict[str, Any], user: str) -> dict[str, Any]:
        try:
            raw = service.original_raw(account, message)
        except BridgeError as err:
            raise fail(err) from None
        invite = invites.from_email(raw, ctx.tasks.timezone_of(user))
        if invite is None:
            raise HTTPException(status_code=404, detail="This email has no calendar invitation.")
        return invite

    def card(account: dict[str, Any], message: dict[str, Any], invite: dict[str, Any], user: str) -> dict[str, Any]:
        sender = (message.get("sender_address") or (message.get("reply_context") or {}).get("reply_to") or "")
        mine = invites.pick_identity(service, account, invite, (message.get("reply_context") or {}).get("delivered_to"))
        return invites.public(invite, mine=mine, answer=state.get(user, invites.key_of(invite)), differs=invites.organizer_differs(invite, sender),
                              calendar=sync.invite_place(user))

    def need_organizer_ok(invite: dict[str, Any], message: dict[str, Any], confirmed: bool) -> None:
        sender = (message.get("sender_address") or (message.get("reply_context") or {}).get("reply_to") or "")
        if invites.organizer_differs(invite, sender) and not confirmed:
            raise HTTPException(status_code=409, detail={"code": "organizer_differs", "message": f"This invitation names {invite['organizer']['email']} as the organiser, who is not the sender. Tick the box to answer them anyway."})

    def calendar_write(user: str, invite: dict[str, Any], response: str) -> str:
        """Put the meeting in the connected calendar (accepted, maybe) or take it out (declined, cancelled). Returns where, or "" when none."""
        key = invites.key_of(invite)
        if response in ("accepted", "tentative", "add"):
            return sync.invite_put(user, key, invites.google_body(invite, key, "tentative" if response == "tentative" else "accepted"),
                                   invites.calendar_file(invite, key, "tentative" if response == "tentative" else "accepted", time.time()))
        return sync.invite_remove(user, key)

    def settle(user: str, invite: dict[str, Any], response: str) -> None:
        """After the answer has really gone: write the calendar and remember the answer. Never raises (runs when Undo send ends)."""
        key = invites.key_of(invite)
        where, problem = "", ""
        try:
            where = calendar_write(user, invite, response)
        except OutboundError as err:
            problem = err.message
        except Exception:
            problem = "The calendar could not be updated."
            log.warning("invite calendar update failed")
        state.put(user, key, response=response, calendar=where, calendar_problem=problem)

    @router.get("/accounts/{account_id}/messages/{message_id}/invite")
    def get_invite(account_id: AccountId, message_id: MessageId, response: Response, session: Session = Depends(session_dep)):
        user = session.principal.user_id
        account = owned(account_id, session, "see invitations")
        message = message_of(account_id, message_id)
        if not read_limit.allow(f"invite:{user}"):
            raise HTTPException(status_code=429, detail="Too many requests. Wait a minute.")
        invite = load(account, message, user)
        response.headers["Cache-Control"] = "no-store"
        return card(account, message, invite, user)

    @router.post("/accounts/{account_id}/messages/{message_id}/invite/answer")
    def answer(body: AnswerBody, account_id: AccountId, message_id: MessageId, session: Session = Depends(session_dep)):
        user = session.principal.user_id
        account = owned(account_id, session, "answer invitations")
        message = message_of(account_id, message_id)
        if not act_limit.allow(f"invite-act:{user}") or not ctx.send_limit.allow(f"send:{user}") or not ctx.send_total.allow("all"):
            raise HTTPException(status_code=429, detail="Too many answers sent recently. Wait a few minutes.")
        invite = load(account, message, user)
        if not (card(account, message, invite, user)["can_answer"]):
            raise HTTPException(status_code=409, detail="This invitation cannot be answered by email.")
        need_organizer_ok(invite, message, body.confirm_organizer)
        delay = review.user_prefs(vault, user)["undo_send_seconds"]
        try:
            built = invites.build_answer(service, account, message, invite, body.response, body.comment)

            def done() -> None:
                settle(user, invite, body.response)

            if delay > 0:
                item = outbox.enqueue(user, account_id, message_id, built, body.comment or "", delay, on_sent=done, kind="reply")
                out = {"queued": True, "id": item.id, "send_at": item.send_at, "now": time.time(), "from": item.chosen, "to": invite["organizer"]["email"]}
            else:
                service.bridge.send(service.target(account), built[0], built[1], built[2])
                done()
                out = {"sent": True, "from": built[1], "answer": state.get(user, invites.key_of(invite))}
        except BridgeError as err:
            raise fail(err) from None
        vault.audit({"event": "invite_answered", "actor_user_id": user, "account_id": account_id, "response": body.response, "at": time.time()})
        return out

    @router.post("/accounts/{account_id}/messages/{message_id}/invite/propose")
    def propose(body: ProposeBody, account_id: AccountId, message_id: MessageId, session: Session = Depends(session_dep)):
        user = session.principal.user_id
        account = owned(account_id, session, "answer invitations")
        message = message_of(account_id, message_id)
        if not act_limit.allow(f"invite-act:{user}") or not ctx.send_limit.allow(f"send:{user}") or not ctx.send_total.allow("all"):
            raise HTTPException(status_code=429, detail="Too many emails sent recently. Wait a few minutes.")
        now = time.time()
        if body.end <= body.start or body.end - body.start > 86400 or body.start < now - 3600 or body.start > now + 2 * 365 * 86400:
            raise HTTPException(status_code=422, detail="Pick a start and end time in the future, no more than a day long.")
        invite = load(account, message, user)
        if not card(account, message, invite, user)["can_answer"]:
            raise HTTPException(status_code=409, detail="This invitation cannot be answered by email.")
        need_organizer_ok(invite, message, body.confirm_organizer)
        delay = review.user_prefs(vault, user)["undo_send_seconds"]
        try:
            built = invites.build_proposal(service, account, message, invite, body.start, body.end, body.zone, body.note)

            def done() -> None:
                state.put(user, invites.key_of(invite), proposed=body.start)

            if delay > 0:
                item = outbox.enqueue(user, account_id, message_id, built, body.note or "", delay, on_sent=done, kind="reply")
                out = {"queued": True, "id": item.id, "send_at": item.send_at, "now": time.time(), "from": item.chosen, "to": invite["organizer"]["email"]}
            else:
                service.bridge.send(service.target(account), built[0], built[1], built[2])
                done()
                out = {"sent": True, "from": built[1]}
        except BridgeError as err:
            raise fail(err) from None
        vault.audit({"event": "invite_new_time_suggested", "actor_user_id": user, "account_id": account_id, "at": time.time()})
        return out

    @router.post("/accounts/{account_id}/messages/{message_id}/invite/calendar")
    def calendar(body: CalendarBody, account_id: AccountId, message_id: MessageId, session: Session = Depends(session_dep)):
        """Add the meeting to the connected calendar without answering (a plain calendar file), or take it out again (also for a cancelled meeting)."""
        user = session.principal.user_id
        account = owned(account_id, session, "change your calendar")
        message = message_of(account_id, message_id)
        if not act_limit.allow(f"invite-act:{user}"):
            raise HTTPException(status_code=429, detail="Too many requests. Wait a minute.")
        invite = load(account, message, user)
        if body.action == "add" and not card(account, message, invite, user)["can_add"]:
            raise HTTPException(status_code=409, detail="This meeting was cancelled, so it cannot be added.")
        if not sync.invite_target(user):
            raise HTTPException(status_code=409, detail="No calendar is connected. Connect one under Settings, Calendar & to-do.")
        try:
            where = calendar_write(user, invite, "add" if body.action == "add" else "declined")
        except OutboundError as err:
            raise HTTPException(status_code=502, detail=err.message) from None
        state.put(user, invites.key_of(invite), response="added" if body.action == "add" else "removed", calendar=where if body.action == "add" else "", calendar_problem="")
        vault.audit({"event": "invite_calendar_" + body.action, "actor_user_id": user, "account_id": account_id, "at": time.time()})
        return {"calendar": where, "answer": state.get(user, invites.key_of(invite))}

    return router
