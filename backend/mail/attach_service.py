"""Summaries of attached files: read each file's words in memory, have the AI summarise them, keep only the summaries.

The raw email is fetched, the files are read, and everything but the finished summaries is dropped. What is kept, encrypted
with the rest of the email's record, is each file's name, size, page count, a one-line summary and headed parts.
"""
from __future__ import annotations

import email
import logging
import threading
from email import policy
from typing import Any

from ..models import RetainedMessageCreate
from . import llm_providers
from .attach_ai import summarise_document
from .errors import BridgeError
from .parse import list_parts
from .render import read_text

log = logging.getLogger("enveliq.attachments")

RECORD = "attachment_ai"             # {"enabled": bool}: the administrator's choice, absent until they choose
MAX_FILES = 20                       # per email
MAX_RAW = 60 * 1024 * 1024           # an email bigger than this is not read for files
MAX_RAW_TOTAL = 200 * 1024 * 1024    # all the emails of one batch together, held in memory for a short while

_running: set[tuple[str, str]] = set()
_running_lock = threading.Lock()


def saved_choice(vault: Any) -> bool | None:
    value = (vault.get_global(RECORD) or {}).get("enabled")
    return value if isinstance(value, bool) else None


def allowed(vault: Any, summariser: Any) -> bool:
    """On for an AI server on your own network unless an administrator turned it off. Off for a cloud service until an administrator turned it on."""
    choice = saved_choice(vault)
    if llm_providers.get(summariser.config.provider).cloud:
        return choice is True
    return choice is not False


def status(vault: Any, summariser: Any) -> dict[str, Any]:
    known = llm_providers.get(summariser.config.provider)
    return {"enabled": allowed(vault, summariser), "saved": saved_choice(vault), "cloud": bool(known.cloud and summariser.enabled),
            "company": (known.company or known.label) if known.cloud and summariser.enabled else None}


def _inline(part: Any) -> bool:
    return bool(part.get("Content-ID")) and (part.get_content_disposition() or "inline") != "attachment"


def files_in(raw: bytes) -> list[dict[str, Any]]:
    """Each attached file of the email (pictures that are part of the text are left out), with its words read, in memory."""
    msg = email.message_from_bytes(raw, policy=policy.default)
    out: list[dict[str, Any]] = []
    for index, part in enumerate(list_parts(msg)):
        if _inline(part):
            continue
        ctype = (part.get_content_type() or "application/octet-stream")[:127]
        name = (part.get_filename() or ("picture" if ctype.startswith("image/") else "attachment"))[:255]
        name = "".join(ch for ch in name if ch >= " " and ch != "\x7f").strip() or "attachment"
        row: dict[str, Any] = {"index": index, "filename": name, "mime_type": ctype, "size_bytes": 0, "pages": None, "text": None, "state": "skipped", "reason": None, "read_note": None}
        if len(out) >= MAX_FILES:
            row["reason"] = f"Only the first {MAX_FILES} files of an email are read."
            out.append(row)
            continue
        try:
            payload = part.get_payload(decode=True) or b""
        except Exception:
            payload = b""
        row["size_bytes"] = len(payload)
        got = read_text(payload, name, ctype) if payload else {"kind": "none", "reason": "This file is empty."}
        if got.get("kind") == "text":
            row.update(text=got["text"], state="reading", pages=got.get("pages"))
            if got.get("pages") and got.get("read_pages") and got["read_pages"] < got["pages"]:
                row["read_note"] = f"Only the first {got['read_pages']} of {got['pages']} pages could be read."
        else:
            row["reason"] = str(got.get("reason") or "This file could not be read.")[:300]
        out.append(row)
    return out


def listing(raw: bytes, reason: str, state: str = "skipped") -> list[dict[str, Any]]:
    """The files of an email as rows that say why they were not read: names and sizes only, nothing is read or sent anywhere."""
    msg = email.message_from_bytes(raw, policy=policy.default)
    out: list[dict[str, Any]] = []
    for index, part in enumerate(list_parts(msg)):
        if _inline(part):
            continue
        ctype = (part.get_content_type() or "application/octet-stream")[:127]
        name = (part.get_filename() or ("picture" if ctype.startswith("image/") else "attachment"))[:255]
        name = "".join(ch for ch in name if ch >= " " and ch != "\x7f").strip() or "attachment"
        try:
            size = len(part.get_payload(decode=True) or b"")
        except Exception:
            size = 0
        out.append({"index": index, "filename": name, "mime_type": ctype, "size_bytes": size, "pages": None, "state": state, "reason": reason, "read_note": None})
        if len(out) >= MAX_FILES + 5:
            break
    return out


def placeholders(count: int, reason: str, state: str = "skipped") -> list[dict[str, Any]]:
    """When the email cannot even be opened: one row per file, with no names, so the card still says what happened."""
    return [{"index": i, "filename": f"Attachment {i + 1}", "mime_type": None, "size_bytes": None, "pages": None, "state": state, "reason": reason, "read_note": None}
            for i in range(min(count, 100))]


def _row(f: dict[str, Any]) -> dict[str, Any]:
    return {"filename": f["filename"], "index": f["index"], "mime_type": f["mime_type"], "size_bytes": f["size_bytes"], "pages": f["pages"],
            "state": f["state"], "reason": f.get("reason"), "note": f.get("note") or f.get("read_note"), "summary": f.get("summary") or "", "parts": f.get("parts") or []}


def _store(vault: Any, account_id: str, message_id: str, files: list[dict[str, Any]]) -> bool:
    """Save the rows. False when the email is gone or has been handled meanwhile (then nothing more is written)."""
    try:
        current = vault.get_message(account_id, message_id)
    except KeyError:
        return False
    if current.get("state", "unread") != "unread":
        return False
    data = {k: v for k, v in current.items() if k != "id"}
    data["attachment_summaries"] = [_row(f) for f in files]
    data["attachment_count"] = len(files)
    data["has_attachments"] = bool(files)
    try:
        vault.update_message(account_id, message_id, RetainedMessageCreate(**data).model_dump(mode="python"))
    except (ValueError, KeyError):
        return False
    return True


def mark_unread(vault: Any, account_id: str, message_id: str, raw: bytes | None, reason: str, state: str = "skipped", count: int = 0) -> None:
    """Make sure the email's card shows its files with the reason they were not read, instead of a count with nothing beside it."""
    rows: list[dict[str, Any]] = []
    if raw is not None and len(raw) <= MAX_RAW:
        try:
            rows = listing(raw, reason, state)
        except Exception:
            rows = []
    if not rows and count:
        rows = placeholders(count, reason, state)
    if rows:
        _store(vault, account_id, message_id, rows)


def run(vault: Any, account_id: str, message_id: str, raw: bytes, summariser: Any, instructions: str = "") -> None:
    """Read the files of this email and summarise them one after another, saving after each so the page can follow."""
    try:
        files = files_in(raw)
    except Exception as exc:
        log.warning("files of %s not read: the email could not be opened (%s)", message_id, type(exc).__name__)
        mark_unread(vault, account_id, message_id, raw, "Enveliq could not open this email's files. Try again in a minute.", "failed")
        return
    if not files:
        log.warning("files of %s not read: the email says it has files but none were found", message_id)
        mark_unread(vault, account_id, message_id, raw, "Enveliq could not find the files in this email. You can still open them with View original email.", "failed")
        return
    del raw
    if not _store(vault, account_id, message_id, files):
        log.info("files of %s not saved: the email is gone or has been handled", message_id)
        return
    section = max(6000, summariser.config.max_chars * 2)
    for f in files:
        if f["state"] != "reading":
            continue
        text = f.pop("text")
        try:
            out = summarise_document(summariser.complete, f["filename"], text, section_chars=section, instructions=instructions)
        except BridgeError as err:
            f["state"], f["reason"] = "failed", ("The AI server could not be reached, so this file was not summarised." if err.code in ("ai_unreachable", "ai_refused")
                                                  else "The AI could not make a summary of this file.")
            if err.code in ("ai_unreachable", "ai_refused"):
                for rest in files:
                    if rest["state"] == "reading":
                        rest["state"], rest["reason"] = "failed", f["reason"]
                        rest.pop("text", None)
                _store(vault, account_id, message_id, files)
                return
        else:
            f.update(state="done", summary=out["line"], parts=out["parts"], note=" ".join(x for x in (out["note"], f.get("read_note")) if x) or None)
        del text
        if not _store(vault, account_id, message_id, files):
            return


def run_in_background(vault: Any, account_id: str, message_id: str, raw: bytes, summariser: Any, instructions: str = "") -> bool:
    """For the Try again button. False if this email is already being worked on."""
    key = (account_id, message_id)
    with _running_lock:
        if key in _running:
            return False
        _running.add(key)

    def go() -> None:
        try:
            run(vault, account_id, message_id, raw, summariser, instructions)
        except Exception as exc:               # never takes the server down
            log.warning("attachment summaries failed: %s", type(exc).__name__)
        finally:
            with _running_lock:
                _running.discard(key)

    threading.Thread(target=go, name="attachment-summaries", daemon=True).start()
    return True
