"""Instant checking for Proton Bridge: keep one connection open and sync the moment Bridge says new mail arrived.

* It uses IMAP IDLE. Bridge pushes a short "something changed" line; no mail is read here. When one arrives, the
  mailbox is marked due and the normal automatic sync does the real work (summaries, alerts, everything), so an
  instant check behaves exactly like a timed one, just sooner.
* One connection per mailbox that has the switch on, and only while the vault is unlocked. When the vault locks,
  the mailbox is removed or the switch is turned off, the connection is closed.
* If the connection drops it is opened again with a growing delay (15 seconds up to 5 minutes). The timed check keeps
  running underneath, so a broken connection never means missed mail, only slower mail.
* Nothing from the mailbox is logged: no addresses, no subjects, no server text.
"""
from __future__ import annotations

import hashlib
import logging
import re
import select
import ssl
import threading
import time
from typing import Any, Callable

from .bridge import Bridge, Target

log = logging.getLogger("enveliq.instant")

RENEW_SECONDS = 25 * 60.0           # IDLE is restarted before servers (which allow about 30 minutes) give up on it
FIRST_DELAY, MAX_DELAY = 15.0, 300.0
EVENT_GAP = 3.0                     # at most one nudge every few seconds, however busy the mailbox
_CHANGE = re.compile(rb"^\* \d+ (EXISTS|EXPUNGE)\b", re.I)


def _readable(imap: Any, seconds: float) -> bool:
    sock = imap.socket()
    if isinstance(sock, ssl.SSLSocket) and sock.pending():
        return True
    return bool(select.select([sock], [], [], seconds)[0])


class _Listener:
    def __init__(self, bridge: Bridge, target: Target, on_change: Callable[[], None], key: str):
        self.bridge, self.target, self.on_change, self.key = bridge, target, on_change, key
        self.stop = threading.Event()
        self.state = "connecting"                       # connecting | listening | retrying
        self.thread = threading.Thread(target=self._run, name="enveliq-instant", daemon=True)

    def _run(self) -> None:
        delay = FIRST_DELAY
        while not self.stop.is_set():
            imap = None
            try:
                imap = self.bridge.open_imap(self.target)
                imap.select("INBOX", True)
                self.state, delay = "listening", FIRST_DELAY
                self._idle(imap)
            except Exception:
                self.state = "retrying"
                log.info("instant check connection dropped")
            finally:
                self.bridge._close_imap(imap)
            if self.stop.wait(delay):
                return
            delay = min(delay * 2, MAX_DELAY)

    def _idle(self, imap: Any) -> None:
        while not self.stop.is_set():
            tag = imap._new_tag()
            imap.send(tag + b" IDLE\r\n")
            if not imap.readline().startswith(b"+"):
                raise OSError("idle not accepted")
            changed = False
            deadline = time.monotonic() + RENEW_SECONDS
            while not self.stop.is_set() and time.monotonic() < deadline:
                if not _readable(imap, 1.0):
                    continue
                line = imap.readline()
                if not line:
                    raise OSError("closed")
                changed = changed or bool(_CHANGE.match(line))
                break                                   # any line ends this round; the next round starts clean
            imap.send(b"DONE\r\n")
            while True:                                 # read everything up to the end of IDLE, so nothing is missed
                line = imap.readline()
                if not line:
                    raise OSError("closed")
                if line.startswith(tag):
                    break
                changed = changed or bool(_CHANGE.match(line))
            if changed:
                self.on_change()
                if self.stop.wait(EVENT_GAP):
                    return


class InstantListeners:
    def __init__(self, service: Any, nudge: Callable[[str], None]):
        self.service = service
        self.nudge = nudge
        self._running: dict[str, _Listener] = {}
        self._guard = threading.Lock()

    @staticmethod
    def wanted(account: dict[str, Any]) -> bool:
        s = account.get("settings") or {}
        return account.get("auth_method") == "proton_bridge" and s.get("instant") is True and s.get("auto_sync") is not False

    def reconcile(self, accounts: list[dict[str, Any]], enabled: bool) -> None:
        want: dict[str, dict[str, Any]] = {}
        if enabled:
            for a in accounts:
                if self.wanted(a) and not self.service.is_check_address(a):
                    want[a["id"]] = a
        with self._guard:
            for aid in list(self._running):
                if aid not in want:
                    self._running.pop(aid).stop.set()
            for aid, account in want.items():
                try:
                    target = self.service.target(account)
                except Exception:
                    continue
                key = hashlib.sha256(repr((target.host, target.imap_port, target.username, target.password)).encode()).hexdigest()
                current = self._running.get(aid)
                if current is not None and current.key != key:          # the sign-in details changed: start again with the new ones
                    current.stop.set()
                    current = None
                    self._running.pop(aid, None)
                if current is None:
                    listener = _Listener(self.service.bridge, target, lambda aid=aid: self.nudge(aid), key)
                    self._running[aid] = listener
                    listener.thread.start()

    def stop_all(self) -> None:
        with self._guard:
            for listener in self._running.values():
                listener.stop.set()
            self._running.clear()

    def states(self) -> dict[str, str]:
        with self._guard:
            return {aid: l.state for aid, l in self._running.items()}
