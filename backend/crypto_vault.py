from __future__ import annotations

import json
import os
import secrets
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.argon2 import Argon2id

ARGON_TIME_COST = 3
ARGON_MEMORY_COST_KIB = 64 * 1024
ARGON_PARALLELISM = 4
ARGON_HASH_LEN = 32

# Each Argon2id derivation uses ~64 MiB of RAM. Allowing only one at a time
# stops a burst of unlock requests from exhausting memory on small HA hosts.
_KDF_SLOT = threading.BoundedSemaphore(1)
NONCE_LEN = 12
KEY_LEN = 32

MASTER_AAD = b"enveliq:master-key:v1"
GLOBAL_AAD_PREFIX = b"enveliq:global:v1:"
ACCOUNT_WRAP_AAD_PREFIX = b"enveliq:account-wrap:v1:"
ACCOUNT_DATA_AAD_PREFIX = b"enveliq:account-data:v1:"
MESSAGE_DATA_AAD_PREFIX = b"enveliq:message-data:v1:"
AUDIT_AAD_PREFIX = b"enveliq:audit:v1:"
USER_AAD_PREFIX = b"enveliq:user:v1:"


class VaultError(RuntimeError):
    pass


class VaultLocked(VaultError):
    pass


class InvalidPassphrase(VaultError):
    pass


class VaultAlreadyInitialized(VaultError):
    pass


class VaultNotInitialized(VaultError):
    pass


@dataclass(frozen=True)
class Principal:
    user_id: str
    name: str
    is_admin: bool


class SecureVault:
    """Encrypted-at-rest storage for the secure prototype.

    Sensitive application data is always written as AES-256-GCM ciphertext.
    The master key is random and is itself encrypted (wrapped) by a KEK derived
    from an administrator passphrase using Argon2id.

    Only non-sensitive structural data is plaintext in SQLite: random UUIDs,
    nonces, salts and ciphertext blobs.
    """

    def __init__(self, db_path: str | Path, idle_lock_seconds: int = 1800):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        try:
            os.chmod(self.db_path.parent, 0o700)
        except OSError:
            pass

        self.idle_lock_seconds = idle_lock_seconds
        self._master_key: bytearray | None = None
        self._last_activity = 0.0
        self._passive: set[int] = set()
        self._lock = threading.RLock()
        self._lock_listeners: list[Callable[[], None]] = []
        self.audit_hooks: list[Callable[[dict[str, Any]], None]] = []
        self._watchdog_stop: threading.Event | None = None
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.db_path)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON")
        con.execute("PRAGMA secure_delete=ON")
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA synchronous=FULL")
        con.execute("PRAGMA temp_store=MEMORY")
        return con

    def _init_db(self) -> None:
        with self._connect() as con:
            con.executescript(
                """
                CREATE TABLE IF NOT EXISTS vault_meta (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    salt BLOB NOT NULL,
                    master_nonce BLOB NOT NULL,
                    wrapped_master BLOB NOT NULL,
                    verifier_nonce BLOB NOT NULL,
                    verifier_ct BLOB NOT NULL
                );

                CREATE TABLE IF NOT EXISTS global_records (
                    id TEXT PRIMARY KEY,
                    nonce BLOB NOT NULL,
                    ciphertext BLOB NOT NULL
                );

                CREATE TABLE IF NOT EXISTS accounts (
                    id TEXT PRIMARY KEY,
                    wrap_nonce BLOB NOT NULL,
                    wrapped_dek BLOB NOT NULL,
                    data_nonce BLOB NOT NULL,
                    ciphertext BLOB NOT NULL
                );

                CREATE TABLE IF NOT EXISTS messages (
                    id TEXT PRIMARY KEY,
                    account_id TEXT NOT NULL,
                    data_nonce BLOB NOT NULL,
                    ciphertext BLOB NOT NULL,
                    FOREIGN KEY(account_id) REFERENCES accounts(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    data_nonce BLOB NOT NULL,
                    ciphertext BLOB NOT NULL
                );

                CREATE TABLE IF NOT EXISTS audit_events (
                    id TEXT PRIMARY KEY,
                    data_nonce BLOB NOT NULL,
                    ciphertext BLOB NOT NULL
                );
                """
            )
            # Record the KDF parameters next to the wrapped key so they can be
            # strengthened later without locking existing vaults out.
            columns = {r["name"] for r in con.execute("PRAGMA table_info(vault_meta)")}
            if "kdf_params" not in columns:
                con.execute("ALTER TABLE vault_meta ADD COLUMN kdf_params TEXT")

        if self.db_path.exists():
            try:
                os.chmod(self.db_path, 0o600)
            except OSError:
                pass

    @staticmethod
    def default_kdf_params() -> dict[str, Any]:
        return {
            "name": "argon2id",
            "time_cost": ARGON_TIME_COST,
            "memory_kib": ARGON_MEMORY_COST_KIB,
            "parallelism": ARGON_PARALLELISM,
            "hash_len": ARGON_HASH_LEN,
        }

    @staticmethod
    def _derive_kek(passphrase: str, salt: bytes, params: dict[str, Any] | None = None) -> bytes:
        if len(passphrase) < 12:
            raise ValueError("Passphrase must be at least 12 characters")
        p = params or SecureVault.default_kdf_params()
        if p.get("name") != "argon2id":
            raise VaultError("Unsupported key derivation function")
        with _KDF_SLOT:
            return Argon2id(
                salt=salt,
                length=int(p["hash_len"]),
                iterations=int(p["time_cost"]),
                lanes=int(p["parallelism"]),
                memory_cost=int(p["memory_kib"]),
            ).derive(passphrase.encode("utf-8"))

    @staticmethod
    def _json_bytes(payload: dict[str, Any]) -> bytes:
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")

    @staticmethod
    def _json_loads(payload: bytes) -> dict[str, Any]:
        return json.loads(payload.decode("utf-8"))

    @staticmethod
    def _encrypt(key: bytes, plaintext: bytes, aad: bytes) -> tuple[bytes, bytes]:
        nonce = secrets.token_bytes(NONCE_LEN)
        ciphertext = AESGCM(key).encrypt(nonce, plaintext, aad)
        return nonce, ciphertext

    @staticmethod
    def _decrypt(key: bytes, nonce: bytes, ciphertext: bytes, aad: bytes) -> bytes:
        return AESGCM(key).decrypt(nonce, ciphertext, aad)

    def is_initialized(self) -> bool:
        with self._connect() as con:
            row = con.execute("SELECT 1 FROM vault_meta WHERE id=1").fetchone()
            return row is not None

    # ---------- Lock state ----------

    def add_lock_listener(self, callback: Callable[[], None]) -> None:
        """Register a callback run every time the vault locks, including idle
        auto-lock, so in-memory caches of decrypted data can be wiped too."""
        self._lock_listeners.append(callback)

    def _notify_locked(self) -> None:
        # Always called WITHOUT self._lock held, so listeners may take their
        # own locks without risking a lock-order deadlock.
        for callback in list(self._lock_listeners):
            try:
                callback()
            except Exception:  # a failing listener must not keep the vault open
                pass

    def _wipe_key_locked(self) -> bool:
        """Zero and drop the master key. Caller holds self._lock."""
        if self._master_key is None:
            return False
        for i in range(len(self._master_key)):
            self._master_key[i] = 0
        self._master_key = None
        self._last_activity = 0.0
        return True

    def _expire_if_idle_locked(self) -> bool:
        if self._master_key is not None and (time.monotonic() - self._last_activity) > self.idle_lock_seconds:
            return self._wipe_key_locked()
        return False

    def _install_key(self, master: bytes) -> None:
        with self._lock:
            replaced = self._wipe_key_locked()
            self._master_key = bytearray(master)
            self._last_activity = time.monotonic()
        if replaced:
            self._notify_locked()

    def is_unlocked(self) -> bool:
        with self._lock:
            expired = self._expire_if_idle_locked()
            unlocked = self._master_key is not None
        if expired:
            self._notify_locked()
        return unlocked

    def initialize(self, passphrase: str) -> None:
        if self.is_initialized():
            raise VaultAlreadyInitialized("Vault is already initialized")
        params = self.default_kdf_params()
        salt = secrets.token_bytes(16)
        kek = self._derive_kek(passphrase, salt, params)
        master = secrets.token_bytes(KEY_LEN)
        master_nonce, wrapped_master = self._encrypt(kek, master, MASTER_AAD)
        verifier_nonce, verifier_ct = self._encrypt(master, b"vault-verifier-v1", b"vault-verifier")

        with self._lock:
            try:
                with self._connect() as con:
                    con.execute(
                        "INSERT INTO vault_meta(id,salt,master_nonce,wrapped_master,verifier_nonce,verifier_ct,kdf_params) "
                        "VALUES(1,?,?,?,?,?,?)",
                        (salt, master_nonce, wrapped_master, verifier_nonce, verifier_ct, json.dumps(params)),
                    )
            except sqlite3.IntegrityError as exc:  # lost a race with a concurrent setup
                raise VaultAlreadyInitialized("Vault is already initialized") from exc
        self._install_key(master)

    def unlock(self, passphrase: str) -> None:
        if not self.is_initialized():
            raise VaultNotInitialized("Vault has not been initialized")

        with self._connect() as con:
            row = con.execute("SELECT * FROM vault_meta WHERE id=1").fetchone()
        assert row is not None
        params = json.loads(row["kdf_params"]) if row["kdf_params"] else self.default_kdf_params()

        # The slow key derivation runs outside self._lock so a guess in
        # progress never blocks requests from users who are already signed in.
        try:
            kek = self._derive_kek(passphrase, row["salt"], params)
            master = self._decrypt(kek, row["master_nonce"], row["wrapped_master"], MASTER_AAD)
            verifier = self._decrypt(master, row["verifier_nonce"], row["verifier_ct"], b"vault-verifier")
            if verifier != b"vault-verifier-v1":
                raise InvalidPassphrase("Invalid passphrase")
        except Exception as exc:  # cryptography intentionally returns generic auth failure
            raise InvalidPassphrase("Invalid passphrase") from exc

        self._install_key(master)

    def change_passphrase(self, current: str, new: str) -> None:
        """Wrap the same master key with a new passphrase (new random salt). The
        stored data is not re-encrypted. Fails with InvalidPassphrase if `current` is wrong."""
        if not self.is_initialized():
            raise VaultNotInitialized("Vault has not been initialized")
        with self._connect() as con:
            row = con.execute("SELECT * FROM vault_meta WHERE id=1").fetchone()
        params = json.loads(row["kdf_params"]) if row["kdf_params"] else self.default_kdf_params()
        try:
            master = self._decrypt(self._derive_kek(current, row["salt"], params), row["master_nonce"], row["wrapped_master"], MASTER_AAD)
            if self._decrypt(master, row["verifier_nonce"], row["verifier_ct"], b"vault-verifier") != b"vault-verifier-v1":
                raise InvalidPassphrase("Invalid passphrase")
        except Exception as exc:
            raise InvalidPassphrase("Invalid passphrase") from exc
        salt = secrets.token_bytes(16)
        new_params = self.default_kdf_params()
        nonce, wrapped = self._encrypt(self._derive_kek(new, salt, new_params), master, MASTER_AAD)
        with self._lock, self._connect() as con:
            con.execute("UPDATE vault_meta SET salt=?, master_nonce=?, wrapped_master=?, kdf_params=? WHERE id=1",
                        (salt, nonce, wrapped, json.dumps(new_params)))

    def lock(self) -> None:
        with self._lock:
            was_unlocked = self._wipe_key_locked()
        if was_unlocked:
            self._notify_locked()

    @contextmanager
    def passive(self):
        """Work done by a background task on this thread does not count as
        activity, so it can never keep an idle vault from locking."""
        ident = threading.get_ident()
        with self._lock:
            self._passive.add(ident)
        try:
            yield
        finally:
            with self._lock:
                self._passive.discard(ident)

    def _master(self) -> bytes:
        with self._lock:
            expired = self._expire_if_idle_locked()
            key = bytes(self._master_key) if self._master_key is not None else None
            if key is not None and threading.get_ident() not in self._passive:
                self._last_activity = time.monotonic()
        if expired:
            self._notify_locked()
        if key is None:
            raise VaultLocked("Vault is locked")
        return key

    def start_idle_watchdog(self, interval_seconds: float = 15.0) -> None:
        """Enforce the idle lock on a timer, so the key leaves memory on time
        even when nobody makes another request."""
        if self._watchdog_stop is not None:
            return
        stop = threading.Event()
        self._watchdog_stop = stop

        def run() -> None:
            while not stop.wait(interval_seconds):
                self.is_unlocked()

        threading.Thread(target=run, name="enveliq-idle-lock", daemon=True).start()

    def stop_idle_watchdog(self) -> None:
        if self._watchdog_stop is not None:
            self._watchdog_stop.set()
            self._watchdog_stop = None

    def touch(self) -> None:
        _ = self._master()

    def status(self) -> dict[str, Any]:
        return {
            "initialized": self.is_initialized(),
            "unlocked": self.is_unlocked(),
            "idle_lock_seconds": self.idle_lock_seconds,
            "cipher": "AES-256-GCM",
            "kdf": "Argon2id",
            "raw_message_body_persistence": False,
            "raw_attachment_persistence": False,
        }

    # ---------- Global encrypted settings ----------

    def set_global(self, record_id: str, payload: dict[str, Any]) -> None:
        master = self._master()
        aad = GLOBAL_AAD_PREFIX + record_id.encode("utf-8")
        nonce, ct = self._encrypt(master, self._json_bytes(payload), aad)
        with self._connect() as con:
            con.execute(
                "INSERT INTO global_records(id,nonce,ciphertext) VALUES(?,?,?) "
                "ON CONFLICT(id) DO UPDATE SET nonce=excluded.nonce,ciphertext=excluded.ciphertext",
                (record_id, nonce, ct),
            )

    def get_global(self, record_id: str) -> dict[str, Any] | None:
        master = self._master()
        with self._connect() as con:
            row = con.execute("SELECT nonce,ciphertext FROM global_records WHERE id=?", (record_id,)).fetchone()
        if row is None:
            return None
        aad = GLOBAL_AAD_PREFIX + record_id.encode("utf-8")
        return self._json_loads(self._decrypt(master, row["nonce"], row["ciphertext"], aad))

    # ---------- Accounts ----------

    def _unwrap_account_dek(self, account_id: str, row: sqlite3.Row | None = None) -> bytes:
        master = self._master()
        if row is None:
            with self._connect() as con:
                row = con.execute("SELECT wrap_nonce,wrapped_dek FROM accounts WHERE id=?", (account_id,)).fetchone()
        if row is None:
            raise KeyError(account_id)
        aad = ACCOUNT_WRAP_AAD_PREFIX + account_id.encode("ascii")
        return self._decrypt(master, row["wrap_nonce"], row["wrapped_dek"], aad)

    def create_account(self, payload: dict[str, Any]) -> str:
        master = self._master()
        account_id = str(uuid.uuid4())
        dek = secrets.token_bytes(KEY_LEN)

        wrap_nonce, wrapped_dek = self._encrypt(
            master,
            dek,
            ACCOUNT_WRAP_AAD_PREFIX + account_id.encode("ascii"),
        )
        data_nonce, ciphertext = self._encrypt(
            dek,
            self._json_bytes(payload),
            ACCOUNT_DATA_AAD_PREFIX + account_id.encode("ascii"),
        )

        with self._connect() as con:
            con.execute(
                "INSERT INTO accounts(id,wrap_nonce,wrapped_dek,data_nonce,ciphertext) VALUES(?,?,?,?,?)",
                (account_id, wrap_nonce, wrapped_dek, data_nonce, ciphertext),
            )
        return account_id

    def get_account(self, account_id: str) -> dict[str, Any]:
        with self._connect() as con:
            row = con.execute("SELECT * FROM accounts WHERE id=?", (account_id,)).fetchone()
        if row is None:
            raise KeyError(account_id)
        dek = self._unwrap_account_dek(account_id, row)
        payload = self._decrypt(
            dek,
            row["data_nonce"],
            row["ciphertext"],
            ACCOUNT_DATA_AAD_PREFIX + account_id.encode("ascii"),
        )
        data = self._json_loads(payload)
        data["id"] = account_id
        return data

    def list_accounts(self) -> list[dict[str, Any]]:
        self._master()
        with self._connect() as con:
            ids = [r["id"] for r in con.execute("SELECT id FROM accounts ORDER BY rowid")]
        return [self.get_account(account_id) for account_id in ids]

    def update_account(self, account_id: str, payload: dict[str, Any]) -> None:
        with self._connect() as con:
            row = con.execute("SELECT * FROM accounts WHERE id=?", (account_id,)).fetchone()
        if row is None:
            raise KeyError(account_id)
        dek = self._unwrap_account_dek(account_id, row)
        nonce, ct = self._encrypt(
            dek,
            self._json_bytes(payload),
            ACCOUNT_DATA_AAD_PREFIX + account_id.encode("ascii"),
        )
        with self._connect() as con:
            con.execute("UPDATE accounts SET data_nonce=?,ciphertext=? WHERE id=?", (nonce, ct, account_id))

    def delete_account(self, account_id: str) -> None:
        self._master()
        with self._connect() as con:
            # Messages are deleted explicitly as well as by ON DELETE CASCADE,
            # so removal never depends on the foreign-key pragma being active.
            con.execute("DELETE FROM messages WHERE account_id=?", (account_id,))
            con.execute("DELETE FROM accounts WHERE id=?", (account_id,))
        # Checkpoint only after the DELETE transaction has fully closed;
        # checkpointing inside it fails and rolled the whole delete back.
        with self._connect() as con:
            con.execute("PRAGMA wal_checkpoint(TRUNCATE)")

    # ---------- Messages ----------

    @staticmethod
    def _assert_no_raw_content(value: Any) -> None:
        forbidden = {
            "raw_body", "body_html", "body_text", "raw_attachment", "attachment_bytes",
            "raw_bytes", "file_bytes", "content_bytes", "attachment_content", "base64_data",
        }
        if isinstance(value, dict):
            for key, child in value.items():
                if str(key).lower() in forbidden:
                    raise ValueError("Raw email bodies and attachment bytes may not be persisted")
                SecureVault._assert_no_raw_content(child)
        elif isinstance(value, list):
            for child in value:
                SecureVault._assert_no_raw_content(child)

    def create_message(self, account_id: str, payload: dict[str, Any]) -> str:
        # Enforce recursively so raw bytes cannot be smuggled inside attachment
        # metadata or other nested structures.
        self._assert_no_raw_content(payload)

        dek = self._unwrap_account_dek(account_id)
        message_id = str(uuid.uuid4())
        nonce, ct = self._encrypt(
            dek,
            self._json_bytes(payload),
            MESSAGE_DATA_AAD_PREFIX + account_id.encode("ascii") + b":" + message_id.encode("ascii"),
        )
        with self._connect() as con:
            con.execute(
                "INSERT INTO messages(id,account_id,data_nonce,ciphertext) VALUES(?,?,?,?)",
                (message_id, account_id, nonce, ct),
            )
        return message_id

    def update_message(self, account_id: str, message_id: str, payload: dict[str, Any]) -> None:
        """Replace one stored message (for example with its AI summary)."""
        self._assert_no_raw_content(payload)
        dek = self._unwrap_account_dek(account_id)
        nonce, ct = self._encrypt(
            dek,
            self._json_bytes(payload),
            MESSAGE_DATA_AAD_PREFIX + account_id.encode("ascii") + b":" + message_id.encode("ascii"),
        )
        with self._connect() as con:
            cur = con.execute(
                "UPDATE messages SET data_nonce=?, ciphertext=? WHERE id=? AND account_id=?",
                (nonce, ct, message_id, account_id),
            )
            if cur.rowcount == 0:
                raise KeyError(message_id)

    def list_messages(self, account_id: str) -> list[dict[str, Any]]:
        dek = self._unwrap_account_dek(account_id)
        with self._connect() as con:
            rows = con.execute("SELECT id,data_nonce,ciphertext FROM messages WHERE account_id=?", (account_id,)).fetchall()
        result = []
        for row in rows:
            aad = MESSAGE_DATA_AAD_PREFIX + account_id.encode("ascii") + b":" + row["id"].encode("ascii")
            payload = self._decrypt(dek, row["data_nonce"], row["ciphertext"], aad)
            data = self._json_loads(payload)
            data["id"] = row["id"]
            result.append(data)
        return result

    def get_message(self, account_id: str, message_id: str) -> dict[str, Any]:
        dek = self._unwrap_account_dek(account_id)
        with self._connect() as con:
            row = con.execute(
                "SELECT id,data_nonce,ciphertext FROM messages WHERE id=? AND account_id=?",
                (message_id, account_id),
            ).fetchone()
        if row is None:
            raise KeyError(message_id)
        aad = MESSAGE_DATA_AAD_PREFIX + account_id.encode("ascii") + b":" + message_id.encode("ascii")
        payload = self._decrypt(dek, row["data_nonce"], row["ciphertext"], aad)
        data = self._json_loads(payload)
        data["id"] = message_id
        return data

    def delete_message(self, account_id: str, message_id: str) -> None:
        self._master()
        with self._connect() as con:
            cur = con.execute("DELETE FROM messages WHERE id=? AND account_id=?", (message_id, account_id))
            if cur.rowcount == 0:
                raise KeyError(message_id)
        # Checkpoint only after the DELETE transaction has fully closed.
        with self._connect() as con:
            con.execute("PRAGMA wal_checkpoint(TRUNCATE)")

    # ---------- Users ----------
    # User records (username, password hash, role, TOTP secret, recovery code
    # digests, passkeys, SSO links) are encrypted under the master key, so a
    # copied database reveals no usernames or second-factor secrets. Sign-in
    # therefore needs the vault unlocked first.

    def _user_aad(self, user_id: str) -> bytes:
        return USER_AAD_PREFIX + user_id.encode("ascii")

    def create_user(self, payload: dict[str, Any]) -> str:
        master = self._master()
        user_id = str(uuid.uuid4())
        nonce, ct = self._encrypt(master, self._json_bytes(payload), self._user_aad(user_id))
        with self._connect() as con:
            con.execute("INSERT INTO users(id,data_nonce,ciphertext) VALUES(?,?,?)", (user_id, nonce, ct))
        return user_id

    def get_user(self, user_id: str) -> dict[str, Any]:
        master = self._master()
        with self._connect() as con:
            row = con.execute("SELECT data_nonce,ciphertext FROM users WHERE id=?", (user_id,)).fetchone()
        if row is None:
            raise KeyError(user_id)
        data = self._json_loads(self._decrypt(master, row["data_nonce"], row["ciphertext"], self._user_aad(user_id)))
        data["id"] = user_id
        return data

    def list_users(self) -> list[dict[str, Any]]:
        master = self._master()
        with self._connect() as con:
            rows = con.execute("SELECT id,data_nonce,ciphertext FROM users ORDER BY rowid").fetchall()
        out = []
        for row in rows:
            data = self._json_loads(self._decrypt(master, row["data_nonce"], row["ciphertext"], self._user_aad(row["id"])))
            data["id"] = row["id"]
            out.append(data)
        return out

    def update_user(self, user_id: str, payload: dict[str, Any]) -> None:
        master = self._master()
        payload = {k: v for k, v in payload.items() if k != "id"}
        nonce, ct = self._encrypt(master, self._json_bytes(payload), self._user_aad(user_id))
        with self._connect() as con:
            cur = con.execute("UPDATE users SET data_nonce=?,ciphertext=? WHERE id=?", (nonce, ct, user_id))
            if cur.rowcount == 0:
                raise KeyError(user_id)

    def delete_user(self, user_id: str) -> None:
        self._master()
        with self._connect() as con:
            con.execute("DELETE FROM users WHERE id=?", (user_id,))
        with self._connect() as con:
            con.execute("PRAGMA wal_checkpoint(TRUNCATE)")

    def count_users(self) -> int:
        with self._connect() as con:
            return con.execute("SELECT COUNT(*) FROM users").fetchone()[0]

    # ---------- Audit ----------

    def audit(self, payload: dict[str, Any]) -> str:
        master = self._master()
        event_id = str(uuid.uuid4())
        nonce, ct = self._encrypt(
            master,
            self._json_bytes(payload),
            AUDIT_AAD_PREFIX + event_id.encode("ascii"),
        )
        with self._connect() as con:
            con.execute(
                "INSERT INTO audit_events(id,data_nonce,ciphertext) VALUES(?,?,?)",
                (event_id, nonce, ct),
            )
        for hook in list(self.audit_hooks):
            try:
                hook(payload)
            except Exception:             # reporting must never break an audited action
                pass
        return event_id

    def plaintext_scan(self, needles: Iterable[str]) -> dict[str, bool]:
        """Development/test helper: prove known sensitive strings are absent from DB/WAL/SHM bytes."""
        paths = [self.db_path, Path(str(self.db_path) + "-wal"), Path(str(self.db_path) + "-shm")]
        blobs = b"".join(p.read_bytes() for p in paths if p.exists())
        return {needle: needle.encode("utf-8") in blobs for needle in needles}

    @staticmethod
    def export_public_crypto_metadata() -> dict[str, Any]:
        return {
            "cipher": "AES-256-GCM",
            "kdf": "Argon2id",
            "argon2_time_cost": ARGON_TIME_COST,
            "argon2_memory_kib": ARGON_MEMORY_COST_KIB,
            "argon2_parallelism": ARGON_PARALLELISM,
            "master_key_bits": KEY_LEN * 8,
            "per_account_dek_bits": KEY_LEN * 8,
        }
