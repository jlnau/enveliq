"""Messages between the people who share one Enveliq.

Every conversation is its own encrypted record (`msg:thread:<long random id>`), and each person has a small encrypted
index (`msg:index:<user id>`) that lists only the conversations they are in. Nothing else points at a conversation.

The server decides who may open a conversation, every time, from the signed-in session: a person who is not in it gets
exactly the same "not found" as for an id that was never used. There is no way for an administrator to read other
people's conversations, and nothing here ever touches anyone's email, tasks, mailboxes or settings.

Plain text only, cut to 2,000 characters; a conversation keeps its most recent 500 messages. What other people see of a
person is their name and picture, and only if that person has not hidden themselves from the people list.
"""
from __future__ import annotations

import re
import secrets
import threading
import time
from typing import Any, Callable

THREAD_PREFIX = "msg:thread:"
INDEX_PREFIX = "msg:index:"
MAX_TEXT = 2000
MAX_MEMBERS = 8                      # including the person starting it
MAX_KEPT = 500
MAX_THREADS = 200
SHOW_LAST = 200                      # messages sent to the page when a conversation is opened
GONE = "Someone who has left"

_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
THREAD_ID = r"^t[0-9a-f]{24}$"
MESSAGE_ID = r"^m[0-9a-f]{16}$"


class MessageError(ValueError):
    """Something the person can fix; the text is safe to show them."""


def clean_text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    text = _CONTROL.sub("", value.replace("\r\n", "\n").replace("\r", "\n"))
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text


class MessageBook:
    def __init__(self, vault: Any, users: Any, clock: Callable[[], float] = time.time):
        self.vault = vault
        self.users = users
        self.clock = clock
        self._lock = threading.RLock()

    # ---------- who may use it ----------

    def enabled(self, user_id: str | None) -> bool:
        if not user_id:
            return False
        from . import features
        user = self._user(user_id)
        if user is None or user.get("disabled"):
            return False
        return bool(features.effective(self.vault, user_id).get("messages"))

    def _user(self, user_id: str) -> dict[str, Any] | None:
        try:
            return self.users.get(user_id)
        except KeyError:
            return None

    def _name(self, user_id: str) -> str:
        user = self._user(user_id)
        if user is None:
            return GONE
        return str(user.get("display_name") or user.get("username") or GONE)

    def _card(self, user_id: str) -> dict[str, Any]:
        """All that anyone else ever learns about a person: a name and a picture."""
        user = self._user(user_id)
        if user is None or user.get("disabled"):
            return {"id": user_id, "name": GONE if user is None else self._name(user_id), "avatar_v": None, "gone": True}
        return {"id": user_id, "name": self._name(user_id), "avatar_v": (user.get("avatar") or {}).get("v"), "gone": False}

    def people(self, me: str) -> list[dict[str, Any]]:
        """The people list: everyone who is active, has Messages on, and has not hidden themselves."""
        out = []
        for u in self.users.all():
            uid = u["id"]
            if uid == me or u.get("disabled") or u.get("people_list") is False or not self.enabled(uid):
                continue
            out.append({"id": uid, "name": self._name(uid), "avatar_v": (u.get("avatar") or {}).get("v")})
        out.sort(key=lambda p: p["name"].lower())
        return out

    # ---------- storage ----------

    def _index(self, user_id: str) -> list[str]:
        raw = self.vault.get_global(INDEX_PREFIX + user_id) or {}
        ids = raw.get("threads")
        return [t for t in ids if isinstance(t, str)] if isinstance(ids, list) else []

    def _save_index(self, user_id: str, ids: list[str]) -> None:
        self.vault.set_global(INDEX_PREFIX + user_id, {"threads": ids[:MAX_THREADS]})

    def _thread(self, thread_id: str, user_id: str) -> dict[str, Any]:
        """The conversation, but only for someone in it. Anyone else gets KeyError, the same as for an unknown id."""
        if not isinstance(thread_id, str) or not re.match(THREAD_ID, thread_id):
            raise KeyError(thread_id)
        raw = self.vault.get_global(THREAD_PREFIX + thread_id)
        if not raw or user_id not in (raw.get("members") or []) or thread_id not in self._index(user_id):
            raise KeyError(thread_id)
        raw.setdefault("messages", [])
        raw.setdefault("read", {})
        raw.setdefault("muted", [])
        raw.setdefault("next", 1)
        return raw

    def _save_thread(self, t: dict[str, Any]) -> None:
        self.vault.set_global(THREAD_PREFIX + t["id"], t)

    # ---------- reading ----------

    @staticmethod
    def _unread(t: dict[str, Any], user_id: str) -> int:
        seen = int((t.get("read") or {}).get(user_id) or 0)
        return sum(1 for m in t["messages"] if m["n"] > seen and m["from"] != user_id and not m.get("deleted"))

    def _title(self, t: dict[str, Any], me: str) -> str:
        others = [self._name(m) for m in t["members"] if m != me]
        if len(others) <= 1:
            return others[0] if others else "Just you"
        if len(others) == 2:
            return f"{others[0]}, {others[1]} and you"
        return f"{others[0]}, {others[1]} and {len(others) - 1} more"

    def _row(self, t: dict[str, Any], me: str) -> dict[str, Any]:
        last = next((m for m in reversed(t["messages"]) if not m.get("deleted")), None)
        return {
            "id": t["id"],
            "title": self._title(t, me),
            "members": [self._card(m) for m in t["members"] if m != me],
            "group": len(t["members"]) > 2,
            "muted": me in t["muted"],
            "unread": self._unread(t, me),
            "last": None if last is None else {"from": last["from"], "mine": last["from"] == me, "name": self._name(last["from"]), "text": last["text"][:140], "at": last["at"]},
            "updated": t.get("updated") or t.get("created") or 0,
        }

    def threads(self, me: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = []
            for tid in self._index(me):
                try:
                    rows.append(self._row(self._thread(tid, me), me))
                except KeyError:
                    continue
            rows.sort(key=lambda r: r["updated"], reverse=True)
            return rows

    def summary(self, me: str) -> dict[str, Any]:
        """For the sidebar count and the card on Home. Muted conversations are not counted."""
        with self._lock:
            total, latest = 0, []
            for tid in self._index(me):
                try:
                    t = self._thread(tid, me)
                except KeyError:
                    continue
                n = 0 if me in t["muted"] else self._unread(t, me)
                if not n:
                    continue
                total += n
                seen = int(t["read"].get(me) or 0)
                mine = [m for m in t["messages"] if m["n"] > seen and m["from"] != me and not m.get("deleted")]
                m = mine[-1]
                latest.append({"thread": tid, "from": self._card(m["from"]), "text": m["text"][:140], "at": m["at"], "count": n})
            latest.sort(key=lambda r: r["at"], reverse=True)
            return {"enabled": True, "unread": total, "conversations": len(latest), "latest": latest[:3]}

    def open(self, me: str, thread_id: str) -> dict[str, Any]:
        with self._lock:
            t = self._thread(thread_id, me)
            shown = t["messages"][-SHOW_LAST:]
            out = self._row(t, me)
            out["messages"] = [
                {"id": m["id"], "from": m["from"], "name": self._name(m["from"]), "mine": m["from"] == me, "at": m["at"], "text": "" if m.get("deleted") else m["text"], "deleted": bool(m.get("deleted"))}
                for m in shown
            ]
            out["everyone"] = [self._card(m) for m in t["members"]]
            return out

    # ---------- writing ----------

    def _check_text(self, text: Any) -> str:
        text = clean_text(text)
        if not text:
            raise MessageError("Write a message first.")
        if len(text) > MAX_TEXT:
            raise MessageError(f"That message is too long. The limit is {MAX_TEXT:,} characters.")
        return text

    def _append(self, t: dict[str, Any], me: str, text: str) -> dict[str, Any]:
        now = self.clock()
        msg = {"id": "m" + secrets.token_hex(8), "n": t["next"], "from": me, "at": now, "text": text}
        t["next"] += 1
        t["messages"].append(msg)
        del t["messages"][:-MAX_KEPT]
        t["updated"] = now
        t["read"][me] = msg["n"]                 # what you write, you have read
        return msg

    def start(self, me: str, others: list[str], text: str) -> dict[str, Any]:
        text = self._check_text(text)
        wanted = []
        for o in others:
            if isinstance(o, str) and o != me and o not in wanted:
                wanted.append(o)
        if not wanted:
            raise MessageError("Choose who to write to.")
        if len(wanted) + 1 > MAX_MEMBERS:
            raise MessageError(f"A group can have up to {MAX_MEMBERS} people, including you.")
        with self._lock:
            mine = self._index(me)
            listed = {p["id"] for p in self.people(me)}
            for o in wanted:
                if o not in listed:
                    raise KeyError(o)            # hidden, switched off, disabled or unknown: all "not found"
            members = [me, *wanted]
            existing = None
            if len(members) == 2:                # a one-to-one conversation is only ever one conversation
                for tid in mine:
                    try:
                        t = self._thread(tid, me)
                    except KeyError:
                        continue
                    if sorted(t["members"]) == sorted(members):
                        existing = t
                        break
            if existing is None:
                if len(mine) >= MAX_THREADS:
                    raise MessageError("You have a lot of conversations. Please leave some of the old ones first.")
                now = self.clock()
                existing = {"id": "t" + secrets.token_hex(12), "members": members, "created": now, "updated": now, "messages": [], "read": {}, "muted": [], "next": 1}
                for m in members:
                    idx = self._index(m)
                    idx.insert(0, existing["id"])
                    self._save_index(m, idx)
            self._append(existing, me, text)
            self._save_thread(existing)
            return self.open(me, existing["id"])

    def post(self, me: str, thread_id: str, text: str) -> dict[str, Any]:
        text = self._check_text(text)
        with self._lock:
            t = self._thread(thread_id, me)
            if not any(o != me and self.enabled(o) for o in t["members"]):
                raise MessageError("Nobody else in this conversation can receive messages any more.")
            self._append(t, me, text)
            self._save_thread(t)
            return self.open(me, thread_id)

    def mark_read(self, me: str, thread_id: str) -> None:
        with self._lock:
            t = self._thread(thread_id, me)
            if t["messages"]:
                top = t["messages"][-1]["n"]
                if int(t["read"].get(me) or 0) < top:
                    t["read"][me] = top
                    self._save_thread(t)

    def unsend(self, me: str, thread_id: str, message_id: str) -> None:
        with self._lock:
            t = self._thread(thread_id, me)
            for m in t["messages"]:
                if m["id"] == message_id and m["from"] == me:
                    m["deleted"], m["text"] = True, ""
                    self._save_thread(t)
                    return
            raise KeyError(message_id)

    def mute(self, me: str, thread_id: str, muted: bool) -> None:
        with self._lock:
            t = self._thread(thread_id, me)
            if muted and me not in t["muted"]:
                t["muted"].append(me)
            if not muted and me in t["muted"]:
                t["muted"].remove(me)
            self._save_thread(t)

    def forget_user(self, user_id: str) -> None:
        """A person was deleted: their messages are removed, they leave every conversation, and their index is emptied."""
        with self._lock:
            for tid in self._index(user_id):
                raw = self.vault.get_global(THREAD_PREFIX + tid)
                if not raw or user_id not in (raw.get("members") or []):
                    continue
                raw["members"] = [m for m in raw["members"] if m != user_id]
                raw["messages"] = [m for m in raw.get("messages", []) if m["from"] != user_id]
                raw["muted"] = [m for m in raw.get("muted", []) if m != user_id]
                (raw.get("read") or {}).pop(user_id, None)
                self.vault.set_global(THREAD_PREFIX + tid, raw if raw["members"] else {"id": tid, "members": [], "messages": []})
            self.vault.set_global(INDEX_PREFIX + user_id, {"threads": []})

