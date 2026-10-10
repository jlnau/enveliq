"""Automatic unlock from a key file.

By default Enveliq's vault is opened by a passphrase someone types after every
restart. Setting ENVELIQ_VAULT_KEY_FILE to a file path switches to a key kept in
that file instead: Enveliq reads it when it starts and unlocks itself.

The file should live OUTSIDE the data folder (a separate folder or a Docker
secret), so a copy of the data folder or a backup of it does not include the key.
The key is a long random string used exactly like the passphrase; the vault's
key derivation (Argon2id) still applies. It is never logged and never sent to a
browser.
"""
from __future__ import annotations

import os
import secrets
import stat
from pathlib import Path

MIN_CHARS = 32


class KeyFileError(Exception):
    """`code` is one of unreadable, too_short, cannot_create. Never includes the key."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def read_key(path: str | Path) -> str | None:
    """The key in the file, or None if the file does not exist."""
    try:
        text = Path(path).read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return None
    except (OSError, UnicodeDecodeError):
        raise KeyFileError("unreadable") from None
    if len(text) < MIN_CHARS:
        raise KeyFileError("too_short")
    return text


def create_key(path: str | Path) -> str:
    """Make a new random key file (owner-only), refusing to overwrite an existing one."""
    key = secrets.token_urlsafe(48)
    try:
        fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(key + "\n")
    except OSError:
        raise KeyFileError("cannot_create") from None
    return key


def too_open(path: str | Path) -> bool:
    """True if other users on the machine can read the file (and it is not a Docker secret)."""
    try:
        mode = os.stat(path).st_mode
    except OSError:
        return False
    return bool(mode & (stat.S_IRGRP | stat.S_IROTH)) and not str(path).startswith("/run/secrets/")
