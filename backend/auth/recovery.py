"""One-time recovery codes for when the authenticator app or passkey is lost.

Ten codes of 10 characters from an unambiguous alphabet (~50 bits each).
Only SHA-256 digests are stored; each code works once.
"""
from __future__ import annotations

import hashlib
import secrets

ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"
COUNT = 10


def _normalise(code: str) -> str:
    return "".join(ch for ch in (code or "").lower() if ch in ALPHABET)


def _digest(code: str) -> str:
    return hashlib.sha256(("enveliq-recovery:" + _normalise(code)).encode()).hexdigest()


def generate() -> tuple[list[str], list[str]]:
    """Return (codes to show once, digests to store)."""
    codes = []
    for _ in range(COUNT):
        raw = "".join(secrets.choice(ALPHABET) for _ in range(10))
        codes.append(f"{raw[:5]}-{raw[5:]}")
    return codes, [_digest(c) for c in codes]


def looks_like_recovery_code(code: str) -> bool:
    return len(_normalise(code)) == 10 and not code.strip().isdigit()


def consume(code: str, digests: list[str]) -> list[str] | None:
    """If the code matches, return the remaining digests; otherwise None."""
    target = _digest(code)
    remaining, found = [], False
    for d in digests:
        if not found and secrets.compare_digest(d, target):
            found = True
            continue
        remaining.append(d)
    return remaining if found else None
