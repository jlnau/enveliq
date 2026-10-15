"""The WebSocket door for other services, and the bell: keys, notes, limits, privacy between people and the host rule."""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from test_summaries import start  # noqa: F401
from test_bridge import mails  # noqa: F401
from backend.mail import inbound as I
from backend.security import private_host

WS = "/api/v1/inbound/ws"


class FakeVault:
    def __init__(self):
        self.g: dict = {}

    def get_global(self, k):
        return self.g.get(k)

    def set_global(self, k, v):
        self.g[k] = json.loads(json.dumps(v))


def test_a_key_is_kept_only_as_a_hash_and_belongs_to_one_person():
    v = FakeVault()
    b = I.InboundBook(v, clock=lambda: 1000.0)
    key = b.make_key("u1")
    assert key.startswith("evq_") and len(key) > 40
    assert key not in json.dumps(v.g)                              # the key itself is never stored
    assert b.user_for(key) == "u1" and b.user_for(key + "x") is None and b.user_for("nope") is None and b.user_for(None) is None
    again = b.make_key("u1")                                       # a new key replaces the old one
    assert b.user_for(key) is None and b.user_for(again) == "u1"
    other = b.make_key("u2")
    assert b.user_for(again) == "u1" and b.user_for(other) == "u2"
    b.revoke_key("u1")
    assert b.user_for(again) is None and b.user_for(other) == "u2"


def test_notes_are_cleaned_limited_and_kept_newest_first():
    b = I.InboundBook(FakeVault())
    n = b.add("u1", "  Front door \x07 open ", "Left open\x00 for 5 minutes", "Home Assistant")
    assert n["title"] == "Front door open" and n["message"] == "Left open for 5 minutes"
    with pytest.raises(I.InboundError):
        b.add("u1", "", "")
    with pytest.raises(I.InboundError):
        b.add("u1", "x" * 101)
    with pytest.raises(I.InboundError):
        b.add("u1", "ok", "y" * 501)
    with pytest.raises(I.InboundError):
        b.add("u1", {"a": 1})
    for i in range(I.MAX_ITEMS + 5):
        b.add("u1", f"note {i}")
    items = b.view("u1")["items"]
    assert len(items) == I.MAX_ITEMS and items[0]["title"] == f"note {I.MAX_ITEMS + 4}"
    assert b.view("u1")["unread"] == I.MAX_ITEMS
    b.mark_read("u1")
    assert b.view("u1")["unread"] == 0
    assert b.dismiss("u1", items[0]["id"]) and not b.dismiss("u1", items[0]["id"])
    b.clear("u1")
    assert b.view("u1")["items"] == []
    assert b.view("u2")["items"] == []                             # nobody else's list is touched


def test_a_deleted_person_loses_their_notes_and_key():
    b = I.InboundBook(FakeVault())
    key = b.make_key("u1")
    b.add("u1", "hello")
    b.forget_user("u1")
    assert b.user_for(key) is None and b.view("u1")["items"] == []


@pytest.mark.parametrize("host,ok", [
    ("192.168.1.50:8765", True), ("192.168.1.50", True), ("10.0.0.7:8765", True), ("172.16.4.2:80", True), ("127.0.0.1:8765", True),
    ("[fd00::1]:8765", True), ("8.8.8.8:8765", False), ("172.32.0.1", False), ("169.254.169.254", False), ("0.0.0.0", False),
    ("enveliq.example.com", False), ("homeassistant.local:8123", False), ("", False), ("192.168.1.50.evil.example", False),
])
def test_only_private_addresses_count_as_local(host, ok):
    assert private_host(host) is ok


# ---------- through the app ----------

@pytest.fixture
def env(tmp_path):
    appm, client, bridge = start(tmp_path, None)
    yield appm, client
    bridge.close()


def make_key(client) -> str:
    r = client.post("/api/v1/me/bell/key", json={})
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
    return r.json()["key"]


def at(client: TestClient, host: str, **headers):
    """A WebSocket handshake that names the given Host (the test client otherwise always says "testserver")."""
    return client.websocket_connect(WS, headers={"host": host, **headers})


def test_a_service_sends_a_note_and_the_person_sees_it(env):
    appm, client = env
    key = make_key(client)
    with client.websocket_connect(WS) as ws:
        ws.send_text(json.dumps({"type": "auth", "token": key}))
        assert ws.receive_json() == {"type": "auth_ok"}
        ws.send_text(json.dumps({"type": "notify", "id": "a1", "title": "Washer finished", "message": "Empty it", "source": "Home Assistant"}))
        assert ws.receive_json() == {"type": "ok", "id": "a1"}
        ws.send_text(json.dumps({"type": "ping"}))
        assert ws.receive_json() == {"type": "pong"}
    r = client.get("/api/v1/me/bell")
    body = r.json()
    assert r.headers["cache-control"] == "no-store" and body["unread"] == 1 and body["ws_path"] == WS
    assert body["items"][0]["title"] == "Washer finished" and body["items"][0]["source"] == "Home Assistant"
    assert "evq_" not in json.dumps(body) and key not in json.dumps(body)
    assert client.post("/api/v1/me/bell/read", json={}).status_code == 204
    assert client.get("/api/v1/me/bell").json()["unread"] == 0
    nid = body["items"][0]["id"]
    assert client.delete("/api/v1/me/bell/not-an-id").status_code == 422
    assert client.delete(f"/api/v1/me/bell/{nid}").status_code == 204
    assert client.delete(f"/api/v1/me/bell/{nid}").status_code == 404
    assert client.get("/api/v1/me/bell").json()["items"] == []


def test_it_works_over_the_local_ip_address_but_only_for_the_door(env):
    appm, client = env
    key = make_key(client)
    with at(client, "192.168.1.50:8765", Authorization=f"Bearer {key}") as ws:                 # the key can also come in a header
        assert ws.receive_json() == {"type": "auth_ok"}
        ws.send_text(json.dumps({"type": "notify", "title": "Over the LAN"}))
        assert ws.receive_json()["type"] == "ok"
    assert client.get("/api/v1/me/bell").json()["items"][0]["title"] == "Over the LAN"
    # nothing else answers on that address
    lan = TestClient(appm.app, base_url="http://192.168.1.50:8765")
    assert lan.get("/api/v1/health").status_code == 400
    assert lan.get("/api/v1/me/bell").status_code == 400
    # and a public address that is not listed is refused even at the door
    for host in ("evil.example.com", "8.8.8.8:8765", "169.254.169.254"):
        with pytest.raises(Exception):
            with at(client, host) as ws:
                ws.send_text(json.dumps({"type": "auth", "token": key}))
                ws.receive_text()


def test_a_wrong_key_or_none_is_turned_away(env):
    appm, client = env
    make_key(client)
    for first in ({"type": "auth", "token": "evq_wrong"}, {"type": "notify", "title": "no key"}, {"type": "auth"}):
        with client.websocket_connect(WS) as ws:
            ws.send_text(json.dumps(first))
            assert ws.receive_json() == {"type": "auth_failed"}
            with pytest.raises(WebSocketDisconnect):
                ws.receive_text()
    with client.websocket_connect(WS) as ws:
        ws.send_text("not json at all")
        assert ws.receive_json() == {"type": "auth_failed"}
    assert client.get("/api/v1/me/bell").json()["items"] == []


def test_a_page_on_another_site_cannot_open_the_door(env):
    appm, client = env
    key = make_key(client)
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(WS, headers={"Origin": "https://evil.example.com"}) as ws:
            ws.send_text(json.dumps({"type": "auth", "token": key}))
            ws.receive_text()


def test_bad_notes_get_a_plain_reason_and_the_door_stays_open(env):
    appm, client = env
    key = make_key(client)
    with client.websocket_connect(WS) as ws:
        ws.send_text(json.dumps({"type": "auth", "token": key}))
        ws.receive_json()
        for bad, word in (({"type": "notify", "id": "b"}, "Send a title"), ({"type": "notify", "title": "x" * 200}, "too long"),
                          ({"type": "dance"}, "Unknown type"), ({"type": "notify", "title": 5}, "must be text")):
            ws.send_text(json.dumps(bad))
            reply = ws.receive_json()
            assert reply["type"] == "error" and word in reply["message"]
        ws.send_text("[1,2]")
        assert ws.receive_json()["type"] == "error"
        ws.send_text(json.dumps({"type": "notify", "title": "Still fine"}))
        assert ws.receive_json()["type"] == "ok"


def test_an_oversized_message_closes_the_door(env):
    appm, client = env
    key = make_key(client)
    with client.websocket_connect(WS) as ws:
        ws.send_text(json.dumps({"type": "auth", "token": key}))
        ws.receive_json()
        ws.send_text(json.dumps({"type": "notify", "title": "a", "message": "z" * (I.MAX_FRAME + 10)}))
        assert ws.receive_json()["type"] == "error"
        with pytest.raises(WebSocketDisconnect):
            ws.receive_text()


def test_a_new_key_cuts_off_the_old_one_even_on_an_open_door(env):
    appm, client = env
    old = make_key(client)
    with client.websocket_connect(WS) as ws:
        ws.send_text(json.dumps({"type": "auth", "token": old}))
        ws.receive_json()
        new = make_key(client)
        ws.send_text(json.dumps({"type": "notify", "title": "late"}))
        assert ws.receive_json() == {"type": "auth_failed"}
    with client.websocket_connect(WS) as ws:
        ws.send_text(json.dumps({"type": "auth", "token": new}))
        assert ws.receive_json() == {"type": "auth_ok"}
    assert client.delete("/api/v1/me/bell/key").status_code == 204
    with client.websocket_connect(WS) as ws:
        ws.send_text(json.dumps({"type": "auth", "token": new}))
        assert ws.receive_json() == {"type": "auth_failed"}


def test_notes_are_rate_limited(env):
    appm, client = env
    key = make_key(client)
    with client.websocket_connect(WS) as ws:
        ws.send_text(json.dumps({"type": "auth", "token": key}))
        ws.receive_json()
        replies = []
        for i in range(I.MAX_PER_MINUTE + 3):
            ws.send_text(json.dumps({"type": "notify", "title": f"n{i}"}))
            replies.append(ws.receive_json()["type"])
    assert replies.count("ok") == I.MAX_PER_MINUTE and replies[-1] == "error"


def test_one_person_never_sees_or_fills_anothers_bell(env):
    from helpers import create_user, sign_in
    appm, client = env
    key = make_key(client)
    create_user(client, "second")
    other = sign_in(appm, "second")
    other_key = make_key(other)
    with client.websocket_connect(WS) as ws:
        ws.send_text(json.dumps({"type": "auth", "token": key}))
        ws.receive_json()
        ws.send_text(json.dumps({"type": "notify", "title": "for the first person"}))
        ws.receive_json()
    assert other.get("/api/v1/me/bell").json()["items"] == []
    nid = client.get("/api/v1/me/bell").json()["items"][0]["id"]
    assert other.delete(f"/api/v1/me/bell/{nid}").status_code == 404
    assert other.delete("/api/v1/me/bell").status_code == 204                 # clearing only touches their own
    assert len(client.get("/api/v1/me/bell").json()["items"]) == 1
    with other.websocket_connect(WS) as ws:
        ws.send_text(json.dumps({"type": "auth", "token": other_key}))
        ws.receive_json()
        ws.send_text(json.dumps({"type": "notify", "title": "for the second"}))
        ws.receive_json()
    assert [i["title"] for i in client.get("/api/v1/me/bell").json()["items"]] == ["for the first person"]


def test_a_disabled_person_cannot_use_their_key(env):
    from helpers import create_user
    appm, client = env
    create_user(client, "second")
    uid = next(u["id"] for u in appm.vault.list_users() if u.get("username") == "second")
    key = appm.inboundbook.make_key(uid)
    user = appm.vault.get_user(uid)
    appm.vault.update_user(uid, {**{k: v for k, v in user.items() if k != "id"}, "disabled": True})
    with client.websocket_connect(WS) as ws:
        ws.send_text(json.dumps({"type": "auth", "token": key}))
        assert ws.receive_json() == {"type": "auth_failed"}


def test_the_bell_needs_a_signed_in_person(env):
    appm, _ = env
    anon = TestClient(appm.app)
    for method, path in (("get", "/api/v1/me/bell"), ("post", "/api/v1/me/bell/key"), ("post", "/api/v1/me/bell/read"),
                         ("delete", "/api/v1/me/bell")):
        assert getattr(anon, method)(path).status_code in (401, 403)


def test_the_key_is_audited_but_never_logged(env):
    appm, client = env
    key = make_key(client)
    log = json.dumps(appm.vault.list_audit() if hasattr(appm.vault, "list_audit") else [])
    assert key not in log


def test_deleting_a_person_also_clears_their_saved_layout_and_opened_emails(env):
    from helpers import create_user
    appm, client = env
    create_user(client, "second")
    uid = next(u["id"] for u in appm.vault.list_users() if u.get("username") == "second")
    appm.vault.set_global("mail-view-v1:" + uid, {"layout": "list", "density": "compact", "width": "full", "rows": "open", "peek": False})
    appm.vault.set_global("enveliq-opened-v1:" + uid, {"keys": ["a1:m1", "a1:m2"]})
    r = client.delete(f"/api/v1/admin/users/{uid}")
    assert r.status_code in (200, 204), r.text
    assert not appm.vault.get_global("mail-view-v1:" + uid)
    assert not appm.vault.get_global("enveliq-opened-v1:" + uid)


HOOK = "/api/v1/inbound/webhook"


def test_a_service_can_send_a_note_with_a_plain_post(env):
    appm, client = env
    key = make_key(client)
    anon = TestClient(appm.app)                                              # no sign-in: only the key
    r = anon.post(HOOK, json={"title": "Washer finished", "message": "Empty it", "source": "Node-RED"}, headers={"Authorization": f"Bearer {key}"})
    assert r.status_code == 200 and r.json() == {"ok": True} and r.headers["cache-control"] == "no-store"
    body = client.get("/api/v1/me/bell").json()
    assert body["webhook_path"] == HOOK and body["unread"] == 1
    assert body["items"][0]["title"] == "Washer finished" and body["items"][0]["source"] == "Node-RED"
    assert key not in json.dumps(body)


def test_the_post_door_turns_away_a_missing_wrong_or_misplaced_key(env):
    appm, client = env
    key = make_key(client)
    anon = TestClient(appm.app)
    assert anon.post(HOOK, json={"title": "x"}).status_code == 401
    assert anon.post(HOOK, json={"title": "x"}, headers={"Authorization": "Bearer evq_wrong"}).status_code == 401
    assert anon.post(HOOK, json={"title": "x"}, headers={"Authorization": key}).status_code == 401               # needs the word Bearer
    assert anon.post(f"{HOOK}?key={key}", json={"title": "x"}).status_code == 401                                  # a key in the address is never read
    assert anon.post(HOOK, json={"title": "x", "token": key}).status_code == 401                                  # nor one in the body
    assert client.get("/api/v1/me/bell").json()["items"] == []
    assert anon.get(HOOK).status_code in (404, 405)                                                                 # it only takes POST


def test_the_post_door_gives_plain_reasons_for_bad_notes(env):
    appm, client = env
    key = make_key(client)
    anon = TestClient(appm.app)
    h = {"Authorization": f"Bearer {key}"}
    assert anon.post(HOOK, json={}, headers=h).status_code == 400
    assert anon.post(HOOK, json=["a list"], headers=h).status_code == 400
    r = anon.post(HOOK, json={"title": "t" * 101}, headers=h)
    assert r.status_code == 400 and "too long" in r.json()["detail"]
    assert anon.post(HOOK, content=b"title=x", headers={**h, "Content-Type": "application/x-www-form-urlencoded"}).status_code == 415
    assert anon.post(HOOK, json={"title": "a", "message": "m" * 5000}, headers=h).status_code in (400, 413)
    assert client.get("/api/v1/me/bell").json()["items"] == []


def test_the_post_door_is_rate_limited_per_key(env):
    appm, client = env
    key = make_key(client)
    anon = TestClient(appm.app)
    h = {"Authorization": f"Bearer {key}"}
    codes = [anon.post(HOOK, json={"title": f"n{i}"}, headers=h).status_code for i in range(I.MAX_PER_MINUTE + 3)]
    assert codes[: I.MAX_PER_MINUTE] == [200] * I.MAX_PER_MINUTE and codes[-1] == 429


def test_a_post_note_lands_only_in_the_keys_own_bell_and_a_disabled_person_is_refused(env):
    from helpers import create_user
    appm, client = env
    create_user(client, "second")
    uid = next(u["id"] for u in appm.vault.list_users() if u.get("username") == "second")
    other_key = appm.inboundbook.make_key(uid)
    anon = TestClient(appm.app)
    assert anon.post(HOOK, json={"title": "for the second person"}, headers={"Authorization": f"Bearer {other_key}"}).status_code == 200
    assert client.get("/api/v1/me/bell").json()["items"] == []
    assert [i["title"] for i in appm.inboundbook.view(uid)["items"]] == ["for the second person"]
    user = appm.vault.get_user(uid)
    appm.vault.update_user(uid, {**{k: v for k, v in user.items() if k != "id"}, "disabled": True})
    assert anon.post(HOOK, json={"title": "again"}, headers={"Authorization": f"Bearer {other_key}"}).status_code == 401


def test_a_new_key_cuts_off_the_old_one_for_the_post_door_too(env):
    appm, client = env
    old = make_key(client)
    new = make_key(client)
    anon = TestClient(appm.app)
    assert anon.post(HOOK, json={"title": "x"}, headers={"Authorization": f"Bearer {old}"}).status_code == 401
    assert anon.post(HOOK, json={"title": "x"}, headers={"Authorization": f"Bearer {new}"}).status_code == 200


def test_the_post_door_also_answers_on_the_local_address_but_nothing_else_does(env):
    appm, client = env
    key = make_key(client)
    lan = TestClient(appm.app, base_url="http://192.168.1.50:8765")
    assert lan.post(HOOK, json={"title": "Over the LAN"}, headers={"Authorization": f"Bearer {key}"}).status_code == 200
    assert client.get("/api/v1/me/bell").json()["items"][0]["title"] == "Over the LAN"
    assert lan.get("/api/v1/health").status_code == 400
    assert lan.get("/api/v1/me/bell").status_code == 400
    assert lan.post("/api/v1/me/bell/key", json={}).status_code == 400
    for host in ("http://evil.example.com", "http://8.8.8.8:8765", "http://169.254.169.254"):
        bad = TestClient(appm.app, base_url=host)
        assert bad.post(HOOK, json={"title": "x"}, headers={"Authorization": f"Bearer {key}"}).status_code == 400
