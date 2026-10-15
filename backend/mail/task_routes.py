"""The task list: what needs doing (made from email summaries) and the few things a person can do with it."""
from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi import Path as PathParam
from pydantic import Field

from ..models import StrictModel
from ..security import Session
from .limits import SlidingWindowLimiter
from .tasks import MOVES

TaskId = Annotated[str, PathParam(pattern=r"^t[0-9a-f]{23}$")]
Action = Annotated[str, PathParam(pattern=r"^(done|reopen|remove|not_today|move)$")]


class TaskMoveBody(StrictModel):
    to: str | None = Field(default=None, max_length=16)
    on: str | None = Field(default=None, max_length=10)


class NewTaskBody(StrictModel):
    account_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_\-]+$")
    message_id: str = Field(min_length=1, max_length=256)
    title: str = Field(min_length=1, max_length=300)
    on: str | None = Field(default=None, max_length=10)


def build_task_router(ctx: Any) -> APIRouter:
    router = APIRouter(prefix="/api/v1")
    book = ctx.tasks
    session_dep = ctx.full_session
    limit = SlidingWindowLimiter(max_events=240, window=60)

    @router.get("/me/tasks")
    def my_tasks(response: Response, tz: Annotated[str | None, Query(max_length=64)] = None, session: Session = Depends(session_dep)):
        user = session.principal.user_id
        if not limit.allow(f"tasks:{user}"):
            raise HTTPException(status_code=429, detail="Too many requests. Wait a minute.")
        response.headers["Cache-Control"] = "no-store"
        return book.view(user, tz)

    @router.post("/me/tasks")
    def add_task(body: NewTaskBody, session: Session = Depends(session_dep)):
        user = session.principal.user_id
        if not limit.allow(f"tasks:{user}"):
            raise HTTPException(status_code=429, detail="Too many requests. Wait a minute.")
        try:
            book.add(user, body.account_id, body.message_id, body.title, on=body.on)
        except KeyError:
            raise HTTPException(status_code=404, detail="That email is no longer in your list.") from None
        except ValueError as err:
            raise HTTPException(status_code=422, detail={"no title": "Write what you want to remember.", "bad date": "Pick a date from today on.",
                                                          "date out of range": "Pick a date within the next year.",
                                                          "too many": "You have a lot of tasks of your own open. Finish a few first."}.get(str(err), "That task is not possible.")) from None
        return book.view(user)

    @router.post("/me/tasks/{task_id}/{action}")
    def change_task(task_id: TaskId, action: Action, body: TaskMoveBody | None = None, session: Session = Depends(session_dep)):
        user = session.principal.user_id
        if not limit.allow(f"tasks:{user}"):
            raise HTTPException(status_code=429, detail="Too many requests. Wait a minute.")
        body = body or TaskMoveBody()
        if action == "move" and body.to not in MOVES:
            raise HTTPException(status_code=422, detail="Choose when to move it to.")
        try:
            book.act(user, task_id, action, to=body.to, on=body.on)
        except KeyError:
            raise HTTPException(status_code=404, detail="That task is no longer on your list.") from None
        except ValueError as err:
            raise HTTPException(status_code=422, detail={"closed": "That task is already finished.", "bad date": "Pick a date from today on.",
                                                          "date out of range": "Pick a date within the next year."}.get(str(err), "That change is not possible.")) from None
        return book.view(user)

    return router
