from __future__ import annotations

import hashlib
import json
import logging
import re
import secrets
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Deque

from fastapi import HTTPException, Request, status

from .crypto_vault import Principal, SecureVault, VaultLocked


REMEMBERED_RECORD = "remembered-sessions"


class RedactingFilter(logging.Filter):
    PATTERNS = [
        re.compile(r"(?i)(authorization\s*[:=]\s*bearer\s+)[^\s,;]+"),
        re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]{16,}"),
        re.compile(r"(?i)(api[_-]?key\s*[:=]\s*)[^\s,;]+"),
        re.compile(r"(?i)(password\s*[:=]\s*)[^\s,;]+"),
        re.compile(r"(?i)(passphrase\s*[:=]\s*)[^\s,;]+"),
        re.compile(r"(?i)(refresh[_-]?token\s*[:=]\s*)[^\s,;]+"),
        re.compile(r"(?i)(access[_-]?token\s*[:=]\s*)[^\s,;]+"),
        re.compile(r"(?i)(session[_-]?token\s*[:=]\s*)[^\s,;]+"),
        re.compile(r"()\bsk-[A-Za-z0-9_-]{8,}"),
    ]

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:
            msg = str(record.msg)
        for pattern in self.PATTERNS:
            msg = pattern.sub(r"\1[REDACTED]", msg)
        record.msg = msg
        record.args = ()
        return True


@dataclass
class Session:
    token: str
    principal: Principal
    expires_at: float
    created_at: float = 0.0
    # "full": signed in. "enroll": password accepted but the MFA policy
    # requires setting up a second factor before anything else is allowed.
    state: str = "full"
    auth_method: str = "password"
    pending: dict = field(default_factory=dict)  # in-progress TOTP/passkey enrolment
    # A "keep me signed in on this device" session lasts its own, longer time (set by the administrator, at most
    # 14 days). 0 means the manager's normal idle time and 12-hour limit apply.
    remember_seconds: int = 0
    # A public handle for "Your devices" (never the token) and a plain name for where it signed in from.
    device_id: str = ""
    label: str = ""
    signed_in_at: float = 0.0               # wall clock, for display only


class SessionManager:
    """In-memory bearer sessions.

    - Sliding idle timeout (ttl_seconds) plus a hard maximum lifetime.
    - At most max_sessions live at once; the oldest is evicted first, so
      repeated sign-ins cannot grow memory without bound.
    - Thread-safe. The vault is never called while our lock is held, which
      keeps lock ordering simple when the vault notifies us that it locked.
    """

    def __init__(
        self,
        vault: SecureVault,
        ttl_seconds: int = 1800,
        max_lifetime_seconds: int = 12 * 3600,
        max_sessions: int = 32,
        clock: Callable[[], float] = time.time,
    ):
        self.vault = vault
        self.ttl_seconds = ttl_seconds
        self.max_lifetime_seconds = max_lifetime_seconds
        self.max_sessions = max_sessions
        self.clock = clock                      # wall clock, only for remembered sign-ins that must outlive a restart
        # Set by the app: user id -> Principal, or None when that person is gone or disabled.
        self.resolver: Callable[[str], Principal | None] | None = None
        self._sessions: dict[str, Session] = {}
        self._lock = threading.RLock()
        self._plock = threading.Lock()          # guards the stored copy; never held together with _lock

    # ---- remembered sign-ins survive a restart ----
    # A "keep me signed in" session is also written, encrypted, into the vault under a hash of its token (never the
    # token itself). After a restart Enveliq opens its own vault from the key file, finds the hash and carries on.
    # Normal 12-hour sign-ins are never stored: they end with the restart, as before.

    @staticmethod
    def _hash(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def _stored(self) -> dict[str, dict]:
        items = (self.vault.get_global(REMEMBERED_RECORD) or {}).get("items") or {}
        now = self.clock()
        return {k: v for k, v in items.items() if isinstance(v, dict) and float(v.get("started", 0)) + int(v.get("seconds", 0)) > now}

    def _store_edit(self, edit: Callable[[dict[str, dict]], None]) -> None:
        """Change the stored copy. Best effort: a locked vault just means nothing is kept, and the sign-in still works until the next restart."""
        try:
            with self._plock:
                on_disk = (self.vault.get_global(REMEMBERED_RECORD) or {}).get("items") or {}
                items = self._stored()                       # also drops the ones that have run out
                edit(items)
                if items != on_disk:
                    self.vault.set_global(REMEMBERED_RECORD, {"items": items})
        except VaultLocked:
            pass

    def _restore(self, token: str) -> Session | None:
        """A remembered sign-in from before a restart, or None."""
        if not token or self.resolver is None:
            return None
        try:
            with self._plock:
                row = self._stored().get(self._hash(token))
        except VaultLocked:
            return None
        if not row:
            return None
        principal = self.resolver(str(row.get("user_id", "")))
        if principal is None:
            self._store_edit(lambda items: items.pop(self._hash(token), None))
            return None
        seconds = int(row["seconds"])
        elapsed = max(0.0, self.clock() - float(row["started"]))
        now = time.monotonic()
        session = Session(token=token, principal=principal, expires_at=now + seconds - elapsed, created_at=now - elapsed,
                          state="full", auth_method=str(row.get("method", "passkey")), remember_seconds=seconds,
                          device_id=str(row.get("device_id") or self._hash(token)[:16]), label=str(row.get("label", "")),
                          signed_in_at=float(row["started"]))
        with self._lock:
            self._sessions.setdefault(token, session)
            return self._sessions[token]

    def life_of(self, session: Session) -> int:
        """The longest this session may last from sign-in, in seconds."""
        return session.remember_seconds or self.max_lifetime_seconds

    def idle_of(self, session: Session) -> int:
        """How long it may sit unused. A remembered session may be left for its whole time."""
        return session.remember_seconds or self.ttl_seconds

    def create(self, principal: Principal, *, state: str = "full", auth_method: str = "password", remember_seconds: int = 0, label: str = "") -> Session:
        now = time.monotonic()
        token = secrets.token_urlsafe(48)
        remember = int(remember_seconds) if state == "full" and remember_seconds and remember_seconds > 0 else 0
        session = Session(token=token, principal=principal, expires_at=now + (remember or self.ttl_seconds), created_at=now,
                          state=state, auth_method=auth_method, remember_seconds=remember,
                          device_id=secrets.token_hex(8), label=label[:80], signed_in_at=self.clock())
        with self._lock:
            self._prune_locked(now)
            while len(self._sessions) >= self.max_sessions:
                oldest = min(self._sessions, key=lambda k: self._sessions[k].created_at)
                self._sessions.pop(oldest, None)
            self._sessions[token] = session
        if remember:
            row = {"user_id": principal.user_id, "started": self.clock(), "seconds": remember, "method": auth_method,
                   "device_id": session.device_id, "label": session.label}
            self._store_edit(lambda items: items.__setitem__(self._hash(token), row))
        return session

    def _prune_locked(self, now: float) -> None:
        for key in [k for k, s in self._sessions.items() if self._expired(s, now)]:
            self._sessions.pop(key, None)

    def _expired(self, session: Session, now: float) -> bool:
        return session.expires_at < now or (now - session.created_at) > self.life_of(session)

    def revoke_all(self) -> None:
        """Forget every sign-in held in memory (the vault locked). Remembered ones come back once it opens again."""
        with self._lock:
            self._sessions.clear()

    def revoke_everyone(self) -> None:
        """Sign everyone out for good, including remembered sign-ins kept across restarts."""
        self.revoke_all()
        self._store_edit(lambda items: items.clear())

    def revoke(self, token: str) -> None:
        with self._lock:
            self._sessions.pop(token, None)
        if token:
            self._store_edit(lambda items: items.pop(self._hash(token), None))

    def revoke_user(self, user_id: str, except_token: str | None = None) -> None:
        with self._lock:
            for key in [k for k, s in self._sessions.items() if s.principal.user_id == user_id and k != except_token]:
                self._sessions.pop(key, None)
        keep = self._hash(except_token) if except_token else None
        self._store_edit(lambda items: [items.pop(k) for k in [k for k, v in items.items() if v.get("user_id") == user_id and k != keep]])

    def devices_of(self, user_id: str, current_token: str = "") -> list[dict]:
        """This person's signed-in devices, newest first (fully signed in, not run out). Never includes a token."""
        now = time.monotonic()
        with self._lock:
            live = [s for s in self._sessions.values() if s.principal.user_id == user_id and s.state == "full" and not self._expired(s, now)]
        rows = [{"id": s.device_id, "label": s.label, "signed_in_at": s.signed_in_at, "method": s.auth_method,
                 "remembered": bool(s.remember_seconds), "current": s.token == current_token} for s in live]
        # A remembered sign-in not used since a restart is still a device.
        try:
            with self._plock:
                stored = self._stored()
        except VaultLocked:
            stored = {}
        seen = {r["id"] for r in rows}
        for key, row in stored.items():
            did = str(row.get("device_id") or key[:16])
            if row.get("user_id") == user_id and did not in seen:
                rows.append({"id": did, "label": str(row.get("label", "")), "signed_in_at": float(row.get("started", 0)),
                             "method": str(row.get("method", "")), "remembered": True, "current": False})
        return sorted(rows, key=lambda r: r["signed_in_at"], reverse=True)

    def revoke_device(self, user_id: str, device_id: str) -> bool:
        """Sign one of this person's devices out. False when there is no such device (someone else's answers the same)."""
        if not device_id:
            return False
        found = False
        with self._lock:
            for key in [k for k, s in self._sessions.items() if s.principal.user_id == user_id and s.device_id == device_id]:
                self._sessions.pop(key, None)
                found = True
        def edit(items: dict[str, dict]) -> None:
            nonlocal found
            for k in [k for k, v in items.items() if v.get("user_id") == user_id and str(v.get("device_id") or k[:16]) == device_id]:
                items.pop(k)
                found = True
        self._store_edit(edit)
        return found

    def update_principal(self, token: str, principal: Principal) -> None:
        with self._lock:
            if token in self._sessions:
                self._sessions[token].principal = principal

    def count(self) -> int:
        with self._lock:
            return len(self._sessions)

    def peek(self, token: str | None) -> Session | None:
        """Return the live session without side effects (used to decide
        whether to show the app or the sign-in page)."""
        if not token:
            return None
        now = time.monotonic()
        with self._lock:
            session = self._sessions.get(token)
        if session is None:
            session = self._restore(token)
        return None if session is None or self._expired(session, now) else session

    def get(self, token: str) -> Session:
        now = time.monotonic()
        with self._lock:
            session = self._sessions.get(token) if token else None
        if session is None and token:
            session = self._restore(token)
        with self._lock:
            if session is None or self._expired(session, now):
                if token:
                    self._sessions.pop(token, None)
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired")
        try:
            self.vault.touch()
        except VaultLocked as exc:
            self.revoke_all()
            raise HTTPException(status_code=status.HTTP_423_LOCKED, detail="Vault is locked") from exc
        with self._lock:
            if token in self._sessions:
                session.expires_at = time.monotonic() + self.idle_of(session)
        return session


class FlowStore:
    """Short-lived, single-use state for multi-step sign-in (second-factor
    step, passkey challenges, OIDC state/nonce/PKCE verifier). Keyed by a
    random value held in an HttpOnly cookie; never stored on disk."""

    def __init__(self, ttl_seconds: int = 600, max_flows: int = 512, max_attempts: int = 5):
        self.ttl_seconds = ttl_seconds
        self.max_flows = max_flows
        self.max_attempts = max_attempts
        self._flows: dict[str, dict] = {}
        self._lock = threading.Lock()

    def create(self, kind: str, data: dict, ttl_seconds: int | None = None) -> str:
        now = time.monotonic()
        flow_id = secrets.token_urlsafe(32)
        with self._lock:
            for key in [k for k, f in self._flows.items() if f["expires"] < now]:
                del self._flows[key]
            while len(self._flows) >= self.max_flows:
                del self._flows[min(self._flows, key=lambda k: self._flows[k]["expires"])]
            self._flows[flow_id] = {"kind": kind, "data": data, "attempts": 0,
                                    "expires": now + (ttl_seconds or self.ttl_seconds)}
        return flow_id

    def get(self, flow_id: str | None, kind: str) -> dict | None:
        if not flow_id:
            return None
        with self._lock:
            flow = self._flows.get(flow_id)
            if flow is None or flow["kind"] != kind or flow["expires"] < time.monotonic():
                return None
            return flow

    def fail(self, flow_id: str) -> bool:
        """Count a wrong answer. Returns False (and ends the flow) once the
        attempt budget is spent."""
        with self._lock:
            flow = self._flows.get(flow_id)
            if flow is None:
                return False
            flow["attempts"] += 1
            if flow["attempts"] >= self.max_attempts:
                del self._flows[flow_id]
                return False
            return True

    def pop(self, flow_id: str | None) -> None:
        if flow_id:
            with self._lock:
                self._flows.pop(flow_id, None)

    def clear(self) -> None:
        with self._lock:
            self._flows.clear()


class UnlockRateLimiter:
    """Limits passphrase guesses.

    Every attempt is counted *before* the passphrase is checked, inside one
    lock, so a burst of parallel guesses cannot all slip through before the
    first failure is recorded. A global budget backs up the per-client one in
    case client addresses can be varied.
    """

    def __init__(
        self,
        max_attempts: int = 5,
        window_seconds: int = 300,
        global_max_attempts: int = 20,
        max_tracked_clients: int = 1024,
    ):
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self.global_max_attempts = global_max_attempts
        self.max_tracked_clients = max_tracked_clients
        self._attempts: dict[str, Deque[float]] = {}
        self._global: Deque[float] = deque()
        self._lock = threading.Lock()

    def _trim(self, q: Deque[float], now: float) -> None:
        while q and (now - q[0]) > self.window_seconds:
            q.popleft()

    def acquire(self, key: str) -> None:
        """Count one attempt, or raise 429 if the budget is spent."""
        now = time.monotonic()
        with self._lock:
            self._trim(self._global, now)
            q = self._attempts.get(key)
            if q is not None:
                self._trim(q, now)
            if len(self._global) >= self.global_max_attempts or (q is not None and len(q) >= self.max_attempts):
                raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many unlock attempts. Wait a few minutes and try again.")
            if q is None:
                if len(self._attempts) >= self.max_tracked_clients:
                    for k in [k for k, v in self._attempts.items() if not v or (now - v[-1]) > self.window_seconds]:
                        del self._attempts[k]
                    if len(self._attempts) >= self.max_tracked_clients:
                        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many unlock attempts. Wait a few minutes and try again.")
                q = self._attempts[key] = deque()
            q.append(now)
            self._global.append(now)

    def succeeded(self, key: str) -> None:
        """A correct passphrase clears that client's per-client count. The
        global count is left alone so it still reflects recent guessing."""
        with self._lock:
            self._attempts.pop(key, None)


def bearer_from_request(request: Request) -> str:
    auth = request.headers.get("authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer session")
    return auth[7:].strip()


def sanitize_validation_errors(errors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Strip submitted values from validation errors. FastAPI's default 422
    body echoes the offending input, which can be a passphrase or password."""
    clean = []
    for err in errors:
        clean.append({
            "loc": [part for part in err.get("loc", []) if isinstance(part, (str, int))],
            "msg": str(err.get("msg", "Invalid value")),
            "type": str(err.get("type", "value_error")),
        })
    return clean


ASGIApp = Callable[[dict, Callable[[], Awaitable[dict]], Callable[[dict], Awaitable[None]]], Awaitable[None]]


class _BodyTooLarge(HTTPException):
    # An HTTPException subclass, because FastAPI re-raises HTTPException from
    # body reading as-is (anything else becomes a generic 400).
    def __init__(self) -> None:
        super().__init__(status_code=413, detail="Request too large")


def private_host(host_header: str) -> bool:
    """True when a Host header is the address of a machine on a private network (192.168.x.x, 10.x.x.x, 172.16-31.x.x, fc00::/7) or this machine.
    Names are never accepted here, only addresses, and link-local addresses (169.254.x.x) are refused."""
    import ipaddress
    host = (host_header or "").strip()
    if host.startswith("["):
        host = host[1:host.find("]")] if "]" in host else ""
    elif host.count(":") == 1:
        host = host.split(":", 1)[0]
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return (ip.is_private or ip.is_loopback) and not (ip.is_link_local or ip.is_unspecified or ip.is_multicast)


class HostGuardMiddleware:
    """Answers only to the host names Enveliq was told about (like Starlette's TrustedHostMiddleware), with one exception:
    the WebSocket door (and its plain POST twin) for other services also answers on a private network address, so Home Assistant can reach it by the
    machine's local IP address without going through the public name. Every other path still needs a listed name."""

    def __init__(self, app: ASGIApp, allowed_hosts: list[str], local_ip_path: str, local_ip_post_path: str | None = None):
        from starlette.middleware.trustedhost import TrustedHostMiddleware
        self.app = app
        self.trusted = TrustedHostMiddleware(app, allowed_hosts=allowed_hosts)
        self.local_ip_path = local_ip_path
        self.local_ip_post_path = local_ip_post_path

    async def __call__(self, scope, receive, send):
        door = (scope.get("type") == "websocket" and scope.get("path") == self.local_ip_path) or (
            self.local_ip_post_path is not None and scope.get("type") == "http" and scope.get("method") == "POST"
            and scope.get("path") == self.local_ip_post_path)
        if door:
            headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}
            if private_host(headers.get("host", "")):
                await self.app(scope, receive, send)
                return
        await self.trusted(scope, receive, send)


class RequestGuardMiddleware:
    """Pure ASGI guard that runs before any request body is parsed.

    - Rejects a malformed Content-Length (400) instead of crashing (500).
    - Enforces the body size limit while the body streams in, so a chunked
      request without Content-Length cannot bypass it (413).
    - Requires application/json for any request that carries a body (415).
      Browsers cannot send that type cross-site without a CORS preflight,
      which this API never grants, so this closes cross-site form posts.
    - Rejects requests whose Origin header names a site that is not allowed.
    """

    BODY_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
    # New email may carry attachments (base64 inside the JSON). Only this one route gets the larger limit.
    LARGE_PATH = re.compile(r"^/api/v1/accounts/[0-9a-f-]{36}/send$")
    LARGE_BYTES = 15 * 1024 * 1024

    def __init__(self, app: ASGIApp, max_body_bytes: int, allowed_origins: set[str] | None = None):
        self.app = app
        self.max_body_bytes = max_body_bytes
        self.small_limit = max_body_bytes
        self.allowed_origins = allowed_origins or set()

    @staticmethod
    async def _send_json(send, status_code: int, detail: str) -> None:
        body = json.dumps({"detail": detail}).encode()
        await send({
            "type": "http.response.start",
            "status": status_code,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode()),
                (b"cache-control", b"no-store"),
                (b"x-content-type-options", b"nosniff"),
            ],
        })
        await send({"type": "http.response.body", "body": body})

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}
        method = scope.get("method", "GET").upper()
        limit = self.LARGE_BYTES if (method == "POST" and self.LARGE_PATH.match(scope.get("path", ""))) else self.small_limit

        origin = headers.get("origin")
        if origin is not None and origin not in self.allowed_origins:
            await self._send_json(send, 403, "Cross-origin requests are not allowed")
            return

        # Fetch metadata: browsers label cross-site requests. State-changing
        # requests from another site are refused (backs up SameSite cookies).
        if method in self.BODY_METHODS and headers.get("sec-fetch-site") == "cross-site":
            await self._send_json(send, 403, "Cross-site requests are not allowed")
            return

        length_header = headers.get("content-length")
        if length_header is not None:
            if not length_header.isdigit():
                await self._send_json(send, 400, "Invalid Content-Length header")
                return
            if int(length_header) > limit:
                await self._send_json(send, 413, "Request too large")
                return

        has_body = (length_header not in (None, "0")) or ("chunked" in headers.get("transfer-encoding", "").lower())
        if method in self.BODY_METHODS and has_body:
            content_type = headers.get("content-type", "").split(";")[0].strip().lower()
            if content_type != "application/json":
                await self._send_json(send, 415, "Request body must be application/json")
                return

        received = 0
        response_started = False

        async def limited_receive():
            nonlocal received
            message = await receive()
            if message.get("type") == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    raise _BodyTooLarge()
            return message

        async def tracking_send(message):
            nonlocal response_started
            if message.get("type") == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, tracking_send)
        except _BodyTooLarge:
            if not response_started:
                await self._send_json(send, 413, "Request too large")
