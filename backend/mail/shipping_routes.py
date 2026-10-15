"""Shipping: the person's online orders, and the few things they can do with them."""
from __future__ import annotations

import time
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi import Path as PathParam

from pydantic import Field

from ..models import StrictModel
from ..security import Session
from . import shipping as S
from .limits import SlidingWindowLimiter

OrderId = Annotated[str, PathParam(pattern=r"^s[0-9a-f]{23}$")]
Action = Annotated[str, PathParam(pattern=r"^(confirm|not_yet|not_order|track|undo|remove)$")]


CarrierId = Annotated[str, PathParam(pattern=r"^c[0-9a-f]{16}$")]


class CarrierBody(StrictModel):
    name: str = Field(max_length=80)
    url: str = Field(max_length=600)
    example_number: str | None = Field(default=None, max_length=80)


class NoteBody(StrictModel):
    note: str = Field(max_length=600)


class HandOrderBody(StrictModel):
    shop: str = Field(max_length=80)
    tracking: str | None = Field(default=None, max_length=80)
    status: str = Field(max_length=20)


class StatusBody(StrictModel):
    status: str = Field(max_length=20)


HAND_ERRORS = {"no shop": "Write who the parcel is from.", "bad tracking": "That tracking number does not look right. It needs 8 to 40 letters or digits.",
               "bad status": "Choose where the parcel is up to.", "already listed": "That tracking number is already on your list.",
               "full": "Your shipping list is full. Remove an order first.", "not by hand": "Only orders you added yourself can be changed by hand."}


def build_shipping_router(ctx: Any) -> APIRouter:
    router = APIRouter(prefix="/api/v1")
    book = ctx.shipping
    session_dep = ctx.full_session
    limit = SlidingWindowLimiter(max_events=240, window=60)

    @router.get("/me/shipping")
    def my_orders(response: Response, session: Session = Depends(session_dep)):
        user = session.principal.user_id
        if not limit.allow(f"ship:{user}"):
            raise HTTPException(status_code=429, detail="Too many requests. Wait a minute.")
        response.headers["Cache-Control"] = "no-store"
        return book.view(user)

    @router.post("/me/shipping")
    def add_order(body: HandOrderBody, response: Response, session: Session = Depends(session_dep)):
        user = session.principal.user_id
        if not limit.allow(f"ship:{user}"):
            raise HTTPException(status_code=429, detail="Too many requests. Wait a minute.")
        if not book.enabled(user):
            raise HTTPException(status_code=403, detail="Shipping is switched off.")
        response.headers["Cache-Control"] = "no-store"
        try:
            return book.add_by_hand(user, body.shop, body.tracking, body.status)
        except ValueError as err:
            raise HTTPException(status_code=422, detail=HAND_ERRORS.get(str(err), "That order is not possible.")) from None

    @router.put("/me/shipping/{order_id}/status")
    def order_status(order_id: OrderId, body: StatusBody, response: Response, session: Session = Depends(session_dep)):
        user = session.principal.user_id
        if not limit.allow(f"ship:{user}"):
            raise HTTPException(status_code=429, detail="Too many requests. Wait a minute.")
        response.headers["Cache-Control"] = "no-store"
        try:
            return book.set_status(user, order_id, body.status)
        except KeyError:
            raise HTTPException(status_code=404, detail="That order is no longer on your list.") from None
        except ValueError as err:
            raise HTTPException(status_code=422, detail=HAND_ERRORS.get(str(err), "That change is not possible.")) from None

    @router.post("/me/shipping/{order_id}/{action}")
    def change_order(order_id: OrderId, action: Action, response: Response, session: Session = Depends(session_dep)):
        user = session.principal.user_id
        if not limit.allow(f"ship:{user}"):
            raise HTTPException(status_code=429, detail="Too many requests. Wait a minute.")
        response.headers["Cache-Control"] = "no-store"
        try:
            return book.act(user, order_id, action)
        except KeyError:
            raise HTTPException(status_code=404, detail="That order is no longer on your list.") from None
        except ValueError as err:
            raise HTTPException(status_code=422, detail=HAND_ERRORS.get(str(err), "That change is not possible yet.")) from None

    @router.put("/me/shipping/{order_id}/note")
    def order_note(order_id: OrderId, body: NoteBody, response: Response, session: Session = Depends(session_dep)):
        user = session.principal.user_id
        if not limit.allow(f"ship:{user}"):
            raise HTTPException(status_code=429, detail="Too many requests. Wait a minute.")
        response.headers["Cache-Control"] = "no-store"
        try:
            return book.set_note(user, order_id, body.note)
        except KeyError:
            raise HTTPException(status_code=404, detail="That order is no longer on your list.") from None

    def allowed(session: Session) -> str:
        user = session.principal.user_id
        if not book.enabled(user):
            raise HTTPException(status_code=403, detail="Shipping is switched off.")
        if not limit.allow(f"ship:{user}"):
            raise HTTPException(status_code=429, detail="Too many requests. Wait a minute.")
        return user

    @router.post("/shipping/carriers", status_code=201)
    def add_carrier(body: CarrierBody, response: Response, session: Session = Depends(session_dep)):
        """Anyone using Shipping may add a carrier; everyone then gets its Track link."""
        user = allowed(session)
        response.headers["Cache-Control"] = "no-store"
        try:
            book.add_carrier(user, body.name, body.url, body.example_number)
        except S.CarrierError as err:
            raise HTTPException(status_code=422, detail=str(err)) from None
        ctx.vault.audit({"event": "shipping_carrier_added", "actor_user_id": user, "at": time.time()})
        return book.view(user)

    def admin_only(session: Session) -> str:
        user = allowed(session)
        if not session.principal.is_admin:
            raise HTTPException(status_code=403, detail="Only an administrator can change a saved carrier.")
        return user

    @router.get("/shipping/carriers")
    def carrier_addresses(response: Response, session: Session = Depends(session_dep)):
        """The saved carriers with their tracking-page addresses, for an administrator who wants to correct one."""
        admin_only(session)
        response.headers["Cache-Control"] = "no-store"
        return {"carriers": book.carrier_addresses()}

    @router.put("/shipping/carriers/{carrier_id}")
    def edit_carrier(carrier_id: CarrierId, body: CarrierBody, response: Response, session: Session = Depends(session_dep)):
        user = admin_only(session)
        response.headers["Cache-Control"] = "no-store"
        try:
            book.update_carrier(carrier_id, body.name, body.url, body.example_number)
        except S.CarrierError as err:
            raise HTTPException(status_code=422, detail=str(err)) from None
        except KeyError:
            raise HTTPException(status_code=404, detail="That carrier is no longer on the list.") from None
        ctx.vault.audit({"event": "shipping_carrier_edited", "actor_user_id": user, "at": time.time()})
        return book.view(user)

    @router.delete("/shipping/carriers/{carrier_id}")
    def remove_carrier(carrier_id: CarrierId, response: Response, session: Session = Depends(session_dep)):
        """The person who added a carrier, or an administrator, may remove it for everyone."""
        user = allowed(session)
        response.headers["Cache-Control"] = "no-store"
        try:
            book.remove_carrier(user, carrier_id, bool(session.principal.is_admin))
        except KeyError:
            raise HTTPException(status_code=404, detail="That carrier is no longer on the list.") from None
        except PermissionError:
            raise HTTPException(status_code=403, detail="Only the person who added a carrier, or an administrator, can remove it.") from None
        ctx.vault.audit({"event": "shipping_carrier_removed", "actor_user_id": user, "at": time.time()})
        return book.view(user)

    return router
