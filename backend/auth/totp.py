"""Time-based one-time passwords (RFC 6238, HMAC-SHA1, 6 digits, 30 s).

Compatible with Aegis, 2FAS, Google Authenticator, 1Password, Bitwarden,
Proton Pass and similar apps. Codes are accepted one step either side of
now for clock drift, and a used time step can never be reused (replay guard).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import io
import secrets
import struct
import time
from urllib.parse import quote, urlencode

import segno

DIGITS = 6
PERIOD = 30
WINDOW = 1


def new_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def _key(secret: str) -> bytes:
    return base64.b32decode(secret + "=" * (-len(secret) % 8), casefold=True)


def code_at(secret: str, step: int) -> str:
    digest = hmac.new(_key(secret), struct.pack(">Q", step), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(value % (10 ** DIGITS)).zfill(DIGITS)


def current_step(now: float | None = None) -> int:
    return int((time.time() if now is None else now) // PERIOD)


def verify(secret: str, code: str, last_step: int | None = None, now: float | None = None) -> int | None:
    """Return the matched time step, or None. Rejects a step at or before
    last_step so an observed code cannot be replayed."""
    code = "".join(ch for ch in (code or "") if ch.isdigit())
    if len(code) != DIGITS:
        return None
    step = current_step(now)
    matched = None
    for candidate in range(step - WINDOW, step + WINDOW + 1):
        if secrets.compare_digest(code_at(secret, candidate), code):
            matched = candidate
    if matched is None or (last_step is not None and matched <= last_step):
        return None
    return matched


def provisioning_uri(secret: str, account_name: str, issuer: str = "Enveliq") -> str:
    label = quote(f"{issuer}:{account_name}", safe="")
    params = urlencode({"secret": secret, "issuer": issuer, "algorithm": "SHA1", "digits": DIGITS, "period": PERIOD})
    return f"otpauth://totp/{label}?{params}"


def qr_svg(uri: str) -> str:
    """Inline SVG QR code for the provisioning URI (rendered server-side so
    the secret never goes to a third-party QR service)."""
    # Not `svg_inline`: that leaves out the SVG namespace, and the page shows this as an <img> (a data: address), where a
    # browser only draws an SVG that carries `xmlns`. Without it the picture is a broken-image icon.
    out = io.BytesIO()
    segno.make(uri, error="m").save(out, kind="svg", scale=5, border=2, dark="#0b0f16", light="#ffffff", xmldecl=False, svgns=True, nl=False)
    return out.getvalue().decode("utf-8")
