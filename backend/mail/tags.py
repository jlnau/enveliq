"""Tags (labels) from the mail service, shown in Enveliq and kept in step with the mailbox.

A person's mailbox may already have tags: Proton calls them labels, Gmail calls them labels, other services call them
keywords or flags. Enveliq lists them, shows which ones an email has, lets the person add or remove one, and can create a
new tag. Every change is made in the real mailbox as well, so Enveliq and the mail service agree.

How each kind of mailbox keeps tags (IMAP, no provider-specific web API):

* **Proton Bridge**: each label is a folder named ``Labels/<name>``. Copying an email there adds the label; deleting the
  copy from that folder removes only the label. A new label is a new ``Labels/<name>`` folder.
* **Gmail**: labels are folders too, but Gmail also lets Enveliq read and change a message's labels directly
  (``X-GM-LABELS``), and a label that does not exist yet is created when it is first used.
* **Other IMAP services** (iCloud, Yahoo, Fastmail, others): tags are IMAP keywords on the message. Only some services keep
  custom keywords; the mailbox says which (``PERMANENTFLAGS``).
* **Outlook / Microsoft 365**: not supported (its categories are not reachable over IMAP).

Only the tag *names* are kept in Enveliq, as a short list on each email's encrypted record. Nothing from the email itself is
read to do this, and tag names are never sent to the AI.
"""
from __future__ import annotations

import base64
import logging
import re
from email import message_from_bytes
from typing import Any

from .errors import BridgeError

log = logging.getLogger("enveliq.tags")

MAX_NAME = 40
MAX_PER_MESSAGE = 20
MAX_LABEL_FOLDERS = 60            # Proton: label folders looked through on each sync
MAX_PER_FOLDER = 300              # Proton: newest emails looked at in each label folder
SYNC_MESSAGES = 200
PROTON_PREFIX = "Labels/"
RESERVED = {"inbox", "archive", "trash", "sent", "drafts", "spam", "junk", "bin", "all mail", "starred", "important", "labels", "folders", "outbox"}
_NAME = re.compile(r"^\w[\w .&+()'-]{0,%d}$" % (MAX_NAME - 1))
_ATOM = re.compile(r"^[A-Za-z0-9_.-]{1,%d}$" % MAX_NAME)
_GMAIL_SPECIAL = {"\\all", "\\drafts", "\\important", "\\flagged", "\\junk", "\\sent", "\\trash", "\\archive"}


class TagError(Exception):
    """Something about a tag that can be said to the person in plain words."""


def dialect_of(account: dict[str, Any]) -> str | None:
    """'proton', 'gmail' or 'keywords' for a mailbox that can keep tags, else None."""
    method = account.get("auth_method")
    settings = account.get("settings") or {}
    if method == "proton_bridge":
        return "proton"
    if method == "imap":
        if settings.get("auth") == "microsoft" or settings.get("provider_id") == "outlook":
            return None
        return "gmail" if settings.get("provider_id") == "gmail" else "keywords"
    return None


# ---------- names ----------

def clean_name(value: Any, dialect: str) -> str:
    name = " ".join(str(value or "").split())
    if not name:
        raise TagError("Write a name for the tag.")
    if len(name) > MAX_NAME:
        raise TagError(f"Keep the tag name to {MAX_NAME} letters or fewer.")
    if name.lower() in RESERVED:
        raise TagError("That name is already used for one of your mail folders. Pick another.")
    if dialect == "keywords":
        if not _ATOM.match(name):
            raise TagError("This mailbox only allows letters, digits, dashes and underscores in a tag name, with no spaces.")
    elif not _NAME.match(name):
        raise TagError("Use letters, digits, spaces and the signs - _ . & + ( ) in a tag name.")
    return name


def utf7_encode(text: str) -> str:
    out, buf = [], ""

    def flush() -> None:
        nonlocal buf
        if buf:
            out.append("&" + base64.b64encode(buf.encode("utf-16-be")).decode("ascii").rstrip("=").replace("/", ",") + "-")
            buf = ""
    for ch in text:
        if 0x20 <= ord(ch) <= 0x7E:
            flush()
            out.append("&-" if ch == "&" else ch)
        else:
            buf += ch
    flush()
    return "".join(out)


def utf7_decode(text: str) -> str:
    def part(m: re.Match[str]) -> str:
        if m.group(1) == "":
            return "&"
        raw = m.group(1).replace(",", "/")
        try:
            return base64.b64decode(raw + "=" * (-len(raw) % 4)).decode("utf-16-be")
        except (ValueError, UnicodeDecodeError):
            return m.group(0)
    return re.sub(r"&([^-]*)-", part, text)


def _quote(name: str) -> str:
    return '"' + utf7_encode(name).replace("\\", "\\\\").replace('"', '\\"') + '"'


def _same(a: str, b: str) -> bool:
    return a.casefold() == b.casefold()


def _tidy(names: list[str], limit: int | None = MAX_PER_MESSAGE) -> list[str]:
    seen: dict[str, str] = {}
    for n in names:
        if n and n.casefold() not in seen:
            seen[n.casefold()] = n
    return sorted(seen.values(), key=str.casefold)[:limit]


# ---------- reading an IMAP reply ----------

def _paren_list(text: str, marker: str) -> list[str] | None:
    """The items of the parenthesised list that follows `marker` in `text`: atoms and quoted strings."""
    at = text.find(marker + " (")
    if at < 0:
        return None
    i, items = at + len(marker) + 2, []
    while i < len(text) and text[i] != ")":
        if text[i] == " ":
            i += 1
        elif text[i] == '"':
            i += 1
            buf = []
            while i < len(text) and text[i] != '"':
                if text[i] == "\\" and i + 1 < len(text):
                    i += 1
                buf.append(text[i])
                i += 1
            i += 1
            items.append("".join(buf))
        else:
            j = i
            while j < len(text) and text[j] not in " )":
                j += 1
            items.append(text[i:j])
            i = j
    return items


def _fetch_lists(data: Any, marker: str) -> dict[int, list[str]]:
    found: dict[int, list[str]] = {}
    for item in data or []:
        raw = item[0] if isinstance(item, tuple) else item
        if not isinstance(raw, bytes):
            continue
        text = raw.decode("utf-8", "replace")
        uid = re.search(r"UID (\d+)", text)
        items = _paren_list(text, marker)
        if uid and items is not None:
            found[int(uid.group(1))] = items
    return found


def _is_user_keyword(flag: str) -> bool:
    return bool(flag) and not flag.startswith(("\\", "$"))


# ---------- what one open mailbox session can do ----------

def read_tags(s: Any, dialect: str) -> dict[str, Any]:
    """{'names': [...], 'can_create': bool} for the open session."""
    if dialect == "proton":
        names = [utf7_decode(n)[len(PROTON_PREFIX):] for _f, n in s._folders() if utf7_decode(n).startswith(PROTON_PREFIX) and len(utf7_decode(n)) > len(PROTON_PREFIX)]
        return {"names": _tidy([n for n in names if "/" not in n], limit=None), "can_create": True}
    if dialect == "gmail":
        names = []
        for flags, raw in s._folders():
            name = utf7_decode(raw)
            if name.upper() == "INBOX" or name.startswith(("[Gmail]", "[Google Mail]")) or name.startswith("CATEGORY_") or flags & _GMAIL_SPECIAL:
                continue
            names.append(name)
        return {"names": _tidy(names, limit=None), "can_create": True}
    s.select_inbox(readonly=False)           # a read-only open reports no permanent flags
    try:
        _typ, data = s.imap.response("PERMANENTFLAGS")
    except Exception:
        data = None
    flags: list[str] = []
    for item in data or []:
        if isinstance(item, bytes):
            flags += (_paren_list("PERMANENTFLAGS " + item.decode("utf-8", "replace"), "PERMANENTFLAGS") or [])
    return {"names": _tidy([f for f in flags if _is_user_keyword(f)], limit=None), "can_create": "\\*" in flags}


def create_tag(s: Any, dialect: str, name: str) -> None:
    known = read_tags(s, dialect)
    if any(_same(name, n) for n in known["names"]):
        raise TagError("You already have a tag with that name.")
    if not known["can_create"]:
        raise TagError("This email service does not let Enveliq make new tags.")
    if dialect == "proton":
        s._call("create", s.imap.create, _quote(PROTON_PREFIX + name))
    elif dialect == "gmail":
        s._call("create", s.imap.create, _quote(name))
    # keywords: the tag exists from the moment it is first put on an email


def _expunge(s: Any, uid: int) -> None:
    caps = {c.upper() for c in s.imap.capabilities}
    if "UIDPLUS" in caps:
        s._call("expunge", s.imap.uid, "EXPUNGE", str(uid))
    else:
        s._call("expunge", s.imap.expunge)


def _in_label_folder(s: Any, folder: str, message_id: str, readonly: bool) -> list[int]:
    s.select_folder(folder, readonly=readonly)
    if not message_id or any(c in message_id for c in '"\\\r\n'):
        return []
    data = s._call("search", s.imap.uid, "SEARCH", None, "HEADER", "Message-ID", f'"{message_id}"')
    return [int(x) for x in (data[0] or b"").split() if x.isdigit()]


def set_tag(s: Any, dialect: str, validity: int, uid: int, message_id: str, name: str, on: bool) -> None:
    """Put the tag on, or take it off, the email at `uid` in the inbox."""
    if dialect == "proton" and not on:
        for hit in _in_label_folder(s, PROTON_PREFIX + name, message_id, readonly=False):
            s._call("store", s.imap.uid, "STORE", str(hit), "+FLAGS.SILENT", "(\\Deleted)")
            _expunge(s, hit)
        return
    if s.select_inbox(readonly=False) != validity:
        raise BridgeError("not_found", "The mailbox was reset on the server. Sync again.")
    if dialect == "proton":
        s._call("copy", s.imap.uid, "COPY", str(uid), _quote(PROTON_PREFIX + name))
    elif dialect == "gmail":
        s._call("store", s.imap.uid, "STORE", str(uid), "+X-GM-LABELS" if on else "-X-GM-LABELS", f"({_quote(name)})")
    else:
        s._call("store", s.imap.uid, "STORE", str(uid), "+FLAGS.SILENT" if on else "-FLAGS.SILENT", f"({name})")


def _header_id(raw: bytes) -> str:
    value = message_from_bytes(raw).get("Message-ID") or ""
    return " ".join(str(value).split())


def tags_of_inbox(s: Any, dialect: str, validity: int, wanted: dict[int, str]) -> dict[int, list[str]]:
    """For inbox emails {uid: message id}, the tags each has now. Emails the mailbox no longer lists are left out."""
    uids = sorted(wanted)
    if not uids:
        return {}
    if dialect in ("gmail", "keywords"):
        found: dict[int, list[str]] = {}
        marker, keep = ("X-GM-LABELS", lambda t: not t.startswith("\\") and not t.startswith("CATEGORY_")) if dialect == "gmail" else ("FLAGS", _is_user_keyword)
        if s.select_inbox(readonly=True) != validity:
            return {}
        for start in range(0, len(uids), 50):
            chunk = ",".join(str(u) for u in uids[start:start + 50])
            data = s._call("fetch", s.imap.uid, "FETCH", chunk, f"({'X-GM-LABELS' if dialect == 'gmail' else 'FLAGS'})")
            for uid, items in _fetch_lists(data, marker).items():
                found[uid] = _tidy([utf7_decode(t) for t in items if keep(t)])
        return found
    # Proton: look through the label folders, matching emails by their Message-ID
    by_id = {mid.strip(): uid for uid, mid in wanted.items() if mid}
    result = {uid: [] for uid in uids}
    for name in read_tags(s, "proton")["names"][:MAX_LABEL_FOLDERS]:
        s.select_folder(PROTON_PREFIX + name, readonly=True)
        for _u, raw in s.header_blocks(s.recent_uids(30, MAX_PER_FOLDER), "MESSAGE-ID"):
            uid = by_id.get(_header_id(raw))
            if uid is not None and name not in result[uid]:
                result[uid].append(name)
    return {uid: _tidy(names) for uid, names in result.items()}


# ---------- the service the routes and the sync use ----------

class TagService:
    def __init__(self, mail: Any, vault: Any, enabled: Any):
        self.mail, self.vault, self.enabled = mail, vault, enabled          # enabled(user_id) -> bool, the person's Tags switch

    def _session(self, account: dict[str, Any]) -> tuple[Any, Any]:
        lock = self.mail.locks.acquire(account["id"])
        try:
            return lock, self.mail.bridge.session(self.mail.target(account))
        except Exception:
            lock.release()
            raise

    def overview(self, account: dict[str, Any]) -> dict[str, Any]:
        dialect = dialect_of(account)
        if not dialect:
            return {"supported": False, "names": [], "can_create": False}
        lock, session = self._session(account)
        try:
            with session as s:
                return {"supported": True, **read_tags(s, dialect)}
        finally:
            lock.release()

    def create(self, account: dict[str, Any], name: str) -> dict[str, Any]:
        dialect = dialect_of(account)
        if not dialect:
            raise TagError("This email service does not keep tags.")
        name = clean_name(name, dialect)
        lock, session = self._session(account)
        try:
            with session as s:
                create_tag(s, dialect, name)
                now = read_tags(s, dialect)
                if dialect == "keywords":
                    now = {"names": _tidy([*now["names"], name], limit=None), "can_create": now["can_create"]}      # it exists once it is first used
                return {"supported": True, "name": name, **now}
        finally:
            lock.release()

    def set_for_message(self, account: dict[str, Any], message_id: str, name: str, on: bool) -> list[str]:
        from .bridge import parse_locator
        from ..models import RetainedMessageCreate
        dialect = dialect_of(account)
        if not dialect:
            raise TagError("This email service does not keep tags.")
        name = clean_name(name, dialect)
        message = self.vault.get_message(account["id"], message_id)
        if message.get("state", "unread") != "unread" or not message.get("source_locator"):
            raise TagError("Only emails in your inbox can be tagged.")
        validity, uid = parse_locator(message["source_locator"])
        mid = ((message.get("reply_context") or {}).get("message_id") or "").strip()
        lock, session = self._session(account)
        try:
            with session as s:
                if on and dialect != "keywords":
                    known = read_tags(s, dialect)["names"]
                    match = next((n for n in known if _same(n, name)), None)
                    if match is None:
                        raise TagError("That tag is not in your mailbox any more. Make it again.")
                    name = match
                elif dialect == "keywords" and on and not read_tags(s, dialect)["can_create"]:
                    raise TagError("This email service does not let Enveliq make new tags.")
                if not on:
                    name = next((n for n in message.get("tags") or [] if _same(n, name)), name)
                set_tag(s, dialect, validity, uid, mid, name, on)
        finally:
            lock.release()
        mine = [n for n in message.get("tags") or [] if not _same(n, name)]
        tags = _tidy([*mine, name] if on else mine)
        data = {k: v for k, v in message.items() if k != "id"}
        data["tags"] = tags
        self.vault.update_message(account["id"], message_id, RetainedMessageCreate(**data).model_dump(mode="python"))
        return tags

    def sync(self, s: Any, account: dict[str, Any], validity: int) -> None:
        """Called by the sync with its open session: bring the stored emails' tags in line with the mailbox."""
        from .bridge import parse_locator
        from ..models import RetainedMessageCreate
        dialect = dialect_of(account)
        if not dialect or not self.enabled(account.get("owner_user_id")):
            return
        wanted: dict[int, str] = {}
        owners: dict[int, dict[str, Any]] = {}
        for m in self.vault.list_messages(account["id"]):
            if m.get("state", "unread") != "unread" or not m.get("source_locator"):
                continue
            try:
                v, uid = parse_locator(m["source_locator"])
            except BridgeError:
                continue
            if v == validity and len(wanted) < SYNC_MESSAGES:
                wanted[uid] = str((m.get("reply_context") or {}).get("message_id") or "")
                owners[uid] = m
        for uid, names in tags_of_inbox(s, dialect, validity, wanted).items():
            m = owners[uid]
            if _tidy(m.get("tags") or []) != names:
                data = {k: v for k, v in m.items() if k != "id"}
                data["tags"] = names
                self.vault.update_message(account["id"], m["id"], RetainedMessageCreate(**data).model_dump(mode="python"))
