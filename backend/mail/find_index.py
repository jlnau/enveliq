"""Fast search: an encrypted word list so a search of a big mailbox is instant.

What is kept: for each email, only where it lives (mailbox, folder, validity, message number) and which words it
contains. The words are in a full-text index that has no copy of the email text. The index is one file per person,
sealed with a key derived from the vault key, so it can only be read while the vault is unlocked. It is not part of
backups or exports, and it is deleted when a person turns Fast search off or is removed.

The index skips numbers longer than 8 digits and words longer than 30 characters, so card numbers, long codes and
keys are not kept. It covers the subject, sender, recipients and the text of the email, not attachments.
"""
from __future__ import annotations

import logging
import os
import re
import secrets
import sqlite3
import struct
import threading
import time
import unicodedata
import zlib
from pathlib import Path
from typing import Any, Callable

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .bridge import Bridge, Target
from .errors import BridgeError
from .find import Term, choose_folders
from .parse import render_original

log = logging.getLogger("enveliq.find")

MAX_WORD = 30
MAX_NUMBER = 8
MAX_TEXT = 300_000
BATCH = 20
PAUSE = 0.2                 # between batches, so a build never loads the mailbox heavily
UPKEEP_SECONDS = 300
SAVE_SECONDS = 60
CHUNK = 16 * 1024 * 1024
MAGIC = b"ENVFIDX1"

_WORD = re.compile(r"[^\W_]+", re.UNICODE)


# ---------- words ----------

def fold(text: str) -> str:
    """Lower case, and without accents, so 'Café' and 'cafe' are the same word."""
    return "".join(c for c in unicodedata.normalize("NFKD", str(text).casefold()) if not unicodedata.combining(c))


def skippable(word: str) -> bool:
    return len(word) > MAX_WORD or (word.isdigit() and len(word) > MAX_NUMBER)


def words(text: str) -> list[str]:
    """The words that are kept for this text."""
    return [w for w in _WORD.findall(fold(text)) if not skippable(w)]


def match_query(terms: list[Term]) -> str | None:
    """An FTS5 query for these search words, or None when the index cannot answer them faithfully
    (a word that is never kept, such as a long number): the live search is used instead.
    Typed words match the start of a word; quoted words must match whole words in that order."""
    parts: list[str] = []
    for term in terms:
        found = _WORD.findall(fold(term.text))
        if not found or any(skippable(w) for w in found):
            return None
        if term.phrase:
            parts.append('"' + " ".join(found) + '"')
        else:
            parts.extend(f'"{w}"*' for w in found)
    return " AND ".join(parts) if parts else None


# ---------- one person's index, in memory ----------

class UserIndex:
    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.db = self._new()
        self.dirty = False

    @staticmethod
    def _new() -> sqlite3.Connection:
        db = sqlite3.connect(":memory:", check_same_thread=False)
        db.executescript(
            """
            CREATE TABLE docs (id INTEGER PRIMARY KEY, account TEXT NOT NULL, folder TEXT NOT NULL, validity INTEGER NOT NULL, uid INTEGER NOT NULL);
            CREATE UNIQUE INDEX docs_place ON docs (account, folder, uid);
            CREATE TABLE folders (account TEXT NOT NULL, folder TEXT NOT NULL, validity INTEGER NOT NULL, total INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (account, folder));
            CREATE TABLE marks (account TEXT PRIMARY KEY, complete INTEGER NOT NULL DEFAULT 0, updated REAL NOT NULL DEFAULT 0);
            CREATE VIRTUAL TABLE fts USING fts5(body, content='', contentless_delete=1, tokenize='unicode61 remove_diacritics 0', prefix='2 3');
            """
        )
        return db

    # -- writing --
    def add(self, account: str, folder: str, validity: int, uid: int, text: str) -> None:
        with self.lock:
            cur = self.db.execute("INSERT OR IGNORE INTO docs (account, folder, validity, uid) VALUES (?,?,?,?)", (account, folder, validity, uid))
            if cur.rowcount:
                self.db.execute("INSERT INTO fts (rowid, body) VALUES (?, ?)", (cur.lastrowid, " ".join(words(text))))
                self.dirty = True

    def remove_uids(self, account: str, folder: str, uids: set[int]) -> None:
        with self.lock:
            for uid in uids:
                row = self.db.execute("SELECT id FROM docs WHERE account=? AND folder=? AND uid=?", (account, folder, uid)).fetchone()
                if row:
                    self.db.execute("DELETE FROM fts WHERE rowid=?", (row[0],))
                    self.db.execute("DELETE FROM docs WHERE id=?", (row[0],))
                    self.dirty = True

    def drop_folder(self, account: str, folder: str) -> None:
        with self.lock:
            for (rid,) in self.db.execute("SELECT id FROM docs WHERE account=? AND folder=?", (account, folder)).fetchall():
                self.db.execute("DELETE FROM fts WHERE rowid=?", (rid,))
            self.db.execute("DELETE FROM docs WHERE account=? AND folder=?", (account, folder))
            self.db.execute("DELETE FROM folders WHERE account=? AND folder=?", (account, folder))
            self.dirty = True

    def drop_account(self, account: str) -> None:
        with self.lock:
            for (rid,) in self.db.execute("SELECT id FROM docs WHERE account=?", (account,)).fetchall():
                self.db.execute("DELETE FROM fts WHERE rowid=?", (rid,))
            self.db.execute("DELETE FROM docs WHERE account=?", (account,))
            self.db.execute("DELETE FROM folders WHERE account=?", (account,))
            self.db.execute("DELETE FROM marks WHERE account=?", (account,))
            self.dirty = True

    def set_folder(self, account: str, folder: str, validity: int, total: int) -> None:
        with self.lock:
            self.db.execute("INSERT INTO folders (account, folder, validity, total) VALUES (?,?,?,?) ON CONFLICT(account, folder) DO UPDATE SET validity=excluded.validity, total=excluded.total", (account, folder, validity, total))
            self.dirty = True

    def set_complete(self, account: str, complete: bool) -> None:
        with self.lock:
            self.db.execute("INSERT INTO marks (account, complete, updated) VALUES (?,?,?) ON CONFLICT(account) DO UPDATE SET complete=excluded.complete, updated=excluded.updated", (account, int(complete), time.time()))
            self.dirty = True

    # -- reading --
    def folder_validity(self, account: str, folder: str) -> int | None:
        with self.lock:
            row = self.db.execute("SELECT validity FROM folders WHERE account=? AND folder=?", (account, folder)).fetchone()
            return row[0] if row else None

    def uids(self, account: str, folder: str) -> set[int]:
        with self.lock:
            return {r[0] for r in self.db.execute("SELECT uid FROM docs WHERE account=? AND folder=?", (account, folder))}

    def progress(self, account: str) -> dict[str, Any]:
        with self.lock:
            done = self.db.execute("SELECT COUNT(*) FROM docs WHERE account=?", (account,)).fetchone()[0]
            total = self.db.execute("SELECT COALESCE(SUM(total),0) FROM folders WHERE account=?", (account,)).fetchone()[0]
            mark = self.db.execute("SELECT complete, updated FROM marks WHERE account=?", (account,)).fetchone()
        return {"done": done, "total": max(total, done), "complete": bool(mark and mark[0]), "updated": mark[1] if mark else 0}

    def search(self, account: str, query: str, limit: int = 5000) -> dict[str, tuple[int, list[int]]]:
        """folder -> (validity, uids newest first) for every email that matches."""
        out: dict[str, tuple[int, list[int]]] = {}
        with self.lock:
            rows = self.db.execute(
                "SELECT d.folder, d.validity, d.uid FROM fts JOIN docs d ON d.id = fts.rowid WHERE fts MATCH ? AND d.account = ? ORDER BY d.uid DESC LIMIT ?",
                (query, account, limit)).fetchall()
        for folder, validity, uid in rows:
            out.setdefault(folder, (validity, []))[1].append(uid)
        return out

    # -- saving --
    def to_bytes(self) -> bytes:
        with self.lock:
            raw = self.db.serialize()
            self.dirty = False
        return zlib.compress(bytes(raw), 1)

    @classmethod
    def from_bytes(cls, blob: bytes) -> "UserIndex":
        idx = cls()
        idx.db.close()
        db = sqlite3.connect(":memory:", check_same_thread=False)
        db.deserialize(zlib.decompress(blob))
        db.execute("SELECT COUNT(*) FROM docs").fetchone()          # fails now, not later, if the file is not what it should be
        idx.db = db
        return idx


# ---------- the sealed file ----------

def seal(blob: bytes, key: bytes, aad: bytes) -> bytes:
    out = [MAGIC]
    aes = AESGCM(key)
    for n, start in enumerate(range(0, max(len(blob), 1), CHUNK)):
        nonce = secrets.token_bytes(12)
        piece = aes.encrypt(nonce, blob[start:start + CHUNK], aad + struct.pack(">I", n))
        out.append(struct.pack(">I", len(piece)) + nonce + piece)
    return b"".join(out)


def unseal(data: bytes, key: bytes, aad: bytes) -> bytes:
    if not data.startswith(MAGIC):
        raise ValueError("not a word list")
    aes, pos, n, parts = AESGCM(key), len(MAGIC), 0, []
    while pos < len(data):
        (size,) = struct.unpack(">I", data[pos:pos + 4])
        nonce, piece = data[pos + 4:pos + 16], data[pos + 16:pos + 16 + size]
        if len(piece) != size:
            raise ValueError("cut short")
        parts.append(aes.decrypt(nonce, piece, aad + struct.pack(">I", n)))
        pos += 16 + size
        n += 1
    return b"".join(parts)


# ---------- the manager: turns it on and off, builds it, keeps it current ----------

class FindIndex:
    def __init__(self, vault: Any, bridge: Bridge, load_account: Callable[[str], dict[str, Any]], target_for: Callable[[dict[str, Any]], Target], directory: Path,
                 upkeep_seconds: float = UPKEEP_SECONDS, pause: float = PAUSE):
        self.vault, self.bridge, self._load, self._target = vault, bridge, load_account, target_for
        self.dir = Path(directory)
        self.upkeep, self.pause = upkeep_seconds, pause
        self._indexes: dict[str, UserIndex] = {}
        self._workers: dict[tuple[str, str], threading.Thread] = {}
        self._stop = threading.Event()
        self._guard = threading.RLock()
        self._saved_at: dict[str, float] = {}
        self._errors: dict[tuple[str, str], str] = {}
        self._rebuild: set[tuple[str, str]] = set()
        vault.add_lock_listener(self.forget_memory)

    # ----- settings (which mailboxes have Fast search on) -----
    def _record(self, user_id: str) -> str:
        return "find-fast-v1:" + user_id

    def enabled(self, user_id: str) -> dict[str, Any]:
        return (self.vault.get_global(self._record(user_id)) or {}).get("accounts", {})

    def is_enabled(self, user_id: str, account_id: str) -> bool:
        return bool(self.enabled(user_id).get(account_id))

    def _save_enabled(self, user_id: str, accounts: dict[str, Any]) -> None:
        self.vault.set_global(self._record(user_id), {"accounts": accounts})

    # ----- files and memory -----
    def _path(self, user_id: str) -> Path:
        return self.dir / (re.sub(r"[^A-Za-z0-9-]", "", user_id) + ".bin")

    def _key(self, user_id: str) -> bytes:
        return self.vault.derive_key(b"find-index|" + user_id.encode())

    def _aad(self, user_id: str) -> bytes:
        return b"enveliq-find-index|" + user_id.encode()

    def forget_memory(self) -> None:
        """The vault locked: drop every word list from memory. The sealed files stay."""
        with self._guard:
            self._indexes.clear()

    def index(self, user_id: str) -> UserIndex:
        with self._guard:
            idx = self._indexes.get(user_id)
            if idx is not None:
                return idx
            path = self._path(user_id)
            idx = None
            if path.exists():
                try:
                    idx = UserIndex.from_bytes(unseal(path.read_bytes(), self._key(user_id), self._aad(user_id)))
                except (ValueError, InvalidTag, sqlite3.DatabaseError, zlib.error, OSError):
                    log.warning("find: a word list could not be read and will be built again")
                    idx = None
            if idx is None:
                idx = UserIndex()
                for account_id in self.enabled(user_id):
                    idx.drop_account(account_id)
            self._indexes[user_id] = idx
            return idx

    def save(self, user_id: str, force: bool = False) -> None:
        with self._guard:
            idx = self._indexes.get(user_id)
            if idx is None or not (idx.dirty or force):
                return
            if not force and time.monotonic() - self._saved_at.get(user_id, 0) < SAVE_SECONDS:
                return
            blob = seal(idx.to_bytes(), self._key(user_id), self._aad(user_id))
            self.dir.mkdir(parents=True, exist_ok=True, mode=0o700)
            tmp = self._path(user_id).with_suffix(".tmp")
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "wb") as fh:
                fh.write(blob)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, self._path(user_id))
            self._saved_at[user_id] = time.monotonic()

    # ----- turning on and off -----
    def enable(self, user_id: str, account_id: str) -> None:
        accounts = dict(self.enabled(user_id))
        accounts[account_id] = {"since": time.time()}
        self._save_enabled(user_id, accounts)
        self._start(user_id, account_id)

    def disable(self, user_id: str, account_id: str) -> None:
        accounts = dict(self.enabled(user_id))
        accounts.pop(account_id, None)
        self._save_enabled(user_id, accounts)
        with self.vault.passive():
            with self._guard:
                self.index(user_id).drop_account(account_id)
                if not accounts:
                    self._indexes.pop(user_id, None)
                    self._path(user_id).unlink(missing_ok=True)
                else:
                    self.save(user_id, force=True)
        self._errors.pop((user_id, account_id), None)

    def rebuild(self, user_id: str, account_id: str) -> None:
        with self._guard:
            self._rebuild.add((user_id, account_id))
        self._start(user_id, account_id)

    def delete_user(self, user_id: str) -> None:
        for account_id in list(self.enabled(user_id)):
            self._errors.pop((user_id, account_id), None)
        self.vault.set_global(self._record(user_id), {})
        with self._guard:
            self._indexes.pop(user_id, None)
        self._path(user_id).unlink(missing_ok=True)

    # ----- asking -----
    def ready(self, user_id: str, account_id: str) -> bool:
        if not self.is_enabled(user_id, account_id) or not self.vault.is_unlocked():
            return False
        return bool(self.index(user_id).progress(account_id)["complete"])

    def lookup(self, user_id: str, account_id: str, terms: list[Term]) -> dict[str, tuple[int, list[int]]] | None:
        """Matches from the word list, or None when the live search should be used instead."""
        if not self.ready(user_id, account_id):
            return None
        query = match_query(terms)
        if query is None:
            return None
        try:
            return self.index(user_id).search(account_id, query)
        except sqlite3.Error:
            return None

    def status(self, user_id: str, account_id: str) -> dict[str, Any]:
        on = self.is_enabled(user_id, account_id)
        out: dict[str, Any] = {"account_id": account_id, "enabled": on, "state": "off", "done": 0, "total": 0, "message": ""}
        if not on:
            return out
        if not self.vault.is_unlocked():
            return {**out, "state": "waiting", "message": "Waiting for Enveliq to be unlocked."}
        p = self.index(user_id).progress(account_id)
        err = self._errors.get((user_id, account_id), "")
        state = "ready" if p["complete"] else "failed" if err else "building"
        return {**out, "state": state, "done": p["done"], "total": p["total"], "updated": p["updated"], "message": err}

    # ----- the work -----
    def start_all(self) -> None:
        """Carry on for every mailbox that has Fast search on. Safe to call again and again."""
        if not self.vault.is_unlocked():
            return
        try:
            with self.vault.passive():
                accounts = self.vault.list_accounts()
            for a in accounts:
                owner = a.get("owner_user_id")
                if owner and self.enabled(owner).get(a["id"]):
                    self._start(owner, a["id"])
        except Exception:
            log.info("find: could not restart word lists")

    def watch(self) -> None:
        """Start a small thread that restarts the work after Enveliq is unlocked (the vault is locked at start-up)."""
        def loop() -> None:
            while not self._stop.wait(30):
                self.start_all()
        threading.Thread(target=loop, name="enveliq-find-watch", daemon=True).start()

    def stop(self) -> None:
        self._stop.set()

    def _start(self, user_id: str, account_id: str) -> None:
        with self._guard:
            worker = self._workers.get((user_id, account_id))
            if worker is not None and worker.is_alive():
                return
            worker = threading.Thread(target=self._run, args=(user_id, account_id), name="enveliq-find-index", daemon=True)
            self._workers[(user_id, account_id)] = worker
        worker.start()

    def _alive(self, user_id: str, account_id: str) -> bool:
        return not self._stop.is_set() and self.is_enabled(user_id, account_id)

    def _run(self, user_id: str, account_id: str) -> None:
        while self._alive(user_id, account_id):
            if not self.vault.is_unlocked():
                self._stop.wait(5)
                continue
            try:
                with self.vault.passive():
                    if (user_id, account_id) in self._rebuild:
                        self._rebuild.discard((user_id, account_id))
                        self.index(user_id).drop_account(account_id)
                    self._pass(user_id, account_id)
                    self.save(user_id)
                self._errors.pop((user_id, account_id), None)
            except KeyError:
                self.disable(user_id, account_id)           # the mailbox is gone
                return
            except BridgeError as err:
                self._errors[(user_id, account_id)] = err.message
            except Exception:
                log.warning("find: a word list pass failed")
                self._errors[(user_id, account_id)] = "Fast search could not update just now. It will try again."
            self._stop.wait(self.upkeep)

    def pass_once(self, user_id: str, account_id: str) -> None:
        """One full pass, run on this thread (used by tests)."""
        with self.vault.passive():
            self._pass(user_id, account_id)
            self.save(user_id, force=True)

    def _pass(self, user_id: str, account_id: str) -> None:
        idx = self.index(user_id)
        account = self._load(account_id)
        if account.get("owner_user_id") != user_id:
            raise KeyError(account_id)
        target = self._target(account)
        complete = True
        with self.bridge.session(target) as s:
            s.set_timeout(120)
            for folder in choose_folders(s.list_folders(), False):
                validity = s.select_folder(folder, True)
                known = idx.folder_validity(account_id, folder)
                if known is not None and known != validity:
                    idx.drop_folder(account_id, folder)                  # the folder was reset on the server: start it again
                uids = s.search(["ALL"])
                have = idx.uids(account_id, folder)
                idx.remove_uids(account_id, folder, have - set(uids))
                idx.set_folder(account_id, folder, validity, len(uids))
                todo = [u for u in uids if u not in have]                # newest first
                for start in range(0, len(todo), BATCH):
                    if not self._alive(user_id, account_id) or not self.vault.is_unlocked():
                        complete = False
                        break
                    for uid in todo[start:start + BATCH]:
                        idx.add(account_id, folder, validity, uid, self._text_of(s, uid))
                    self.save(user_id)
                    self._stop.wait(self.pause)
                else:
                    continue
                break
        idx.set_complete(account_id, complete)

    @staticmethod
    def _text_of(s: Any, uid: int) -> str:
        """The words of one email, read now and not kept. An email that cannot be read is listed with no words, so it is not retried."""
        try:
            shown = render_original(s.original(uid))
        except BridgeError:
            return ""
        people = " ".join(f"{p.get('name') or ''} {p.get('address') or ''}" for p in [shown.get("from") or {}, *(shown.get("to") or [])])
        return f"{shown.get('subject') or ''} {people} {str(shown.get('text') or '')[:MAX_TEXT]}"
