"""Reminder channels that need more than a web request: Browser push (this device) and Email (your own mailbox).

Browser push follows RFC 8030 (Web Push), RFC 8291 (message encryption, aes128gcm) and RFC 8292 (VAPID). The server keeps one
signing key (in the vault); each device that agrees to notifications gives the browser's push service address and two keys,
which are stored encrypted and never shown again. The push service only ever sees an encrypted message.
"""
from __future__ import annotations

import base64
import json
import os
import re
import secrets
import time
import urllib.parse
from typing import Any

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, utils
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from . import outbound
from .notify import CHANNELS, CHECKS, Notifier, _clean, f, register_extra
from .outbound import OutboundError

VAPID_RECORD = "webpush_vapid"
MAX_DEVICES = 5
RECORD_SIZE = 4096


def b64e(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def b64d(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


# ---------- RFC 8291 ----------

def encrypt(plaintext: bytes, ua_public: bytes, auth_secret: bytes, *, as_private: ec.EllipticCurvePrivateKey | None = None, salt: bytes | None = None) -> bytes:
    """The body of a Web Push request: header (salt, record size, key) followed by one encrypted record."""
    if len(plaintext) > RECORD_SIZE - 17 - 1:
        raise ValueError("message too long")
    as_private = as_private or ec.generate_private_key(ec.SECP256R1())
    salt = salt or os.urandom(16)
    as_public = as_private.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    ua_key = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), ua_public)
    secret = as_private.exchange(ec.ECDH(), ua_key)
    ikm = HKDF(hashes.SHA256(), 32, auth_secret, b"WebPush: info\x00" + ua_public + as_public).derive(secret)
    cek = HKDF(hashes.SHA256(), 16, salt, b"Content-Encoding: aes128gcm\x00").derive(ikm)
    nonce = HKDF(hashes.SHA256(), 12, salt, b"Content-Encoding: nonce\x00").derive(ikm)
    body = AESGCM(cek).encrypt(nonce, plaintext + b"\x02", None)
    return salt + RECORD_SIZE.to_bytes(4, "big") + bytes([len(as_public)]) + as_public + body


def decrypt(body: bytes, ua_private: ec.EllipticCurvePrivateKey, auth_secret: bytes) -> bytes:
    """What a browser does with the message. Used by the tests."""
    salt, idlen = body[:16], body[20]
    as_public, data = body[21:21 + idlen], body[21 + idlen:]
    ua_public = ua_private.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    secret = ua_private.exchange(ec.ECDH(), ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), as_public))
    ikm = HKDF(hashes.SHA256(), 32, auth_secret, b"WebPush: info\x00" + ua_public + as_public).derive(secret)
    cek = HKDF(hashes.SHA256(), 16, salt, b"Content-Encoding: aes128gcm\x00").derive(ikm)
    nonce = HKDF(hashes.SHA256(), 12, salt, b"Content-Encoding: nonce\x00").derive(ikm)
    plain = AESGCM(cek).decrypt(nonce, data, None)
    return plain.rstrip(b"\x00")[:-1]


# ---------- RFC 8292 (VAPID) ----------

def vapid_key(vault: Any) -> ec.EllipticCurvePrivateKey:
    rec = vault.get_global(VAPID_RECORD) or {}
    if rec.get("private"):
        return ec.derive_private_key(int.from_bytes(b64d(rec["private"]), "big"), ec.SECP256R1())
    key = ec.generate_private_key(ec.SECP256R1())
    vault.set_global(VAPID_RECORD, {"private": b64e(key.private_numbers().private_value.to_bytes(32, "big"))})
    return key


def public_key_text(key: ec.EllipticCurvePrivateKey) -> str:
    return b64e(key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint))


def vapid_header(key: ec.EllipticCurvePrivateKey, endpoint: str, subject: str, now: float | None = None) -> str:
    parts = urllib.parse.urlsplit(endpoint)
    claims = {"aud": f"{parts.scheme}://{parts.netloc}", "exp": int((now or time.time()) + 12 * 3600), "sub": subject}
    signing = b64e(json.dumps({"typ": "JWT", "alg": "ES256"}, separators=(",", ":")).encode()) + "." + b64e(json.dumps(claims, separators=(",", ":")).encode())
    r, s = utils.decode_dss_signature(key.sign(signing.encode(), ec.ECDSA(hashes.SHA256())))
    return f"vapid t={signing}.{b64e(r.to_bytes(32, 'big') + s.to_bytes(32, 'big'))}, k={public_key_text(key)}"


def subject(origin: str) -> str:
    env = os.environ.get("ENVELIQ_VAPID_SUBJECT", "").strip()
    if env.startswith(("mailto:", "https://")):
        return env
    return origin if origin.startswith("https://") else "mailto:enveliq@enveliq.invalid"


# ---------- devices ----------

def devices(values: dict[str, str]) -> list[dict[str, Any]]:
    try:
        raw = json.loads(values.get("subs") or "[]")
    except ValueError:
        return []
    return [d for d in raw if isinstance(d, dict) and d.get("endpoint") and d.get("p256dh") and d.get("auth") and d.get("id")]


def _describe_browser(values: dict[str, str], notifier: Notifier) -> dict[str, Any]:
    return {"devices": [{"id": d["id"], "label": d.get("label", "A device"), "added": d.get("added")} for d in devices(values)]}


def add_device(notifier: Notifier, user_id: str, endpoint: str, p256dh: str, auth: str, label: str) -> None:
    endpoint = _clean(endpoint, 800)
    parts = urllib.parse.urlsplit(endpoint)
    if parts.scheme != "https" or not parts.hostname or parts.username or parts.password:
        raise ValueError("That device did not give a usable address.")
    try:
        if len(b64d(p256dh)) != 65 or len(b64d(auth)) < 16:
            raise ValueError
        ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), b64d(p256dh))
    except Exception:
        raise ValueError("That device sent keys Enveliq cannot use.") from None
    try:
        outbound.check_target(endpoint, [])               # push services are on the internet; never a private address
    except OutboundError as err:
        raise ValueError(err.message) from None
    with notifier._lock:
        values = notifier.get_values(user_id, "browser")
        current = [d for d in devices(values) if d["endpoint"] != endpoint]
        if len(current) >= MAX_DEVICES:
            raise ValueError(f"You can use up to {MAX_DEVICES} devices. Remove one first.")
        current.append({"id": secrets.token_hex(6), "endpoint": endpoint, "p256dh": p256dh, "auth": auth, "label": _clean(label, 60) or "A device", "added": time.time()})
        notifier.set_values(user_id, "browser", {"subs": json.dumps(current)}, enabled=True)


def remove_device(notifier: Notifier, user_id: str, device_id: str) -> None:
    with notifier._lock:
        values = notifier.get_values(user_id, "browser")
        keep = [d for d in devices(values) if d["id"] != device_id]
        notifier.set_values(user_id, "browser", {"subs": json.dumps(keep)} if keep else {})


def _send_browser(values: dict[str, Any], note: dict[str, Any], ctx: dict[str, Any]) -> None:
    notifier: Notifier = ctx["notifier"]
    user_id, vault = ctx["user_id"], ctx["vault"]
    key = vapid_key(vault)
    origin = getattr(notifier, "origin", "")
    payload = json.dumps({"title": note["title"], "body": note["body"], "url": note.get("url") or note.get("path") or "/"}, ensure_ascii=False).encode()
    stored = notifier.get_values(user_id, "browser")
    sent, last, dead = 0, None, []
    for d in devices(stored):
        try:
            body = encrypt(payload, b64d(d["p256dh"]), b64d(d["auth"]))
            code, _ = outbound.request("POST", d["endpoint"], allow=[], body=body, headers={
                "Authorization": vapid_header(key, d["endpoint"], subject(origin)), "Content-Encoding": "aes128gcm", "Content-Type": "application/octet-stream",
                "TTL": "3600", "Urgency": "normal" if note.get("priority") != "high" else "high"})
            if code in (404, 410):
                dead.append(d["id"])
            elif 200 <= code < 300:
                sent += 1
            else:
                last = OutboundError("error", f"The browser's notification service answered with an error ({code}).")
        except OutboundError as err:
            last = err
        except ValueError:
            last = OutboundError("error", "The message could not be prepared.")
    for did in dead:
        remove_device(notifier, user_id, did)
    if not sent:
        if dead and not last:
            raise OutboundError("gone", "That device no longer accepts notifications. Turn them on again on the device.")
        raise last or OutboundError("not_set", "No device is set up yet.")


register_extra("browser", {
    "id": "browser", "label": "This device (browser)", "blurb": "A pop-up on this phone or computer, even when Enveliq is closed.", "fields": [],
    "steps": ["Press Turn on for this device and choose Allow when the browser asks.",
              "Press Send a test. The pop-up should appear within a few seconds.",
              "Repeat on each device you want (up to 5). On an iPhone or iPad, first add Enveliq to the Home Screen (Share, Add to Home Screen) and open it from there.",
              "Needs an https:// address (or localhost). If notifications are blocked, allow them in the browser's site settings."],
    "send": _send_browser, "local_ok": False, "describe": _describe_browser,
    "keep": "Press Turn on for this device first.",
}, lambda v: {})


# ---------- Email ----------
_ADDRESS = re.compile(r"^[^\s@<>,;]{1,64}@[^\s@<>,;]{1,255}$")


def _post_email(notifier: Notifier, user_id: str, checked: dict[str, str]) -> dict[str, str]:
    mine = notifier.mailer.addresses(user_id) if notifier.mailer else []
    if not mine:
        raise ValueError("Add a mailbox to Enveliq first. Reminder emails go only to your own mailboxes.")
    want = _clean(checked.get("address"), 320).lower()
    if not want:
        return {"address": mine[0]}
    for a in mine:
        if a.lower() == want:
            return {"address": a}
    raise ValueError("Choose one of your own mailboxes: " + ", ".join(mine) + ".")


def _send_email(values: dict[str, Any], note: dict[str, Any], ctx: dict[str, Any]) -> None:
    mailer = ctx.get("mailer")
    if mailer is None:
        raise OutboundError("not_set", "Email is not available here.")
    body = note["body"] + (f"\n\nOpen Enveliq: {note['url']}" if note.get("url") else "")
    mailer.send(ctx["user_id"], values["address"], note["title"], body)


def _check_email(v: dict[str, str]) -> dict[str, str]:
    a = _clean(v.get("address"), 320)
    if a and not _ADDRESS.match(a):
        raise ValueError("That does not look like an email address.")
    return {"address": a}


register_extra("email", {
    "id": "email", "label": "Email", "blurb": "A short email to your own mailbox. Good as a quiet backup.",
    "fields": [f("address", "Send to", required=False, placeholder="Leave blank for your first mailbox", help="One of your own mailboxes in Enveliq. Reminders are never sent to anyone else.")],
    "steps": ["Leave the box blank to use your first mailbox, or type the address of another of your mailboxes.",
              "Press Save and send a test. Check your inbox.",
              "Reminder emails are marked so that Enveliq does not make a task or a summary out of its own message."],
    "send": _send_email, "local_ok": False, "post": _post_email,
}, _check_email)
