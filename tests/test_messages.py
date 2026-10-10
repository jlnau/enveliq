"""Messages between people: who can open what, who is listed, what happens when someone is hidden, disabled or deleted."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from helpers import create_user, load_app, setup_admin, sign_in

API = "/api/v1/messages"
UNKNOWN = "t" + "0" * 24                      # well formed, never used


class Home:
    """An administrator (Boss) and three ordinary people (Bee, Sunny and Pip), each signed in on their own."""

    def __init__(self, tmp_path: Path):
        self.appm = load_app(tmp_path)
        self.boss, _ = setup_admin(self.appm)
        self.boss.patch("/api/v1/me/profile", json={"display_name": "Boss", "email": "boss@example.invalid", "about": "In charge"})
        self.ids: dict[str, str] = {"boss": self.boss.get("/api/v1/me").json()["id"]}
        self.who: dict[str, object] = {"boss": self.boss}
        for username, name in (("beth", "Bee"), ("sam", "Sunny"), ("pat", "Pip")):
            made = create_user(self.boss, username)
            self.boss.patch(f"/api/v1/admin/users/{made['id']}", json={"display_name": name})
            client = sign_in(self.appm, username)
            client.patch("/api/v1/me/profile", json={"email": f"{username}@example.invalid", "about": f"About {name}"})
            self.ids[username] = made["id"]
            self.who[username] = client

    def __getitem__(self, name: str):
        return self.who[name]

    def start(self, sender: str, others: list[str], text: str = "Hello") -> dict:
        r = self[sender].post(f"{API}/threads", json={"to": [self.ids[o] for o in others], "text": text})
        assert r.status_code == 201, r.text
        return r.json()


@pytest.fixture
def home(tmp_path):
    h = Home(tmp_path)
    yield h
    h.appm.vault.lock()


# ---------- 1-3: nobody outside a conversation can open it ----------

def test_a_person_outside_a_conversation_gets_the_same_not_found_as_for_an_unused_id(home):
    t = home.start("boss", ["sam"], "Private note for Sunny")
    tid = t["id"]
    missing = home["beth"].get(f"{API}/threads/{UNKNOWN}")
    assert missing.status_code == 404
    for call in (
        lambda c: c.get(f"{API}/threads/{tid}"),
        lambda c: c.post(f"{API}/threads/{tid}/messages", json={"text": "let me in"}),
        lambda c: c.post(f"{API}/threads/{tid}/read"),
        lambda c: c.put(f"{API}/threads/{tid}/mute", json={"muted": True}),
        lambda c: c.delete(f"{API}/threads/{tid}/messages/m{'0' * 16}"),
    ):
        r = call(home["beth"])
        assert r.status_code == 404 and r.json() == missing.json()
        assert "Private note" not in r.text
    # the same answer for an id that was never used
    assert home["beth"].get(f"{API}/threads/{UNKNOWN}").json() == missing.json()
    # and the conversation itself is untouched
    assert [m["text"] for m in home["sam"].get(f"{API}/threads/{tid}").json()["messages"]] == ["Private note for Sunny"]


def test_lists_unread_counts_and_people_never_include_other_peoples_conversations(home):
    home.start("boss", ["sam"], "Just for Sunny")
    assert home["beth"].get(f"{API}/threads").json() == {"threads": []}
    summary = home["beth"].get(f"{API}/summary").json()
    assert summary["unread"] == 0 and summary["latest"] == []
    assert home["sam"].get(f"{API}/summary").json()["unread"] == 1
    assert "Just for Sunny" not in json.dumps(home["beth"].get(f"{API}/people").json())


def test_an_administrator_who_is_not_in_a_conversation_cannot_open_it_or_list_it(home):
    t = home.start("beth", ["sam"], "Between Bee and Sunny")
    r = home["boss"].get(f"{API}/threads/{t['id']}")
    assert r.status_code == 404 and "Between" not in r.text
    assert home["boss"].post(f"{API}/threads/{t['id']}/messages", json={"text": "hi"}).status_code == 404
    assert home["boss"].get(f"{API}/threads").json() == {"threads": []}
    assert home["boss"].get(f"{API}/summary").json()["unread"] == 0
    for path in (f"{API}/all", f"{API}/threads/all", "/api/v1/admin/messages", "/api/v1/admin/messages/threads"):
        assert home["boss"].get(path).status_code in (404, 405, 422)


# ---------- the basics ----------

def test_a_one_to_one_conversation_is_only_ever_one_conversation(home):
    a = home.start("beth", ["sam"], "First")
    b = home.start("sam", ["beth"], "Second")
    assert a["id"] == b["id"]
    assert [m["text"] for m in b["messages"]] == ["First", "Second"]
    assert len(home["beth"].get(f"{API}/threads").json()["threads"]) == 1


def test_unread_counts_reading_muting_and_unsending(home):
    t = home.start("beth", ["sam"], "One")
    tid = t["id"]
    home["beth"].post(f"{API}/threads/{tid}/messages", json={"text": "Two"})
    s = home["sam"].get(f"{API}/summary").json()
    assert s["unread"] == 2 and s["conversations"] == 1 and s["latest"][0]["text"] == "Two" and s["latest"][0]["from"]["name"] == "Bee"
    assert home["beth"].get(f"{API}/summary").json()["unread"] == 0            # what you write, you have read
    # opening does not mark read by itself; saying so does
    assert home["sam"].get(f"{API}/threads/{tid}").json()["unread"] == 2
    assert home["sam"].post(f"{API}/threads/{tid}/read").status_code == 204
    assert home["sam"].get(f"{API}/summary").json()["unread"] == 0
    # a muted conversation is not counted
    assert home["sam"].put(f"{API}/threads/{tid}/mute", json={"muted": True}).status_code == 204
    home["beth"].post(f"{API}/threads/{tid}/messages", json={"text": "Three"})
    assert home["sam"].get(f"{API}/summary").json()["unread"] == 0
    assert home["sam"].put(f"{API}/threads/{tid}/mute", json={"muted": False}).status_code == 204
    assert home["sam"].get(f"{API}/summary").json()["unread"] == 1
    # only your own message can be unsent, and it goes for everyone
    opened = home["beth"].get(f"{API}/threads/{tid}").json()
    mine = next(m for m in opened["messages"] if m["text"] == "Two")
    assert home["sam"].delete(f"{API}/threads/{tid}/messages/{mine['id']}").status_code == 404
    assert home["beth"].delete(f"{API}/threads/{tid}/messages/{mine['id']}").status_code == 204
    after = home["sam"].get(f"{API}/threads/{tid}").json()
    gone = next(m for m in after["messages"] if m["id"] == mine["id"])
    assert gone["deleted"] is True and gone["text"] == ""
    assert "Two" not in json.dumps(after)


def test_groups_are_small_and_cannot_include_yourself_twice_or_strangers(home):
    g = home.start("boss", ["beth", "sam"], "Hello all")
    assert g["group"] is True and len(g["everyone"]) == 3
    assert "Bee" in g["title"] and "Sunny" in g["title"]
    again = home["boss"].post(f"{API}/threads", json={"to": [home.ids["beth"], home.ids["beth"], home.ids["boss"]], "text": "dup"})
    assert again.status_code == 201 and again.json()["group"] is False          # duplicates and yourself are dropped
    assert home["boss"].post(f"{API}/threads", json={"to": ["not-a-person"], "text": "x"}).status_code == 404
    assert home["boss"].post(f"{API}/threads", json={"to": [home.ids["boss"]], "text": "x"}).status_code == 422
    too_many = [home.ids["beth"]] * 8
    assert home["boss"].post(f"{API}/threads", json={"to": too_many, "text": "x"}).status_code == 422


# ---------- 4: hiding from the list ----------

def test_a_person_who_hides_is_not_listed_but_can_still_write_and_be_answered(home):
    assert home["sam"].get("/api/v1/me").json()["show_in_people"] is True
    r = home["sam"].patch("/api/v1/me/profile", json={"show_in_people": False})
    assert r.status_code == 200 and r.json()["show_in_people"] is False
    assert home["sam"].get("/api/v1/me").json()["show_in_people"] is False
    names = [p["name"] for p in home["beth"].get(f"{API}/people").json()["people"]]
    assert "Sunny" not in names and {"Boss", "Pip"} <= set(names)
    assert home["beth"].post(f"{API}/threads", json={"to": [home.ids["sam"]], "text": "hi"}).status_code == 404
    # Sunny can still write to Bee, and Bee can answer
    t = home.start("sam", ["beth"], "Hi Bee")
    assert home["beth"].post(f"{API}/threads/{t['id']}/messages", json={"text": "Hi Sunny"}).status_code == 201
    # switching back shows them again
    home["sam"].patch("/api/v1/me/profile", json={"show_in_people": True})
    assert "Sunny" in [p["name"] for p in home["beth"].get(f"{API}/people").json()["people"]]


def test_you_are_never_in_your_own_people_list(home):
    assert home.ids["beth"] not in [p["id"] for p in home["beth"].get(f"{API}/people").json()["people"]]


# ---------- 5-6: disabled and deleted people ----------

def test_a_disabled_person_cannot_send_and_cannot_be_written_to(home):
    t = home.start("beth", ["sam"], "Before")
    home.boss.patch(f"/api/v1/admin/users/{home.ids['beth']}", json={"disabled": True})
    assert home["beth"].post(f"{API}/threads/{t['id']}/messages", json={"text": "after"}).status_code in (401, 403)
    assert home["beth"].get(f"{API}/summary").status_code in (401, 403)
    assert "Bee" not in [p["name"] for p in home["sam"].get(f"{API}/people").json()["people"]]
    assert home["sam"].post(f"{API}/threads", json={"to": [home.ids["beth"]], "text": "hello?"}).status_code == 404
    refused = home["sam"].post(f"{API}/threads/{t['id']}/messages", json={"text": "still there?"})
    assert refused.status_code == 422 and "receive" in refused.json()["detail"]


def test_deleting_a_person_removes_their_messages_and_takes_them_out_of_groups(home):
    group = home.start("boss", ["beth", "sam"], "Group hello")
    home["beth"].post(f"{API}/threads/{group['id']}/messages", json={"text": "Bee was here"})
    pair = home.start("beth", ["sam"], "Bee to Sunny")
    assert home.boss.delete(f"/api/v1/admin/users/{home.ids['beth']}").status_code == 204
    g = home["sam"].get(f"{API}/threads/{group['id']}").json()
    assert [m["text"] for m in g["messages"]] == ["Group hello"]
    assert home.ids["beth"] not in [p["id"] for p in g["everyone"]] and "Bee" not in json.dumps(g)
    p = home["sam"].get(f"{API}/threads/{pair['id']}").json()
    assert p["messages"] == [] and "Bee to Sunny" not in json.dumps(p)
    assert home["sam"].post(f"{API}/threads/{pair['id']}/messages", json={"text": "hello?"}).status_code == 422
    assert home.boss.get(f"{API}/threads/{group['id']}").json()["everyone"]


# ---------- 7-8: text, length and speed ----------

def test_markup_is_kept_as_plain_text_and_control_characters_are_dropped(home):
    nasty = "<script>alert(1)</script> <img src=x onerror=alert(2)>\x00\x1b[31m ok"
    t = home.start("beth", ["sam"], nasty)
    shown = home["sam"].get(f"{API}/threads/{t['id']}")
    assert shown.headers["content-type"].startswith("application/json") and shown.headers["cache-control"] == "no-store"
    text = shown.json()["messages"][0]["text"]
    assert text.startswith("<script>alert(1)</script> <img src=x onerror=alert(2)>") and "\x00" not in text and "\x1b" not in text


def test_empty_and_over_long_messages_are_refused(home):
    t = home.start("beth", ["sam"], "Start")
    for bad in ("", "   \n  ", "x" * 2001):
        assert home["beth"].post(f"{API}/threads/{t['id']}/messages", json={"text": bad}).status_code in (422,)
        assert home["beth"].post(f"{API}/threads", json={"to": [home.ids["sam"]], "text": bad}).status_code in (422,)
    assert home["beth"].post(f"{API}/threads/{t['id']}/messages", json={"text": "y" * 2000}).status_code == 201
    assert home["beth"].post(f"{API}/threads/{t['id']}/messages", json={"text": "z", "from": home.ids["sam"]}).status_code == 422   # nobody chooses who it is from


def test_sending_too_many_too_fast_is_refused(home):
    t = home.start("beth", ["sam"], "Start")
    codes = [home["beth"].post(f"{API}/threads/{t['id']}/messages", json={"text": f"m{i}"}).status_code for i in range(40)]
    assert 429 in codes and codes.index(429) <= 30
    assert home["sam"].post(f"{API}/threads/{t['id']}/messages", json={"text": "someone else is not limited"}).status_code == 201


# ---------- 9: what other people learn about you ----------

def test_payloads_contain_no_email_address_username_or_settings_of_anyone(home):
    t = home.start("beth", ["sam", "pat"], "Hello")
    seen = [
        home["sam"].get(f"{API}/people").text, home["sam"].get(f"{API}/threads").text, home["sam"].get(f"{API}/summary").text,
        home["sam"].get(f"{API}/threads/{t['id']}").text, home["pat"].get(f"{API}/people").text,
    ]
    blob = "\n".join(seen).lower()
    for secret in ("example.invalid", "username", "email", "beth", "pat\"", "\"sam", "role", "totp", "password", "prefs", "settings", "about", "in charge"):
        assert secret not in blob, secret
    person = home["sam"].get(f"{API}/people").json()["people"][0]
    assert set(person) == {"id", "name", "avatar_v"}


# ---------- 10: the on/off switches ----------

def test_the_administrator_can_turn_messages_off_and_nothing_is_lost(home):
    t = home.start("beth", ["sam"], "Keep me")
    assert home.boss.put("/api/v1/admin/features", json={"messages": False}).status_code == 200
    assert home["sam"].get("/api/v1/me/features").json()["effective"]["messages"] is False
    for call in (
        lambda c: c.get(f"{API}/threads"), lambda c: c.get(f"{API}/people"), lambda c: c.get(f"{API}/threads/{t['id']}"),
        lambda c: c.post(f"{API}/threads", json={"to": [home.ids["beth"]], "text": "x"}),
        lambda c: c.post(f"{API}/threads/{t['id']}/messages", json={"text": "x"}),
    ):
        assert call(home["sam"]).status_code == 403
    assert home["sam"].get(f"{API}/summary").json() == {"enabled": False, "unread": 0, "latest": []}
    assert home.boss.get(f"{API}/people").status_code == 403         # the switch is for everyone, administrators included
    home.boss.put("/api/v1/admin/features", json={"messages": True})
    assert [m["text"] for m in home["sam"].get(f"{API}/threads/{t['id']}").json()["messages"]] == ["Keep me"]


def test_a_person_can_switch_messages_off_for_themselves_and_drops_out_of_the_list(home):
    assert home["pat"].put("/api/v1/me/features", json={"messages": False}).status_code == 200
    assert home["pat"].get(f"{API}/threads").status_code == 403
    assert "Pip" not in [p["name"] for p in home["beth"].get(f"{API}/people").json()["people"]]
    assert home["beth"].post(f"{API}/threads", json={"to": [home.ids["pat"]], "text": "x"}).status_code == 404


def test_the_features_page_lists_messages(home):
    flags = home.boss.get("/api/v1/admin/features").json()
    assert flags["flags"]["messages"] is True and "Messages" in flags["labels"]["messages"]


def test_you_must_be_signed_in(home):
    from fastapi.testclient import TestClient
    stranger = TestClient(home.appm.app, raise_server_exceptions=False)
    for path in ("/summary", "/people", "/threads", f"/threads/{UNKNOWN}"):
        assert stranger.get(API + path).status_code == 401


def test_malformed_ids_are_refused_before_anything_is_looked_up(home):
    assert home["beth"].get(f"{API}/threads/not-an-id").status_code == 422
    assert home["beth"].delete(f"{API}/threads/{UNKNOWN}/messages/nope").status_code == 422


def test_what_is_stored_is_encrypted_and_never_in_the_clear(home, tmp_path):
    home.start("beth", ["sam"], "A very recognisable sentence 8731")
    blob = b"".join(p.read_bytes() for p in tmp_path.rglob("*") if p.is_file())
    assert blob and b"A very recognisable sentence 8731" not in blob
