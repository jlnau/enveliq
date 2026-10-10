"""Outlook, Hotmail and Microsoft 365 mailboxes.

Microsoft does not accept passwords or app passwords from other apps any more.
It wants a sign-in on its own page (OAuth 2.0 authorisation code flow with
PKCE) and then the app presents a short-lived access token to IMAP and SMTP
("XOAUTH2"). That needs an *application registration* in Microsoft Entra. Enveliq
ships none: the administrator makes their own (free, a few minutes, see
docs/MICROSOFT.md) and enters its client ID under Administration, Microsoft
sign-in. Nothing is registered on anyone's behalf and no Enveliq secret is held
by anyone else.

What is kept: the refresh token, encrypted in the vault with the mailbox, never
sent to the browser. Access tokens live in memory only and are dropped when the
vault locks. Tokens, codes and anything Microsoft says back are never logged or
returned; errors are fixed codes with fixed wording.
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
import secrets
import threading
import time
from typing import Any, Callable
from urllib.parse import urlencode

import httpx

RECORD = "microsoft_oauth"
LOGIN_HOST = "https://login.microsoftonline.com"
IMAP_HOST, IMAP_PORT = "outlook.office365.com", 993
SMTP_HOST, SMTP_PORT = "smtp.office365.com", 587
SCOPES = ("offline_access", "openid", "email", "https://outlook.office.com/IMAP.AccessAsUser.All", "https://outlook.office.com/SMTP.Send")
CLIENT_ID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
TENANT = re.compile(r"^(common|consumers|organizations|[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}|[A-Za-z0-9][A-Za-z0-9.-]{2,252})$")
EMAIL = re.compile(r"^[A-Za-z0-9._%+'-]{1,64}@[A-Za-z0-9.-]{1,253}\.[A-Za-z]{2,63}$")
REFRESH_MARGIN = 120

DEFAULT = {"enabled": False, "client_id": "", "tenant": "common", "client_secret": ""}

MESSAGES = {
    "ms_not_set_up": "Microsoft sign-in is not set up yet. An administrator has to add the app registration under Administration, Microsoft sign-in.",
    "ms_signin_needed": "Microsoft no longer accepts the saved sign-in for this mailbox (it expired, or access was removed). Remove the mailbox and add it again.",
    "ms_unreachable": "Microsoft's sign-in service could not be reached. Check that this machine can reach login.microsoftonline.com.",
    "ms_rejected": "Microsoft refused the sign-in. Check the client ID, the account types and the redirect address in the app registration.",
    "ms_public_client": "The app registration does not allow public client flows. In Entra: Authentication, Advanced settings, Allow public client flows: Yes.",
    "ms_bad_client": "Microsoft does not know that client ID in the account type chosen. Check the client ID, and that the registration allows these accounts.",
    "ms_bad_secret": "Microsoft refused the client secret. Make a new one, or remove it if the registration is a public client.",
    "ms_secret_not_wanted": "The registration is a public client, so a client secret must not be sent. Remove the secret in Enveliq.",
    "ms_consent": "Consent is needed. A work or school administrator may have to approve the app (Entra: API permissions, Grant admin consent).",
    "ms_no_address": "Microsoft did not say which email address signed in. Try again, or use a different account.",
    "ms_denied": "The Microsoft sign-in was cancelled or refused.",
    "ms_expired": "That sign-in took too long or was not started here. Press Sign in with Microsoft again.",
    "ms_state": "The sign-in could not be matched to this browser. Press Sign in with Microsoft again.",
    "ms_mailbox_refused": "Microsoft signed you in, but the mailbox refused the connection. For a work or school account an administrator may have to allow IMAP and SMTP AUTH for this mailbox (see docs/MICROSOFT.md).",
}
# Microsoft's own error numbers that have a fixed explanation.
KNOWN = {7000218: "ms_public_client", 700016: "ms_bad_client", 7000215: "ms_bad_secret", 7000222: "ms_bad_secret", 700025: "ms_secret_not_wanted",
         65001: "ms_consent", 90094: "ms_consent", 90008: "ms_consent", 500011: "ms_consent", 70011: "ms_rejected", 900144: "ms_rejected"}


class MsError(Exception):
    """`code` is a fixed word from MESSAGES; `message` is its fixed wording."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code
        self.message = MESSAGES.get(code, MESSAGES["ms_rejected"])


class ConfigError(ValueError):
    pass


def load(vault: Any) -> dict[str, Any]:
    saved = vault.get_global(RECORD) or {}
    out = dict(DEFAULT)
    for key, default in DEFAULT.items():
        value = saved.get(key, default)
        out[key] = value if isinstance(value, type(default)) else default
    out["enabled"] = saved.get("enabled") is True
    return out


def public(cfg: dict[str, Any], redirect_uri: str) -> dict[str, Any]:
    return {"enabled": cfg["enabled"], "client_id": cfg["client_id"], "tenant": cfg["tenant"], "has_secret": bool(cfg["client_secret"]),
            "redirect_uri": redirect_uri, "ready": ready(cfg)}


def ready(cfg: dict[str, Any]) -> bool:
    return bool(cfg["enabled"] and CLIENT_ID.match(cfg["client_id"]) and TENANT.match(cfg["tenant"]))


def apply(old: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
    client_id = str(body.get("client_id", "")).strip()
    tenant = str(body.get("tenant", "")).strip() or "common"
    if client_id and not CLIENT_ID.match(client_id):
        raise ConfigError("The client ID is a long code like 12345678-abcd-1234-abcd-1234567890ab. Copy it from the app registration's Overview page (Application (client) ID).")
    if not TENANT.match(tenant):
        raise ConfigError("The directory is common, consumers, organizations, or your Directory (tenant) ID.")
    if body.get("enabled") and not client_id:
        raise ConfigError("Enter the client ID, or switch Microsoft sign-in off.")
    secret = old["client_secret"] if body.get("client_secret") is None else str(body["client_secret"]).strip()
    return {"enabled": bool(body.get("enabled")), "client_id": client_id, "tenant": tenant, "client_secret": secret}


def pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)[:96]
    return verifier, base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")


def _claims(id_token: str) -> dict[str, Any]:
    """The claims of an ID token received straight from Microsoft's token address over https
    (so its signature need not be checked again). Used only to learn which address signed in."""
    try:
        payload = id_token.split(".")[1]
        return json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    except (IndexError, ValueError):
        return {}


class Microsoft:
    def __init__(self, vault: Any, *, transport: httpx.BaseTransport | None = None, clock: Callable[[], float] = time.time):
        self.vault = vault
        self.transport = transport
        self.clock = clock
        self._tokens: dict[str, tuple[str, float]] = {}
        self._guard = threading.Lock()
        self._locks: dict[str, threading.Lock] = {}
        if vault is not None:
            vault.add_lock_listener(self.forget)

    def forget(self) -> None:
        with self._guard:
            self._tokens.clear()

    def config(self) -> dict[str, Any]:
        return load(self.vault)

    def _endpoint(self, cfg: dict[str, Any], leaf: str) -> str:
        return f"{LOGIN_HOST}/{cfg['tenant']}/oauth2/v2.0/{leaf}"

    def authorization_url(self, redirect_uri: str) -> tuple[str, dict[str, str]]:
        cfg = self.config()
        if not ready(cfg):
            raise MsError("ms_not_set_up")
        verifier, challenge = pkce_pair()
        state = secrets.token_urlsafe(32)
        query = urlencode({"client_id": cfg["client_id"], "response_type": "code", "redirect_uri": redirect_uri, "response_mode": "query",
                           "scope": " ".join(SCOPES), "state": state, "code_challenge": challenge, "code_challenge_method": "S256", "prompt": "select_account"})
        return self._endpoint(cfg, "authorize") + "?" + query, {"state": state, "verifier": verifier}

    def _post(self, cfg: dict[str, Any], form: dict[str, str]) -> dict[str, Any]:
        form = {"client_id": cfg["client_id"], **form}
        if cfg["client_secret"]:
            form["client_secret"] = cfg["client_secret"]
        try:
            with httpx.Client(timeout=15.0, follow_redirects=False, transport=self.transport, headers={"Accept": "application/json", "User-Agent": "Enveliq"}) as http:
                r = http.post(self._endpoint(cfg, "token"), data=form)
        except httpx.HTTPError:
            raise MsError("ms_unreachable") from None
        try:
            data = r.json()
        except ValueError:
            data = {}
        if r.status_code != 200 or not isinstance(data, dict) or "access_token" not in data:
            codes = data.get("error_codes") if isinstance(data, dict) and isinstance(data.get("error_codes"), list) else []
            for n in codes:
                if n in KNOWN:
                    raise MsError(KNOWN[n])
            if isinstance(data, dict) and data.get("error") == "invalid_grant":
                raise MsError("ms_signin_needed")
            raise MsError("ms_rejected")
        return data

    def exchange(self, code: str, redirect_uri: str, verifier: str) -> dict[str, Any]:
        """Trade the sign-in code for tokens: {refresh_token, access_token, expires_in, email}."""
        cfg = self.config()
        if not ready(cfg):
            raise MsError("ms_not_set_up")
        data = self._post(cfg, {"grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri, "code_verifier": verifier, "scope": " ".join(SCOPES)})
        claims = _claims(str(data.get("id_token") or ""))
        email = str(claims.get("email") or claims.get("preferred_username") or "").strip()
        if not data.get("refresh_token") or not EMAIL.match(email):
            raise MsError("ms_no_address")
        return {"refresh_token": data["refresh_token"], "access_token": data["access_token"], "expires_in": int(data.get("expires_in") or 3000), "email": email}

    def remember(self, account_id: str, tokens: dict[str, Any]) -> None:
        """Keep the access token just received for a new mailbox, so its first connection needs no refresh."""
        with self._guard:
            self._tokens[account_id] = (tokens["access_token"], self.clock() + int(tokens["expires_in"]))

    def access_token(self, account: dict[str, Any]) -> str:
        """A valid access token for the mailbox, refreshing (and keeping the new refresh token) when needed."""
        account_id = account["id"]
        with self._guard:
            lock = self._locks.setdefault(account_id, threading.Lock())
        with lock:
            cached = self._tokens.get(account_id)
            if cached and cached[1] - self.clock() > REFRESH_MARGIN:
                return cached[0]
            cfg = self.config()
            if not ready(cfg):
                raise MsError("ms_not_set_up")
            refresh = str(account.get("oauth_refresh_token") or "")
            try:
                fresh = self.vault.get_account(account_id)
                refresh = str(fresh.get("oauth_refresh_token") or refresh)
            except KeyError:
                fresh = None
            if not refresh:
                raise MsError("ms_signin_needed")
            data = self._post(cfg, {"grant_type": "refresh_token", "refresh_token": refresh, "scope": " ".join(SCOPES)})
            new = data.get("refresh_token")
            if new and new != refresh and fresh is not None:
                fresh = dict(fresh)
                fresh.pop("id", None)
                fresh["oauth_refresh_token"] = new
                self.vault.update_account(account_id, fresh)
            token = str(data["access_token"])
            self._tokens[account_id] = (token, self.clock() + int(data.get("expires_in") or 3000))
            return token
