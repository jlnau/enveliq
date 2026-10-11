"""Trips: the person's flights, stays and hire cars, and the few things they can do with them."""
from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi import Path as PathParam
from pydantic import StrictBool

from ..models import StrictModel
from ..security import Session
from .limits import SlidingWindowLimiter

BookingId = Annotated[str, PathParam(pattern=r"^v[0-9a-f]{23}$")]


class SettingsBody(StrictModel):
    calendar: StrictBool


def build_trips_router(ctx: Any) -> APIRouter:
    router = APIRouter(prefix="/api/v1")
    book = ctx.trips
    session_dep = ctx.full_session
    limit = SlidingWindowLimiter(max_events=240, window=60)

    def mine(session: Session, response: Response) -> str:
        user = session.principal.user_id
        if not limit.allow(f"trips:{user}"):
            raise HTTPException(status_code=429, detail="Too many requests. Wait a minute.")
        response.headers["Cache-Control"] = "no-store"
        return user

    @router.get("/me/trips")
    def my_trips(response: Response, session: Session = Depends(session_dep)):
        return book.view(mine(session, response))

    @router.put("/me/trips/settings")
    def my_settings(body: SettingsBody, response: Response, session: Session = Depends(session_dep)):
        user = mine(session, response)
        if not book.enabled(user):
            raise HTTPException(status_code=403, detail="Trips is switched off.")
        return book.set_calendar(user, body.calendar)

    @router.post("/me/trips/{booking_id}/remove")
    def remove_booking(booking_id: BookingId, response: Response, session: Session = Depends(session_dep)):
        user = mine(session, response)
        if not book.enabled(user):
            raise HTTPException(status_code=403, detail="Trips is switched off.")
        try:
            return book.remove(user, booking_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="That booking is no longer on your list.") from None

    return router
