from __future__ import annotations

import logging
import os
import secrets
import stat
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Annotated, Any
from urllib.parse import urlsplit

from fastapi import Depends, FastAPI, HTTPException, Path as PathParam, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from .attachments import PreviewLeaseStore
from .auth.oidc import OIDCClient, OIDCSettings
from .auth.passkeys import OFFICIAL_ANDROID_CERT, RelyingParty, android_origin, asset_links as passkey_asset_links, parse_cert_fingerprints
from .auth.routes import build_router
from . import keyfile
from .mail.bridge import Bridge
from .mail.errors import BridgeError, HTTP_STATUS as BRIDGE_HTTP_STATUS
from .mail.microsoft import Microsoft
from .mail.microsoft_routes import build_microsoft_router
from .mail.routes import build_mail_router
from .mail.extra_routes import build_extra_router
from .mail.find_routes import build_find_router
from .mail.task_routes import build_task_router
from .mail.shipping import ShipBook
from .mail.inbound import InboundBook
from .mail.inbound_routes import WEBHOOK_PATH as INBOUND_WEBHOOK_PATH, WS_PATH as INBOUND_WS_PATH, build_inbound_router
from .mail.rss import RssBook, RssRefresher
from .mail import features
from .mail.tags import TagService
from .mail.tag_routes import build_tag_router
from .mail.rss_routes import build_rss_router
from .mail.important import ImportantPeople
from .mail.important_routes import build_important_router
from .mail.rules import Rules
from .mail.rules_routes import build_rules_router
from .mail.drafts import Drafts
from .mail.drafts_routes import build_drafts_router
from .mail.scheduled import ScheduledMail, ScheduledSender
from .mail.scheduled_routes import build_scheduled_router
from .mail.saved_writing import SavedWriting
from .mail.saved_writing_routes import build_saved_writing_router
from .mail.junk import JunkBook
from .mail.junk_routes import build_junk_router
from .mail.subscriptions import SubBook
from .mail.subscriptions_routes import build_subscriptions_router
from .mail.trips import TripBook
from .mail.trips_routes import build_trips_router
from .mail.messages import MessageBook
from .mail.messages_routes import build_messages_router
from .mail.writehelp import WriteHelpBook
from .mail.writehelp_routes import build_writehelp_router
from .mail.style import StyleBook
from .mail.style_routes import build_style_router
from .mail.digest import DigestBook
from .mail.digest_routes import build_digest_router
from .mail.shipping_routes import build_shipping_router
from .mail.waiting import WaitBook
from .mail.waiting_routes import build_waiting_router
from .mail.check_routes import build_check_router
from .backup import BackupManager
from .backup_routes import build_backup_router
from .export import build_exporter
from .mail import contacts as contacts_mod
from .mail.checkbox import CheckBox
from .mail.tasks import TaskBook
from .mail.notify import Notifier
from .mail.notify_routes import build_notify_router
from .mail.summary import DailySummary
from .mail.senders import SenderBook
from .mail.senders_routes import build_senders_router
from .mail.agent import Agent
from .mail.agent_routes import build_agent_router
from .mail.calsync import Sync
from .mail import extra_channels, marks
from .mail.outbound import OutboundError
from .mail.sync_routes import build_sync_router
from .mail.gcal_routes import build_gcal_router
from .mail.mail_alerts import MailAlerts
from .mail.reminders import Reminders
from .mail.outbox import Outbox
from .version import VERSION
from .update_check import UpdateChecker
from .mail.scheduler import AutoSync
from .mail import review
from .mail.service import MailService
from .reporting import Reporter
from .reporting.routes import build_reporting_router
from .auth.users import UserService
from .crypto_vault import (
    InvalidPassphrase,
    Principal,
    SecureVault,
    VaultLocked,
    VaultNotInitialized,
)
from .models import (
    AccountCreate,
    AccountPatch,
    AttachmentPolicyPatch,
    GlobalSettings,
    ResolveMessageRequest,
    RetainedMessageCreate,
    UnlockRequest,
    UpdateNoticeBody,
)
from .security import (
    FlowStore,
    HostGuardMiddleware,
    RedactingFilter,
    RequestGuardMiddleware,
    Session,
    SessionManager,
    UnlockRateLimiter,
    sanitize_validation_errors,
)

# Files this process creates (SQLite DB, WAL, SHM, setup code) are private.
os.umask(0o077)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
WEB_DIR = PROJECT_ROOT / "web"
APP_PAGE = PROJECT_ROOT / "prototype" / "index.html"
BRAND_WEB_DIR = PROJECT_ROOT / "brand" / "web"
DATA_DIR = Path(os.environ.get("ENVELIQ_DATA_DIR", str(PROJECT_ROOT / "data")))
DB_PATH = DATA_DIR / "vault.sqlite3"
SETUP_CODE_PATH = DATA_DIR / "setup-code.txt"
IDLE_LOCK_SECONDS = int(os.environ.get("ENVELIQ_IDLE_LOCK_SECONDS", "1800"))
SESSION_TTL_SECONDS = int(os.environ.get("ENVELIQ_SESSION_TTL_SECONDS", "1800"))
MAX_BODY_BYTES = int(os.environ.get("ENVELIQ_MAX_JSON_BYTES", str(1024 * 1024)))
PORT = int(os.environ.get("ENVELIQ_PORT", "8765"))

# The address people use to reach Enveliq. Passkeys are bound to its host
# name and SSO providers redirect back to it, so it must match what is in the
# browser's address bar (behind a reverse proxy: the proxy's https:// URL).
PUBLIC_URL = os.environ.get("ENVELIQ_PUBLIC_URL", f"http://localhost:{PORT}").rstrip("/")
_pub = urlsplit(PUBLIC_URL)
if _pub.scheme not in ("http", "https") or not _pub.hostname or _pub.path not in ("", "/"):
    raise RuntimeError("ENVELIQ_PUBLIC_URL must look like https://enveliq.example.com (no path)")
if _pub.scheme == "http" and _pub.hostname not in ("localhost", "127.0.0.1", "::1") and os.environ.get("ENVELIQ_ALLOW_INSECURE_PUBLIC_URL") != "1":
    raise RuntimeError("ENVELIQ_PUBLIC_URL must use https:// unless it is localhost. Put Enveliq behind a TLS reverse proxy, "
                       "or on a network you trust set ENVELIQ_ALLOW_INSECURE_PUBLIC_URL=1 (see docs/NETWORK_ACCESS.md).")
PUBLIC_ORIGIN = f"{_pub.scheme}://{_pub.netloc}"
COOKIE_SECURE = os.environ.get("ENVELIQ_COOKIE_SECURE", "1" if _pub.scheme == "https" else "0") == "1"
SESSION_COOKIE = "__Host-enveliq_session" if COOKIE_SECURE else "enveliq_session"
FLOW_COOKIE = "__Host-enveliq_flow" if COOKIE_SECURE else "enveliq_flow"

ALLOWED_HOSTS = [h.strip() for h in os.environ.get(
    "ENVELIQ_ALLOWED_HOSTS", f"{_pub.hostname},localhost,127.0.0.1").split(",") if h.strip()]
ALLOWED_ORIGINS = {o.strip() for o in os.environ.get(
    "ENVELIQ_ALLOWED_ORIGINS", f"{PUBLIC_ORIGIN},http://localhost:{PORT},http://127.0.0.1:{PORT}").split(",") if o.strip()}

UUID_PATTERN = r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"


def _prepare_data_dir(path: Path) -> None:
    """Create the data directory privately, and refuse one that another user
    could have planted (wrong owner or a symlink), e.g. under a shared /tmp."""
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode):
        raise RuntimeError(f"Data directory {path} is a symlink; refusing to use it")
    if hasattr(os, "getuid") and info.st_uid != os.getuid():
        raise RuntimeError(f"Data directory {path} is owned by another user; refusing to use it")
    os.chmod(path, 0o700)


_prepare_data_dir(DATA_DIR)

logger = logging.getLogger("enveliq")
if not any(getattr(h, "_enveliq_redacting", False) for h in logger.handlers):
    handler = logging.StreamHandler()
    handler.addFilter(RedactingFilter())
    handler._enveliq_redacting = True  # type: ignore[attr-defined]
    logger.addHandler(handler)
logger.setLevel(logging.INFO)
if _pub.scheme == "http" and _pub.hostname not in ("localhost", "127.0.0.1", "::1"):
    logger.warning("Enveliq is set to be opened over plain http at %s. Passwords and sign-in cookies are not encrypted on the network; "
                   "use this only on a network you trust (docs/NETWORK_ACCESS.md).", PUBLIC_ORIGIN)
logger.propagate = False

# With a key file the vault unlocks itself, so the idle lock (which would just lock it
# again) is switched off. See docs/VAULT_KEY.md.
VAULT_KEY_FILE = os.environ.get("ENVELIQ_VAULT_KEY_FILE", "").strip()
VAULT_KEY_ENV = os.environ.get("ENVELIQ_VAULT_KEY", "").strip()
if VAULT_KEY_ENV.upper().startswith("PASTE-YOUR"):      # the placeholder in the install file was never replaced: same as no key
    VAULT_KEY_ENV = ""
AUTO_UNLOCK = bool(VAULT_KEY_FILE or VAULT_KEY_ENV)


def read_configured_key() -> str | None:
    """The vault key from the key file (which wins if both are set) or ENVELIQ_VAULT_KEY.
    None if the file is configured but absent; raises KeyFileError if unusable."""
    if VAULT_KEY_FILE:
        return keyfile.read_key(VAULT_KEY_FILE)
    if len(VAULT_KEY_ENV) < keyfile.MIN_CHARS:
        raise keyfile.KeyFileError("too_short")
    return VAULT_KEY_ENV

vault = SecureVault(DB_PATH, idle_lock_seconds=(10 ** 9 if AUTO_UNLOCK else IDLE_LOCK_SECONDS))
sessions = SessionManager(vault, ttl_seconds=SESSION_TTL_SECONDS)
flows = FlowStore()
users = UserService(vault)
unlock_limiter = UnlockRateLimiter()
setup_limiter = UnlockRateLimiter(max_attempts=10, global_max_attempts=30)
login_limiter = UnlockRateLimiter(max_attempts=10, global_max_attempts=200, max_tracked_clients=4096)
preview_leases = PreviewLeaseStore()
oidc_client = OIDCClient(allow_http=os.environ.get("ENVELIQ_OIDC_ALLOW_HTTP") == "1")
# The Android app can sign in with a passkey kept on the phone when this site trusts the app's signing key (docs/ANDROID.md, "Passkeys on the phone").
# The official app's key is built in; ENVELIQ_ANDROID_CERT_SHA256 adds more (for someone who builds the app with their own key).
ANDROID_CERTS = parse_cert_fingerprints(",".join(x for x in (OFFICIAL_ANDROID_CERT, os.environ.get("ENVELIQ_ANDROID_CERT_SHA256", "")) if x))
relying_party = RelyingParty(rp_id=_pub.hostname, origin=PUBLIC_ORIGIN, extra_origins=tuple(android_origin(f) for f in ANDROID_CERTS))
SSO_REDIRECT_URI = f"{PUBLIC_ORIGIN}/api/v1/auth/sso/callback"

# Whenever the vault locks (manual, idle timer or key replacement), drop every
# session and sign-in step, and wipe every decrypted preview held in RAM.
def _principal_for(user_id: str):
    """Who a remembered sign-in belongs to after a restart, or None if they are gone or switched off."""
    try:
        user = users.get(user_id)
    except (KeyError, VaultLocked):
        return None
    return None if user.get("disabled") else users.principal(user)


sessions.resolver = _principal_for
vault.add_lock_listener(sessions.revoke_all)
vault.add_lock_listener(flows.clear)
vault.add_lock_listener(preview_leases.clear)


# ---------- First-run setup code ----------
# Until setup is complete, anyone who can reach the server could otherwise
# claim it. Setup needs a one-time code that only someone with access to the
# server (its data folder or log) can read.

_setup_code: str | None = None


SETUP_CODE_MIN_LENGTH = 16


def usable_setup_code(value: str | None) -> str:
    """The setup code from the settings, or "" if it is empty, still the placeholder from the install file, or too short to be safe.
    A guessable code would let anyone who can reach the page claim the server, so in that case a random one is made instead."""
    code = (value or "").strip()
    if not code:
        return ""
    if "change-me" in code.lower() or len(code) < SETUP_CODE_MIN_LENGTH:
        logger.warning("ENVELIQ_SETUP_CODE was ignored because it is the placeholder or shorter than %d characters. A random setup code was made instead; it is in %s.", SETUP_CODE_MIN_LENGTH, SETUP_CODE_PATH)
        return ""
    return code


def _init_setup_code() -> None:
    global _setup_code
    if vault.is_initialized():
        SETUP_CODE_PATH.unlink(missing_ok=True)
        _setup_code = None
        return
    code = usable_setup_code(os.environ.get("ENVELIQ_SETUP_CODE")) or (
        SETUP_CODE_PATH.read_text().strip() if SETUP_CODE_PATH.exists() else secrets.token_urlsafe(18))
    SETUP_CODE_PATH.write_text(code + "\n")
    os.chmod(SETUP_CODE_PATH, 0o600)
    _setup_code = code
    logger.warning("Enveliq is not set up yet. Open %s/setup and enter the setup code from %s", PUBLIC_ORIGIN, SETUP_CODE_PATH)


def check_setup_code(candidate: str) -> bool:
    return bool(_setup_code) and secrets.compare_digest(candidate.strip(), _setup_code)


def setup_completed() -> None:
    global _setup_code
    _setup_code = None
    SETUP_CODE_PATH.unlink(missing_ok=True)


_init_setup_code()

DEFAULT_ATTACHMENT_POLICY: dict[str, Any] = {
    "preview_enabled": True,
    "max_source_bytes": 25 * 1024 * 1024,
    "max_preview_bytes": 10 * 1024 * 1024,
    "preview_ttl_seconds": 300,
    "global_ram_cap_bytes": 64 * 1024 * 1024,
}


def apply_attachment_policy(policy: dict[str, Any] | None) -> dict[str, Any]:
    effective = {**DEFAULT_ATTACHMENT_POLICY, **(policy or {})}
    preview_leases.configure(
        enabled=bool(effective["preview_enabled"]),
        ttl_seconds=int(effective["preview_ttl_seconds"]),
        max_total_bytes=int(effective["global_ram_cap_bytes"]),
        max_item_bytes=int(effective["max_preview_bytes"]),
    )
    return effective


_auto = {"problem": None, "at": 0.0}
_auto_lock = threading.Lock()


def try_auto_unlock() -> None:
    """Open the vault with the key file, if one is configured. Sets a fixed problem
    code (missing, unreadable, too_short, wrong) instead of raising; never logs the key."""
    if not AUTO_UNLOCK or not vault.is_initialized() or vault.is_unlocked():
        return
    with _auto_lock:
        if vault.is_unlocked() or time.monotonic() - _auto["at"] < 3:
            return
        _auto["at"] = time.monotonic()
        try:
            key = read_configured_key()
        except keyfile.KeyFileError as err:
            _auto["problem"] = err.code
            logger.error("Cannot unlock from the key file: %s", err.code)
            return
        if key is None:
            _auto["problem"] = "missing"
            logger.error("Cannot unlock from the key file: the file does not exist")
            return
        try:
            vault.unlock(key)
        except InvalidPassphrase:
            _auto["problem"] = "wrong"
            logger.error("Cannot unlock from the key file: it does not match this vault")
            return
        _auto["problem"] = None
        if VAULT_KEY_FILE and keyfile.too_open(VAULT_KEY_FILE):
            logger.warning("The vault key file can be read by other users on this machine; restrict it (chmod 600).")
        load_attachment_policy()
        vault.audit({"event": "vault_unlocked", "client": "key file", "at": time.time()})
        logger.info("Vault unlocked from the configured key")


REQUIRE_VAULT_KEY = True       # a new install must be given a vault key; only the automatic tests switch this off

NEED_VAULT_KEY = ("This server was not given a vault key. Make one with: openssl rand -hex 32 (or the Docker command in the setup guide), "
                  "put it in the .env file as ENVELIQ_VAULT_KEY=..., keep a copy somewhere safe, then run: docker compose up -d. Then reload this page.")


def vault_key_for_setup(passphrase: str | None) -> str:
    """The secret the new vault is created with: the key file's key (made if absent). A new install without a vault key is refused."""
    if not AUTO_UNLOCK:
        if REQUIRE_VAULT_KEY:
            raise ValueError(NEED_VAULT_KEY)
        if not passphrase:
            raise ValueError("Enter a vault passphrase.")
        return passphrase
    try:
        key = read_configured_key()
        if key is not None:
            return key
        return keyfile.create_key(VAULT_KEY_FILE)
    except keyfile.KeyFileError as err:
        raise ValueError({
            "unreadable": "Enveliq cannot read the vault key file. Check its permissions.",
            "too_short": "The vault key is too short. Use a long random key (at least 32 characters), for example: openssl rand -base64 48",
            "cannot_create": "Enveliq could not create the vault key file. Make its folder writable, or create the file yourself with: openssl rand -base64 48 > FILE",
        }[err.code]) from None


def load_attachment_policy() -> None:
    try:
        apply_attachment_policy(vault.get_global("attachment-policy"))
    except VaultLocked:
        pass


@asynccontextmanager
async def lifespan(_: FastAPI):
    try_auto_unlock()
    vault.start_idle_watchdog()
    auto_sync.start()
    backups.start()
    reminders.start()
    scheduled_sender.start()
    rss_refresher.start()
    sync.start()
    reporter.start()
    reporter.event("app_started")
    try:
        yield
    finally:
        reporter.stop()
        auto_sync.stop()
        backups.stop()
        reminders.stop()
        scheduled_sender.stop()
        rss_refresher.stop()
        sync.stop()
        outbox.stop()
        vault.stop_idle_watchdog()
        vault.lock()


app = FastAPI(title="Enveliq", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
app.add_middleware(HostGuardMiddleware, allowed_hosts=ALLOWED_HOSTS, local_ip_path=INBOUND_WS_PATH, local_ip_post_path=INBOUND_WEBHOOK_PATH)
# Added last, so it runs first: size, type and origin checks happen before
# anything parses the request.
app.add_middleware(RequestGuardMiddleware, max_body_bytes=MAX_BODY_BYTES, allowed_origins=ALLOWED_ORIGINS)

API_CSP = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"
PAGE_CSP = ("default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; manifest-src 'self'; "
            "form-action 'self'; frame-ancestors 'none'; base-uri 'none'")
# The inbox page is still the single-file prototype with inline script and
# styles; it gets a looser policy until it is split into bundled files.
APP_CSP = ("default-src 'none'; script-src 'self' 'unsafe-inline'; style-src 'unsafe-inline'; img-src 'self' data: blob:; "
           "connect-src 'self'; frame-src 'self'; manifest-src 'self'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'")


@app.middleware("http")
async def secure_headers(request: Request, call_next):
    response: Response = await call_next(request)
    path = request.url.path
    response.headers["X-Content-Type-Options"] = "nosniff"
    framed = request.method == "GET" and path.startswith("/api/") and path.endswith("/original/html") and "Content-Security-Policy" in response.headers
    response.headers["X-Frame-Options"] = "SAMEORIGIN" if framed else "DENY"       # only the formatted email may be shown in a frame of our own page
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(), payment=(), usb=()"
    response.headers["Cache-Control"] = "no-store"
    response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
    response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
    if COOKIE_SECURE:
        response.headers["Strict-Transport-Security"] = "max-age=31536000"
    if not framed:      # the formatted email brings its own, stricter policy (backend/mail/htmlview.py)
        response.headers["Content-Security-Policy"] = API_CSP if path.startswith("/api/") else (APP_CSP if path == "/" else PAGE_CSP)
    return response


# ---------- Sessions and identity ----------

def set_cookie(response: Response, name: str, value: str, *, max_age: int) -> None:
    response.set_cookie(name, value, max_age=max_age, httponly=True, secure=COOKIE_SECURE, samesite="lax", path="/")


def clear_cookie(response: Response, name: str) -> None:
    response.delete_cookie(name, path="/", secure=COOKIE_SECURE, httponly=True, samesite="lax")


def any_session(request: Request) -> Session:
    """A signed-in session, including one that must still set up a second
    factor. The user record is re-read on every request, so disabling a user
    or changing their role takes effect immediately."""
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise HTTPException(status_code=401, detail="Sign in to continue")
    session = sessions.get(token)
    try:
        user = users.get(session.principal.user_id)
    except KeyError as exc:
        sessions.revoke(token)
        raise HTTPException(status_code=401, detail="Sign in to continue") from exc
    if user.get("disabled"):
        sessions.revoke(token)
        raise HTTPException(status_code=401, detail="This account is disabled")
    principal = users.principal(user)
    sessions.update_principal(token, principal)
    session.principal = principal
    if session.state == "full" and session.auth_method != "sso" and users.mfa_required(user) and not users.has_mfa(user):
        session.state = "enroll"  # policy tightened since this session started
    return session


def full_session(session: Session = Depends(any_session)) -> Session:
    if session.state != "full":
        raise HTTPException(status_code=403, detail="Set up two-factor sign-in to continue")
    return session


def admin_session(session: Session = Depends(full_session)) -> Session:
    if not session.principal.is_admin:
        raise HTTPException(status_code=403, detail="Administrator access required")
    return session


current_session = full_session


def peek_full_session(request: Request) -> Session | None:
    try:
        session = sessions.peek(request.cookies.get(SESSION_COOKIE))
        if session is None or session.state != "full" or not vault.is_unlocked():
            return None
        user = users.get(session.principal.user_id)
        return None if user.get("disabled") else session
    except (KeyError, VaultLocked):
        return None


def sso_settings() -> OIDCSettings | None:
    try:
        return OIDCSettings.from_record(vault.get_global("sso-oidc"))
    except VaultLocked:
        return None


def sso_public() -> dict[str, Any]:
    settings = sso_settings()
    return {"enabled": bool(settings), "label": settings.label if settings else None}


def remember_seconds() -> int:
    """How long a "keep me signed in on this device" sign-in lasts, in seconds, or 0 when it is off.

    It is off until an administrator sets a number of days (at most 14), and it only works while Enveliq opens its own
    vault from a key file: otherwise the vault locks itself when idle and signs everyone out, whatever the number says."""
    if not AUTO_UNLOCK:
        return 0
    try:
        days = users.policy().get("remember_days", 0)
    except VaultLocked:
        return 0
    return int(days) * 86400 if isinstance(days, int) and not isinstance(days, bool) and 0 < days <= 14 else 0


def delete_user_data(user_id: str) -> None:
    """Remove every mailbox a user owns, with its messages and previews, and the person's own messages to other people."""
    messagebook.forget_user(user_id)
    inboundbook.forget_user(user_id)
    writehelpbook.forget_user(user_id)
    stylebook.forget_user(user_id)
    digestbook.forget_user(user_id)
    importantbook.forget_user(user_id)
    savedbook.forget_user(user_id)
    draftbook.forget_user(user_id)
    scheduledbook.forget_user(user_id)
    rulebook.forget_user(user_id)
    senderbook.forget_user(user_id)
    junkbook.forget_user(user_id)
    finder = getattr(mail_ctx, "find_index", None)
    if finder is not None:
        finder.delete_user(user_id)                                     # their search word list, if they had one
    vault.set_global("enveliq-opened-v1:" + user_id, {})          # which emails this person has opened (the new-mail glow)
    vault.set_global("mail-view-v1:" + user_id, {})               # their saved layout
    vault.set_global("mail-context-v1:" + user_id, {})            # last selected email
    for account in vault.list_accounts():
        if account.get("owner_user_id") == user_id:
            preview_leases.purge_account(account["id"])
            vault.delete_account(account["id"])


ctx = SimpleNamespace(
    vault=vault, users=users, sessions=sessions, flows=flows, oidc=oidc_client, rp=relying_party,
    login_limiter=login_limiter, setup_limiter=setup_limiter,
    session_cookie=SESSION_COOKIE, flow_cookie=FLOW_COOKIE, set_cookie=set_cookie, clear_cookie=clear_cookie,
    any_session=any_session, full_session=full_session, admin_session=admin_session,
    peek_full_session=peek_full_session, sso_settings=sso_settings, sso_public=sso_public,
    sso_redirect_uri=SSO_REDIRECT_URI, check_setup_code=check_setup_code, setup_completed=setup_completed,
    delete_user_data=delete_user_data, vault_key_for_setup=vault_key_for_setup,
    remember_seconds=remember_seconds, remember_possible=AUTO_UNLOCK,
)
app.include_router(build_router(ctx))


# ---------- Mailbox access helpers ----------

def account_visible_to(account: dict[str, Any], principal: Principal) -> bool:
    owner = account.get("owner_user_id")
    privacy = account.get("privacy") or {}
    visibility = privacy.get("visibility", "private")
    shared = privacy.get("shared_with", [])
    return owner == principal.user_id or visibility == "household" or principal.user_id in shared


def account_owned_by(account: dict[str, Any], principal: Principal) -> bool:
    return account.get("owner_user_id") == principal.user_id


def load_account(account_id: str, principal: Principal, *, owner_only: bool, action: str = "") -> dict[str, Any]:
    """Fetch an account the caller may see. Accounts the caller cannot see get
    the same 404 as accounts that do not exist, so ids cannot be probed."""
    try:
        account = vault.get_account(account_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Account not found") from exc
    if not account_visible_to(account, principal):
        raise HTTPException(status_code=404, detail="Account not found")
    if owner_only and not account_owned_by(account, principal):
        raise HTTPException(status_code=403, detail=f"Only the mailbox owner can {action or 'do this'}")
    return account


AccountId = Annotated[str, PathParam(pattern=UUID_PATTERN)]
MessageId = Annotated[str, PathParam(pattern=UUID_PATTERN)]

OWNER_ACCOUNT_FIELDS = (
    "id", "provider", "display_name", "email_address", "auth_method", "server", "port",
    "username", "settings", "privacy", "owner_user_id", "created_at",
)
SHARED_ACCOUNT_FIELDS = ("id", "provider", "display_name", "email_address", "auth_method", "owner_user_id")


def public_account(account: dict[str, Any], principal: Principal) -> dict[str, Any]:
    """Allowlist of fields the browser may see. Credentials never leave the
    backend; household members who can see a shared mailbox get only what
    they need to recognise it, not its server or login details."""
    if account_owned_by(account, principal):
        out = {k: account.get(k) for k in OWNER_ACCOUNT_FIELDS if k in account}
        out["password_set"] = bool(account.get("password"))
        out["oauth_connected"] = bool(account.get("oauth_refresh_token"))
        out["check_address"] = checkbox.account_id() == account.get("id")      # the forwarding-only mailbox is not read as an inbox
        return out
    out = {k: account.get(k) for k in SHARED_ACCOUNT_FIELDS if k in account}
    out["privacy"] = {"visibility": (account.get("privacy") or {}).get("visibility", "private")}
    return out


def public_message(message: dict[str, Any]) -> dict[str, Any]:
    # Provider locators (for the message and its attachments) remain
    # backend-only. They can encode IMAP UIDs, section identifiers or provider
    # object IDs and are unnecessary in the UI.
    clean = dict(message)
    clean.pop("source_locator", None)
    attachments = []
    for item in clean.get("attachments", []) or []:
        safe = dict(item)
        safe.pop("remote_locator", None)
        attachments.append(safe)
    clean["attachments"] = attachments
    return clean


# ---------- Proton Bridge mailboxes ----------

bridge = Bridge()
reporter = Reporter(vault)
mail_service = MailService(bridge, reporter=reporter)
microsoft = Microsoft(vault)
mail_service.microsoft = microsoft
MICROSOFT_REDIRECT_URI = f"{PUBLIC_ORIGIN}/api/v1/mail/microsoft/callback"
outbox = Outbox(vault, mail_service)
auto_sync = AutoSync(vault, mail_service, int(os.environ["ENVELIQ_SYNC_MINUTES"]) if os.environ.get("ENVELIQ_SYNC_MINUTES", "").strip().lstrip("-").isdigit() else None)
checkbox = CheckBox(vault, mail_service)
mail_service.check_id = checkbox.account_id
auto_sync.checker = checkbox
taskbook = TaskBook(vault)
shipbook = ShipBook(vault)
rssbook = RssBook(vault)
inboundbook = InboundBook(vault)
rss_refresher = RssRefresher(vault, rssbook)
subbook = SubBook(vault, taskbook.timezone_of)
importantbook = ImportantPeople(vault)
savedbook = SavedWriting(vault)
draftbook = Drafts(vault)
scheduledbook = ScheduledMail(vault)
scheduled_sender = ScheduledSender(vault, mail_service, scheduledbook, vault.audit)
rulebook = Rules(vault)
tripbook = TripBook(vault, taskbook.timezone_of)
messagebook = MessageBook(vault, users)
writehelpbook = WriteHelpBook(vault)
stylebook = StyleBook(vault, mail_service)
mail_service.shipments = shipbook
tagservice = TagService(mail_service, vault, lambda user: bool(user) and features.effective(vault, user)['tags'])
mail_service.tags_sync = tagservice.sync
mail_service.subscriptions = subbook
mail_service.trips = tripbook
waitbook = WaitBook(vault)
mail_service.waits = waitbook
junkbook = JunkBook(vault, mail_service)
senderbook = SenderBook(vault, mail_service, rulebook, importantbook, taskbook.held)
notifier = Notifier(vault)
_click = "" if _pub.hostname in ("localhost", "127.0.0.1", "::1") else PUBLIC_ORIGIN
reminders = Reminders(vault, taskbook, notifier, _click)
_mailalerts = MailAlerts(notifier, _click, taskbook.timezone_of, important=importantbook)
auto_sync.mail_alerts = _mailalerts
digestbook = DigestBook(vault, notifier, taskbook, _mailalerts, importantbook, _click)
reminders.subs = subbook
dailysummary = DailySummary(vault, shipbook, waitbook, subbook, taskbook.held)
reminders.summary = dailysummary
reminders.digest_tick = digestbook.tick
auto_sync.digest_hold = lambda uid: digestbook.hold_pass(uid) if digestbook.enabled(uid) else 0
reminders.style_tick = lambda uid: (mail_service.refresh_ai(vault), stylebook.maintain(uid, mail_service.summariser))
sync = Sync(vault, taskbook, notifier, PUBLIC_ORIGIN)
backups = BackupManager(vault, DATA_DIR / "backups")
sync.trips = tripbook
tripbook.changed = sync.mark
notifier.origin = PUBLIC_ORIGIN
mail_service.holds = taskbook.held


class _Mailer:
    """Lets the Email reminder channel write to the person's own mailbox, and nowhere else."""

    @staticmethod
    def _mine(user_id: str) -> list[dict[str, Any]]:
        return [a for a in vault.list_accounts() if a.get("owner_user_id") == user_id and a.get("email_address")]

    def addresses(self, user_id: str) -> list[str]:
        return [str(a["email_address"]) for a in self._mine(user_id)]

    def send(self, user_id: str, to: str, subject: str, body: str) -> None:
        mine = self._mine(user_id)
        account = next((a for a in mine if str(a["email_address"]).lower() == to.lower()), None)
        if account is None:
            raise OutboundError("not_allowed", "Reminder emails go only to your own mailboxes.")
        try:
            msg, chosen, recipients = mail_service.build_new(account, [str(account["email_address"])], [], [], subject, body, None, [])
            msg[marks.HEADER] = marks.make(vault, str(msg["Message-ID"]))
            mail_service.bridge.send(mail_service.target(account), msg, chosen, recipients)
        except BridgeError:
            raise OutboundError("error", "The mailbox would not send it. Check the mailbox connection.") from None


notifier.mailer = _Mailer()
mail_ctx = SimpleNamespace(
    checkbox=checkbox,
    agent=Agent(vault, mail_service.summariser), tasks=taskbook, shipping=shipbook, rss=rssbook, inbound=inboundbook, allowed_origins=ALLOWED_ORIGINS, tags=tagservice, subscriptions=subbook, junk=junkbook, senders=senderbook, important=importantbook, saved_writing=savedbook, drafts=draftbook, scheduled=scheduledbook, rules=rulebook, trips=tripbook, messages=messagebook, writehelp=writehelpbook, style=stylebook, digest=digestbook, waiting=waitbook, summary=dailysummary, sync=sync, notifier=notifier, click_url=_click, vault=vault, users=users, mail=mail_service, bridge=bridge, auto_sync=auto_sync, outbox=outbox, full_session=full_session, admin_session=admin_session, load_account=load_account,
    microsoft=microsoft,
)
app.include_router(build_mail_router(mail_ctx))
app.include_router(build_extra_router(mail_ctx))          # after the main router: shares its send limits
app.include_router(build_find_router(mail_ctx))           # after the extra router: uses its summary queue
app.include_router(build_task_router(mail_ctx))
app.include_router(build_shipping_router(mail_ctx))
app.include_router(build_rss_router(mail_ctx))
app.include_router(build_tag_router(mail_ctx))
app.include_router(build_subscriptions_router(mail_ctx))
app.include_router(build_important_router(mail_ctx))
app.include_router(build_saved_writing_router(mail_ctx))
app.include_router(build_drafts_router(mail_ctx))
app.include_router(build_scheduled_router(mail_ctx))
app.include_router(build_rules_router(mail_ctx))
app.include_router(build_trips_router(mail_ctx))
app.include_router(build_waiting_router(mail_ctx))
app.include_router(build_junk_router(mail_ctx))
app.include_router(build_senders_router(mail_ctx))
app.include_router(build_check_router(mail_ctx))
def apply_rules(account: dict, arrived: list) -> None:
    """Mail that has just arrived: apply the owner's rules (archive it, or mark it reviewed). Nothing else about the
    email is read. Mail from the owner's important people is never touched, and a rule never bins anything (sending to Junk is
    not binning: the email stays in the mailbox's Junk folder)."""
    user = account.get("owner_user_id")
    if not user:
        return
    for item in arrived:
        rule = rulebook.match(user, item["sender_address"], item["subject"])
        if not rule or importantbook.contains(user, item["sender_address"]):
            continue
        try:
            resolve_message(account["id"], item["id"], rule["action"], user, by="rule")
        except BridgeError:
            break                              # the mailbox cannot be changed right now: leave the rest where they are
        except KeyError:
            continue


mail_service.on_new = apply_rules
exporter = build_exporter(
    vault, users, public_account=public_account, public_message=public_message, principal_of=users.principal,
    prefs=lambda uid: review.user_prefs(vault, uid),
    contacts_of=lambda uid: [contacts_mod._public(a, p) for a, p in contacts_mod._load(vault, uid).items()],
    threads_of=lambda uid: [t for t in (_thread_or_none(uid, tid) for tid in messagebook._index(uid)) if t],
    notify_state=lambda uid: {"settings": notifier.settings(uid), "channels_on": notifier.enabled_channels(uid)},
    sync_state=lambda uid: sync.overview(uid))


def _thread_or_none(uid: str, tid: str):
    try:
        return messagebook._thread(tid, uid)
    except KeyError:
        return None


app.include_router(build_backup_router(SimpleNamespace(
    vault=vault, users=users, sessions=sessions, backups=backups, login_limiter=login_limiter, exporter=exporter,
    admin_session=admin_session, full_session=full_session)))
app.include_router(build_messages_router(mail_ctx))
app.include_router(build_inbound_router(mail_ctx))
app.include_router(build_writehelp_router(mail_ctx))
app.include_router(build_style_router(mail_ctx))
app.include_router(build_digest_router(mail_ctx))
app.include_router(build_notify_router(mail_ctx))
app.include_router(build_agent_router(mail_ctx))
for _r in build_sync_router(mail_ctx):
    app.include_router(_r)
app.include_router(build_gcal_router(SimpleNamespace(
    vault=vault, sync=sync, flows=flows, full_session=full_session, admin_session=admin_session, set_cookie=set_cookie, clear_cookie=clear_cookie,
    flow_cookie=FLOW_COOKIE, peek_full_session=peek_full_session, google_redirect_uri=f"{PUBLIC_ORIGIN}/api/v1/sync/google/callback",
)))
app.include_router(build_microsoft_router(SimpleNamespace(
    vault=vault, mail=mail_service, bridge=bridge, microsoft=microsoft, flows=flows, full_session=full_session, admin_session=admin_session,
    set_cookie=set_cookie, clear_cookie=clear_cookie, flow_cookie=FLOW_COOKIE, peek_full_session=peek_full_session, microsoft_redirect_uri=MICROSOFT_REDIRECT_URI,
)))
app.include_router(build_reporting_router(SimpleNamespace(vault=vault, reporter=reporter, admin_session=admin_session)))


# ---------- Server state and vault lifecycle ----------

@app.get("/api/v1/health")
def health():
    return {"ok": True}


@app.get("/api/v1/status")
def status_endpoint():
    # Unauthenticated, so it says only what the sign-in, setup and unlock pages need to choose what to show.
    # No version, no encryption settings and no public address: those are for signed-in people (/api/v1/system).
    try_auto_unlock()
    unlocked = vault.is_unlocked()
    initialized = vault.is_initialized()
    out: dict[str, Any] = {
        "initialized": initialized, "unlocked": unlocked, "setup_required": not initialized,
        "sign_in": {"password": True, "passkeys": True, "sso": sso_public() if unlocked else {"enabled": False, "label": None},
                    "remember": bool(unlocked and remember_seconds())},
    }
    if not unlocked:                      # only the setup and unlock pages ask, and only while the vault is closed
        out["auto_unlock"] = AUTO_UNLOCK
        out["vault_key_needed"] = bool(REQUIRE_VAULT_KEY and not AUTO_UNLOCK and not initialized)
        out["auto_unlock_problem"] = _auto["problem"] if AUTO_UNLOCK else None
    return out


update_checker = UpdateChecker(VERSION)


def update_notice_enabled() -> bool:
    """On unless an administrator switched it off (Administration, Updates). Needs the vault open to be read."""
    try:
        return bool((vault.get_global("update-notice") or {}).get("enabled", True))
    except VaultLocked:
        return False


@app.get("/api/v1/admin/update-notice")
def get_update_notice(session: Session = Depends(admin_session)):
    enabled = update_notice_enabled()
    if enabled:
        update_checker.maybe_refresh()
    return {"enabled": enabled, "current": VERSION, "update": update_checker.newer() if enabled else None}


@app.put("/api/v1/admin/update-notice")
def put_update_notice(body: UpdateNoticeBody, session: Session = Depends(admin_session)):
    vault.set_global("update-notice", {"enabled": body.enabled})
    vault.audit({"event": "update_notice_changed", "actor_user_id": session.principal.user_id, "enabled": body.enabled, "at": time.time()})
    if body.enabled:
        update_checker.maybe_refresh()
    return {"enabled": body.enabled, "current": VERSION, "update": update_checker.newer() if body.enabled else None}


@app.get("/api/v1/app-update")
def app_update(session: Session = Depends(full_session)):
    """The newest published release, for the Android app to compare with its own number. Anyone signed in may ask.
    The phone never contacts GitHub: this server already does (once a day), and only a version number and Enveliq's own
    release page address are passed on. Empty when the administrator switched the update notice off."""
    if not update_notice_enabled():
        return {"latest": None}
    update_checker.maybe_refresh()
    return {"latest": dict(update_checker.latest) if update_checker.latest else None}


_apk_lock = threading.Lock()


@app.get("/api/v1/app-update/apk")
def app_update_apk(session: Session = Depends(full_session)):
    """The newest Android app, passed on from Enveliq's own releases so the phone never contacts GitHub. The server
    checks it against the checksum published with it first. Nothing about the person is sent to GitHub."""
    import tempfile
    from starlette.background import BackgroundTask
    from .update_check import ApkError, fetch_apk
    latest = dict(update_checker.latest) if update_notice_enabled() and update_checker.latest else None
    if not latest:
        raise HTTPException(status_code=404, detail="No update is offered.")
    if not _apk_lock.acquire(blocking=False):
        raise HTTPException(status_code=429, detail="Another download is already running. Try again in a minute.")
    tmp = tempfile.NamedTemporaryFile(prefix="enveliq-apk-", suffix=".apk", delete=False)
    try:
        try:
            digest = fetch_apk(latest["version"], tmp)
        except ApkError:
            raise HTTPException(status_code=502, detail="The new version could not be fetched safely. Try again later.")
    except BaseException:
        tmp.close()
        os.unlink(tmp.name)
        raise
    finally:
        _apk_lock.release()
    tmp.close()
    return FileResponse(tmp.name, media_type="application/vnd.android.package-archive", filename="Enveliq-" + latest["version"] + ".apk",
                        headers={"X-Enveliq-Sha256": digest}, background=BackgroundTask(os.unlink, tmp.name))


@app.get("/api/v1/system")
def system_endpoint(session: Session = Depends(full_session)):
    """What the inbox and the Security page show about this Enveliq. Signed-in people only; the technical
    detail (encryption settings, public address, key-file unlock) is for administrators."""
    out: dict[str, Any] = {
        "version": VERSION,
        "cipher": "AES-256-GCM", "kdf": "Argon2id",
        "idle_lock_seconds": 0 if AUTO_UNLOCK else vault.idle_lock_seconds,
        "raw_message_body_persistence": False, "raw_attachment_persistence": False,
    }
    if session.principal.is_admin and update_notice_enabled():
        update_checker.maybe_refresh()            # at most once a day, in the background
        update = update_checker.newer()
        if update:
            out["update"] = update                # administrators only: they are the ones who update Enveliq
    if session.principal.is_admin:
        out.update({"public_url": PUBLIC_ORIGIN, "auto_unlock": AUTO_UNLOCK, "crypto": SecureVault.export_public_crypto_metadata(),
                    "attachments": {"raw_persistence": False, "preview_mode": "safe-derivative-in-ram"}})
    return out


@app.post("/api/v1/unlock")
def unlock_endpoint(body: UnlockRequest, request: Request):
    """Unlock the vault after a restart. This does not sign anyone in: people
    sign in separately once the vault is open."""
    client_key = request.client.host if request.client else "unknown"
    if not vault.is_initialized():
        raise HTTPException(status_code=409, detail="Enveliq is not set up yet")
    unlock_limiter.acquire(client_key)  # counts this attempt before checking it
    try:
        vault.unlock(body.passphrase.get_secret_value())
    except InvalidPassphrase as exc:
        logger.warning("Failed vault unlock attempt from client=%s", client_key)
        raise HTTPException(status_code=401, detail="That vault passphrase is not correct") from exc
    unlock_limiter.succeeded(client_key)
    load_attachment_policy()
    vault.audit({"event": "vault_unlocked", "client": client_key, "at": time.time()})
    logger.info("Vault unlocked")
    return {"status": vault.status()}


@app.post("/api/v1/lock", status_code=204)
def lock_endpoint(session: Session = Depends(admin_session)):
    if AUTO_UNLOCK:
        raise HTTPException(status_code=409, detail="Locking is turned off because Enveliq unlocks itself from a key file.")
    # Locking affects every user, so it is an administrator action. Audit
    # first, then erase key material; the vault's lock listeners revoke all
    # sessions and sign-in steps and wipe preview leases.
    vault.audit({"event": "vault_locked", "actor_user_id": session.principal.user_id, "at": time.time()})
    vault.lock()
    logger.info("Vault locked")
    return Response(status_code=204)


# ---------- Pages ----------

def _page_redirect(request: Request) -> str | None:
    if not vault.is_initialized():
        return "/setup"
    try_auto_unlock()
    if not vault.is_unlocked():
        return "/unlock"
    session = sessions.peek(request.cookies.get(SESSION_COOKIE))
    if session is None:
        return "/login"
    if session.state != "full" or peek_full_session(request) is None:
        return "/account?enroll=1" if session.state == "enroll" else "/login"
    return None


@app.get("/", include_in_schema=False)
def app_page(request: Request):
    target = _page_redirect(request)
    if target:
        return RedirectResponse(target, status_code=303)
    return FileResponse(APP_PAGE, media_type="text/html")


for _route in ("/setup", "/unlock", "/login", "/account", "/admin", "/mailboxes", "/welcome", "/security", "/terms", "/privacy", "/app-signin"):
    def _auth_page(request: Request) -> FileResponse:
        return FileResponse(WEB_DIR / "auth.html", media_type="text/html")
    app.add_api_route(_route, _auth_page, methods=["GET"], include_in_schema=False)

@app.get("/.well-known/assetlinks.json", include_in_schema=False)
def asset_links_file():
    """Tells Android this site trusts the Enveliq app for passkeys. Public by design (anyone can read it) and holds no secret:
    it only lists the public fingerprint of the app's signing certificate."""
    if not ANDROID_CERTS:
        raise HTTPException(status_code=404, detail="Not found")
    return JSONResponse(passkey_asset_links(ANDROID_CERTS), headers={"Cache-Control": "public, max-age=3600"})


@app.get("/sw.js", include_in_schema=False)
def service_worker():
    """The small script that shows reminder pop-ups. It must be served from the top so it covers every page."""
    try:
        text = (WEB_DIR / "static" / "sw.js").read_text(encoding="utf-8")
    except OSError:
        raise HTTPException(status_code=404, detail="Not found")
    return Response(text, media_type="text/javascript", headers={"Cache-Control": "no-cache", "Service-Worker-Allowed": "/"})


MANIFEST = {
    "id": "/", "name": "Enveliq", "short_name": "Enveliq", "description": "Turn email into clarity.",
    "start_url": "/", "scope": "/", "display": "standalone", "background_color": "#0d0f14", "theme_color": "#0d0f14",
    "icons": [
        {"src": "/brand/enveliq-icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any"},
        {"src": "/brand/enveliq-icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any"},
        {"src": "/brand/enveliq-icon-maskable-512.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable"},
    ],
}


@app.get("/manifest.webmanifest", include_in_schema=False)
def web_manifest():
    """Lets a phone or computer install Enveliq as an app with its own icon. Same for everyone; holds nothing private."""
    return JSONResponse(MANIFEST, media_type="application/manifest+json")


@app.get("/embed.js", include_in_schema=False)
def embed_script():
    """The setup guide, account and administration pages as one module, for the pop-ups on the inbox page.
    Built from the same two files the standalone pages use, so there is one copy of the code."""
    try:
        text = "\n".join((WEB_DIR / "static" / name).read_text(encoding="utf-8") for name in ("welcome.js", "auth.js"))
    except OSError:
        raise HTTPException(status_code=404, detail="Not found")
    return Response(text, media_type="text/javascript", headers={"Cache-Control": "no-cache"})


if (WEB_DIR / "static").is_dir():
    app.mount("/static", StaticFiles(directory=WEB_DIR / "static"), name="static")
if BRAND_WEB_DIR.is_dir():
    app.mount("/brand", StaticFiles(directory=BRAND_WEB_DIR), name="brand")


# ---------- Accounts ----------

@app.get("/api/v1/accounts")
def list_accounts_endpoint(session: Session = Depends(current_session)):
    visible = [a for a in vault.list_accounts() if account_visible_to(a, session.principal)]
    return [public_account(a, session.principal) for a in visible]


@app.post("/api/v1/accounts", status_code=201)
def create_account_endpoint(body: AccountCreate, session: Session = Depends(current_session)):
    data = body.model_dump(mode="python")
    data["password"] = body.password.get_secret_value() if body.password else None
    data["oauth_refresh_token"] = body.oauth_refresh_token.get_secret_value() if body.oauth_refresh_token else None
    data["owner_user_id"] = session.principal.user_id  # server-side binding, never client supplied
    data["privacy"] = {"visibility": "private", "shared_with": []}
    data["created_at"] = time.time()
    account_id = vault.create_account(data)
    vault.audit({"event": "account_created", "actor_user_id": session.principal.user_id, "account_id": account_id, "at": time.time()})
    return public_account(vault.get_account(account_id), session.principal)


@app.patch("/api/v1/accounts/{account_id}")
def patch_account_endpoint(body: AccountPatch, account_id: AccountId, session: Session = Depends(current_session)):
    account = load_account(account_id, session.principal, owner_only=True, action="change account settings")

    patch = body.model_dump(exclude_unset=True, mode="python")
    # null means "leave unchanged". Above all, a null credential must never
    # silently wipe the stored password or token.
    patch = {k: v for k, v in patch.items() if v is not None}
    if "password" in patch:
        patch["password"] = body.password.get_secret_value()  # type: ignore[union-attr]
    if "oauth_refresh_token" in patch:
        patch["oauth_refresh_token"] = body.oauth_refresh_token.get_secret_value()  # type: ignore[union-attr]
    account.update(patch)
    account.pop("id", None)
    vault.update_account(account_id, account)
    vault.audit({"event": "account_updated", "actor_user_id": session.principal.user_id, "account_id": account_id, "at": time.time()})
    return public_account(vault.get_account(account_id), session.principal)


@app.delete("/api/v1/accounts/{account_id}", status_code=204)
def delete_account_endpoint(account_id: AccountId, session: Session = Depends(current_session)):
    load_account(account_id, session.principal, owner_only=True, action="disconnect this account")
    vault.audit({"event": "account_disconnected", "actor_user_id": session.principal.user_id, "account_id": account_id, "at": time.time()})
    preview_leases.purge_account(account_id)
    vault.delete_account(account_id)
    return Response(status_code=204)


# ---------- Retained messages ----------

@app.post("/api/v1/accounts/{account_id}/messages", status_code=201)
def create_retained_message_endpoint(body: RetainedMessageCreate, account_id: AccountId, session: Session = Depends(current_session)):
    load_account(account_id, session.principal, owner_only=True, action="write retained message data")
    message_id = vault.create_message(account_id, body.model_dump(mode="python"))
    return {"id": message_id}


@app.get("/api/v1/accounts/{account_id}/messages")
def list_retained_messages_endpoint(account_id: AccountId, session: Session = Depends(current_session)):
    account = load_account(account_id, session.principal, owner_only=False)
    if account_owned_by(account, session.principal):
        review.purge_expired(vault, account)
    stored = vault.list_messages(account_id)
    if account_owned_by(account, session.principal) and any(m.get("ai_pending") for m in stored):
        mail_service.enqueue_held(vault, account)          # after a restart the line is empty: put the waiting mail back in it
        stored = vault.list_messages(account_id)           # (mail that is no longer waited for has just been released)
    # New mail stays out of the list until its summary and the summaries of its files are ready.
    return [public_message(m) for m in stored if not (m.get("ai_pending") and m.get("state", "unread") == "unread")]


@app.post("/api/v1/accounts/{account_id}/messages/{message_id}/resolve", status_code=204)
def resolve_message_endpoint(
    body: ResolveMessageRequest,
    account_id: AccountId,
    message_id: MessageId,
    session: Session = Depends(current_session),
):
    # Ownership is checked before the message is looked up, so non-owners
    # learn nothing about which message ids exist.
    load_account(account_id, session.principal, owner_only=True, action="resolve this review item")
    try:
        vault.get_message(account_id, message_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Message not found") from exc

    try:
        resolve_message(account_id, message_id, body.outcome, session.principal.user_id)
    except BridgeError as err:
        raise HTTPException(status_code=BRIDGE_HTTP_STATUS.get(err.code, 502),
                            detail={"code": err.code, "message": err.message}) from None
    return Response(status_code=204)


@app.post("/api/v1/accounts/{account_id}/messages/{message_id}/unread", status_code=204)
def mark_message_unread(account_id: AccountId, message_id: MessageId, session: Session = Depends(current_session)):
    """Marks a Reviewed email unread again: the real mailbox gets its unread mark back and the email returns to the inbox list."""
    load_account(account_id, session.principal, owner_only=True, action="mark this email unread")
    try:
        stored = vault.get_message(account_id, message_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Message not found") from exc
    if stored.get("state") != "reviewed" or stored.get("found_until"):
        raise HTTPException(status_code=409, detail="Only an email you marked Reviewed can be marked unread.")
    try:
        mail_service.mark_unread(vault.get_account(account_id), stored)
    except BridgeError as err:
        raise HTTPException(status_code=BRIDGE_HTTP_STATUS.get(err.code, 502),
                            detail={"code": err.code, "message": err.message}) from None
    data = {k: v for k, v in stored.items() if k != "id"}
    data.update(state="unread", resolved_at=None)
    vault.update_message(account_id, message_id, data)
    vault.audit({"event": "message_marked_unread", "actor_user_id": session.principal.user_id, "account_id": account_id,
                 "message_id": message_id, "at": time.time()})
    return Response(status_code=204)


def resolve_message(account_id: str, message_id: str, outcome: str, user_id: str, *, by: str | None = None) -> None:
    """Reviewed, archived, binned, junked or expired, for one message. Shared by the buttons and by a person's rules.

    Archive/bin/mark-read happens at the mail provider first. Only after that succeeds do we purge local
    retained metadata/summaries and any temporary safe preview leases, so a failed action leaves the item
    in place. Raises BridgeError when the mailbox cannot be changed, and KeyError when the message is gone."""
    account = vault.get_account(account_id)
    stored = vault.get_message(account_id, message_id)
    found = bool(stored.get("found_until"))
    if found:
        # A kept search result: Reviewed only forgets it here. The mailbox is never changed, and nothing is filed under Reviewed.
        if outcome not in ("reviewed", "expired"):
            raise BridgeError("found_only_reviewed", "A found email can only be marked Reviewed. Open it in your mail app to archive or bin it.")
    else:
        mail_service.apply_outcome(account, stored, outcome)
    preview_leases.purge_message(account_id, message_id)
    kept = None if found else review.kept_state_for(vault, user_id, outcome)
    if outcome != "expired":
        taskbook.close_message(user_id, account_id, message_id, "handled")
    if kept:
        # The mailbox has been changed already. Keep a trimmed card for a few days.
        vault.update_message(account_id, message_id, review.keep_record(vault.get_message(account_id, message_id), kept))
    else:
        vault.delete_message(account_id, message_id)
    event = {
        "event": "message_resolved",
        "outcome": outcome,
        "kept": bool(kept),
        "actor_user_id": user_id,
        "account_id": account_id,
        "message_id": message_id,
        "at": time.time(),
    }
    if by:
        event["by"] = by
    vault.audit(event)


# ---------- Administration ----------

@app.get("/api/v1/admin/attachment-policy")
def get_attachment_policy_endpoint(session: Session = Depends(admin_session)):
    policy = {**DEFAULT_ATTACHMENT_POLICY, **(vault.get_global("attachment-policy") or {})}
    return {
        **policy,
        "raw_attachment_persistence": False,
        "raw_original_served_to_browser": False,
        "purge_on": ["reviewed", "archived", "binned", "expired"],
        "ram_usage": preview_leases.stats(),
    }


@app.put("/api/v1/admin/attachment-policy")
def set_attachment_policy_endpoint(body: AttachmentPolicyPatch, session: Session = Depends(admin_session)):
    data = body.model_dump(mode="python")
    vault.set_global("attachment-policy", data)
    apply_attachment_policy(data)
    vault.audit({"event": "attachment_policy_updated", "actor_user_id": session.principal.user_id, "at": time.time()})
    return {"saved": True, **data, "raw_attachment_persistence": False}


@app.get("/api/v1/admin/global-settings")
def get_global_settings_endpoint(session: Session = Depends(admin_session)):
    settings = vault.get_global("admin-global-settings") or {}
    # Never echo secret material back into the browser.
    has_key = bool(settings.pop("api_key", None))
    return {**settings, "api_key_set": has_key}


@app.put("/api/v1/admin/global-settings")
def set_global_settings_endpoint(body: GlobalSettings, session: Session = Depends(admin_session)):
    data = body.model_dump(mode="python")
    if body.api_key is not None:
        data["api_key"] = body.api_key.get_secret_value()
    else:
        existing = vault.get_global("admin-global-settings") or {}
        if "api_key" in existing:
            data["api_key"] = existing["api_key"]
        else:
            data.pop("api_key", None)
    vault.set_global("admin-global-settings", data)
    vault.audit({"event": "global_settings_updated", "actor_user_id": session.principal.user_id, "at": time.time()})
    return {"saved": True}


# ---------- Errors ----------

@app.exception_handler(RequestValidationError)
def handle_validation_error(_: Request, exc: RequestValidationError):
    # FastAPI's default 422 echoes submitted values (passphrases, passwords).
    return JSONResponse(status_code=422, content={"detail": sanitize_validation_errors(list(exc.errors()))})


@app.exception_handler(VaultLocked)
def handle_locked(_: Request, __: VaultLocked):
    return JSONResponse(status_code=423, content={"detail": "Vault is locked"})


@app.exception_handler(VaultNotInitialized)
def handle_not_initialized(_: Request, __: VaultNotInitialized):
    return JSONResponse(status_code=409, content={"detail": "Enveliq is not set up yet"})
