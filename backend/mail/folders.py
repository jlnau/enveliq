"""Folders: the list of a mailbox's folders, making a new one, moving an email into one, and looking inside one.

Only the folder names and a page of header lines are fetched, live, and shown. Nothing from inside a folder is stored here.
A reference to one email in a folder is a signed token the server made, so the page can never name a folder or a message number itself."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import secrets
import time
from typing import Any, Callable

from .bridge import Bridge, Target
from .errors import BridgeError
from .find import FindError, criteria, parse_query
from .parse import _addresses, clean, likely_has_files, parse_headers, received_at_of

PAGE = 25
NAME_MAX = 80
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
SPECIAL = {"\\sent": "Sent", "\\drafts": "Drafts", "\\trash": "Bin", "\\junk": "Junk", "\\all": "All mail", "\\flagged": "Starred", "\\important": "Important", "\\archive": "Archive"}
NOT_TARGETS = {"\\sent", "\\drafts", "\\trash", "\\junk", "\\all", "\\flagged", "\\important"}   # a move into these is Bin, Junk or Archive, which have their own buttons
PLAIN_NO = ("inbox", "sent", "drafts", "trash", "spam", "junk", "bin", "deleted items", "sent items", "all mail", "starred", "important")


def _label(name: str) -> str:
    last = name.replace("\\", "/").split("/")[-1].strip() or name
    return last


def folder_rows(raw: list[tuple[set[str], str]], kind: str) -> list[dict[str, Any]]:
    """Every folder the person can open, with a plain label. Proton's labels and Gmail's own bookkeeping folders are left out."""
    rows = []
    for flags, name in raw:
        low = name.lower()
        if name.upper() == "INBOX" or low.startswith("labels/") or low.startswith("[gmail]/") and not (flags & set(SPECIAL)):
            continue
        special = next((f for f in SPECIAL if f in flags), None)
        if special is None and low in ("archive", "sent", "drafts", "trash", "spam", "junk"):
            special = "\\" + ("trash" if low == "trash" else "junk" if low in ("spam", "junk") else low)
        label = SPECIAL[special] if special else _label(name)
        rows.append({"name": name, "label": label, "special": bool(special),
                     "target": special not in NOT_TARGETS and not (special is None and low in PLAIN_NO)})
    rows.sort(key=lambda r: (r["special"], r["label"].lower()))
    return rows


def clean_new_name(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("name")
    name = re.sub(r"\s+", " ", _CONTROL.sub("", value)).strip()
    if not name or len(name) > NAME_MAX:
        raise ValueError("name")
    if re.search(r"[/\\\"*%#&]", name) or name.lower() in PLAIN_NO or name.startswith(".") or name.endswith("."):
        raise ValueError("name")
    return name


class Folders:
    def __init__(self, bridge: Bridge, load_account: Callable[[str], dict[str, Any]], target_for: Callable[[dict[str, Any]], Target]):
        self.bridge, self._load, self._target = bridge, load_account, target_for
        self._secret = secrets.token_bytes(32)

    def list(self, account: dict[str, Any]) -> list[dict[str, Any]]:
        with self.bridge.session(self._target(account)) as s:
            s.set_timeout(30)
            return folder_rows(s.list_folders(), self._target(account).kind)

    def create(self, account: dict[str, Any], label: str) -> dict[str, Any]:
        name = clean_new_name(label)
        target = self._target(account)
        full = name if target.kind == "imap" else "Folders/" + name
        with self.bridge.session(target) as s:
            s.set_timeout(30)
            if any(n.lower() == full.lower() or _label(n).lower() == name.lower() for _f, n in s.list_folders()):
                raise BridgeError("already_listed", "There is already a folder with that name.")
            s.create_folder(full)
            rows = folder_rows(s.list_folders(), target.kind)
        return next(r for r in rows if r["name"] == full)

    def move(self, account: dict[str, Any], uid: int, validity: int, folder: str) -> None:
        """Move one email out of the Inbox into one of the person's own folders. The name must be one the mailbox listed."""
        target = self._target(account)
        with self.bridge.session(target) as s:
            s.set_timeout(30)
            allowed = {r["name"] for r in folder_rows(s.list_folders(), target.kind) if r["target"]}
            if folder not in allowed:
                raise BridgeError("not_found", "That folder is not in this mailbox.")
            if s.select_inbox(readonly=False) != validity:
                raise BridgeError("not_found", "The mailbox was reset on the server. Sync again.")
            s.move(uid, folder)

    def move_from_folder(self, account: dict[str, Any], folder: str, validity: int, uid: int, dest: str | None) -> None:
        """Move one email that sits in a folder to another of the person's folders, or back to the Inbox (dest None),
        or to the Bin (dest "\\trash"). A folder name must be one the mailbox listed."""
        target = self._target(account)
        with self.bridge.session(target) as s:
            s.set_timeout(30)
            if dest == "\\trash":
                where = s.folder_for("trash")
            elif dest == "\\archive":
                where = s.folder_for("archive")
                if where == folder:
                    raise BridgeError("not_found", "That email is already in the Archive.")
            elif dest is None:
                where = "INBOX"
            else:
                allowed = {r["name"] for r in folder_rows(s.list_folders(), target.kind) if r["target"]}
                if dest not in allowed or dest == folder:
                    raise BridgeError("not_found", "That folder is not in this mailbox.")
                where = dest
            if s.select_folder(folder, False) != validity:
                raise BridgeError("not_found", "The mailbox was reset on the server. Open the folder again.")
            s.move(uid, where)

    def flag_in_folder(self, account: dict[str, Any], folder: str, validity: int, uid: int, starred: bool) -> None:
        """Star or unstar one email where it sits (the mailbox's own Flagged mark)."""
        with self.bridge.session(self._target(account)) as s:
            s.set_timeout(30)
            if s.select_folder(folder, False) != validity:
                raise BridgeError("not_found", "The mailbox was reset on the server. Open the folder again.")
            s.set_flagged(uid, starred)

    def headers(self, account: dict[str, Any], folder: str, validity: int, uid: int) -> bytes:
        """The header lines of one email where it sits (read only)."""
        with self.bridge.session(self._target(account)) as s:
            s.set_timeout(60)
            if s.select_folder(folder, True) != validity:
                raise BridgeError("not_found", "The mailbox was reset on the server. Open the folder again.")
            for _uid, raw in s.header_blocks([uid]):
                return raw
        raise BridgeError("not_found", "This email can no longer be found in the mailbox.")

    # ---------- looking inside a folder ----------

    def _token(self, user: str, account_id: str, folder: str, validity: int, uid: int) -> str:
        body = base64.urlsafe_b64encode(json.dumps([account_id, folder, validity, uid], separators=(",", ":")).encode()).decode().rstrip("=")
        mac = hmac.new(self._secret, f"{user}|{body}".encode(), hashlib.sha256).hexdigest()[:24]
        return f"{body}.{mac}"

    def open_token(self, user: str, token: str) -> tuple[str, str, int, int]:
        """(account id, folder, validity, uid) from a token this server made for this person, or not found."""
        try:
            body, mac = token.rsplit(".", 1)
            good = hmac.new(self._secret, f"{user}|{body}".encode(), hashlib.sha256).hexdigest()[:24]
            if not hmac.compare_digest(good, mac):
                raise ValueError
            account_id, folder, validity, uid = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
            if not (isinstance(account_id, str) and isinstance(folder, str) and isinstance(validity, int) and isinstance(uid, int)):
                raise ValueError
            return account_id, folder, validity, uid
        except (ValueError, TypeError):
            raise BridgeError("not_found", "Not found.") from None

    def page(self, user: str, account: dict[str, Any], folder: str, offset: int, words: str = "") -> dict[str, Any]:
        target = self._target(account)
        with self.bridge.session(target) as s:
            s.set_timeout(60)
            names = {r["name"] for r in folder_rows(s.list_folders(), target.kind)}
            if folder not in names:
                raise BridgeError("not_found", "That folder is not in this mailbox.")
            validity = s.select_folder(folder, True)
            if words.strip():
                crit, utf8 = criteria(parse_query(words), target)      # the same words and rules as Search all my mail, inside this one folder
                uids = s.search(crit, utf8)
            else:
                uids = s.search(["ALL"])
            chunk = uids[offset:offset + PAGE]
            rows = []
            for uid, raw in s.header_blocks(chunk):
                msg = parse_headers(raw)
                name, address = (_addresses(msg, "From") or [("", "")])[0]
                to_name, to_address = (_addresses(msg, "To") or [("", "")])[0]
                rows.append({"token": self._token(user, account["id"], folder, validity, uid), "uid": uid,
                             "from_name": clean(name, 200), "from_address": clean(address, 320),
                             "to_name": clean(to_name, 200), "to_address": clean(to_address, 320), "to_more": max(0, len(_addresses(msg, "To")) - 1),
                             "subject": clean(msg.get("Subject"), 300) or "(no subject)", "date": received_at_of(raw), "has_files": likely_has_files(msg)})
        rows.sort(key=lambda r: -r["uid"])
        for r in rows:
            r.pop("uid")
        return {"rows": rows, "total": len(uids), "more": offset + PAGE < len(uids), "now": time.time()}

    def original(self, account: dict[str, Any], folder: str, validity: int, uid: int) -> bytes:
        with self.bridge.session(self._target(account)) as s:
            s.set_timeout(60)
            if s.select_folder(folder, True) != validity:
                raise BridgeError("not_found", "The mailbox was reset on the server. Open the folder again.")
            return s.original(uid)
