"""Password hashing with Argon2id (via `cryptography`).

Parameters follow the OWASP Password Storage Cheat Sheet minimum for
Argon2id (19 MiB, 2 iterations, 1 lane). Hashes are self-describing so the
parameters can be raised later; `needs_rehash` reports when to upgrade.
"""
from __future__ import annotations

import base64
import secrets
import threading

from cryptography.hazmat.primitives.kdf.argon2 import Argon2id

TIME_COST = 2
MEMORY_KIB = 19 * 1024
LANES = 1
HASH_LEN = 32
MIN_LENGTH = 12
MAX_LENGTH = 1024

# At most two hashes at once (~38 MiB), so a login burst cannot exhaust RAM.
_SLOTS = threading.BoundedSemaphore(2)


def _b64(b: bytes) -> str:
    return base64.b64encode(b).decode("ascii")


def _derive(password: str, salt: bytes, t: int, m: int, p: int, n: int) -> bytes:
    with _SLOTS:
        return Argon2id(salt=salt, length=n, iterations=t, lanes=p, memory_cost=m).derive(password.encode("utf-8"))


DEFAULT_RULES = {
    "pw_min_length": MIN_LENGTH,   # characters
    "pw_min_digits": 0,            # numbers 0-9
    "pw_min_upper": 0,             # capital letters
    "pw_min_lower": 0,             # small letters
    "pw_min_symbols": 0,           # anything that is not a letter or number
    "pw_forbid_username": True,    # the password may not contain the username
}
RULE_LIMITS = {"pw_min_length": (8, 128), "pw_min_digits": (0, 32), "pw_min_upper": (0, 32),
               "pw_min_lower": (0, 32), "pw_min_symbols": (0, 32)}


def clean_rules(raw: dict | None) -> dict:
    """The password rules with every value forced into a safe range, so a damaged setting can never lock people out."""
    raw = raw or {}
    out = dict(DEFAULT_RULES)
    for key, (lo, hi) in RULE_LIMITS.items():
        try:
            out[key] = max(lo, min(hi, int(raw.get(key, DEFAULT_RULES[key]))))
        except (TypeError, ValueError):
            pass
    out["pw_forbid_username"] = bool(raw.get("pw_forbid_username", DEFAULT_RULES["pw_forbid_username"]))
    return out


def describe_rules(rules: dict | None) -> list[str]:
    """The rules in plain words, for showing next to a new-password box."""
    r = clean_rules(rules)

    def many(n: int, one: str, more: str) -> str:
        return f"at least {n} {one if n == 1 else more}"

    out = [f"at least {r['pw_min_length']} characters long"]
    if r["pw_min_digits"]:
        out.append(many(r["pw_min_digits"], "number", "numbers"))
    if r["pw_min_upper"]:
        out.append(many(r["pw_min_upper"], "capital letter", "capital letters"))
    if r["pw_min_lower"]:
        out.append(many(r["pw_min_lower"], "small letter", "small letters"))
    if r["pw_min_symbols"]:
        out.append(many(r["pw_min_symbols"], "symbol (like ! ? # %)", "symbols (like ! ? # %)"))
    if r["pw_forbid_username"]:
        out.append("not contain your username")
    return out


def validate_new_password(password: str, rules: dict | None = None, username: str | None = None) -> None:
    r = clean_rules(rules)
    if len(password) > MAX_LENGTH:
        raise ValueError("Password is too long")
    problems = []
    if len(password) < r["pw_min_length"]:
        problems.append(f"be at least {r['pw_min_length']} characters long")
    counts = {
        "pw_min_digits": (sum(c.isdigit() for c in password), "number", "numbers"),
        "pw_min_upper": (sum(c.isupper() for c in password), "capital letter", "capital letters"),
        "pw_min_lower": (sum(c.islower() for c in password), "small letter", "small letters"),
        "pw_min_symbols": (sum(not c.isalnum() for c in password), "symbol", "symbols"),
    }
    for key, (have, one, more) in counts.items():
        need = r[key]
        if need and have < need:
            problems.append(f"have at least {need} {one if need == 1 else more}")
    if r["pw_forbid_username"] and username and len(username) >= 3 and username.lower() in password.lower():
        problems.append("not contain your username")
    if problems:
        raise ValueError("Password must " + ", ".join(problems[:-1]) + (" and " if len(problems) > 1 else "") + problems[-1])


def hash_password(password: str) -> dict:
    salt = secrets.token_bytes(16)
    digest = _derive(password, salt, TIME_COST, MEMORY_KIB, LANES, HASH_LEN)
    return {"alg": "argon2id", "t": TIME_COST, "m": MEMORY_KIB, "p": LANES, "salt": _b64(salt), "hash": _b64(digest)}


def verify_password(password: str, stored: dict | None) -> bool:
    """Constant-work verification. With no stored hash (unknown user) a
    dummy hash is still computed so response time does not reveal whether
    the username exists."""
    if not stored or stored.get("alg") != "argon2id":
        _derive(password or "x", secrets.token_bytes(16), TIME_COST, MEMORY_KIB, LANES, HASH_LEN)
        return False
    try:
        salt = base64.b64decode(stored["salt"])
        expected = base64.b64decode(stored["hash"])
        actual = _derive(password, salt, int(stored["t"]), int(stored["m"]), int(stored["p"]), len(expected))
    except Exception:
        return False
    return secrets.compare_digest(actual, expected)


def needs_rehash(stored: dict) -> bool:
    return (stored.get("t"), stored.get("m"), stored.get("p")) != (TIME_COST, MEMORY_KIB, LANES)
