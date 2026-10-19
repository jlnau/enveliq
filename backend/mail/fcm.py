"""Google's push service (Firebase Cloud Messaging) for the Enveliq Android app.

The administrator pastes the Firebase project's service-account key once; it is kept encrypted in the vault and is never shown again.
The server uses it to ask Google to wake one phone with a very small message: only the kind ("mail" or "test") and a count.
No sender, subject, summary or address is ever put in a message. The app wakes up and asks Enveliq for the details itself.
"""
from __future__ import annotations

import base64
import json
import re
import threading
import time
from typing import Any

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from . import outbound
from .outbound import OutboundError

RECORD = "fcm_service_account"
TOKEN_URL = "https://oauth2.googleapis.com/token"
SEND_URL = "https://fcm.googleapis.com/v1/projects/{project}/messages:send"
SCOPE = "https://www.googleapis.com/auth/firebase.messaging"
PROJECT = re.compile(r"^[a-z][a-z0-9-]{4,60}[a-z0-9]$")
EMAIL = re.compile(r"^[A-Za-z0-9._-]{1,100}@[A-Za-z0-9.-]{1,100}\.iam\.gserviceaccount\.com$")
DEVICE_TOKEN = re.compile(r"^[A-Za-z0-9:_\-]{20,400}$")


class FcmKeyError(ValueError):
    """The pasted key cannot be used. The message is safe to show: it never repeats the key."""


def parse_key(text: str) -> dict[str, str]:
    """Check a service-account key file's text and keep only the three things sending needs."""
    try:
        raw = json.loads(text)
    except ValueError:
        raise FcmKeyError("That is not the key file. Open the .json file you downloaded from Firebase and paste everything in it.") from None
    if not isinstance(raw, dict) or raw.get("type") != "service_account":
        raise FcmKeyError("That is not a service-account key. In Firebase, Project settings, Service accounts, press Generate new private key.")
    project, email, private = str(raw.get("project_id") or ""), str(raw.get("client_email") or ""), str(raw.get("private_key") or "")
    if not PROJECT.match(project) or not EMAIL.match(email):
        raise FcmKeyError("The key file is missing its project or account name. Download a fresh one from Firebase.")
    try:
        key = serialization.load_pem_private_key(private.encode(), password=None)
    except Exception:
        raise FcmKeyError("The private key inside the file could not be read. Download a fresh one from Firebase.") from None
    if not isinstance(key, rsa.RSAPrivateKey):
        raise FcmKeyError("The private key inside the file is not the kind Firebase uses. Download a fresh one.")
    return {"project_id": project, "client_email": email, "private_key": private}


def load(vault: Any) -> dict[str, str] | None:
    raw = vault.get_global(RECORD) or {}
    if raw.get("project_id") and raw.get("client_email") and raw.get("private_key"):
        return {k: str(raw[k]) for k in ("project_id", "client_email", "private_key")}
    return None


def public(vault: Any) -> dict[str, Any]:
    cfg = load(vault)
    return {"set": cfg is not None, "project_id": cfg["project_id"] if cfg else "", "client_email": cfg["client_email"] if cfg else ""}


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


_cache: dict[str, tuple[float, str]] = {}
_lock = threading.Lock()


def _access_token(cfg: dict[str, str], now: float | None = None) -> str:
    now = time.time() if now is None else now
    with _lock:
        hit = _cache.get(cfg["client_email"])
        if hit and hit[0] > now + 60:
            return hit[1]
    header = _b64(json.dumps({"alg": "RS256", "typ": "JWT"}, separators=(",", ":")).encode())
    claims = _b64(json.dumps({"iss": cfg["client_email"], "scope": SCOPE, "aud": TOKEN_URL, "iat": int(now), "exp": int(now) + 3600}, separators=(",", ":")).encode())
    key = serialization.load_pem_private_key(cfg["private_key"].encode(), password=None)
    signature = key.sign(f"{header}.{claims}".encode(), padding.PKCS1v15(), hashes.SHA256())   # type: ignore[union-attr]
    code, _, body = outbound.request_full("POST", TOKEN_URL, allow=[], form={"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer", "assertion": f"{header}.{claims}.{_b64(signature)}"})
    try:
        token = str(json.loads(body.decode("utf-8", "replace")).get("access_token") or "")
    except ValueError:
        token = ""
    if code != 200 or not token:
        raise OutboundError("refused", "Google did not accept the Firebase key. Check that it belongs to the right project, or download a new one.")
    with _lock:
        _cache[cfg["client_email"]] = (now + 3300, token)
    return token


def forget_token(cfg: dict[str, str] | None = None) -> None:
    with _lock:
        if cfg is None:
            _cache.clear()
        else:
            _cache.pop(cfg["client_email"], None)


def send(vault: Any, device_token: str, data: dict[str, str]) -> str:
    """Ask Google to wake one phone. Returns "sent", or "gone" when Google says the phone no longer has the app. Raises OutboundError otherwise."""
    cfg = load(vault)
    if cfg is None:
        raise OutboundError("not_set", "Your administrator has not set up Android alerts yet.")
    if not DEVICE_TOKEN.match(device_token):
        return "gone"
    message = {"message": {"token": device_token, "data": {str(k): str(v)[:40] for k, v in data.items()}, "android": {"priority": "HIGH", "ttl": "3600s"}}}
    code, _, body = outbound.request_full("POST", SEND_URL.format(project=cfg["project_id"]), allow=[], json_body=message,
                                          headers={"Authorization": "Bearer " + _access_token(cfg)})
    if 200 <= code < 300:
        return "sent"
    if code in (401, 403):
        forget_token(cfg)
        raise OutboundError("refused", "Google refused the message. Check that Firebase Cloud Messaging is switched on for the project and that the key is current.")
    if code == 404 or (code == 400 and b"UNREGISTERED" in body):
        return "gone"
    raise OutboundError("error", f"Google's notification service answered with an error ({code}).")
