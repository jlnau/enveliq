"""The personal writing-style guide and Quick AI Send."""
from __future__ import annotations

import pytest

import backend.mail.style as S
import backend.mail.writehelp as W
from backend.mail.errors import BridgeError
from backend.mail.style import StyleBook, own_words

from test_llm import FakeModel
from test_summaries import start, synced
from helpers import create_user, sign_in


# ---------- only the person's own words ----------

def test_quoted_lines_signatures_and_replies_are_cut_away():
    text = ("Hi Sam,\n\nThanks for sending this over. I will look at it tonight and come back to you.\n\nCheers,\nMorgan\n\n"
            "On Tue, 6 Oct 2026 at 9:00 AM, Sam <sam@example.com> wrote:\n> Here is the plan.\n> More plan.\n")
    out = own_words(text)
    assert "Thanks for sending this over" in out and "Cheers" in out
    assert "wrote" not in out and "Here is the plan" not in out


def test_a_signature_marker_and_phone_footer_end_the_sample():
    out = own_words("Sounds good to me, see you at the usual place then.\n-- \nMorgan Example\n0400 000 000\n")
    assert out == "Sounds good to me, see you at the usual place then."
    assert own_words("Yes that works for me, thank you very much.\nSent from my phone") == "Yes that works for me, thank you very much."


def test_forwards_and_forwarded_content_are_left_out():
    assert own_words("Please see below, thought you should know about this one.", "Fwd: Your invoice") == ""
    out = own_words("Please see below for the details I mentioned yesterday.\n\n---------- Forwarded message ----------\nFrom: Bank\nSubject: Offer\nBuy now buy now")
    assert "Forwarded" not in out and "Buy now" not in out and "Please see below" in out


def test_outlook_style_original_message_block_is_cut():
    out = own_words("Thanks, I have booked it for Friday afternoon as discussed.\n\n-----Original Message-----\nFrom: Dee\nSent: Monday\nTo: Morgan\nSubject: Booking\n\nCan you book?")
    assert out == "Thanks, I have booked it for Friday afternoon as discussed."


def test_links_and_addresses_are_not_kept_and_tiny_emails_are_skipped():
    out = own_words("Have a look at https://example.com/very/long/path?x=1 and write to me at me@example.com when you are ready.")
    assert "https://" not in out and "me@example.com" not in out and "[link]" in out
    assert own_words("Thanks!") == "" and own_words("") == ""


def test_a_sample_is_cut_to_the_limit():
    assert len(own_words("word " * 2000)) <= S.SAMPLE_MAX


# ---------- the record ----------

class Vault:
    def __init__(self):
        self.data = {}
        self.accounts = []

    def get_global(self, key):
        return self.data.get(key)

    def set_global(self, key, value):
        self.data[key] = value

    def list_accounts(self):
        return self.accounts


class Brain:
    enabled = True

    def __init__(self, text="- Tone: friendly and short\n- Habits: signs off with Cheers"):
        self.text, self.calls = text, []

    def chat(self, system, turns, max_tokens=700, timeout=None):
        self.calls.append((system, turns))
        return self.text


def book(samples=("I will see you on Friday as planned, thank you.",), now=1_000_000.0):
    clock = {"now": now}
    b = StyleBook(Vault(), None, clock=lambda: clock["now"])
    b.collect = lambda user: list(samples)
    return b, clock


def test_it_is_off_until_the_person_turns_it_on_and_gives_no_guide_while_off():
    b, _ = book()
    assert b.get("u1")["on"] is False and b.guide_for("u1") == ""
    b.rebuild("u1", Brain())
    assert b.guide_for("u1") == ""                      # a guide that exists is still not used while learning is off
    b.save("u1", on=True)
    assert "friendly and short" in b.guide_for("u1")


def test_rebuild_keeps_only_the_samples_and_the_guide():
    b, _ = book()
    b.save("u1", on=True)
    brain = Brain()
    st = b.rebuild("u1", brain)
    assert st["samples"] == 1 and st["generated_at"] and st["mode"] == "auto"
    raw = b.vault.data["style:u1"]
    assert set(raw) <= {"on", "guide", "mode", "generated_at", "samples", "samples_at", "error"}
    assert "untrusted data" in brain.calls[0][1][0]["content"] and "no tools" in brain.calls[0][0]


def test_editing_the_guide_switches_to_manual_and_a_rebuild_in_auto_does_not_overwrite_it():
    b, _ = book()
    b.save("u1", on=True)
    b.rebuild("u1", Brain())
    st = b.save("u1", guide="- Always write in capital letters")
    assert st["mode"] == "manual" and st["guide"].startswith("- Always")
    b.rebuild("u1", Brain("- Something else entirely, new text here"), only_if_auto=True)
    assert b.get("u1")["guide"] == "- Always write in capital letters"
    b.save("u1", mode="auto")
    assert b.get("u1")["mode"] == "auto" and not b.get("u1")["generated_at"]


def test_automatic_mode_makes_a_new_guide_once_a_week(monkeypatch):
    b, clock = book()
    b.save("u1", on=True)
    started = []
    monkeypatch.setattr(S.threading, "Thread", lambda target, **kw: type("T", (), {"start": lambda self: (started.append(1), target())})())
    brain = Brain()
    assert b.maintain("u1", brain) is True and len(started) == 1           # never made: make one
    assert b.maintain("u1", brain, now=clock["now"] + 3 * 86400) is False  # three days later: nothing
    assert b.maintain("u1", brain, now=clock["now"] + 8 * 86400) is True   # a week later: again
    b.save("u1", guide="- My own words about how I write.")
    assert b.maintain("u1", brain, now=clock["now"] + 30 * 86400) is False  # manual: never
    b.save("u1", on=False, mode="auto")
    assert b.maintain("u1", brain, now=clock["now"] + 30 * 86400) is False  # off: never


def test_a_failed_attempt_waits_a_day_and_no_samples_gives_a_plain_message():
    b, clock = book(samples=())
    b.save("u1", on=True)
    with pytest.raises(BridgeError) as err:
        b.rebuild("u1", Brain())
    assert "no sent emails" in err.value.message.lower() or "enough of your own words" in err.value.message
    assert b.get("u1")["error"]
    assert b.maintain("u1", Brain(), now=clock["now"] + 3600) is False


def test_forgetting_a_person_clears_everything():
    b, _ = book()
    b.save("u1", on=True)
    b.rebuild("u1", Brain())
    b.forget_user("u1")
    assert not b.vault.data["style:u1"] and b.guide_for("u1") == ""


# ---------- Quick AI Send: a proofread that may not change facts ----------

def test_parse_and_the_safety_check():
    assert W.parse_quick("SUBJECT:\nDinner\nBODY:\nSee you at 6.") == ("Dinner", "See you at 6.")
    with pytest.raises(BridgeError):
        W.parse_quick("Hello there")
    assert W.quick_ok("see you at 6pm on 12/10 at me@example.com", "See you at 6pm on 12/10 at me@example.com.")
    assert not W.quick_ok("see you at 6pm", "See you at 7pm.")                 # a changed number
    assert not W.quick_ok("send it to me@example.com", "Send it to you@example.com.")
    assert not W.quick_ok("see you soon", "See you soon. I am also very happy to help with anything else that you might need, please ask.")
    assert not W.quick_ok("see you soon", "")
    assert not W.quick_ok("Call me on [your number]", "Call me on.")           # a gap must stay


def test_quick_fix_returns_the_proofread_text_and_refuses_unsafe_changes():
    ok = W.quick_fix(Brain("SUBJECT:\nDinner on Friday\nBODY:\nHi Sam,\n\nSee you at 6."), "dinner on friday", "hi sam\n\nsee you at 6")
    assert ok == {"subject": "Dinner on Friday", "text": "Hi Sam,\n\nSee you at 6.", "changed": True}
    with pytest.raises(BridgeError) as err:
        W.quick_fix(Brain("SUBJECT:\n\nBODY:\nHi Sam, see you at 7."), "", "hi sam see you at 6")
    assert err.value.code == "quick_unsafe"
    with pytest.raises(BridgeError):
        W.quick_fix(Brain("SUBJECT:\nNew subject I made up\nBODY:\nhi"), "", "hi")      # a subject the person never gave
    with pytest.raises(BridgeError) as empty:
        W.quick_fix(Brain(), "x", "   ")
    assert empty.value.code == "empty_draft"


def test_the_proofread_rules_and_guide_reach_the_model_as_data():
    brain = Brain("SUBJECT:\n\nBODY:\nHello.")
    W.quick_fix(brain, "", "hello", guide="- Short and warm")
    system, turns = brain.calls[0]
    assert system.startswith(W.QUICK_RULES) and "Short and warm" in system and "no tools" in system
    assert "[EMAIL TEXT: data]" in turns[0]["content"]


def test_writing_help_uses_the_guide_too():
    system = W.system_prompt("", "- Warm and brief")
    assert "Warm and brief" in system and system.startswith(W.FIXED_RULES)


# ---------- through the app ----------

PROOFREAD = "SUBJECT:\n\nBODY:\nHi Sam, see you at 6."


@pytest.fixture
def env(tmp_path):
    model = FakeModel(reply=lambda body: PROOFREAD if "proofreader" in str(body) else "- Tone: warm and brief")
    appm, client, bridge = start(tmp_path, model)
    yield appm, client, bridge, model
    bridge.close()
    model.close()


def test_quick_ai_send_has_its_own_switch_and_never_sends(env):
    _, client, bridge, model = env
    synced(client, bridge, ai=False)
    assert client.get("/api/v1/me/write-help").json()["quick"] is False
    assert client.post("/api/v1/me/write-help/quick-fix", json={"draft": "hi sam see you at 6"}).status_code == 403
    assert client.put("/api/v1/me/write-help", json={"on": False, "quick": True}).json()["quick"] is True
    r = client.post("/api/v1/me/write-help/quick-fix", json={"draft": "hi sam see you at 6"})
    assert r.status_code == 200 and r.json()["text"] == "Hi Sam, see you at 6." and "no-store" in r.headers["cache-control"]
    assert client.put("/api/v1/me/write-help", json={"on": True}).json()["quick"] is True      # saving the other switch keeps it


def test_an_unsafe_proofread_is_a_plain_422_and_empty_drafts_are_refused(env):
    _, client, bridge, model = env
    synced(client, bridge, ai=False)
    client.put("/api/v1/me/write-help", json={"on": False, "quick": True})
    r = client.post("/api/v1/me/write-help/quick-fix", json={"draft": "hi sam see you at 9"})
    assert r.status_code == 422 and "nothing was sent" in r.json()["detail"]["message"]
    assert client.post("/api/v1/me/write-help/quick-fix", json={"draft": ""}).status_code == 422


def test_the_style_guide_settings_and_edit_flow(env):
    _, client, bridge, _ = env
    synced(client, bridge, ai=False)
    s = client.get("/api/v1/me/writing-style").json()
    assert s["available"] is True and s["on"] is False and s["guide"] == "" and s["mode"] == "auto"
    s = client.put("/api/v1/me/writing-style", json={"on": True, "guide": "- I keep it short."}).json()
    assert s["on"] is True and s["mode"] == "manual" and s["guide"] == "- I keep it short."
    assert client.put("/api/v1/me/writing-style", json={"mode": "auto"}).json()["mode"] == "auto"
    assert client.put("/api/v1/me/writing-style", json={"mode": "sometimes"}).status_code == 422


def test_nobody_else_sees_my_guide(env):
    appm, client, bridge, _ = env
    synced(client, bridge, ai=False)
    client.put("/api/v1/me/writing-style", json={"on": True, "guide": "- Private habits of mine."})
    create_user(client, "casey")
    other = sign_in(appm, "casey")
    assert other.get("/api/v1/me/writing-style").json()["guide"] == ""


def test_the_audit_log_never_holds_the_guide(env):
    appm, client, bridge, _ = env
    synced(client, bridge, ai=False)
    events = []
    real = appm.vault.audit
    appm.vault.audit = lambda payload: (events.append(payload), real(payload))[1]
    client.put("/api/v1/me/writing-style", json={"on": True, "guide": "- SECRET-STYLE-WORDS"})
    assert any(e.get("event") == "writing_style_settings" for e in events) and "SECRET-STYLE-WORDS" not in str(events)
