"""Backup and restore of the encrypted vault. Administrators only.

A backup is a consistent copy of the vault file (taken with SQLite's own backup
call, so it is safe while Enveliq is running). It holds only what the vault
holds: ciphertext. It never includes the key file, which lives outside the data
folder. Anyone who gets a backup also needs the vault passphrase or the key
file to read it.

Restore replaces the stored mail, people and settings with the ones in a backup
made by this same vault (the same master key). The passphrase wrapping in
`vault_meta` is left alone, so the passphrase you have today keeps working. The
sign-in history (audit events) is kept, never replaced.
"""
from __future__ import annotations

import logging
import os
import re
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Callable

log = logging.getLogger("enveliq.backup")

RECORD = "backup_config"
DEFAULT_KEEP_DAYS = 7
MIN_KEEP_DAYS, MAX_KEEP_DAYS = 1, 60
DAY = 86400.0
KINDS = ("manual", "auto", "before-restore")
NAME = re.compile(r"^enveliq-(\d{8})-(\d{6})-(manual|auto|before-restore)\.sqlite3$")
MAX_MANUAL = 20                                     # a stop to a folder that grows without end
RESTORE_TABLES = ("global_records", "accounts", "messages", "users")     # audit_events and vault_meta stay as they are


class BackupError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code, self.message = code, message


class BackupManager:
    def __init__(self, vault: Any, folder: Path, clock: Callable[[], float] = time.time):
        self.vault = vault
        self.folder = Path(folder)
        self.clock = clock
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.last_error: str | None = None

    # ---------- settings ----------

    def settings(self) -> dict[str, Any]:
        raw = self.vault.get_global(RECORD) or {}
        days = raw.get("keep_days")
        if not isinstance(days, int) or isinstance(days, bool) or not MIN_KEEP_DAYS <= days <= MAX_KEEP_DAYS:
            days = DEFAULT_KEEP_DAYS
        return {"daily": raw.get("daily") is True, "keep_days": days}

    def save_settings(self, daily: bool, keep_days: int) -> dict[str, Any]:
        days = max(MIN_KEEP_DAYS, min(int(keep_days), MAX_KEEP_DAYS))
        self.vault.set_global(RECORD, {"daily": bool(daily), "keep_days": days})
        return self.settings()

    # ---------- the folder ----------

    def _prepare(self) -> None:
        self.folder.mkdir(parents=True, exist_ok=True, mode=0o700)
        try:
            os.chmod(self.folder, 0o700)
        except OSError:
            pass

    @staticmethod
    def _stamp(name: str) -> float:
        m = NAME.match(name)
        return time.mktime(time.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S")) if m else 0.0

    def list(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        if not self.folder.is_dir():
            return out
        for p in self.folder.iterdir():
            m = NAME.match(p.name)
            if not m or not p.is_file():
                continue
            out.append({"name": p.name, "kind": m.group(3), "at": self._stamp(p.name), "bytes": p.stat().st_size})
        return sorted(out, key=lambda b: (b["at"], b["name"]), reverse=True)

    def latest(self) -> dict[str, Any] | None:
        found = self.list()
        return found[0] if found else None

    def path_of(self, name: str) -> Path:
        """Only a name this manager made. Anything else is 'not found', so a path can never be steered."""
        if not isinstance(name, str) or not NAME.match(name):
            raise BackupError("not_found", "Backup not found")
        p = self.folder / name
        if not p.is_file():
            raise BackupError("not_found", "Backup not found")
        return p

    # ---------- making one ----------

    def create(self, kind: str = "manual") -> dict[str, Any]:
        if kind not in KINDS:
            raise BackupError("bad_kind", "Unknown kind of backup")
        if not self.vault.is_initialized():
            raise BackupError("not_ready", "There is nothing to back up yet")
        with self._lock:
            self._prepare()
            if kind == "manual" and sum(1 for b in self.list() if b["kind"] == "manual") >= MAX_MANUAL:
                raise BackupError("too_many", f"There are already {MAX_MANUAL} saved backups. Delete one you no longer need first.")
            stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime(self.clock()))
            final = self.folder / f"enveliq-{stamp}-{kind}.sqlite3"
            n = 1
            while final.exists():                           # two in the same second
                stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime(self.clock() + n))
                final = self.folder / f"enveliq-{stamp}-{kind}.sqlite3"
                n += 1
            part = final.with_suffix(".partial")
            part.unlink(missing_ok=True)
            fd = os.open(part, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            os.close(fd)
            try:
                src = sqlite3.connect(self.vault.db_path)
                dst = sqlite3.connect(part)
                try:
                    src.backup(dst)
                    dst.execute("PRAGMA journal_mode=DELETE")          # one self-contained file
                finally:
                    dst.close()
                    src.close()
                self._verify(part)
                os.chmod(part, 0o600)
                os.replace(part, final)
            except Exception as err:
                part.unlink(missing_ok=True)
                self.last_error = "backup_failed"
                log.warning("backup failed")
                if isinstance(err, BackupError):
                    raise
                raise BackupError("failed", "The backup could not be made. Check the free space on the disk.") from None
            self.last_error = None
            return {"name": final.name, "kind": kind, "at": self._stamp(final.name), "bytes": final.stat().st_size}

    def _verify(self, path: Path) -> None:
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            if con.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise BackupError("corrupt", "The copy did not pass its check")
            if con.execute("SELECT COUNT(*) FROM vault_meta").fetchone()[0] != 1:
                raise BackupError("corrupt", "The copy does not hold a vault")
        finally:
            con.close()

    def delete(self, name: str) -> None:
        with self._lock:
            self.path_of(name).unlink()

    # ---------- keeping the folder tidy ----------

    def prune(self) -> int:
        """Only automatic backups are removed by age. Ones a person made, and the safety copy
        taken before a restore, stay until someone deletes them."""
        cutoff = self.clock() - self.settings()["keep_days"] * DAY
        gone = 0
        with self._lock:
            for b in self.list():
                if b["kind"] == "auto" and b["at"] < cutoff:
                    try:
                        (self.folder / b["name"]).unlink()
                        gone += 1
                    except OSError:
                        pass
            if self.folder.is_dir():
                for p in self.folder.glob("*.partial"):
                    if p.stat().st_mtime < self.clock() - 3600:
                        p.unlink(missing_ok=True)
        return gone

    def run_due(self) -> bool:
        """The daily backup: made when it is switched on and the last automatic one is over a day old."""
        if not self.vault.is_unlocked():
            return False
        with self.vault.passive():
            if not self.settings()["daily"]:
                return False
            autos = [b for b in self.list() if b["kind"] == "auto"]
            if autos and self.clock() - autos[0]["at"] < DAY:
                return False
            self.create("auto")
            self.prune()
            return True

    def start(self) -> None:
        if self._thread:
            return
        self._thread = threading.Thread(target=self._run, name="enveliq-backup", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        while not self._stop.wait(600):
            try:
                self.run_due()
            except Exception:
                log.warning("daily backup pass failed")

    # ---------- restoring ----------

    def check_restorable(self, name: str) -> dict[str, Any]:
        """Is this backup from this same vault (same master key)? Returns what it holds, in counts only."""
        path = self.path_of(name)
        self._verify(path)
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        con.row_factory = sqlite3.Row
        try:
            meta = con.execute("SELECT verifier_nonce, verifier_ct FROM vault_meta WHERE id=1").fetchone()
            if meta is None:
                raise BackupError("corrupt", "The copy does not hold a vault")
            try:
                ok = self.vault._decrypt(self.vault._master(), meta["verifier_nonce"], meta["verifier_ct"], b"vault-verifier") == b"vault-verifier-v1"
            except Exception:
                ok = False
            if not ok:
                raise BackupError("other_vault", "This backup was made by a different Enveliq (a different key), so it can't be restored here.")
            counts = {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in ("accounts", "messages", "users")}
            user_ids = {r[0] for r in con.execute("SELECT id FROM users")}
        finally:
            con.close()
        return {"counts": counts, "user_ids": user_ids}

    def restore(self, name: str, acting_user_id: str) -> dict[str, Any]:
        """Replace mail, people and settings with the backup's. A safety copy of today's vault is made first."""
        with self._lock:
            info = self.check_restorable(name)
            if acting_user_id not in info["user_ids"]:
                raise BackupError("not_in_backup", "You are not in that backup, so restoring it would lock you out. Ask the administrator it was made for.")
            safety = self.create("before-restore")
            path = self.path_of(name)
            con = sqlite3.connect(self.vault.db_path, isolation_level=None, timeout=30)
            try:
                con.execute("PRAGMA foreign_keys=ON")
                con.execute("PRAGMA secure_delete=ON")
                con.execute("ATTACH DATABASE ? AS old", (str(path),))
                con.execute("BEGIN IMMEDIATE")
                try:
                    for table in ("messages", "accounts", "users", "global_records"):
                        con.execute(f"DELETE FROM main.{table}")
                    for table in ("global_records", "accounts", "messages", "users"):
                        cols = [r[1] for r in con.execute(f"PRAGMA main.table_info({table})")]
                        lst = ",".join(cols)
                        con.execute(f"INSERT INTO main.{table}({lst}) SELECT {lst} FROM old.{table}")
                    con.execute("COMMIT")
                except Exception:
                    con.execute("ROLLBACK")
                    raise
                con.execute("DETACH DATABASE old")
                con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            except Exception:
                log.warning("restore failed")
                raise BackupError("failed", "The restore did not work and nothing was changed.") from None
            finally:
                con.close()
            return {"restored": name, "safety_copy": safety["name"], "counts": info["counts"]}
