"""The daily summary: email that can wait is held out of the inbox and gathered in the summary; urgent mail alerts at once."""
from __future__ import annotations

import json
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from backend.mail.digest import DigestBook, HOLD_DAYS
from backend.mail.llm import parse_reply
from backend.mail.mail_alerts import MailAlerts

SYD = ZoneInfo("Australia/Sydney")


def at(day, hour, minute=0):
    return datetime(2026, 10, day, hour, minute, tzinfo=SYD).timestamp()


class Vault:
    def __init__(self, messages):
        self.g = {}
        self.messages = messages

    def get_global(self, k):
        return self.g.get(k)

    def set_global(self, k, v):
        self.g[k] = v

    def list_accounts(self):
        return [{"id": "a1", "owner_user_id": "u1"}, {"id": "a2", "owner_user_id": "u2"}]

    def list_messages(self, account_id):
        return self.messages.get(account_id, [])


class Notifier:
    def __init__(self, **s):
        self.s = {"digest_inbox": True, "morning_time": "08:00", "mail_on": True, "mail_details": False, "quiet_on": False,
                  "quiet_from": "21:00", "quiet_to": "07:00"} | s
        self.sent = []
        self.channels = True

    def settings(self, uid):
        return self.s

    def has_any(self, uid):
        return self.channels

    def send_all(self, uid, note):
        self.sent.append(note)
        return {"ntfy": None}


class Tasks:
    def __init__(self, due=()):
        self.due = list(due)

    def timezone_of(self, uid):
        return "Australia/Sydney"

    def open_tasks(self, uid):
        return [{"account_id": a, "message_id": m, "due": d} for a, m, d in self.due]


class Important:
    def contains(self, uid, address):
        return address == "boss@example.invalid"


def msg(i, *, when, act=False, summary="A short AI summary.", category="Other", state="unread", sender="s", **extra):
    return {"id": f"m{i}", "subject": f"Subject {i}", "sender_display": f"Sender {i}", "sender_address": f"{sender}{i}@example.invalid", "summary": summary,
            "category": category, "state": state, "received_at": when, "act_today": act, **extra}


def make(messages, notifier=None, tasks=None, now=at(21, 9)):
    vault = Vault({"a1": messages, "a2": [msg(99, when=at(21, 6), summary="Someone else's mail")]})
    notifier = notifier or Notifier()
    clock = {"t": now}
    alerts = MailAlerts(notifier, "", lambda uid: "Australia/Sydney", clock=lambda: clock["t"])
    book = DigestBook(vault, notifier, tasks or Tasks(), alerts, Important(), "https://mail.example.com", clock=lambda: clock["t"])

    def write(account_id, message_id, **change):
        for m in vault.messages[account_id]:
            if m["id"] == message_id:
                m.update(change)
    book.write = write
    book.clock_box = clock
    return book, vault, notifier


def by_id(vault, i):
    return next(m for m in vault.messages["a1"] if m["id"] == f"m{i}")


# ---- the AI's judgement ----
def test_the_ai_reply_carries_act_today_and_a_reason_only_when_true():
    out = parse_reply(json.dumps({"summary": "Pay by Friday", "act_today": True, "today_reason": "Payment is due tomorrow"}))
    assert out["act_today"] is True and out["today_reason"] == "Payment is due tomorrow"
    out = parse_reply(json.dumps({"summary": "Sale", "act_today": False, "today_reason": "ignore me"}))
    assert out["act_today"] is False and out["today_reason"] is None
    assert parse_reply(json.dumps({"summary": "Old style reply"}))["act_today"] is False


# ---- urgent mail alerts, the rest is held and is not announced one by one ----
def test_with_the_switch_on_only_urgent_mail_and_important_people_alert_at_once():
    n = Notifier()
    a = MailAlerts(n, "", lambda uid: "Australia/Sydney", clock=lambda: at(21, 12), important=Important())
    calm = {"account_id": "a1", "id": "m1", "sender_display": "Shop", "subject": "Sale", "priority": "normal"}
    assert a.send("u1", [calm]) == 0 and n.sent == []
    assert a.send("u1", [calm, {**calm, "id": "m2", "act_today": True}]) == 1 and n.sent[-1]["path"].endswith("m2")


def test_with_the_switch_off_nothing_changes():
    n = Notifier(digest_inbox=False)
    a = MailAlerts(n, "", lambda uid: "Australia/Sydney", clock=lambda: at(21, 12))
    assert a.send("u1", [{"account_id": "a1", "id": "m1", "sender_display": "Shop", "subject": "Sale", "priority": "normal"}]) == 1


# ---- holding ----
def test_the_first_pass_leaves_what_is_already_in_the_inbox_alone():
    book, vault, _ = make([msg(1, when=at(21, 6))])
    assert book.hold_pass("u1") == 0 and not by_id(vault, 1).get("held_for_summary")


def test_new_mail_that_can_wait_is_held_urgent_and_important_mail_is_not():
    book, vault, _ = make([msg(1, when=at(21, 6))])
    book.hold_pass("u1")
    vault.messages["a1"] += [msg(2, when=at(21, 8)), msg(3, when=at(21, 8), act=True), msg(4, when=at(21, 8), sender="boss"), msg(5, when=at(21, 8), summary="Not summarised yet.")]
    vault.messages["a1"][-2]["sender_address"] = "boss@example.invalid"
    assert book.hold_pass("u1") == 1
    held = [m["id"] for m in vault.messages["a1"] if m.get("held_for_summary")]
    assert held == ["m2"]                                            # m3 is urgent, m4 is an important person, m5 is not read by the AI yet
    assert book.hold_pass("u1") == 0                                 # nothing is held twice, and m5 is not held when it is read later than its first look
    assert [m["id"] for m in vault.messages["a2"] if m.get("held_for_summary")] == []     # someone else's mail is never touched


def test_the_summary_is_the_held_list_newest_first_and_knows_when_it_is_unseen():
    book, vault, _ = make([msg(1, when=at(21, 6))])
    book.hold_pass("u1")
    vault.messages["a1"] += [msg(2, when=at(21, 8), category="Shopping"), msg(3, when=at(21, 8, 30))]
    book.clock_box["t"] = at(21, 8, 40)
    book.hold_pass("u1")
    v = book.view("u1")
    assert v["enabled"] and v["count"] == 2 and v["unread"] is True and sorted(i["message_id"] for i in v["items"]) == ["m2", "m3"]
    book.clock_box["t"] = at(21, 9)
    book.mark_seen("u1")
    assert book.view("u1")["unread"] is False
    book.clock_box["t"] = at(21, 9, 30)
    vault.messages["a1"].append(msg(4, when=at(21, 9, 25)))
    book.hold_pass("u1")
    assert book.view("u1")["unread"] is True


def test_each_item_says_how_many_files_the_email_has():
    book, vault, _ = make([msg(1, when=at(21, 6))])
    book.hold_pass("u1")
    vault.messages["a1"] += [msg(2, when=at(21, 8), attachment_count=3, has_attachments=True), msg(3, when=at(21, 8, 10), has_attachments=True), msg(4, when=at(21, 8, 20))]
    book.clock_box["t"] = at(21, 8, 40)
    book.hold_pass("u1")
    counts = {i["message_id"]: i["attachments"] for i in book.view("u1")["items"]}
    assert counts == {"m2": 3, "m3": 1, "m4": 0}


def test_handling_an_email_anywhere_takes_it_out_of_the_summary():
    book, vault, _ = make([msg(1, when=at(21, 6))])
    book.hold_pass("u1")
    vault.messages["a1"].append(msg(2, when=at(21, 8)))
    book.hold_pass("u1")
    by_id(vault, 2)["state"] = "reviewed"
    assert book.view("u1")["count"] == 0
    book.hold_pass("u1")
    assert not by_id(vault, 2).get("held_for_summary")


# ---- letting go ----
def test_take_one_out_or_finish_the_summary_and_the_rest_go_back_unchanged():
    book, vault, _ = make([msg(1, when=at(21, 6))])
    book.hold_pass("u1")
    vault.messages["a1"] += [msg(2, when=at(21, 8)), msg(3, when=at(21, 8))]
    book.hold_pass("u1")
    assert book.release("u1", only=("a1", "m2")) == 1
    assert [m["id"] for m in vault.messages["a1"] if m.get("held_for_summary")] == ["m3"]
    assert by_id(vault, 2)["state"] == "unread" and by_id(vault, 2)["summary"] == "A short AI summary."
    assert book.release("u1") == 1 and book.view("u1")["count"] == 0
    assert book.release("u1") == 0


def test_held_for_seven_days_goes_back_in_the_inbox_by_itself():
    book, vault, _ = make([msg(1, when=at(21, 6))])
    book.hold_pass("u1")
    vault.messages["a1"].append(msg(2, when=at(21, 8)))
    book.hold_pass("u1")
    book.clock_box["t"] = at(21, 9) + HOLD_DAYS * 86400 + 60
    book.hold_pass("u1")
    assert not by_id(vault, 2).get("held_for_summary")


def test_switching_it_off_puts_everything_back():
    n = Notifier()
    book, vault, _ = make([msg(1, when=at(21, 6))], notifier=n)
    book.tick("u1")
    vault.messages["a1"].append(msg(2, when=at(21, 8)))
    book.tick("u1")
    assert by_id(vault, 2).get("held_for_summary") is True
    n.s["digest_inbox"] = False
    book.tick("u1")
    assert not by_id(vault, 2).get("held_for_summary")


def test_it_is_private():
    book, vault, _ = make([msg(1, when=at(21, 6))])
    book.hold_pass("u1")
    vault.messages["a2"].append(msg(7, when=at(21, 8)))
    book.hold_pass("u1")
    assert book.view("u2")["count"] == 0
    assert not any(m.get("held_for_summary") for m in vault.messages["a2"])
    book.forget_user("u1")
    assert book._raw("u1") == {}


# ---- a second look ----
def test_a_deadline_that_arrives_brings_held_mail_back_and_alerts_once():
    book, vault, notifier = make([msg(1, when=at(20, 15))], tasks=Tasks(due=[("a1", "m1", "2026-10-21")]))
    book.hold_pass("u1")
    by_id(vault, 1).update(held_for_summary=True, held_at=at(21, 7))
    assert book.reassess("u1") == 1 and len(notifier.sent) == 1
    assert not by_id(vault, 1).get("held_for_summary")
    assert book.reassess("u1") == 0 and len(notifier.sent) == 1
    later, _, n2 = make([msg(1, when=at(20, 15))], tasks=Tasks(due=[("a1", "m1", "2026-10-25")]))
    assert later.reassess("u1") == 0 and n2.sent == []


# ---- the one daily alert ----
def test_one_alert_a_day_at_the_chosen_time_says_how_many_are_waiting():
    book, vault, notifier = make([msg(1, when=at(21, 6))], now=at(21, 7, 30))
    book.hold_pass("u1")
    vault.messages["a1"] += [msg(2, when=at(21, 7)), msg(3, when=at(21, 7))]
    book.hold_pass("u1")
    assert book.daily_alert("u1") is False and notifier.sent == []   # before the daily summary time
    book.clock_box["t"] = at(21, 8, 5)
    assert book.daily_alert("u1") is True
    note = notifier.sent[0]
    assert "2 emails" in note["body"] and note["url"] == "https://mail.example.com/?summary=1" and "Sender" not in note["body"]
    assert book.daily_alert("u1") is False and len(notifier.sent) == 1
    book.clock_box["t"] = at(22, 8, 5)
    assert book.daily_alert("u1") is True and len(notifier.sent) == 2        # the next day's alert, for what is still waiting


def test_no_alert_when_nothing_is_waiting_or_in_quiet_hours_or_without_a_channel():
    book, vault, notifier = make([msg(1, when=at(21, 6))], now=at(21, 9))
    book.hold_pass("u1")
    assert book.daily_alert("u1") is False and notifier.sent == []
    vault.messages["a1"].append(msg(2, when=at(21, 8)))
    book.hold_pass("u1")
    quiet = Notifier(quiet_on=True, quiet_from="08:00", quiet_to="10:00")
    b2, v2, _ = make([msg(1, when=at(21, 6))], notifier=quiet, now=at(21, 9))
    b2.hold_pass("u1")
    v2.messages["a1"].append(msg(2, when=at(21, 8)))
    b2.hold_pass("u1")
    assert b2.daily_alert("u1") is False and quiet.sent == []        # waits for quiet hours to end
    b2.clock_box["t"] = at(21, 10, 5)
    assert b2.daily_alert("u1") is True
    none = Notifier()
    none.channels = False
    b3, v3, _ = make([msg(1, when=at(21, 6))], notifier=none)
    b3.hold_pass("u1")
    v3.messages["a1"].append(msg(2, when=at(21, 8)))
    b3.hold_pass("u1")
    assert b3.daily_alert("u1") is False and none.sent == []


# ---- through the real app ----
import pytest                                                                       # noqa: E402
from test_llm import FakeModel                                                      # noqa: E402
from test_summaries import start, synced                                            # noqa: E402
from helpers import create_user, sign_in                                            # noqa: E402


@pytest.fixture
def env(tmp_path):
    model = FakeModel()
    appm, client, bridge = start(tmp_path, model)
    yield appm, client, bridge
    bridge.close()
    model.close()


def test_the_routes_show_remove_and_finish_the_summary(env):
    appm, client, bridge = env
    synced(client, bridge)
    assert client.get("/api/v1/me/held-summary").json() == {"enabled": False, "count": 0, "unread": False, "items": []}
    assert client.put("/api/v1/me/notifications/settings", json={"digest_inbox": True}).json()["settings"]["digest_inbox"] is True
    assert client.put("/api/v1/me/notifications/settings", json={"digest_inbox": "yes please"}).status_code == 422
    account = next(a for a in appm.vault.list_accounts() if a.get("auth_method") in ("proton_bridge", "imap"))
    mails = [m for m in appm.vault.list_messages(account["id"]) if m.get("state", "unread") == "unread"][:2]
    assert len(mails) == 2
    for m in mails:
        appm.digestbook.write(account["id"], m["id"], held_for_summary=True, held_at=time.time())
    assert [m for m in client.get(f"/api/v1/accounts/{account['id']}/messages").json() if m.get("held_for_summary")]      # the list says which are held
    s = client.get("/api/v1/me/held-summary").json()
    assert s["enabled"] and s["count"] == 2 and s["unread"] and all({"account_id", "message_id", "summary", "subject", "category"} <= set(i) for i in s["items"])
    create_user(client, "casey")
    other = sign_in(appm, "casey")
    assert other.get("/api/v1/me/held-summary").json()["count"] == 0
    assert other.post("/api/v1/me/held-summary/remove", json={"account_id": account["id"], "message_id": mails[0]["id"]}).status_code == 404
    assert other.post("/api/v1/me/held-summary/complete").json() == {"returned": 0}
    assert client.get("/api/v1/me/held-summary").json()["count"] == 2                                  # casey changed nothing
    assert client.post("/api/v1/me/held-summary/seen").status_code == 200 and client.get("/api/v1/me/held-summary").json()["unread"] is False
    assert client.post("/api/v1/me/held-summary/remove", json={"account_id": account["id"], "message_id": mails[0]["id"]}).status_code == 200
    assert client.post("/api/v1/me/held-summary/remove", json={"account_id": account["id"], "message_id": mails[0]["id"]}).status_code == 404      # no longer held
    assert client.get("/api/v1/me/held-summary").json()["count"] == 1
    assert client.post("/api/v1/me/held-summary/complete").json() == {"returned": 1}
    assert client.get("/api/v1/me/held-summary").json()["count"] == 0
