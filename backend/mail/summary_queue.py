"""Generate summary: a line of requests, one at a time, kept on the server.

Pressing Generate summary on an email adds it here. A single background worker takes them in the
order they were pressed, so a person can press it on many emails without anything breaking, and the
line is still there after a refresh, on another device, or after leaving the page. It lives in the
server's memory only: a server restart empties it. It holds ids, never email text.
"""
from __future__ import annotations

import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Callable

from .errors import BridgeError

MAX_WAITING = 50          # per person
KEEP_FAILED = 900.0       # a failed request stays listed this long so it can be retried
KEEP_DONE = 30.0


@dataclass
class Job:
    user_id: str
    account_id: str
    message_id: str
    state: str = "waiting"        # waiting, writing, failed, done
    error: str = ""
    at: float = 0.0


class SummaryQueue:
    def __init__(self, run: Callable[[str, str], None], clock: Callable[[], float] = time.time, autostart: bool = True):
        self._autostart = autostart
        self._run = run                       # run(account_id, message_id), raises BridgeError with a plain reason
        self._clock = clock
        self._jobs: "OrderedDict[tuple[str, str], Job]" = OrderedDict()
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._thread: threading.Thread | None = None

    def add(self, user_id: str, account_id: str, message_id: str) -> Job:
        key = (account_id, message_id)
        with self._lock:
            self._forget_old()
            job = self._jobs.get(key)
            if job is not None and job.user_id == user_id and job.state in ("waiting", "writing"):
                return job
            if sum(1 for j in self._jobs.values() if j.user_id == user_id and j.state in ("waiting", "writing")) >= MAX_WAITING:
                raise BridgeError("busy", f"You already have {MAX_WAITING} summaries waiting. Wait for some to finish.")
            self._jobs.pop(key, None)                  # a retry goes to the back of the line
            job = Job(user_id, account_id, message_id, at=self._clock())
            self._jobs[key] = job
        self._start()
        self._wake.set()
        return job

    def cancel(self, user_id: str, account_id: str, message_id: str) -> bool:
        with self._lock:
            job = self._jobs.get((account_id, message_id))
            if job is None or job.user_id != user_id or job.state == "writing":
                return False
            del self._jobs[(account_id, message_id)]
            return True

    def listing(self, user_id: str) -> dict[str, Any]:
        with self._lock:
            self._forget_old()
            mine = [j for j in self._jobs.values() if j.user_id == user_id]
            ahead = 0
            items = []
            for j in self._jobs.values():                # position counts everyone's waiting jobs: it is one shared line
                if j.state in ("waiting", "writing"):
                    ahead += 1
                if j.user_id == user_id:
                    items.append({"account_id": j.account_id, "message_id": j.message_id, "state": j.state, "error": j.error,
                                  "position": ahead if j.state in ("waiting", "writing") else 0})
            return {"items": items, "waiting": sum(1 for j in mine if j.state == "waiting"), "writing": sum(1 for j in mine if j.state == "writing")}

    def _forget_old(self) -> None:
        now = self._clock()
        for key in [k for k, j in self._jobs.items() if (j.state == "failed" and now - j.at > KEEP_FAILED) or (j.state == "done" and now - j.at > KEEP_DONE)]:
            del self._jobs[key]

    def _start(self) -> None:
        if not self._autostart:
            return
        if self._thread is None or not self._thread.is_alive():
            self._thread = threading.Thread(target=self._loop, name="summary-queue", daemon=True)
            self._thread.start()

    def _next(self) -> Job | None:
        with self._lock:
            for j in self._jobs.values():
                if j.state == "waiting":
                    j.state = "writing"
                    return j
        return None

    def work_once(self) -> bool:
        """Run the oldest waiting request. False if there was none."""
        job = self._next()
        if job is None:
            return False
        try:
            self._run(job.account_id, job.message_id)
            outcome, error = "done", ""
        except BridgeError as err:
            outcome, error = "failed", err.message
        except Exception:
            outcome, error = "failed", "Something went wrong. Try again."
        with self._lock:
            if self._jobs.get((job.account_id, job.message_id)) is job:
                job.state, job.error, job.at = outcome, error, self._clock()
        return True

    def _loop(self) -> None:
        while True:
            if not self.work_once():
                self._wake.wait(30)
                self._wake.clear()
                with self._lock:
                    if not self._jobs:
                        self._thread = None
                        return
