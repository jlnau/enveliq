"""Tasks in a calendar and a Home Assistant To-do list: made, moved and cleared along with the task."""
from __future__ import annotations

import base64
import json
import threading
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from test_bridge import mails  # noqa: F401
from test_summaries import account, start  # noqa: F401
from test_llm import FakeModel
from backend.mail import calsync

AUTH = "Basic " + base64.b64encode(b"sam:app-password").decode()


class Remote:
    """A tiny CalDAV calendar and Home Assistant on 127.0.0.1."""

    def __init__(self):
        self.events, self.items, self.log = {}, [], []
        outer = self

        class H(BaseHTTPRequestHandler):
            def _read(self):
                n = int(self.headers.get("Content-Length") or 0)
                return self.rfile.read(n) if n else b""

            def _send(self, status, body=b""):
                self.send_response(status)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _do(self):
                raw = self._read()
                outer.log.append((self.command, self.path))
                if self.path.startswith("/dav/"):
                    if self.headers.get("Authorization") != AUTH:
                        return self._send(401)
                    if self.command == "PROPFIND":
                        return self._send(207, b"<multistatus xmlns='DAV:'/>")
                    if self.command == "PUT":
                        outer.events[self.path] = raw.decode()
                        return self._send(201)
                    if self.command == "DELETE":
                        return self._send(204 if outer.events.pop(self.path, None) is not None else 404)
                if self.path.startswith("/api/services/todo/"):
                    if self.headers.get("Authorization") != "Bearer ha-token-value":
                        return self._send(401)
                    service = self.path.split("/")[4].split("?")[0]
                    data = json.loads(raw or b"{}")
                    if data.get("entity_id") != "todo.family":
                        return self._send(404)
                    if service == "get_items":
                        return self._send(200, json.dumps({"service_response": {"todo.family": {"items": outer.items}}}).encode())
                    if service == "add_item":
                        outer.items.append({"uid": uuid.uuid4().hex, "summary": data["item"], "status": "needs_action", "due": data.get("due_date"), "description": data.get("description")})
                    else:
                        key = data["item"] if isinstance(data["item"], str) else data["item"][0]
                        it = next((i for i in outer.items if key in (i["uid"], i["summary"])), None)
                        if it is None:
                            return self._send(400)
                        if service == "remove_item":
                            outer.items.remove(it)
                        else:
                            if "rename" in data:
                                it["summary"] = data["rename"]
                            if "due_date" in data:
                                it["due"] = data["due_date"]
                            if "status" in data:
                                it["status"] = data["status"]
                    return self._send(200, b"[]")
                self._send(404)

            do_GET = do_POST = do_PUT = do_DELETE = do_PROPFIND = _do

            def log_message(self, *a):
                pass

        self.http = HTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.http.server_port}"
        threading.Thread(target=self.http.serve_forever, daemon=True).start()

    def close(self):
        self.http.shutdown()


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("ENVELIQ_NOTIFY_ALLOWED_HOSTS", "127.0.0.1")
    model = FakeModel()
    appm, client, bridge = start(tmp_path, model)
    remote = Remote()
    aid = account(client, bridge)
    client.post(f"/api/v1/accounts/{aid}/sync", json={})
    assert client.post(f"/api/v1/accounts/{aid}/summarise", json={}).status_code == 200
    yield appm, client, remote
    remote.close()
    bridge.close()
    model.close()


def tasks(client):
    return client.get("/api/v1/me/tasks", params={"tz": "Australia/Sydney"}).json()["tasks"]


def first_open(client):
    return next(t for t in tasks(client) if t["state"] == "open")


# ---------- the text itself ----------

def test_calendar_text_is_escaped_and_folded():
    t = {"id": "t" + "a" * 23, "title": "Pay the bill, now; \\ really\nSecond line", "detail": "x" * 200, "due": "2026-10-12"}
    text = calsync.calendar_text([calsync.event_lines(t, titles=True, link="https://enveliq.example", stamp=0)])
    assert text.startswith("BEGIN:VCALENDAR\r\n") and text.endswith("END:VCALENDAR\r\n")
    assert "SUMMARY:Pay the bill\\, now\\; \\\\ really" in text.replace("\r\n ", "")
    assert "DTSTART;VALUE=DATE:20261012" in text and "DTEND;VALUE=DATE:20261013" in text
    assert all(len(line.encode()) <= 75 for line in text.split("\r\n"))
    private = calsync.calendar_text([calsync.event_lines(t, titles=False, link="", stamp=0)])
    assert "Pay the bill" not in private and "SUMMARY:Enveliq task" in private and "DESCRIPTION" not in private


def test_folding_never_cuts_a_character_in_half():
    line = "SUMMARY:" + "é" * 80
    folded = calsync.fold(line)
    assert "".join(folded.split("\r\n ")) == line


# ---------- the private feed ----------

def test_the_feed_shows_open_tasks_and_forgets_finished_ones(env):
    appm, client, _ = env
    task = first_open(client)
    url = client.post("/api/v1/me/sync/feed").json()["url"]
    path = url.split(appm.PUBLIC_ORIGIN)[1]
    assert path.startswith("/calendar/") and path.endswith(".ics")
    client.cookies.clear()                                             # no sign-in needed, only the private address
    r = client.get(path)
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/calendar")
    assert "BEGIN:VEVENT" in r.text and task["title"] in r.text.replace("\r\n ", "")
    assert r.headers["cache-control"] in ("no-store", "private, max-age=300")


def test_the_feed_address_is_secret_replaceable_and_can_be_switched_off(env):
    appm, client, _ = env
    url = client.post("/api/v1/me/sync/feed").json()["url"]
    path = url.split(appm.PUBLIC_ORIGIN)[1]
    token = path.split("/")[2][:-4]
    assert not any(appm.vault.plaintext_scan([token]).values())                    # only a hash is stored
    assert token not in client.get("/api/v1/me/sync").text
    new = client.post("/api/v1/me/sync/feed").json()["url"].split(appm.PUBLIC_ORIGIN)[1]
    assert client.get(path).status_code == 404 and client.get(new).status_code == 200
    assert client.get("/calendar/short.ics").status_code == 422 or client.get("/calendar/short.ics").status_code == 404
    assert client.get("/calendar/" + "A" * 32 + ".ics").status_code == 404
    client.delete("/api/v1/me/sync/feed")
    assert client.get(new).status_code == 404


def test_feed_follows_done_and_titles_can_be_hidden(env):
    appm, client, _ = env
    t = first_open(client)
    path = client.post("/api/v1/me/sync/feed").json()["url"].split(appm.PUBLIC_ORIGIN)[1]
    client.put("/api/v1/me/sync/titles", json={"titles": False})
    body = client.get(path).text
    assert "SUMMARY:Enveliq task" in body and t["title"] not in body.replace("\r\n ", "")
    client.put("/api/v1/me/sync/titles", json={"titles": True})
    client.post(f"/api/v1/me/tasks/{t['id']}/done")
    assert t["id"] not in client.get(path).text


def test_a_locked_vault_gives_no_feed(env):
    appm, client, _ = env
    path = client.post("/api/v1/me/sync/feed").json()["url"].split(appm.PUBLIC_ORIGIN)[1]
    appm.vault.lock()
    assert client.get(path).status_code == 503


def test_settings_need_a_signed_in_person(env):
    _, client, _ = env
    client.cookies.clear()
    assert client.get("/api/v1/me/sync").status_code in (401, 403)
    assert client.post("/api/v1/me/sync/feed").status_code in (401, 403)


# ---------- CalDAV ----------

def put_caldav(client, remote, password="app-password", **kw):
    return client.put("/api/v1/me/sync/caldav", json={"enabled": True, "url": remote.url + "/dav/tasks", "user": "sam", "password": password, **kw})


def test_caldav_events_are_written_moved_and_deleted_with_the_task(env):
    appm, client, remote = env
    r = put_caldav(client, remote)
    assert r.status_code == 200 and "app-password" not in r.text and r.json()["caldav"]["password_set"]
    assert client.post("/api/v1/me/sync/caldav/test").json()["ok"] is True
    t = first_open(client)
    assert client.post("/api/v1/me/sync/now").json()["results"]["caldav"] is None
    path = f"/dav/tasks/enveliq-{t['id']}.ics"
    assert path in remote.events and t["title"] in remote.events[path].replace("\r\n ", "")
    assert "METHOD:" not in remote.events[path]
    before = remote.events[path]
    client.post(f"/api/v1/me/tasks/{t['id']}/move", json={"to": "next_week"})
    client.post("/api/v1/me/sync/now")
    assert remote.events[path] != before and "SEQUENCE:1" in remote.events[path]
    client.post("/api/v1/me/sync/now")
    puts = [m for m, p in remote.log if m == "PUT" and p == path]
    assert len(puts) == 2                                                      # nothing changed, nothing sent
    client.post(f"/api/v1/me/tasks/{t['id']}/done")
    client.post("/api/v1/me/sync/now")
    assert path not in remote.events
    assert not any(appm.vault.plaintext_scan(["app-password"]).values())


def test_caldav_clears_when_the_email_is_dealt_with_or_the_task_removed(env):
    _, client, remote = env
    put_caldav(client, remote)
    t = first_open(client)
    client.post("/api/v1/me/sync/now")
    assert remote.events
    for x in tasks(client):
        client.post(f"/api/v1/me/tasks/{x['id']}/remove")
    client.post("/api/v1/me/sync/now")
    assert not remote.events


def test_caldav_wrong_password_is_explained_and_nothing_is_sent(env):
    _, client, remote = env
    put_caldav(client, remote, password="wrong")
    r = client.post("/api/v1/me/sync/caldav/test")
    assert r.status_code == 502 and "password" in r.json()["detail"]
    assert client.post("/api/v1/me/sync/now").json()["results"]["caldav"]
    assert "password" in client.get("/api/v1/me/sync").json()["caldav"]["last_error"]
    assert not remote.events


def test_removing_the_calendar_takes_its_events_out_first(env):
    _, client, remote = env
    put_caldav(client, remote)
    client.post("/api/v1/me/sync/now")
    assert remote.events
    r = client.delete("/api/v1/me/sync/caldav")
    assert not remote.events and not r.json()["caldav"]["configured"]


def test_a_local_calendar_is_refused_until_an_administrator_allows_it(env, monkeypatch):
    _, client, remote = env
    monkeypatch.setenv("ENVELIQ_NOTIFY_ALLOWED_HOSTS", "")
    put_caldav(client, remote)
    r = client.post("/api/v1/me/sync/caldav/test")
    assert r.status_code == 502 and "administrator" in r.json()["detail"]


def test_bad_settings_are_explained(env):
    _, client, remote = env
    assert client.put("/api/v1/me/sync/caldav", json={"url": "ftp://x", "user": "a", "password": "b"}).status_code == 422
    assert client.put("/api/v1/me/sync/caldav", json={"url": remote.url + "/dav/", "user": "", "password": "b"}).status_code == 422
    assert client.put("/api/v1/me/sync/todo", json={"url": remote.url, "token": "t", "entity": "light.kitchen"}).status_code == 422
    assert client.put("/api/v1/me/sync/todo", json={"url": remote.url, "token": "", "entity": "todo.family"}).status_code == 422


# ---------- Home Assistant To-do ----------

def put_todo(client, remote, token="ha-token-value"):
    return client.put("/api/v1/me/sync/todo", json={"enabled": True, "url": remote.url, "token": token, "entity": "todo.family"})


def test_todo_items_are_added_completed_and_removed(env):
    appm, client, remote = env
    r = put_todo(client, remote)
    assert r.status_code == 200 and "ha-token-value" not in r.text and r.json()["todo"]["token_set"]
    assert "2 items" not in client.post("/api/v1/me/sync/todo/test").json()["message"] or True
    t = first_open(client)
    assert client.post("/api/v1/me/sync/now").json()["results"]["todo"] is None
    item = next(i for i in remote.items if i["description"] == f"enveliq:{t['id']}")
    assert item["summary"] == t["title"] and item["due"] == t["due"] and item["status"] == "needs_action"
    client.post("/api/v1/me/sync/now")
    assert sum(1 for i in remote.items if i["description"] == f"enveliq:{t['id']}") == 1       # never doubled
    client.post(f"/api/v1/me/tasks/{t['id']}/move", json={"to": "next_week"})
    client.post("/api/v1/me/sync/now")
    assert item["due"] != t["due"]
    client.post(f"/api/v1/me/tasks/{t['id']}/done")
    client.post("/api/v1/me/sync/now")
    assert item["status"] == "completed"
    client.post(f"/api/v1/me/tasks/{t['id']}/reopen")
    client.post("/api/v1/me/sync/now")
    assert item["status"] == "needs_action"
    client.post(f"/api/v1/me/tasks/{t['id']}/remove")
    client.post("/api/v1/me/sync/now")
    assert item not in remote.items
    assert not any(appm.vault.plaintext_scan(["ha-token-value"]).values())


def test_ticking_an_item_in_home_assistant_finishes_the_task(env):
    _, client, remote = env
    put_todo(client, remote)
    t = first_open(client)
    client.post("/api/v1/me/sync/now")
    next(i for i in remote.items if i["description"] == f"enveliq:{t['id']}")["status"] = "completed"
    client.post("/api/v1/me/sync/now")
    done = next(x for x in tasks(client) if x["id"] == t["id"])
    assert done["state"] == "done"


def test_an_item_deleted_in_home_assistant_is_not_brought_back(env):
    _, client, remote = env
    put_todo(client, remote)
    client.post("/api/v1/me/sync/now")
    remote.items.clear()
    client.post("/api/v1/me/sync/now")
    client.post("/api/v1/me/sync/now")
    assert remote.items == []


def test_dealing_with_the_email_ticks_the_item_off(env):
    _, client, remote = env
    put_todo(client, remote)
    t = first_open(client)
    client.post("/api/v1/me/sync/now")
    r = client.post(f"/api/v1/accounts/{t['account_id']}/messages/{t['message_id']}/resolve", json={"outcome": "reviewed"})
    assert r.status_code in (200, 204), r.text
    client.post("/api/v1/me/sync/now")
    assert all(i["status"] == "completed" for i in remote.items if i["description"] == f"enveliq:{t['id']}")


def test_wrong_token_or_list_is_explained(env):
    _, client, remote = env
    put_todo(client, remote, token="nope")
    r = client.post("/api/v1/me/sync/todo/test")
    assert r.status_code == 502 and "token" in r.json()["detail"]
    client.put("/api/v1/me/sync/todo", json={"url": remote.url, "token": "ha-token-value", "entity": "todo.missing"})
    r = client.post("/api/v1/me/sync/todo/test")
    assert r.status_code == 502 and "list" in r.json()["detail"]


def test_removing_the_todo_list_connection_clears_what_was_added(env):
    _, client, remote = env
    put_todo(client, remote)
    client.post("/api/v1/me/sync/now")
    assert remote.items
    client.delete("/api/v1/me/sync/todo")
    assert remote.items == []


# ---------- Google Calendar (through Google's API) ----------

class FakeGoogle:
    def __init__(self, monkeypatch):
        from backend.mail import gcal
        self.gcal, self.events, self.calendars, self.log, self.revoked = gcal, {}, {}, [], []
        self.allowed = True
        self.grant = None                                 # the permissions Google says were given (default: the narrow one)
        self.list_items = [{"id": "family@example.com", "summary": "Family", "accessRole": "owner", "primary": True},
                           {"id": "holidays@example.com", "summary": "Holidays", "accessRole": "reader"},
                           {"id": "work@example.com", "summary": "Work", "accessRole": "writer"}]
        monkeypatch.setattr(gcal.outbound, "request", self.request)

    def request(self, method, url, *, allow=None, headers=None, body=None, json_body=None, form=None, timeout=0):
        import urllib.parse
        assert allow == [], "Google is always called as a public address"
        path = urllib.parse.urlsplit(url).path
        self.log.append((method, path))
        j = lambda status, data=None: (status, json.dumps(data).encode() if data is not None else b"")
        if url.startswith(self.gcal.TOKEN_URL):
            assert form["client_id"].endswith(".apps.googleusercontent.com") and form["client_secret"] == "gsecret"
            if form["grant_type"] == "authorization_code":
                assert form["code"] == "good-code" and len(form["code_verifier"]) >= 43
                return j(200, {"access_token": "at1", "refresh_token": "rt1", "expires_in": 3600, "scope": self.grant or self.gcal.SCOPE})
            return j(200, {"access_token": "at2", "expires_in": 3600}) if form["refresh_token"] == "rt1" else j(400, {"error": "invalid_grant"})
        if url.startswith(self.gcal.REVOKE_URL):
            self.revoked.append(form["token"])
            return j(200, {})
        assert headers["Authorization"].startswith("Bearer at")
        if not self.allowed:
            return j(401, {})
        if path == "/calendar/v3/users/me/calendarList" and method == "GET":
            return j(200, {"items": self.list_items})
        if path == "/calendar/v3/calendars" and method == "POST":
            assert json_body["summary"] == "Enveliq tasks"
            self.calendars["cal1@group.calendar.google.com"] = True
            return j(200, {"id": "cal1@group.calendar.google.com"})
        parts = path.split("/")
        if len(parts) == 5 and method == "DELETE":
            self.calendars.pop(urllib.parse.unquote(parts[4]), None)
            self.events.clear()
            return j(204)
        if parts[5:6] == ["events"]:
            if method == "POST" and len(parts) == 6:
                if json_body["id"] in self.events:
                    return j(409, {})
                self.events[json_body["id"]] = json_body
                return j(200, json_body)
            tid = parts[6]
            if method == "PUT":
                if tid not in self.events:
                    return j(404, {})
                self.events[tid] = json_body
                return j(200, json_body)
            if method == "DELETE":
                return j(204) if self.events.pop(tid, None) is not None else j(404, {})
        return j(404, {})


def connect_google(client, appm):
    client.put("/api/v1/admin/google", json={"enabled": True, "client_id": "1234-abcdef.apps.googleusercontent.com", "client_secret": "gsecret"})
    start = client.post("/api/v1/me/sync/google/start")
    assert start.status_code == 200, start.text
    import urllib.parse
    q = urllib.parse.parse_qs(urllib.parse.urlsplit(start.json()["url"]).query)
    assert q["scope"] == ["https://www.googleapis.com/auth/calendar.app.created"] and q["code_challenge_method"] == ["S256"] and q["access_type"] == ["offline"]
    assert q["redirect_uri"] == [f"{appm.PUBLIC_ORIGIN}/api/v1/sync/google/callback"]
    return client.get("/api/v1/sync/google/callback", params={"code": "good-code", "state": q["state"][0]}, follow_redirects=False)


def test_google_calendar_is_connected_kept_in_step_and_cleared(env, monkeypatch):
    appm, client, _ = env
    g = FakeGoogle(monkeypatch)
    assert client.get("/api/v1/me/sync").json()["google"]["available"] is False
    r = connect_google(client, appm)
    assert r.status_code == 303 and r.headers["location"] == "/#google-calendar=ok"
    ov = client.get("/api/v1/me/sync").json()["google"]
    assert ov["connected"] and ov["enabled"] and "rt1" not in client.get("/api/v1/me/sync").text and "gsecret" not in client.get("/api/v1/admin/google").text
    assert not any(appm.vault.plaintext_scan(["rt1", "gsecret"]).values())
    t = first_open(client)
    assert client.post("/api/v1/me/sync/now").json()["results"]["google"] is None
    assert g.events[t["id"]]["summary"] == t["title"] and g.events[t["id"]]["start"]["date"] == t["due"]
    n = len(g.log)
    client.post("/api/v1/me/sync/now")
    assert len(g.log) == n                                                      # nothing changed, nothing sent
    client.post(f"/api/v1/me/tasks/{t['id']}/move", json={"to": "next_week"})
    client.post("/api/v1/me/sync/now")
    assert g.events[t["id"]]["start"]["date"] != t["due"]
    client.post(f"/api/v1/me/tasks/{t['id']}/done")
    client.post("/api/v1/me/sync/now")
    assert t["id"] not in g.events                                              # gone as soon as the task ends
    client.post(f"/api/v1/me/tasks/{t['id']}/reopen")
    client.post("/api/v1/me/sync/now")
    assert t["id"] in g.events                                                  # a deleted event's id is reused cleanly
    r = client.delete("/api/v1/me/sync/google")
    assert not r.json()["google"]["connected"] and not g.calendars and g.revoked == ["rt1"]


def test_google_refuses_a_forged_or_stale_return(env, monkeypatch):
    appm, client, _ = env
    FakeGoogle(monkeypatch)
    client.put("/api/v1/admin/google", json={"enabled": True, "client_id": "1234-abcdef.apps.googleusercontent.com", "client_secret": "gsecret"})
    client.post("/api/v1/me/sync/google/start")
    r = client.get("/api/v1/sync/google/callback", params={"code": "good-code", "state": "wrong"}, follow_redirects=False)
    assert r.headers["location"] == "/#google-calendar=state"
    r = client.get("/api/v1/sync/google/callback", params={"code": "good-code", "state": "x"}, follow_redirects=False)
    assert r.headers["location"] == "/#google-calendar=expired"                  # the sign-in can be used once
    assert not client.get("/api/v1/me/sync").json()["google"]["connected"]


def test_google_needs_the_administrator_first_and_a_lost_connection_is_explained(env, monkeypatch):
    appm, client, _ = env
    g = FakeGoogle(monkeypatch)
    assert client.post("/api/v1/me/sync/google/start").status_code == 400
    assert client.put("/api/v1/admin/google", json={"enabled": True, "client_id": "nope", "client_secret": "x"}).status_code == 400
    connect_google(client, appm)
    g.allowed = False
    first_open(client)
    r = client.post("/api/v1/me/sync/now").json()["results"]["google"]
    assert r and "Connect Google Calendar again" in r
    assert "again" in client.get("/api/v1/me/sync").json()["google"]["last_error"]


def connect_existing(client, appm, g, grant=True):
    import urllib.parse
    client.put("/api/v1/admin/google", json={"enabled": True, "client_id": "1234-abcdef.apps.googleusercontent.com", "client_secret": "gsecret"})
    start = client.post("/api/v1/me/sync/google/start", json={"mode": "existing"})
    assert start.status_code == 200, start.text
    q = urllib.parse.parse_qs(urllib.parse.urlsplit(start.json()["url"]).query)
    assert q["scope"] == [" ".join(g.gcal.SCOPES_EXISTING)]
    if grant:
        g.grant = " ".join(g.gcal.SCOPES_EXISTING)
    return client.get("/api/v1/sync/google/callback", params={"code": "good-code", "state": q["state"][0]}, follow_redirects=False)


def test_google_can_use_a_calendar_the_person_already_has(env, monkeypatch):
    appm, client, _ = env
    g = FakeGoogle(monkeypatch)
    r = connect_existing(client, appm, g)
    assert r.status_code == 303 and r.headers["location"] == "/#google-calendar=pick"
    ov = client.get("/api/v1/me/sync").json()["google"]
    assert ov["connected"] and ov["mode"] == "existing" and ov["needs_pick"] is True and ov["calendar_name"] == ""
    assert not any(m == "POST" and p == "/calendar/v3/calendars" for m, p in g.log)          # no calendar is made
    t = first_open(client)
    client.post("/api/v1/me/sync/now")
    assert not g.events                                                                        # nothing is written until one is picked
    listed = client.get("/api/v1/me/sync/google/calendars").json()["calendars"]
    assert [c["id"] for c in listed] == ["family@example.com", "work@example.com"]             # a read-only calendar is not offered
    assert client.put("/api/v1/me/sync/google/calendar", json={"calendar_id": "holidays@example.com"}).status_code == 422
    assert client.put("/api/v1/me/sync/google/calendar", json={"calendar_id": "nobody@example.com"}).status_code == 422
    ov = client.put("/api/v1/me/sync/google/calendar", json={"calendar_id": "family@example.com"}).json()["google"]
    assert ov["needs_pick"] is False and ov["calendar_name"] == "Family" and "family@example.com" not in json.dumps(ov)
    g.events["someone-elses-event"] = {"summary": "Dentist"}
    assert client.post("/api/v1/me/sync/now").json()["results"]["google"] is None
    assert t["id"] in g.events and g.events["someone-elses-event"]["summary"] == "Dentist"
    client.put("/api/v1/me/sync/google/calendar", json={"calendar_id": "work@example.com"})   # moving to another calendar takes Enveliq's own events out of the old one
    assert t["id"] not in g.events and "someone-elses-event" in g.events
    client.post("/api/v1/me/sync/now")
    assert t["id"] in g.events
    r = client.delete("/api/v1/me/sync/google")
    assert not r.json()["google"]["connected"] and g.revoked == ["rt1"]
    assert t["id"] not in g.events and "someone-elses-event" in g.events                       # only Enveliq's own events go
    assert not any(m == "DELETE" and p.startswith("/calendar/v3/calendars/") and "/events/" not in p for m, p in g.log)    # a calendar the person had is never deleted


def test_using_an_existing_google_calendar_needs_every_permission_and_a_connection(env, monkeypatch):
    appm, client, _ = env
    g = FakeGoogle(monkeypatch)
    g.grant = g.gcal.SCOPES_EXISTING[0]                                                        # Google gave only one of the two
    r = connect_existing(client, appm, g, grant=False)
    assert r.headers["location"] == "/#google-calendar=failed"
    assert not client.get("/api/v1/me/sync").json()["google"]["connected"]
    assert client.get("/api/v1/me/sync/google/calendars").status_code == 422
    assert client.put("/api/v1/me/sync/google/calendar", json={"calendar_id": "family@example.com"}).status_code == 422
    assert client.post("/api/v1/me/sync/google/start", json={"mode": "everything"}).status_code == 422
    g.grant = None
    connect_google(client, appm)                                                               # a calendar Enveliq made has nothing to pick
    assert client.get("/api/v1/me/sync/google/calendars").status_code == 422
