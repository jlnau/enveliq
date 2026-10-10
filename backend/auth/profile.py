"""Optional profile details: name, email, a short note and a small picture.

Only the username and password are needed to use Enveliq; everything here is
optional. The picture is kept inside the encrypted user record and is checked
by what the bytes really are (JPEG, PNG or WebP), never by what the browser
claims, so nothing but a plain picture is ever served back.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import re

MAX_AVATAR_BYTES = 120_000          # the browser shrinks pictures to about 256 px first
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class ProfileError(ValueError):
    pass


def clean_email(value: str | None) -> str | None:
    value = (value or "").strip()
    if not value:
        return None
    if len(value) > 254 or not EMAIL_RE.match(value):
        raise ProfileError("That doesn't look like an email address")
    return value


def clean_text(value: str | None, limit: int) -> str:
    # Single spaces, no control characters; this is shown to other people later.
    value = re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", "", (value or "")).strip()
    return value[:limit]


def sniff(data: bytes) -> str | None:
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def parse_avatar(image: str) -> dict:
    """Accept a data URL or bare base64; return the record to store."""
    text = (image or "").strip()
    if text.startswith("data:"):
        head, _, text = text.partition(",")
        if ";base64" not in head:
            raise ProfileError("That picture could not be read")
    try:
        data = base64.b64decode(text, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ProfileError("That picture could not be read") from exc
    if not data or len(data) > MAX_AVATAR_BYTES:
        raise ProfileError("That picture is too large. Try a smaller one.")
    mime = sniff(data)
    if not mime:
        raise ProfileError("Please use a JPEG, PNG or WebP picture")
    return {"mime": mime, "data": base64.b64encode(data).decode("ascii"), "v": hashlib.sha256(data).hexdigest()[:12]}
