"""Tasks in a calendar and in a Home Assistant To-do list.

Three ways out, each optional and each per person:

* A private calendar feed (an .ics address). Any calendar app can subscribe. It always shows exactly the open tasks, so a
  task that is done, removed or whose email was dealt with disappears the next time the calendar app looks. Google and
  Outlook look only every few hours; that is their delay, not Enveliq's.
* CalDAV (Nextcloud, Radicale, Baikal, Fastmail and others). Enveliq writes and deletes the events itself, so a finished
  task leaves the calendar within a minute.
* A Home Assistant To-do list. New tasks are added, finished ones are ticked off, removed ones are deleted, and ticking
  one in Home Assistant finishes it here too.

Everything is rebuilt from the task list, never from "what changed", so a failure just means the next pass fixes it.
Secrets are write-only. Calls to other servers go through outbound.py, which keeps them off networks nobody allowed.
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import re
import secrets
import threading
import time
import urllib.parse
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable

from . import gcal, outbound
from .outbound import OutboundError

log = logging.getLogger("enveliq.sync")
RECORD = "sync:"
FEED_INDEX = "sync_feeds"
ENTITY = re.compile(r"^todo\.[a-z0-9_]{1,80}$")
TOKEN = re.compile(r"^[A-Za-z0-9_-]{20,64}$")
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
GENERIC = "Enveliq task"


def _clean(value: Any, limit: int) -> str:
    return _CONTROL.sub("", str(value or "")).strip()[:limit]


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


# ---------- iCalendar text ----------

def esc(text: str) -> str:
    return _clean(text, 400).replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def fold(line: str) -> str:
    """RFC 5545: lines are at most 75 bytes; a longer one continues on the next line after a space."""
    raw, out = line.encode("utf-8"), []
    while len(raw) > 75:
        cut = 75 if not out else 74
        while cut and (raw[cut] & 0xC0) == 0x80:        # never cut inside a character
            cut -= 1
        out.append(raw[:cut].decode("utf-8"))
        raw = raw[cut:]
    out.append(raw.decode("utf-8"))
    return "\r\n ".join(out)


def event_lines(task: dict[str, Any], *, titles: bool, link: str, stamp: float, seq: int = 0) -> list[str]:
    due = date.fromisoformat(task["due"])
    summary = task["title"] if titles else GENERIC
    lines = ["BEGIN:VEVENT", f"UID:{task['id']}@enveliq", "DTSTAMP:" + datetime.fromtimestamp(stamp, timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
             f"DTSTART;VALUE=DATE:{due:%Y%m%d}", f"DTEND;VALUE=DATE:{due + timedelta(days=1):%Y%m%d}", f"SEQUENCE:{seq}",
             "SUMMARY:" + esc(summary), "TRANSP:TRANSPARENT", "CATEGORIES:Enveliq"]
    if titles and task.get("detail"):
        lines.append("DESCRIPTION:" + esc(task["detail"]))
    if link:
        lines.append("URL:" + _clean(link, 300))
    lines.append("END:VEVENT")
    return lines


def calendar_text(events: list[list[str]], name: str = "Enveliq tasks") -> str:
    head = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Enveliq//Tasks//EN", "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
            "X-WR-CALNAME:" + esc(name), "REFRESH-INTERVAL;VALUE=DURATION:PT1H", "X-PUBLISHED-TTL:PT1H"]
    body = [ln for ev in events for ln in ev]
    return "\r\n".join(fold(ln) for ln in head + body + ["END:VCALENDAR"]) + "\r\n"


def _empty() -> dict[str, Any]:
    return {"titles": True, "feed": {"hash": None, "made": None},
            "caldav": {"enabled": False, "url": "", "user": "", "password": "", "pushed": {}, "last_ok": None, "last_error": None},
            "todo": {"enabled": False, "url": "", "token": "", "entity": "", "pushed": {}, "last_ok": None, "last_error": None},
            "google": {"enabled": False, "refresh_token": "", "calendar_id": "", "pushed": {}, "last_ok": None, "last_error": None}}


def _url(value: str, label: str) -> str:
    v = _clean(value, 300).rstrip("/")
    p = urllib.parse.urlsplit(v)
    if p.scheme not in ("http", "https") or not p.hostname or p.username or p.password or re.search(r"\s", v):
        raise ValueError(f"{label} must be a full address starting with http:// or https://")
    return v


class Sync:
    def __init__(self, vault: Any, tasks: Any, notifier: Any, origin: str, clock: Callable[[], float] = time.time):
        self.vault, self.tasks, self.notifier, self.origin, self.clock = vault, tasks, notifier, origin.rstrip("/"), clock
        self._lock = threading.RLock()
        self._dirty: set[str] = set()
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_full: dict[str, float] = {}
        self.google = gcal.Google(vault, clock)
        tasks.listeners.append(self._changed)

    # ---------- storage ----------
    def _load(self, uid: str) -> dict[str, Any]:
        raw = self.vault.get_global(RECORD + uid) or {}
        out = _empty()
        for key in ("caldav", "todo", "feed", "google"):
            if isinstance(raw.get(key), dict):
                out[key].update(raw[key])
        if isinstance(raw.get("titles"), bool):
            out["titles"] = raw["titles"]
        return out

    def _save(self, uid: str, rec: dict[str, Any]) -> None:
        self.vault.set_global(RECORD + uid, rec)

    def _link(self) -> str:
        return "" if "localhost" in self.origin or "127.0.0.1" in self.origin else self.origin

    def internet_ready(self) -> bool:
        p = urllib.parse.urlsplit(self.origin)
        return p.scheme == "https" and p.hostname not in (None, "localhost", "127.0.0.1", "::1")

    # ---------- what the settings page sees ----------
    def overview(self, uid: str) -> dict[str, Any]:
        rec = self._load(uid)
        cd, td, gd = rec["caldav"], rec["todo"], rec["google"]
        return {"titles": rec["titles"], "internet_ready": self.internet_ready(), "origin": self.origin,
                "feed": {"on": bool(rec["feed"]["hash"]), "made": rec["feed"]["made"]},
                "google": {"available": gcal.ready(self.google.config()), "connected": bool(gd["refresh_token"]), "enabled": gd["enabled"], "count": len(gd["pushed"]),
                           "last_ok": gd["last_ok"], "last_error": gd["last_error"]},
                "caldav": {"enabled": cd["enabled"], "url": cd["url"], "user": cd["user"], "password_set": bool(cd["password"]), "configured": bool(cd["url"]),
                           "count": len(cd["pushed"]), "last_ok": cd["last_ok"], "last_error": cd["last_error"]},
                "todo": {"enabled": td["enabled"], "url": td["url"], "entity": td["entity"], "token_set": bool(td["token"]), "configured": bool(td["url"]),
                         "count": sum(1 for p in td["pushed"].values() if p.get("status") == "needs_action"), "last_ok": td["last_ok"], "last_error": td["last_error"]}}

    def set_titles(self, uid: str, on: bool) -> None:
        with self._lock:
            rec = self._load(uid)
            rec["titles"] = bool(on)
            rec["caldav"]["pushed"] = {k: dict(v, sig="") for k, v in rec["caldav"]["pushed"].items()}      # rewrite events with the new wording
            rec["todo"]["pushed"] = {k: dict(v, sig="") for k, v in rec["todo"]["pushed"].items()}
            rec["google"]["pushed"] = {k: dict(v, sig="") for k, v in rec["google"]["pushed"].items()}
            self._save(uid, rec)
        self.mark(uid)

    # ---------- the private feed ----------
    def feed_new(self, uid: str) -> str:
        """Make (or replace) the person's feed address. Returns the address; only its hash is kept."""
        token = secrets.token_urlsafe(24)
        with self._lock:
            rec = self._load(uid)
            index = dict(self.vault.get_global(FEED_INDEX) or {})
            if rec["feed"]["hash"]:
                index.pop(rec["feed"]["hash"], None)
            digest = _hash(token)
            index[digest] = uid
            rec["feed"] = {"hash": digest, "made": self.clock()}
            self.vault.set_global(FEED_INDEX, index)
            self._save(uid, rec)
        return f"{self.origin}/calendar/{token}.ics"

    def feed_off(self, uid: str) -> None:
        with self._lock:
            rec = self._load(uid)
            index = dict(self.vault.get_global(FEED_INDEX) or {})
            if rec["feed"]["hash"]:
                index.pop(rec["feed"]["hash"], None)
                self.vault.set_global(FEED_INDEX, index)
            rec["feed"] = {"hash": None, "made": None}
            self._save(uid, rec)

    def feed_owner(self, token: str) -> str | None:
        if not TOKEN.match(token or ""):
            return None
        uid = (self.vault.get_global(FEED_INDEX) or {}).get(_hash(token))
        return uid if isinstance(uid, str) else None

    def feed_text(self, uid: str) -> str:
        self.tasks.reconcile(uid)
        rec = self._load(uid)
        now = self.clock()
        events = [event_lines(t, titles=rec["titles"], link=self._link(), stamp=now) for t in self.tasks.snapshot(uid) if t["state"] == "open"]
        events.sort(key=lambda e: e[3])
        return calendar_text(events)

    # ---------- CalDAV and To-do settings ----------
    def save_caldav(self, uid: str, enabled: bool, url: str, user: str, password: str) -> None:
        with self._lock:
            rec = self._load(uid)
            cd = rec["caldav"]
            new_url = _url(url, "The calendar address") + "/"
            if not _clean(user, 160):
                raise ValueError("A user name is needed.")
            pw = _clean(password, 300) or cd["password"]
            if not pw:
                raise ValueError("A password is needed. For most services use an app password.")
            if new_url != cd["url"] or _clean(user, 160) != cd["user"]:
                cd["pushed"] = {}
            cd.update(enabled=bool(enabled), url=new_url, user=_clean(user, 160), password=pw, last_error=None)
            self._save(uid, rec)
        self.mark(uid)

    def connect_google(self, uid: str, refresh_token: str) -> None:
        """Called after the person agreed on Google's page: keep the connection and make the calendar."""
        tz = self.tasks.timezone_of(uid)
        calendar_id = self.google.make_calendar(uid, refresh_token, tz)
        with self._lock:
            rec = self._load(uid)
            old = rec["google"]
            rec["google"] = {"enabled": True, "refresh_token": refresh_token, "calendar_id": calendar_id, "pushed": {}, "last_ok": None, "last_error": None}
            self._save(uid, rec)
        if old.get("refresh_token") and old.get("calendar_id") and old["calendar_id"] != calendar_id:
            self.google.delete_calendar(uid, refresh_token, old["calendar_id"])
        self.mark(uid)

    def set_google_enabled(self, uid: str, on: bool) -> None:
        with self._lock:
            rec = self._load(uid)
            if not rec["google"]["refresh_token"]:
                raise ValueError("Connect Google Calendar first.")
            rec["google"]["enabled"] = bool(on)
            self._save(uid, rec)
        self.mark(uid)

    def save_todo(self, uid: str, enabled: bool, url: str, token: str, entity: str) -> None:
        with self._lock:
            rec = self._load(uid)
            td = rec["todo"]
            new_url = _url(url, "The Home Assistant address")
            ent = _clean(entity, 90).lower()
            if not ENTITY.match(ent):
                raise ValueError("The list name looks like todo.my_list (Home Assistant: Settings, Devices, Entities, search for todo).")
            tok = _clean(token, 600) or td["token"]
            if not tok:
                raise ValueError("A long-lived access token is needed.")
            if new_url != td["url"] or ent != td["entity"]:
                td["pushed"] = {}
            td.update(enabled=bool(enabled), url=new_url, token=tok, entity=ent, last_error=None)
            self._save(uid, rec)
        self.mark(uid)

    def clear(self, uid: str, which: str, remove_remote: bool = True) -> None:
        """Stop mirroring. With remove_remote, events and items that Enveliq added are taken out first (best effort)."""
        if which not in ("caldav", "todo", "google"):
            raise KeyError(which)
        if which == "google":
            rec = self._load(uid)["google"]
            if rec["refresh_token"]:
                if remove_remote and rec["calendar_id"]:
                    self.google.delete_calendar(uid, rec["refresh_token"], rec["calendar_id"])      # takes every event with it
                self.google.revoke(rec["refresh_token"])
            self.google.forget(uid)
            remove_remote = False
        if remove_remote:
            try:
                self._run(uid, which, wipe=True)
            except Exception:
                pass
        with self._lock:
            rec = self._load(uid)
            rec[which] = _empty()[which]
            self._save(uid, rec)

    # ---------- keeping them in step ----------
    def _changed(self, uid: str, task: dict[str, Any], change: str) -> None:
        self.mark(uid)

    def mark(self, uid: str) -> None:
        with self._lock:
            self._dirty.add(uid)
        self._wake.set()

    def sync_now(self, uid: str) -> dict[str, str | None]:
        """Run both mirrors for one person. Returns {mirror: None when fine, else the problem}."""
        out: dict[str, str | None] = {}
        for which in ("caldav", "todo", "google"):
            rec = self._load(uid)
            if rec[which]["enabled"]:
                try:
                    self._run(uid, which)
                    out[which] = None
                except OutboundError as err:
                    out[which] = err.message
        return out

    def _run(self, uid: str, which: str, wipe: bool = False) -> None:
        rec = self._load(uid)
        part = rec[which]
        ready = {"caldav": part.get("url") and part.get("password"), "todo": part.get("url") and part.get("token"), "google": part.get("refresh_token") and part.get("calendar_id")}[which]
        if not ready:
            return
        err: str | None = None
        try:
            if which == "caldav":
                self._caldav(uid, rec, wipe)
            elif which == "google":
                self._google(uid, rec, wipe)
            else:
                self._todo(uid, rec, wipe)
        except OutboundError as e:
            err = e.message
            raise
        except Exception:
            err = "Syncing failed."
            raise OutboundError("error", err) from None
        finally:
            with self._lock:
                cur = self._load(uid)
                cur[which]["pushed"] = part["pushed"]
                cur[which]["last_error"] = err
                if err is None:
                    cur[which]["last_ok"] = self.clock()
                self._save(uid, cur)

    # ----- CalDAV -----
    def _dav(self, cd: dict[str, Any], method: str, url: str, **kw: Any) -> tuple[int, bytes]:
        auth = base64.b64encode(f"{cd['user']}:{cd['password']}".encode()).decode()
        status, body = outbound.request(method, url, allow=self.notifier.allow(), headers={"Authorization": "Basic " + auth, **kw.pop("headers", {})}, **kw)
        if status in (401, 403):
            raise OutboundError("auth", "The user name or password was not accepted.")
        return status, body

    def test_caldav(self, uid: str) -> str:
        cd = self._load(uid)["caldav"]
        if not cd["url"]:
            raise OutboundError("not_set", "Save the details first.")
        status, _ = self._dav(cd, "PROPFIND", cd["url"], headers={"Depth": "0", "Content-Type": "application/xml; charset=utf-8"},
                              body=b'<?xml version="1.0"?><propfind xmlns="DAV:"><prop><resourcetype/></prop></propfind>')
        if status == 404:
            raise OutboundError("not_found", "That calendar address was not found.")
        if status not in (200, 207):
            raise OutboundError("error", f"The calendar answered with an unexpected reply ({status}).")
        return "Connected."

    def _caldav(self, uid: str, rec: dict[str, Any], wipe: bool) -> None:
        cd = rec["caldav"]
        pushed: dict[str, Any] = cd["pushed"]
        now = self.clock()
        open_tasks = {} if wipe else {t["id"]: t for t in self.tasks.snapshot(uid) if t["state"] == "open"}
        for tid in list(pushed):
            if tid not in open_tasks:
                status, _ = self._dav(cd, "DELETE", cd["url"] + f"enveliq-{tid}.ics")
                if status not in (200, 202, 204, 404, 410):
                    raise OutboundError("error", f"The calendar refused to remove an event ({status}).")
                pushed.pop(tid, None)
        for tid, t in open_tasks.items():
            sig = _hash(f"{t['due']}|{t['title'] if rec['titles'] else ''}|{t['detail'] if rec['titles'] else ''}")[:16]
            cur = pushed.get(tid)
            if cur and cur.get("sig") == sig:
                continue
            seq = (cur or {}).get("seq", -1) + 1
            body = calendar_text([event_lines(t, titles=rec["titles"], link=self._link(), stamp=now, seq=seq)]).replace("METHOD:PUBLISH\r\n", "")
            status, _ = self._dav(cd, "PUT", cd["url"] + f"enveliq-{tid}.ics", body=body.encode("utf-8"), headers={"Content-Type": "text/calendar; charset=utf-8"})
            if status == 404:
                raise OutboundError("not_found", "That calendar address was not found.")
            if status not in (200, 201, 204):
                raise OutboundError("error", f"The calendar refused an event ({status}).")
            pushed[tid] = {"sig": sig, "seq": seq}

    # ----- Google Calendar -----
    def _google(self, uid: str, rec: dict[str, Any], wipe: bool) -> None:
        g = rec["google"]
        pushed: dict[str, Any] = g["pushed"]
        rt, cal = g["refresh_token"], "/calendars/" + urllib.parse.quote(g["calendar_id"], safe="")
        now = self.clock()
        open_tasks = {} if wipe else {t["id"]: t for t in self.tasks.snapshot(uid) if t["state"] == "open"}
        for tid in list(pushed):
            if tid not in open_tasks:
                status, _ = self.google.call(uid, rt, "DELETE", f"{cal}/events/{tid}")
                if status not in (200, 204, 404, 410):
                    raise OutboundError("error", f"Google refused to remove an event ({status}).")
                pushed.pop(tid, None)
        for tid, t in open_tasks.items():
            titles = rec["titles"]
            sig = _hash(f"{t['due']}|{t['title'] if titles else ''}|{t['detail'] if titles else ''}")[:16]
            if pushed.get(tid, {}).get("sig") == sig:
                continue
            due = date.fromisoformat(t["due"])
            body = {"id": tid, "summary": t["title"] if titles else GENERIC, "status": "confirmed", "transparency": "transparent",
                    "start": {"date": due.isoformat()}, "end": {"date": (due + timedelta(days=1)).isoformat()}, "extendedProperties": {"private": {"enveliq": tid}}}
            if titles and t.get("detail"):
                body["description"] = _clean(t["detail"], 1000)
            if self._link():
                body["source"] = {"title": "Enveliq", "url": self._link()}
            if tid in pushed:
                status, _ = self.google.call(uid, rt, "PUT", f"{cal}/events/{tid}", body)
                if status == 404:
                    status, _ = self.google.call(uid, rt, "POST", f"{cal}/events", body)
            else:
                status, _ = self.google.call(uid, rt, "POST", f"{cal}/events", body)
                if status == 409:                                  # a deleted event keeps its id: bring it back
                    status, _ = self.google.call(uid, rt, "PUT", f"{cal}/events/{tid}", body)
            if status == 404 and not pushed.get(tid):
                raise OutboundError("not_found", "Google cannot find Enveliq's calendar. Connect Google Calendar again.")
            if status >= 400:
                raise OutboundError("error", f"Google refused an event ({status}).")
            pushed[tid] = {"sig": sig}

    # ----- Home Assistant To-do -----
    def _ha(self, td: dict[str, Any], service: str, data: dict[str, Any], response: bool = False) -> Any:
        url = f"{td['url']}/api/services/todo/{service}" + ("?return_response" if response else "")
        status, body = outbound.request("POST", url, allow=self.notifier.allow(), headers={"Authorization": "Bearer " + td["token"]}, json_body=data)
        if status in (401, 403):
            raise OutboundError("auth", "Home Assistant did not accept the access token.")
        if status == 404:
            raise OutboundError("not_found", "Home Assistant did not find that list. Check the name.")
        if status >= 400:
            raise OutboundError("error", f"Home Assistant refused the request ({status}).")
        try:
            return json.loads(body.decode("utf-8", "replace") or "null")
        except ValueError:
            return None

    def _ha_items(self, td: dict[str, Any]) -> list[dict[str, Any]]:
        data = self._ha(td, "get_items", {"entity_id": td["entity"]}, response=True)
        try:
            items = data["service_response"][td["entity"]]["items"]
        except (TypeError, KeyError):
            raise OutboundError("error", "Home Assistant did not return the list. Check the name, and that it is a to-do list.") from None
        return [i for i in items if isinstance(i, dict)]

    def test_todo(self, uid: str) -> str:
        td = self._load(uid)["todo"]
        if not td["url"]:
            raise OutboundError("not_set", "Save the details first.")
        return f"Connected. The list has {len(self._ha_items(td))} items."

    @staticmethod
    def _find(items: list[dict[str, Any]], tid: str, p: dict[str, Any]) -> dict[str, Any] | None:
        for it in items:
            if p.get("uid") and it.get("uid") == p["uid"]:
                return it
        for it in items:
            if it.get("description") == f"enveliq:{tid}":
                return it
        return None

    def _todo(self, uid: str, rec: dict[str, Any], wipe: bool) -> None:
        td = rec["todo"]
        pushed: dict[str, Any] = td["pushed"]
        titles = rec["titles"]
        book = {t["id"]: t for t in self.tasks.snapshot(uid)}
        items = self._ha_items(td)
        ent = td["entity"]
        for tid in list(pushed):
            t, p = book.get(tid), pushed[tid]
            if wipe or t is None or t["state"] == "removed":
                found = self._find(items, tid, p)
                if found is not None:
                    self._ha(td, "remove_item", {"entity_id": ent, "item": [found.get("uid") or found.get("summary")]})
                pushed.pop(tid, None)
        if wipe:
            return
        for tid, t in book.items():
            p = pushed.get(tid)
            summary = t["title"] if titles else GENERIC
            sig = _hash(f"{t['due']}|{summary}")[:16]
            if t["state"] == "open":
                if p is None or p.get("status") == "dismissed" and p.get("sig") != sig:
                    self._ha_add(td, items, tid, t, summary, pushed, sig)
                    continue
                if p.get("status") == "dismissed":
                    continue
                found = self._find(items, tid, p)
                if found is None:                      # the person deleted it in Home Assistant: leave it deleted
                    p["status"] = "dismissed"
                    continue
                if found.get("status") == "completed" and p["status"] == "needs_action":   # ticked in Home Assistant
                    try:
                        self.tasks.act(uid, tid, "done")
                    except KeyError:
                        pass
                    p["status"] = "completed"
                    continue
                key = found.get("uid") or found.get("summary")
                if p["status"] == "completed":                                              # reopened in Enveliq
                    self._ha(td, "update_item", {"entity_id": ent, "item": key, "status": "needs_action", "due_date": t["due"], "rename": summary})
                    p.update(status="needs_action", sig=sig)
                elif p.get("sig") != sig:
                    self._ha(td, "update_item", {"entity_id": ent, "item": key, "rename": summary, "due_date": t["due"]})
                    p["sig"] = sig
            elif p and p.get("status") == "needs_action":                                  # done, replied, handled or gone
                found = self._find(items, tid, p)
                if found is not None and found.get("status") != "completed":
                    self._ha(td, "update_item", {"entity_id": ent, "item": found.get("uid") or found.get("summary"), "status": "completed"})
                p["status"] = "completed"
        for tid in [k for k, p in pushed.items() if k not in book]:
            pushed.pop(tid, None)

    def _ha_add(self, td: dict[str, Any], items: list[dict[str, Any]], tid: str, t: dict[str, Any], summary: str, pushed: dict[str, Any], sig: str) -> None:
        ent = td["entity"]
        data = {"entity_id": ent, "item": summary, "due_date": t["due"], "description": f"enveliq:{tid}"}
        try:
            self._ha(td, "add_item", data)
        except OutboundError:
            data.pop("due_date"), data.pop("description")        # a plain shopping-style list takes only the text
            self._ha(td, "add_item", data)
        mine = {i.get("uid") for i in items}
        after = self._ha_items(td)
        found = next((i for i in after if i.get("description") == f"enveliq:{tid}"), None) or next(
            (i for i in after if i.get("summary") == summary and i.get("status") != "completed" and i.get("uid") not in mine), None)
        pushed[tid] = {"uid": found.get("uid") if found else None, "status": "needs_action", "sig": sig}
        items[:] = after

    # ---------- the loop ----------
    def tick(self, full: bool = False) -> None:
        if not self.vault.is_unlocked():
            return
        with self.vault.passive():
            with self._lock:
                dirty, self._dirty = self._dirty, set()
            now = self.clock()
            users = [u["id"] for u in self.vault.list_users() if not u.get("disabled")]
            for uid in users:
                rec = self._load(uid)
                if not (rec["caldav"]["enabled"] or rec["todo"]["enabled"] or rec["google"]["enabled"]):
                    continue
                if uid not in dirty and now - self._last_full.get(uid, 0) < 300:
                    continue
                self._last_full[uid] = now
                try:
                    self.tasks.reconcile(uid)
                    self.sync_now(uid)
                except Exception:
                    log.info("a calendar or To-do sync failed")

    def start(self) -> None:
        if self._thread:
            return
        self._thread = threading.Thread(target=self._run_loop, name="enveliq-sync", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()

    def _run_loop(self) -> None:
        while not self._stop.is_set():
            self._wake.wait(30)
            self._wake.clear()
            if self._stop.is_set():
                break
            try:
                self.tick()
            except Exception:
                log.warning("sync pass failed")
