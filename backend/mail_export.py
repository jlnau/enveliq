"""Export for the new Mail: one zip with everything a person needs to move from Enveliq to Mail (the Casier module).

The zip holds a locked copy of the vault (the same kind of copy a backup is), a small manifest, and the Proton Bridge certificate if one
is mounted (a certificate is public). It never holds the vault key or passphrase: whoever imports it types that.
"""
from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import time
import zipfile
from pathlib import Path
from typing import Any

from .version import VERSION

FORMAT = "enveliq-for-mail"
FORMAT_VERSION = 1
KEEP_SECONDS = 3600
NAME_PATTERN = r"^enveliq-for-mail-\d{8}-\d{6}\.zip$"


def key_mode(env: dict[str, str] | None = None) -> str:
    """"key" when the server unlocks itself from ENVELIQ_VAULT_KEY (or its file), otherwise "passphrase"."""
    e = os.environ if env is None else env
    return "key" if (e.get("ENVELIQ_VAULT_KEY", "").strip() or e.get("ENVELIQ_VAULT_KEY_FILE", "").strip()) else "passphrase"


def _hosts(name: str, env: dict[str, str]) -> list[str]:
    return [h.strip() for h in env.get(name, "").split(",") if h.strip()]


def _bridge_certificate(env: dict[str, str]) -> bytes | None:
    path = Path(env.get("ENVELIQ_BRIDGE_CA_FILE", "/etc/enveliq/proton-bridge.crt"))
    try:
        data = path.read_bytes()
    except OSError:
        return None
    return data if b"BEGIN CERTIFICATE" in data and len(data) < 65536 else None


def prepare_folder(folder: Path, now: float | None = None) -> None:
    folder.mkdir(mode=0o700, exist_ok=True)
    os.chmod(folder, 0o700)
    t = time.time() if now is None else now
    for old in folder.glob("enveliq-for-mail-*.zip"):
        try:
            if t - old.stat().st_mtime > KEEP_SECONDS:
                old.unlink()
        except OSError:
            pass


def build(vault_db: Path, folder: Path, env: dict[str, str] | None = None, now: float | None = None) -> dict[str, Any]:
    """Make the zip in `folder` and say what it is called. The vault is copied with SQLite's own backup, so it is safe while Enveliq runs."""
    e = dict(os.environ if env is None else env)
    t = time.time() if now is None else now
    prepare_folder(folder, t)
    stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime(t))
    final = folder / f"enveliq-for-mail-{stamp}.zip"
    n = 1
    while final.exists():
        final = folder / f"enveliq-for-mail-{time.strftime('%Y%m%d-%H%M%S', time.localtime(t + n))}.zip"
        n += 1
    part = final.with_suffix(".partial")
    part.unlink(missing_ok=True)
    with tempfile.TemporaryDirectory(dir=folder) as tmp:
        copy = Path(tmp) / "vault.sqlite3"
        src = sqlite3.connect(vault_db)
        dst = sqlite3.connect(copy)
        try:
            src.backup(dst)
            dst.execute("PRAGMA journal_mode=DELETE")
        finally:
            dst.close()
            src.close()
        check = sqlite3.connect(f"file:{copy}?mode=ro", uri=True)
        try:
            if check.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise RuntimeError("vault copy failed its check")
        finally:
            check.close()
        cert = _bridge_certificate(e)
        manifest = {
            "format": FORMAT, "format_version": FORMAT_VERSION, "enveliq_version": VERSION, "made_at": int(t),
            "vault_unlock": key_mode(e),
            "bridge_allowed_hosts": _hosts("ENVELIQ_BRIDGE_ALLOWED_HOSTS", e),
            "mail_allowed_hosts": _hosts("ENVELIQ_MAIL_ALLOWED_HOSTS", e),
            "has_bridge_certificate": cert is not None,
        }
        fd = os.open(part, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as fh, zipfile.ZipFile(fh, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("manifest.json", json.dumps(manifest, indent=2))
            z.write(copy, "vault.sqlite3")
            if cert is not None:
                z.writestr("bridge-ca.pem", cert)
    os.replace(part, final)
    return {"name": final.name, "bytes": final.stat().st_size, "vault_unlock": manifest["vault_unlock"], "has_bridge_certificate": cert is not None}
