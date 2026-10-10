"""Switch an existing vault between a typed passphrase and a key file.

    docker compose exec -it enveliq python -m backend.vault_key adopt
    docker compose exec -it enveliq python -m backend.vault_key use-passphrase
    docker compose exec enveliq python -m backend.vault_key status

Nothing stored is re-encrypted: the vault's master key is wrapped with the new
secret. Run it on the server (it needs the data folder), then restart Enveliq.
Needs ENVELIQ_VAULT_KEY (or ENVELIQ_VAULT_KEY_FILE) set (see docs/VAULT_KEY.md).
"""
from __future__ import annotations

import getpass
import os
import sys
from pathlib import Path

from . import keyfile
from .crypto_vault import InvalidPassphrase, SecureVault


def _vault() -> SecureVault:
    data = Path(os.environ.get("ENVELIQ_DATA_DIR", str(Path(__file__).resolve().parent.parent / "data")))
    return SecureVault(data / "vault.sqlite3")


def _configured(create: bool = False) -> tuple[str | None, bool]:
    """(key, was_existing) from the key file (wins if both are set) or ENVELIQ_VAULT_KEY."""
    path = os.environ.get("ENVELIQ_VAULT_KEY_FILE", "").strip()
    env = os.environ.get("ENVELIQ_VAULT_KEY", "").strip()
    if not path and not env:
        sys.exit("Set ENVELIQ_VAULT_KEY (or ENVELIQ_VAULT_KEY_FILE) first (see docs/VAULT_KEY.md).")
    try:
        if path:
            existing = keyfile.read_key(path)
            if existing is None and create:
                return keyfile.create_key(path), False
            return existing, True
        if len(env) < keyfile.MIN_CHARS:
            raise keyfile.KeyFileError("too_short")
        return env, True
    except keyfile.KeyFileError as err:
        sys.exit({"unreadable": "Cannot read the key file.", "too_short": "The key is too short (use at least 32 characters, e.g. openssl rand -base64 48).",
                  "cannot_create": "Cannot create the key file: make its folder writable."}[err.code])


def adopt() -> None:
    vault = _vault()
    if not vault.is_initialized():
        sys.exit("Enveliq is not set up yet. A new setup uses the key automatically; nothing to switch.")
    key, existing = _configured()
    current = getpass.getpass("Current vault passphrase: ")
    try:
        if key is None:
            # Check the passphrase BEFORE making a key file, so a wrong passphrase
            # never leaves behind a key file that does not match the vault.
            vault.unlock(current)
            key, existing = _configured(create=True)
        vault.change_passphrase(current, key)
    except InvalidPassphrase:
        sys.exit("That passphrase is not correct. Nothing was changed.")
    print(f"Done. The vault now opens with the configured key ({'existing' if existing else 'newly made'}).")
    print("Keep a copy of the key somewhere SEPARATE from the data. Without it the data cannot be opened.")
    print("Restart Enveliq: it will unlock itself and the unlock page will no longer appear.")


def use_passphrase() -> None:
    vault = _vault()
    key, _ = _configured()
    if key is None:
        sys.exit("Cannot read the key, so the vault cannot be opened to change it.")
    new = getpass.getpass("New vault passphrase (12 or more characters): ")
    if len(new) < 12 or new != getpass.getpass("Repeat it: "):
        sys.exit("The passphrase must be at least 12 characters and typed the same twice. Nothing was changed.")
    try:
        vault.change_passphrase(key, new)
    except InvalidPassphrase:
        sys.exit("The key does not match this vault. Nothing was changed.")
    print("Done. The vault now opens with the new passphrase.")
    print("Remove ENVELIQ_VAULT_KEY and ENVELIQ_VAULT_KEY_FILE from the Compose file and restart Enveliq. You will type the passphrase after each restart.")


def status() -> None:
    vault = _vault()
    if not vault.is_initialized():
        print("Not set up yet.")
        return
    if not os.environ.get("ENVELIQ_VAULT_KEY_FILE", "").strip() and not os.environ.get("ENVELIQ_VAULT_KEY", "").strip():
        print("Mode: typed passphrase (no key configured).")
        return
    key, _ = _configured()
    if key is None:
        print("Key file configured, but the file does not exist.")
        return
    try:
        vault.unlock(key)
        print("Mode: automatic unlock. The configured key matches this vault.")
    except InvalidPassphrase:
        print("A key is configured, but it does NOT match this vault (the vault still uses a typed passphrase).")


if __name__ == "__main__":
    commands = {"adopt": adopt, "use-passphrase": use_passphrase, "status": status}
    if len(sys.argv) != 2 or sys.argv[1] not in commands:
        sys.exit(__doc__)
    commands[sys.argv[1]]()
