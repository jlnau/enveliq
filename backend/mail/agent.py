"""Hermes: a plain chat with the AI model the administrator set up.

Plain chat only. Hermes sees what the person types and nothing else: no mailbox, no tasks, no settings, and it cannot
change anything. Each person has one encrypted record (`agent:<user id>`) holding their own saved chats, so a
conversation is still there tomorrow and can be reopened, renamed or deleted. Nothing the model says is ever treated as
an instruction.
"""
from __future__ import annotations

import re
import secrets
import threading
import time
from typing import Any

from .llm import BridgeError, Summariser

RECORD_PREFIX = "agent:"
NAME = "Hermes"
MAX_TEXT = 2000          # one message from the person
KEEP = 100               # messages kept in one chat
SEND = 20                # most recent messages the model is shown
MAX_CHATS = 40
SETTINGS_RECORD = "agent_settings"
WHO = ("all", "admins")
GIVE_UP = 240           # a question still unanswered after this long is shown as failed
WAIT_HERE = 20.0        # how long the request that sends a message waits for a quick answer before the page starts checking back
TITLE_MAX = 60
CHAT_ID = re.compile(r"^c[0-9a-f]{12}$")
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

SYSTEM = (
    f"You are {NAME}, a friendly helper inside Enveliq, a private email and task app. Talk with the person plainly and kindly, "
    "in short answers they can act on. Use ordinary words, no jargon, and plain text only (no markdown tables or headings). "
    "You cannot see their email, tasks or settings, and you cannot change anything in the app. If they ask for that, say so "
    "and suggest how they could do it themselves in the app. Never ask for passwords, keys or codes."
)


class ChatError(Exception):
    """Something the person can fix; `status` is the HTTP code to answer with."""

    def __init__(self, message: str, status: int = 422):
        super().__init__(message)
        self.status = status


def clean(value: Any, limit: int) -> str:
    return _CONTROL.sub("", str(value or "")).replace("\r\n", "\n").replace("\r", "\n").strip()[:limit]


def one_line(value: Any, limit: int) -> str:
    return re.sub(r"\s+", " ", clean(value, limit * 3)).strip()[:limit]


class Agent:
    def __init__(self, vault: Any, summariser: Summariser):
        self.vault, self.summariser = vault, summariser
        self._lock = threading.Lock()
        self._user_locks: dict[str, threading.Lock] = {}

    def _user_lock(self, user_id: str) -> threading.Lock:
        with self._lock:
            return self._user_locks.setdefault(user_id, threading.Lock())

    # ---------- settings (the administrator's) ----------

    def _raw(self) -> dict[str, Any]:
        raw = self.vault.get_global(SETTINGS_RECORD) or {}
        if any(k in raw for k in ("mode", "url", "model", "key")):
            # An older version could send the chat to a separate agent address. That option is gone, so the saved address,
            # model name and access key are forgotten here instead of being kept for nothing.
            raw = {"who": raw.get("who"), "name": raw.get("name")}
            try:
                self.vault.set_global(SETTINGS_RECORD, raw)
            except Exception:
                pass
        return raw

    def settings(self) -> dict[str, Any]:
        """What the administrator sees and the chat uses."""
        raw = self._raw()
        who = raw.get("who") if raw.get("who") in WHO else "all"
        return {"who": who, "name": one_line(raw.get("name"), 40) or NAME}

    def save_settings(self, who: str, name: str) -> dict[str, Any]:
        if who not in WHO:
            raise ChatError("Unknown choice.")
        self.vault.set_global(SETTINGS_RECORD, {"who": who, "name": one_line(name, 40) or NAME})
        return self.settings()

    # ---------- storage ----------

    @staticmethod
    def _messages(raw: Any) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for m in raw if isinstance(raw, list) else []:
            if isinstance(m, dict) and m.get("role") in ("user", "assistant") and isinstance(m.get("text"), str):
                try:
                    at = float(m.get("at") or 0)
                except (TypeError, ValueError):
                    at = 0.0
                out.append({"role": m["role"], "text": m["text"][:6000], "at": at})
        return out[-KEEP:]

    def _load(self, user_id: str) -> list[dict[str, Any]]:
        rec = self.vault.get_global(RECORD_PREFIX + user_id) or {}
        chats: list[dict[str, Any]] = []
        for c in rec.get("chats") if isinstance(rec.get("chats"), list) else []:
            if isinstance(c, dict) and isinstance(c.get("id"), str) and CHAT_ID.match(c["id"]):
                msgs = self._messages(c.get("messages"))
                pend = c.get("pending")
                chats.append({"id": c["id"], "title": one_line(c.get("title"), TITLE_MAX) or "New chat", "at": float(c.get("at") or 0), "messages": msgs,
                              "pending": float(pend) if isinstance(pend, (int, float)) and not isinstance(pend, bool) else None,
                              "error": one_line(c.get("error"), 300) or None})
        if not chats and rec.get("messages"):        # the first version kept one chat; carry it over
            msgs = self._messages(rec.get("messages"))
            if msgs:
                first = next((m["text"] for m in msgs if m["role"] == "user"), "")
                chats.append({"id": "c" + secrets.token_hex(6), "title": one_line(first, 40) or "Earlier chat", "at": msgs[-1]["at"], "messages": msgs})
        return sorted(chats, key=lambda c: c["at"], reverse=True)

    def _save(self, user_id: str, chats: list[dict[str, Any]]) -> None:
        self.vault.set_global(RECORD_PREFIX + user_id, {"chats": chats[:MAX_CHATS]})

    # ---------- reading ----------

    def view(self, user_id: str, chat_id: str | None = None, latest: bool = False) -> dict[str, Any]:
        chats = self._load(user_id)
        current = next((c for c in chats if c["id"] == chat_id), None) if chat_id else (chats[0] if latest and chats else None)
        return {
            "chats": [{"id": c["id"], "title": c["title"], "at": c["at"], "count": len(c["messages"])} for c in chats],
            "chat": ({"id": current["id"], "title": current["title"], "messages": current["messages"], **self._state(current)} if current else None),
        }

    def _state(self, chat: dict[str, Any]) -> dict[str, Any]:
        """Is the agent still working on the last message? A question left unanswered for too long counts as failed
        (for example after Enveliq was restarted while the agent was thinking)."""
        pend = chat.get("pending")
        if pend and time.time() - pend > GIVE_UP:
            return {"pending": False, "error": chat.get("error") or "The agent did not answer in time. Try again."}
        return {"pending": bool(pend), "error": chat.get("error")}

    # ---------- changing ----------

    def send(self, user_id: str, text: str, chat_id: str | None, wait: float | None = None) -> dict[str, Any]:
        """Add the person's message to a chat (a new one when `chat_id` is None) and ask the model. A quick answer is
        returned at once. A slow one (an agent using tools can take minutes, longer than a web proxy will wait) is finished
        in the background: the view then says `pending` and the page checks back. The person's message is kept even when
        the model cannot be reached, so nothing they typed is lost."""
        text = clean(text, MAX_TEXT)
        if not text:
            raise ChatError("Type a message first.")
        with self._user_lock(user_id):
            chats = self._load(user_id)
            if chat_id:
                chat = next((c for c in chats if c["id"] == chat_id), None)
                if chat is None:
                    raise ChatError("That chat is no longer there.", 404)
                if self._state(chat)["pending"]:
                    raise ChatError("Hermes is still answering your last message. Wait for it first.", 409)
            else:
                if len(chats) >= MAX_CHATS:
                    raise ChatError(f"You have {MAX_CHATS} saved chats. Delete one you don't need, then start a new chat.", 409)
                chat = {"id": "c" + secrets.token_hex(6), "title": one_line(text, 40) or "New chat", "at": time.time(), "messages": []}
                chats.append(chat)
            chat["messages"].append({"role": "user", "text": text, "at": time.time()})
            chat["messages"] = chat["messages"][-KEEP:]
            chat["at"] = time.time()
            chat["pending"], chat["error"] = time.time(), None
            self._save(user_id, chats)
            turns = [{"role": m["role"], "content": m["text"]} for m in chat["messages"][-SEND:]]
            while turns and turns[0]["role"] != "user":
                turns.pop(0)
            conf = self.settings()
            cid = chat["id"]
        done = threading.Event()
        outcome: dict[str, Any] = {}

        def work() -> None:
            try:
                outcome["text"] = self.summariser.chat(SYSTEM.replace(NAME, conf["name"], 1), turns)
            except BridgeError as err:
                outcome["error"] = err
            except Exception:                                    # never leave a chat stuck on "thinking"
                outcome["error"] = BridgeError("ai_unreachable", "The AI server could not be reached or took too long to answer.")
            finally:
                self._finish(user_id, cid, outcome)
                done.set()

        threading.Thread(target=work, name="agent-chat", daemon=True).start()
        done.wait(max(0.0, WAIT_HERE if wait is None else wait))
        err = outcome.get("error") if done.is_set() else None
        if err is not None:        # failed while the sender was waiting: it is reported by this request, not kept on the chat
            with self._user_lock(user_id):
                chats = self._load(user_id)
                chat = next((c for c in chats if c["id"] == cid), None)
                if chat is not None and chat.get("error"):
                    chat["error"] = None
                    self._save(user_id, chats)
            raise err
        return self.view(user_id, cid)

    def _finish(self, user_id: str, chat_id: str, outcome: dict[str, Any]) -> None:
        """Write the answer (or why there is none) into the chat."""
        with self._user_lock(user_id):
            chats = self._load(user_id)
            chat = next((c for c in chats if c["id"] == chat_id), None)       # the person may have deleted it meanwhile
            if chat is None:
                return
            if "text" in outcome:
                chat["messages"].append({"role": "assistant", "text": outcome["text"], "at": time.time()})
                chat["messages"] = chat["messages"][-KEEP:]
                chat["error"] = None
            else:
                chat["error"] = one_line(getattr(outcome.get("error"), "message", ""), 300) or "The agent could not answer."
            chat["pending"] = None
            chat["at"] = time.time()
            self._save(user_id, chats)

    def rename(self, user_id: str, chat_id: str, title: str) -> None:
        title = one_line(title, TITLE_MAX)
        if not title:
            raise ChatError("Give the chat a name.")
        with self._user_lock(user_id):
            chats = self._load(user_id)
            chat = next((c for c in chats if c["id"] == chat_id), None)
            if chat is None:
                raise ChatError("That chat is no longer there.", 404)
            chat["title"] = title
            self._save(user_id, chats)

    def delete(self, user_id: str, chat_id: str) -> None:
        with self._user_lock(user_id):
            chats = self._load(user_id)
            self._save(user_id, [c for c in chats if c["id"] != chat_id])


__all__ = ["Agent", "BridgeError", "ChatError", "NAME", "MAX_TEXT", "CHAT_ID"]
