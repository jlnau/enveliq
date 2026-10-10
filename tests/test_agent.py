"""Hermes: a plain chat with the configured AI model. It sees only what is typed, and the saved chats are private."""
from __future__ import annotations

import time

import pytest

import backend.mail.agent as agent_mod

from test_bridge import mails  # noqa: F401
from test_summaries import start
from test_llm import FakeModel
from helpers import create_user, sign_in  # noqa: F401


@pytest.fixture
def env(tmp_path):
    model = FakeModel(reply=lambda body: "Hello from the model.")
    appm, client, bridge = start(tmp_path, model)
    yield appm, client, bridge, model
    bridge.close()
    model.close()


def say(client, text, chat=None):
    r = client.post("/api/v1/me/agent/messages", json={"text": text, **({"chat": chat} if chat else {})})
    assert r.status_code == 200, r.text
    return r.json()


def test_nothing_saved_yet(env):
    _, client, _, _ = env
    r = client.get("/api/v1/me/agent")
    assert r.status_code == 200 and r.json() == {"name": "Hermes", "mode": "plain", "ready": True, "chats": [], "chat": None}
    assert "no-store" in r.headers["cache-control"]


def test_a_chat_is_saved_and_the_model_sees_the_earlier_turns(env):
    _, client, _, model = env
    out = say(client, "What is a good way to start the day?")
    assert [m["role"] for m in out["chat"]["messages"]] == ["user", "assistant"] and out["chat"]["messages"][1]["text"] == "Hello from the model."
    assert out["chat"]["title"] == "What is a good way to start the day?" and len(out["chats"]) == 1
    sent = model.requests[-1]["messages"]
    assert sent[0]["role"] == "system" and "cannot see their email" in sent[0]["content"]
    assert sent[-1] == {"role": "user", "content": "What is a good way to start the day?"}
    cid = out["chat"]["id"]
    say(client, "And after lunch?", cid)
    assert [m["content"] for m in model.requests[-1]["messages"][1:]][:2] == ["What is a good way to start the day?", "Hello from the model."]
    again = client.get("/api/v1/me/agent").json()                      # coming back later opens the latest chat
    assert again["chat"]["id"] == cid and len(again["chat"]["messages"]) == 4


def test_several_chats_are_kept_apart_and_reopened(env):
    _, client, _, model = env
    a = say(client, "First topic")["chat"]["id"]
    b = say(client, "Second topic")["chat"]["id"]                      # no chat given: a new one starts
    assert a != b and model.requests[-1]["messages"][1:] == [{"role": "user", "content": "Second topic"}]
    out = client.get("/api/v1/me/agent").json()
    assert [c["title"] for c in out["chats"]] == ["Second topic", "First topic"] and out["chat"]["id"] == b      # newest first
    old = client.get("/api/v1/me/agent", params={"chat": a}).json()
    assert old["chat"]["messages"][0]["text"] == "First topic"
    say(client, "More on the first", a)
    assert client.get("/api/v1/me/agent").json()["chats"][0]["id"] == a      # the one you just used moves to the top


def test_rename_and_delete(env):
    _, client, _, _ = env
    cid = say(client, "hello there")["chat"]["id"]
    r = client.patch(f"/api/v1/me/agent/chats/{cid}", json={"title": "  Plan   for Friday "})
    assert r.status_code == 200 and r.json()["chats"][0]["title"] == "Plan for Friday"
    assert client.patch(f"/api/v1/me/agent/chats/{cid}", json={"title": ""}).status_code == 422
    assert client.patch("/api/v1/me/agent/chats/c000000000000", json={"title": "x"}).status_code == 404
    r = client.delete(f"/api/v1/me/agent/chats/{cid}")
    assert r.status_code == 200 and r.json()["chats"] == [] and r.json()["chat"] is None
    assert client.delete(f"/api/v1/me/agent/chats/{cid}").status_code == 200          # already gone is fine
    assert client.post("/api/v1/me/agent/messages", json={"text": "hi", "chat": cid}).status_code == 404


def test_an_old_single_chat_is_carried_over(env):
    appm, client, _, _ = env
    uid = client.get("/api/v1/me").json()["id"]
    appm.vault.set_global("agent:" + uid, {"messages": [{"role": "user", "text": "from before", "at": 5}, {"role": "assistant", "text": "yes", "at": 6}]})
    out = client.get("/api/v1/me/agent").json()
    assert len(out["chats"]) == 1 and out["chat"]["title"] == "from before" and len(out["chat"]["messages"]) == 2


def test_the_chat_limit_asks_you_to_delete_one(env):
    _, client, _, _ = env
    from backend.mail import agent as A
    uid = client.get("/api/v1/me").json()["id"]
    appm = env[0]
    chats = [{"id": f"c{i:012x}", "title": f"t{i}", "at": float(i), "messages": []} for i in range(A.MAX_CHATS)]
    appm.vault.set_global("agent:" + uid, {"chats": chats})
    r = client.post("/api/v1/me/agent/messages", json={"text": "one more"})
    assert r.status_code == 409 and "Delete one" in r.json()["detail"]


def test_each_person_has_their_own_chats(env):
    appm, client, _, _ = env
    cid = say(client, "my private note")["chat"]["id"]
    create_user(client, "sam")
    other = sign_in(appm, "sam")
    assert other.get("/api/v1/me/agent").json()["chats"] == []
    assert other.get("/api/v1/me/agent", params={"chat": cid}).json()["chat"] is None      # not even by guessing the id
    assert other.post("/api/v1/me/agent/messages", json={"text": "hi", "chat": cid}).status_code == 404
    other.delete(f"/api/v1/me/agent/chats/{cid}")
    assert len(client.get("/api/v1/me/agent").json()["chats"]) == 1


def test_needs_a_session(env):
    appm, _, _, _ = env
    from fastapi.testclient import TestClient
    anon = TestClient(appm.app)
    assert anon.get("/api/v1/me/agent").status_code in (401, 403)
    assert anon.post("/api/v1/me/agent/messages", json={"text": "hi"}).status_code in (401, 403)
    assert anon.patch("/api/v1/me/agent/chats/c000000000000", json={"title": "x"}).status_code in (401, 403)
    assert anon.delete("/api/v1/me/agent/chats/c000000000000").status_code in (401, 403)


def test_bad_input_is_refused(env):
    _, client, _, model = env
    assert client.post("/api/v1/me/agent/messages", json={"text": ""}).status_code == 422
    assert client.post("/api/v1/me/agent/messages", json={"text": "x" * 2001}).status_code == 422
    assert client.post("/api/v1/me/agent/messages", json={"text": "hi", "role": "system"}).status_code == 422
    assert client.post("/api/v1/me/agent/messages", json={"text": "hi", "chat": "../../x"}).status_code == 422
    assert client.get("/api/v1/me/agent", params={"chat": "nope"}).status_code == 422
    assert model.requests == []


def test_a_down_model_keeps_what_was_typed_and_says_why(tmp_path):
    model = FakeModel(status=500, headers={})
    appm, client, bridge = start(tmp_path, model)
    try:
        r = client.post("/api/v1/me/agent/messages", json={"text": "are you there?"})
        assert r.status_code in (502, 503, 504) and r.json()["detail"]["code"] == "ai_unreachable"
        kept = client.get("/api/v1/me/agent").json()["chat"]
        assert [m["role"] for m in kept["messages"]] == ["user"]
    finally:
        bridge.close()
        model.close()


def test_no_model_set_up_says_so(tmp_path):
    appm, client, bridge = start(tmp_path, None)
    try:
        assert client.get("/api/v1/me/agent").json()["ready"] is False
        r = client.post("/api/v1/me/agent/messages", json={"text": "hi"})
        assert r.status_code == 409 and r.json()["detail"]["code"] == "ai_not_configured"
    finally:
        bridge.close()


def test_the_models_words_are_text_only(tmp_path):
    model = FakeModel(reply=lambda body: "<script>alert(1)</script>\x00ok")
    appm, client, bridge = start(tmp_path, model)
    try:
        r = client.post("/api/v1/me/agent/messages", json={"text": "hi"})
        assert r.json()["chat"]["messages"][1]["text"] == "<script>alert(1)</script>ok"      # stored as plain text; the page escapes it
    finally:
        bridge.close()
        model.close()


def test_own_mode_sends_no_enveliq_instructions(env):
    _, client, _, model = env
    say(client, "hello")
    assert model.requests[-1]["messages"][0]["role"] == "system"                       # plain chat: Enveliq's own instructions
    r = client.put("/api/v1/admin/agent", json={"mode": "own", "who": "all", "name": "Hermes"})
    assert r.status_code == 200 and r.json() == {"mode": "own", "who": "all", "name": "Hermes", "url": "", "model": "", "has_key": False}
    out = say(client, "What lights are on?")
    assert out["mode"] == "own"
    sent = model.requests[-1]["messages"]
    assert all(m["role"] != "system" for m in sent) and sent[-1] == {"role": "user", "content": "What lights are on?"}
    client.put("/api/v1/admin/agent", json={"mode": "plain", "who": "all", "name": "Robin"})
    say(client, "and now?")
    assert "You are Robin," in model.requests[-1]["messages"][0]["content"]


def test_the_administrator_can_keep_it_to_administrators(env):
    appm, client, _, _ = env
    create_user(client, "sam")
    sam = sign_in(appm, "sam")
    assert sam.get("/api/v1/me/agent").status_code == 200
    client.put("/api/v1/admin/agent", json={"mode": "own", "who": "admins", "name": "Hermes"})
    for call in (lambda: sam.get("/api/v1/me/agent"), lambda: sam.post("/api/v1/me/agent/messages", json={"text": "hi"}),
                 lambda: sam.patch("/api/v1/me/agent/chats/c000000000000", json={"title": "x"}), lambda: sam.delete("/api/v1/me/agent/chats/c000000000000")):
        assert call().status_code == 403
    assert client.get("/api/v1/me/agent").status_code == 200


def test_only_an_administrator_changes_the_settings(env):
    appm, client, _, _ = env
    create_user(client, "sam")
    sam = sign_in(appm, "sam")
    assert sam.get("/api/v1/admin/agent").status_code == 403
    assert sam.put("/api/v1/admin/agent", json={"mode": "own", "who": "all", "name": "x"}).status_code == 403
    assert client.put("/api/v1/admin/agent", json={"mode": "root", "who": "all", "name": "x"}).status_code == 422
    assert client.put("/api/v1/admin/agent", json={"mode": "own", "who": "everyone", "name": "x"}).status_code == 422
    assert client.get("/api/v1/admin/agent").json() == {"mode": "plain", "who": "all", "name": "Hermes", "url": "", "model": "", "has_key": False}      # plain chat unless chosen


def test_the_chat_can_talk_to_a_separate_agent_while_summaries_keep_the_plain_model(env):
    _, client, _, model = env
    main = FakeModel(reply=lambda body: "Your network looks fine.")
    try:
        r = client.put("/api/v1/admin/agent", json={"mode": "own", "who": "all", "name": "Hermes", "url": main.url, "model": "hermes-agent", "key": "secret-key"})
        assert r.status_code == 200 and r.json()["url"] == main.url and r.json()["model"] == "hermes-agent" and r.json()["has_key"] is True
        assert "secret-key" not in r.text and "secret-key" not in client.get("/api/v1/admin/agent").text      # the key is never shown again
        before = len(model.requests)
        out = say(client, "Is pfSense up?")
        assert out["chat"]["messages"][-1]["text"] == "Your network looks fine."
        assert len(model.requests) == before and main.requests[-1]["model"] == "hermes-agent" and main.auth[-1] == "Bearer secret-key"
        assert all(m["role"] != "system" for m in main.requests[-1]["messages"])
        # saving again without a key keeps the key; an empty address goes back to the plain model
        again = client.put("/api/v1/admin/agent", json={"mode": "own", "who": "all", "name": "Hermes"}).json()
        assert again["has_key"] is True and again["url"] == main.url
        t = client.post("/api/v1/admin/agent/test").json()
        assert t["state"] == "ok" and t["reply"] == "Your network looks fine." and client.get("/api/v1/admin/agent/test").json()["state"] == "ok"
        gone = client.put("/api/v1/admin/agent", json={"mode": "own", "who": "all", "name": "Hermes", "url": "", "model": ""}).json()
        assert gone["url"] == "" and gone["has_key"] is False
        say(client, "back to the plain one")
        assert len(model.requests) == before + 1
    finally:
        main.close()


def test_the_separate_agent_address_is_checked(env):
    _, client, _, _ = env
    bad = client.put("/api/v1/admin/agent", json={"mode": "own", "who": "all", "name": "x", "url": "https://example.com/v1/chat/completions", "model": "m"})
    assert bad.status_code == 422                                                         # not on the owner's network
    half = client.put("/api/v1/admin/agent", json={"mode": "own", "who": "all", "name": "x", "url": "http://192.168.1.5:8642/v1/chat/completions"})
    assert client.get("/api/v1/admin/agent").json()["url"] == "" and half.status_code == 422      # an address needs a model name
    assert client.post("/api/v1/admin/agent/test").status_code == 422                      # nothing saved to test


def _poll(client, chat, seconds=8.0):
    end = time.time() + seconds
    while time.time() < end:
        got = client.get("/api/v1/me/agent", params={"chat": chat}).json()["chat"]
        if not got["pending"]:
            return got
        time.sleep(0.1)
    raise AssertionError("still pending")


def test_a_slow_agent_does_not_hold_the_request_open(tmp_path, monkeypatch):
    monkeypatch.setattr(agent_mod, "WAIT_HERE", 0.2)
    def slow(body):
        time.sleep(1.0)
        return "Done, all quiet on the network."
    model = FakeModel(reply=slow)
    appm, client, bridge = start(tmp_path, model)
    try:
        out = say(client, "Check pfSense")
        chat = out["chat"]
        assert chat["pending"] is True and [m["role"] for m in chat["messages"]] == ["user"] and chat["error"] is None      # the page is told to check back
        busy = client.post("/api/v1/me/agent/messages", json={"text": "and Grafana?", "chat": chat["id"]})
        assert busy.status_code == 409                                                  # one question at a time
        done = _poll(client, chat["id"])
        assert [m["role"] for m in done["messages"]] == ["user", "assistant"] and done["messages"][1]["text"] == "Done, all quiet on the network."
        assert done["pending"] is False and done["error"] is None
        again = say(client, "Thanks", chat["id"])                                       # free again once it has answered
        assert again["chat"]["pending"] is True
        _poll(client, chat["id"])
    finally:
        bridge.close()
        model.close()


def test_a_slow_failure_is_shown_on_the_chat_and_the_message_is_kept(tmp_path, monkeypatch):
    monkeypatch.setattr(agent_mod, "WAIT_HERE", 0.2)
    def slow_empty(body):
        time.sleep(0.6)
        return ""
    model = FakeModel(reply=slow_empty)
    appm, client, bridge = start(tmp_path, model)
    try:
        chat = say(client, "Are you there?")["chat"]
        assert chat["pending"] is True
        done = _poll(client, chat["id"])
        assert done["pending"] is False and done["error"] and [m["role"] for m in done["messages"]] == ["user"]
        retry = say(client, "Hello?", chat["id"])                                        # a retry on the same chat works and clears the old error
        assert retry["chat"]["error"] is None
        _poll(client, chat["id"])
    finally:
        bridge.close()
        model.close()


def test_a_question_left_unanswered_for_too_long_is_shown_as_failed(monkeypatch):
    """After Enveliq restarts while an agent was thinking, the chat must not say "thinking" forever."""
    from backend.mail.llm import LlmConfig, Summariser

    class Vault:
        def __init__(self):
            self.d = {}
        def get_global(self, k):
            return self.d.get(k)
        def set_global(self, k, v):
            self.d[k] = v

    vault = Vault()
    agent = agent_mod.Agent(vault, Summariser(LlmConfig()))
    now = time.time()
    vault.set_global("agent:u1", {"chats": [{"id": "c000000000001", "title": "Old", "at": now, "pending": now - 10,
                                              "messages": [{"role": "user", "text": "hi", "at": now}]}]})
    assert agent.view("u1", "c000000000001")["chat"]["pending"] is True               # still within the time allowed
    vault.set_global("agent:u1", {"chats": [{"id": "c000000000001", "title": "Old", "at": now, "pending": now - agent_mod.GIVE_UP - 5,
                                              "messages": [{"role": "user", "text": "hi", "at": now}]}]})
    got = agent.view("u1", "c000000000001")["chat"]
    assert got["pending"] is False and "did not answer" in got["error"]
    with pytest.raises(agent_mod.ChatError):                                          # and a new message can be sent again
        agent.send("u1", "again", "c000999999999")
