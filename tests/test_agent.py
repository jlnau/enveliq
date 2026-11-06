"""Hermes: a plain chat with the configured AI model. It sees only what is typed, and the saved chats are private."""
from __future__ import annotations

import time

import pytest

import backend.mail.agent as agent_mod

from test_bridge import mails  # noqa: F401
from test_summaries import account as make_account, start
from test_llm import FakeModel
from helpers import create_user, sign_in  # noqa: F401


@pytest.fixture
def env(tmp_path):
    model = FakeModel(reply=lambda body: "Hello from the model.")
    appm, client, bridge = start(tmp_path, model)
    yield appm, client, bridge, model
    bridge.close()
    model.close()


def asked(msg):
    """The person's own words in the last turn sent to the model (the turn also carries their Enveliq data)."""
    assert "ENVELIQ DATA" in msg["content"]
    return msg["content"].split("My question: ", 1)[1].split("\n\n(", 1)[0]


def say(client, text, chat=None):
    r = client.post("/api/v1/me/agent/messages", json={"text": text, **({"chat": chat} if chat else {})})
    assert r.status_code == 200, r.text
    return r.json()


def test_nothing_saved_yet(env):
    _, client, _, _ = env
    r = client.get("/api/v1/me/agent")
    assert r.status_code == 200 and r.json() == {"name": "Hermes", "ready": True, "chats": [], "chat": None}
    assert "no-store" in r.headers["cache-control"]


def test_a_chat_is_saved_and_the_model_sees_the_earlier_turns(env):
    _, client, _, model = env
    out = say(client, "What is a good way to start the day?")
    assert [m["role"] for m in out["chat"]["messages"]] == ["user", "assistant"] and out["chat"]["messages"][1]["text"] == "Hello from the model."
    assert out["chat"]["title"] == "What is a good way to start the day?" and len(out["chats"]) == 1
    sent = model.requests[-1]["messages"]
    assert sent[0]["role"] == "system" and "Answer only from ENVELIQ DATA" in sent[0]["content"] and "Never invent" in sent[0]["content"]
    assert sent[-1]["role"] == "user" and asked(sent[-1]) == "What is a good way to start the day?"
    cid = out["chat"]["id"]
    say(client, "And after lunch?", cid)
    assert [m["content"] for m in model.requests[-1]["messages"][1:]][:2] == ["What is a good way to start the day?", "Hello from the model."]
    again = client.get("/api/v1/me/agent").json()                      # coming back later opens the latest chat
    assert again["chat"]["id"] == cid and len(again["chat"]["messages"]) == 4


def test_several_chats_are_kept_apart_and_reopened(env):
    _, client, _, model = env
    a = say(client, "First topic")["chat"]["id"]
    b = say(client, "Second topic")["chat"]["id"]                      # no chat given: a new one starts
    assert a != b and len(model.requests[-1]["messages"]) == 2 and asked(model.requests[-1]["messages"][1]) == "Second topic"
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


def test_the_chat_always_uses_enveliqs_own_instructions_and_the_chosen_name(env):
    _, client, _, model = env
    say(client, "hello")
    assert model.requests[-1]["messages"][0]["role"] == "system"
    r = client.put("/api/v1/admin/agent", json={"who": "all", "name": "Robin"})
    assert r.status_code == 200 and r.json() == {"who": "all", "name": "Robin"}
    say(client, "and now?")
    assert "You are Robin," in model.requests[-1]["messages"][0]["content"]


def test_the_administrator_can_keep_it_to_administrators(env):
    appm, client, _, _ = env
    create_user(client, "sam")
    sam = sign_in(appm, "sam")
    assert sam.get("/api/v1/me/agent").status_code == 200
    client.put("/api/v1/admin/agent", json={"who": "admins", "name": "Hermes"})
    for call in (lambda: sam.get("/api/v1/me/agent"), lambda: sam.post("/api/v1/me/agent/messages", json={"text": "hi"}),
                 lambda: sam.patch("/api/v1/me/agent/chats/c000000000000", json={"title": "x"}), lambda: sam.delete("/api/v1/me/agent/chats/c000000000000")):
        assert call().status_code == 403
    assert client.get("/api/v1/me/agent").status_code == 200


def test_only_an_administrator_changes_the_settings(env):
    appm, client, _, _ = env
    create_user(client, "sam")
    sam = sign_in(appm, "sam")
    assert sam.get("/api/v1/admin/agent").status_code == 403
    assert sam.put("/api/v1/admin/agent", json={"who": "all", "name": "x"}).status_code == 403
    assert client.put("/api/v1/admin/agent", json={"who": "everyone", "name": "x"}).status_code == 422
    assert client.get("/api/v1/admin/agent").json() == {"who": "all", "name": "Hermes"}
    # the separate-agent choices are gone: they are refused, not quietly ignored
    for extra in ({"mode": "own"}, {"url": "http://192.168.1.5:8642/v1/chat/completions"}, {"model": "hermes-agent"}, {"key": "k"}, {"clear_key": True}):
        assert client.put("/api/v1/admin/agent", json={"who": "all", "name": "x", **extra}).status_code == 422
    assert client.post("/api/v1/admin/agent/test").status_code in (404, 405) and client.get("/api/v1/admin/agent/test").status_code in (404, 405)


def test_an_address_and_key_saved_by_an_older_version_are_forgotten(env):
    appm, client, _, model = env
    vault = appm.vault
    vault.set_global("agent_settings", {"mode": "own", "who": "admins", "name": "Old", "url": "http://192.168.1.5:8642/v1/chat/completions",
                                        "model": "hermes-agent", "key": "secret-key"})
    assert client.get("/api/v1/admin/agent").json() == {"who": "admins", "name": "Old"}
    kept = vault.get_global("agent_settings")
    assert kept == {"who": "admins", "name": "Old"} and "secret-key" not in str(kept)
    # and the chat uses the plain AI model with Enveliq's own instructions, never the old address
    client.put("/api/v1/admin/agent", json={"who": "all", "name": "Old"})
    before = len(model.requests)
    say(client, "hello")
    assert len(model.requests) == before + 1 and model.requests[-1]["messages"][0]["role"] == "system"


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


def test_the_model_is_given_the_persons_own_emails_and_the_data_is_not_saved_in_the_chat(env):
    appm, client, bridge, model = env
    aid = make_account(client, bridge, ai=False)
    for m in appm.vault.list_messages(aid):
        appm.vault.delete_message(aid, m["id"])
    appm.vault.create_message(aid, {"subject": "Your flight to Perth", "sender_display": "Example Air", "sender_address": "bookings@example.com",
                                    "summary": "Flight EX12 leaves Sydney on Thursday 12 November at 2:05 PM.", "received_at": time.time() - 3600, "state": "unread"})
    out = say(client, "Do I have any flights booked?")
    last = model.requests[-1]["messages"][-1]["content"]
    assert "Your flight to Perth" in last and "Flight EX12 leaves Sydney on Thursday 12 November at 2:05 PM." in last and "Example Air" in last
    assert last.index("ENVELIQ DATA") < last.index("Your flight to Perth") < last.index("My question: Do I have any flights booked?")
    assert [m["text"] for m in out["chat"]["messages"]][0] == "Do I have any flights booked?"          # only the question is kept in the chat
    assert "ENVELIQ DATA" not in str(client.get("/api/v1/me/agent").json())
    assert "Answer only from ENVELIQ DATA" in model.requests[-1]["messages"][0]["content"]


def test_when_the_data_cannot_be_read_the_model_is_told_so_instead_of_being_left_to_guess(env, monkeypatch):
    _, client, _, model = env
    import backend.mail.agent as agent_mod2

    def boom(*a, **k):
        raise RuntimeError("no")
    monkeypatch.setattr(agent_mod2, "build_context", boom)
    say(client, "whats the newest email")
    assert "could not read the person's data" in model.requests[-1]["messages"][-1]["content"]
