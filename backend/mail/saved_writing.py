"""A signature and saved replies: text a person wrote themselves, to reuse when they write an email.

One encrypted record per person (`saved:<user id>`) under the vault's master key. It holds the person's own
text only (never email text), and only that person can read it. Enveliq never writes it for them and the AI
never sees it unless the person puts it in a message and asks for writing help.
"""
from __future__ import annotations

import re
import secrets
import threading
from typing import Any

from . import outhtml

RECORD_PREFIX = "saved:"
MAX_SIGNATURE = 1000
MAX_SIGNATURE_HTML = 6000
MAX_SIGNATURES = 40
MAX_REPLIES = 30
MAX_TITLE = 60
MAX_TEXT = 3000
_LOCK = threading.Lock()
_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")      # everything except new line and tab


class SavedError(ValueError):
    """Plain, safe-to-show reason a change was refused."""


def clean_text(value: Any, limit: int) -> str:
    text = _CTRL.sub("", str(value or "").replace("\r\n", "\n").replace("\r", "\n")).strip()
    return text[:limit]


class SavedWriting:
    def __init__(self, vault: Any) -> None:
        self.vault = vault

    def _load(self, user_id: str) -> dict[str, Any]:
        raw = self.vault.get_global(RECORD_PREFIX + user_id) or {}
        replies = [r for r in (raw.get("replies") or []) if isinstance(r, dict) and r.get("id")]
        sigs = {str(a): v for a, v in (raw.get("signatures") or {}).items() if isinstance(v, dict) and v.get("html")}
        return {"signature": str(raw.get("signature") or ""), "signature_html": str(raw.get("signature_html") or ""), "signatures": sigs, "replies": replies}

    def _save(self, user_id: str, state: dict[str, Any]) -> None:
        self.vault.set_global(RECORD_PREFIX + user_id, state)

    def view(self, user_id: str) -> dict[str, Any]:
        s = self._load(user_id)
        return {"signature": s["signature"], "signature_html": s["signature_html"],
                "signatures": [{"address": a, "html": v["html"], "text": v.get("text", "")} for a, v in sorted(s["signatures"].items())],
                "replies": [{"id": r["id"], "title": r.get("title", ""), "text": r.get("text", "")} for r in s["replies"]],
                "limits": {"signature": MAX_SIGNATURE, "signatures": MAX_SIGNATURES, "replies": MAX_REPLIES, "title": MAX_TITLE, "text": MAX_TEXT}}

    @staticmethod
    def _format(html: str) -> tuple[str, str]:
        """A signature written with formatting, rebuilt from the allowed list (no pictures), and its plain-text copy."""
        try:
            cleaned = outhtml.clean_html(str(html or "")[:MAX_SIGNATURE_HTML * 3], {}) if html else ""
        except outhtml.OutHtmlError:
            raise SavedError("That signature is too long.") from None
        text = clean_text(outhtml.to_text(cleaned), MAX_SIGNATURE) if cleaned else ""
        if not text:
            return "", ""
        if len(cleaned) > MAX_SIGNATURE_HTML:
            raise SavedError("That signature is too long.")
        return cleaned, text

    def set_signature(self, user_id: str, text: str, html: str | None = None) -> dict[str, Any]:
        """The default signature. With [html] it keeps the formatting (bold, italic, links); the plain text is made from it."""
        with _LOCK:
            s = self._load(user_id)
            if html is not None:
                s["signature_html"], s["signature"] = self._format(html)
            else:
                s["signature"], s["signature_html"] = clean_text(text, MAX_SIGNATURE), ""
            self._save(user_id, s)
        return self.view(user_id)

    def set_address_signature(self, user_id: str, address: str, html: str) -> dict[str, Any]:
        """The signature used when writing from one sending address. Empty removes it (the default is used again)."""
        key = str(address or "").strip().lower()
        with _LOCK:
            s = self._load(user_id)
            cleaned, text = self._format(html)
            if cleaned:
                if key not in s["signatures"] and len(s["signatures"]) >= MAX_SIGNATURES:
                    raise SavedError(f"You can keep up to {MAX_SIGNATURES} signatures. Remove one first.")
                s["signatures"][key] = {"html": cleaned, "text": text}
            else:
                s["signatures"].pop(key, None)
            self._save(user_id, s)
        return self.view(user_id)

    def add_reply(self, user_id: str, title: str, text: str) -> dict[str, Any]:
        title, text = clean_text(title, MAX_TITLE).replace("\n", " "), clean_text(text, MAX_TEXT)
        if not title or not text:
            raise SavedError("Give the reply a short name and some text.")
        with _LOCK:
            s = self._load(user_id)
            if len(s["replies"]) >= MAX_REPLIES:
                raise SavedError(f"You can keep up to {MAX_REPLIES} saved replies. Remove one first.")
            s["replies"].append({"id": "r" + secrets.token_hex(8), "title": title, "text": text})
            self._save(user_id, s)
        return self.view(user_id)

    def update_reply(self, user_id: str, reply_id: str, title: str, text: str) -> dict[str, Any] | None:
        title, text = clean_text(title, MAX_TITLE).replace("\n", " "), clean_text(text, MAX_TEXT)
        if not title or not text:
            raise SavedError("Give the reply a short name and some text.")
        with _LOCK:
            s = self._load(user_id)
            for r in s["replies"]:
                if r["id"] == reply_id:
                    r["title"], r["text"] = title, text
                    self._save(user_id, s)
                    break
            else:
                return None
        return self.view(user_id)

    def remove_reply(self, user_id: str, reply_id: str) -> dict[str, Any] | None:
        with _LOCK:
            s = self._load(user_id)
            kept = [r for r in s["replies"] if r["id"] != reply_id]
            if len(kept) == len(s["replies"]):
                return None
            s["replies"] = kept
            self._save(user_id, s)
        return self.view(user_id)

    def forget_user(self, user_id: str) -> None:
        self.vault.set_global(RECORD_PREFIX + user_id, {})
