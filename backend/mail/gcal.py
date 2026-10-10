"""Google Calendar through Google's own calendar API, so a finished task leaves the calendar at once.

The administrator makes a free "OAuth client" in their own Google Cloud project (docs/CALENDAR.md has every click) and pastes its
ID and secret into Administration, Reminders. Each person then presses Connect Google Calendar and agrees on Google's page.
Enveliq asks only for the narrow permission "calendar.app.created": it may make calendars of its own and change what is in
them, and cannot see or touch anything else in the person's Google account. It makes one calendar called "Enveliq tasks".
All requests go to Google over https through outbound.py.
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
import secrets
import time
import urllib.parse
from typing import Any, Callable

from . import outbound
from .outbound import OutboundError

RECORD = "google_oauth"
SCOPE = "https://www.googleapis.com/auth/calendar.app.created"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
API = "https://www.googleapis.com/calendar/v3"
CLIENT_ID = re.compile(r"^[A-Za-z0-9._-]{10,200}\.apps\.googleusercontent\.com$")
CALENDAR_NAME = "Enveliq tasks"


class ConfigError(ValueError):
    pass


def load(vault: Any) -> dict[str, Any]:
    raw = vault.get_global(RECORD) or {}
    return {"enabled": bool(raw.get("enabled")), "client_id": str(raw.get("client_id") or ""), "client_secret": str(raw.get("client_secret") or "")}


def ready(cfg: dict[str, Any]) -> bool:
    return bool(cfg["enabled"] and cfg["client_id"] and cfg["client_secret"])


def public(cfg: dict[str, Any], redirect_uri: str) -> dict[str, Any]:
    return {"enabled": cfg["enabled"], "client_id": cfg["client_id"], "client_secret_set": bool(cfg["client_secret"]), "redirect_uri": redirect_uri, "ready": ready(cfg)}


def apply(old: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
    client_id = str(body.get("client_id") or "").strip()
    if client_id and not CLIENT_ID.match(client_id):
        raise ConfigError("The client ID ends in .apps.googleusercontent.com. Copy it from Google Cloud, APIs & Services, Credentials.")
    secret = old["client_secret"] if body.get("client_secret") is None else str(body["client_secret"]).strip()
    if body.get("enabled") and not (client_id and secret):
        raise ConfigError("Enter the client ID and client secret, or switch Google Calendar off.")
    return {"enabled": bool(body.get("enabled")), "client_id": client_id, "client_secret": secret}


def pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)[:96]
    return verifier, base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")


class Google:
    def __init__(self, vault: Any, clock: Callable[[], float] = time.time):
        self.vault, self.clock = vault, clock
        self._tokens: dict[str, tuple[str, float]] = {}

    def config(self) -> dict[str, Any]:
        return load(self.vault)

    # ----- signing in -----
    def authorization_url(self, redirect_uri: str) -> tuple[str, dict[str, str]]:
        cfg = self.config()
        if not ready(cfg):
            raise OutboundError("not_set", "An administrator needs to set up Google Calendar first (Administration, Reminders).")
        verifier, challenge = pkce_pair()
        state = secrets.token_urlsafe(24)
        query = urllib.parse.urlencode({"client_id": cfg["client_id"], "redirect_uri": redirect_uri, "response_type": "code", "scope": SCOPE, "access_type": "offline",
                                        "prompt": "consent", "state": state, "code_challenge": challenge, "code_challenge_method": "S256", "include_granted_scopes": "false"})
        return f"{AUTH_URL}?{query}", {"state": state, "verifier": verifier}

    def _token(self, form: dict[str, str]) -> dict[str, Any]:
        cfg = self.config()
        status, body = outbound.request("POST", TOKEN_URL, allow=[], form={**form, "client_id": cfg["client_id"], "client_secret": cfg["client_secret"]})
        try:
            data = json.loads(body.decode("utf-8", "replace"))
        except ValueError:
            data = {}
        if status >= 400 or not isinstance(data, dict):
            if isinstance(data, dict) and data.get("error") == "invalid_grant":
                raise OutboundError("signin", "Google no longer accepts this connection. Connect Google Calendar again.")
            if isinstance(data, dict) and data.get("error") in ("invalid_client", "unauthorized_client"):
                raise OutboundError("config", "Google did not accept the client ID or secret. An administrator should check them.")
            raise OutboundError("error", "Google did not accept the sign-in.")
        return data

    def exchange(self, code: str, redirect_uri: str, verifier: str) -> dict[str, Any]:
        data = self._token({"grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri, "code_verifier": verifier})
        if not data.get("refresh_token") or not data.get("access_token"):
            raise OutboundError("error", "Google did not give a long-lasting connection. Remove Enveliq at myaccount.google.com/permissions and try again.")
        if SCOPE not in str(data.get("scope", "")).split():
            raise OutboundError("error", "The permission to manage Enveliq's own calendar was not given.")
        return data

    def access_token(self, uid: str, refresh_token: str) -> str:
        cached = self._tokens.get(uid)
        if cached and cached[1] > self.clock() + 60:
            return cached[0]
        data = self._token({"grant_type": "refresh_token", "refresh_token": refresh_token})
        self._tokens[uid] = (data["access_token"], self.clock() + int(data.get("expires_in") or 3000))
        return data["access_token"]

    def forget(self, uid: str) -> None:
        self._tokens.pop(uid, None)

    def revoke(self, token: str) -> None:
        try:
            outbound.request("POST", REVOKE_URL, allow=[], form={"token": token})
        except OutboundError:
            pass

    # ----- the calendar -----
    def call(self, uid: str, refresh_token: str, method: str, path: str, body: Any = None) -> tuple[int, Any]:
        token = self.access_token(uid, refresh_token)
        status, raw = outbound.request(method, API + path, allow=[], headers={"Authorization": "Bearer " + token}, json_body=body)
        if status == 401:
            self.forget(uid)
            raise OutboundError("signin", "Google no longer accepts this connection. Connect Google Calendar again.")
        if status == 403:
            text = raw.decode("utf-8", "replace")
            if "accessNotConfigured" in text or "has not been used" in text or "SERVICE_DISABLED" in text:
                raise OutboundError("config", "The Google Calendar API is switched off in your Google Cloud project. Enable it (docs/CALENDAR.md, step 2).")
            if "ateLimitExceeded" in text:
                raise OutboundError("busy", "Google asked Enveliq to slow down. It will try again.")
            raise OutboundError("refused", "Google refused the request.")
        if status == 429:
            raise OutboundError("busy", "Google asked Enveliq to slow down. It will try again.")
        try:
            data = json.loads(raw.decode("utf-8", "replace")) if raw else None
        except ValueError:
            data = None
        return status, data

    def make_calendar(self, uid: str, refresh_token: str, tz: str | None) -> str:
        status, data = self.call(uid, refresh_token, "POST", "/calendars", {"summary": CALENDAR_NAME, "description": "Tasks from Enveliq. Enveliq adds and removes the events here by itself.", "timeZone": tz or "UTC"})
        if status >= 400 or not isinstance(data, dict) or not data.get("id"):
            raise OutboundError("error", "Google would not make the calendar.")
        return str(data["id"])

    def delete_calendar(self, uid: str, refresh_token: str, calendar_id: str) -> None:
        try:
            self.call(uid, refresh_token, "DELETE", "/calendars/" + urllib.parse.quote(calendar_id, safe=""))
        except OutboundError:
            pass
