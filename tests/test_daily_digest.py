"""The daily summary item in the inbox: the AI's "needs me today" judgement, urgent mail alerting at once, one summary a day, and privacy."""
from __future__ import annotations

import json
from datetime import datetime
from zoneinfo import ZoneInfo

from backend.mail.digest import DigestBook
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

    def settings(self, uid):
        return self.s

    def has_any(self, uid):
        return True

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


def msg(i, *, when, act=False, reason=None, summary="A short AI summary.", category="Other", state="unread", **extra):
    return {"id": f"m{i}", "subject": f"Subject {i}", "sender_display": f"Sender {i}", "sender_address": f"s{i}@example.invalid", "summary": summary,
            "category": category, "state": state, "received_at": when, "act_today": act, "today_reason": reason, **extra}


def make(messages, notifier=None, tasks=None, clock=None):
    vault = Vault({"a1": messages, "a2": [msg(99, when=at(21, 6), summary="Someone else's mail")]})
    notifier = notifier or Notifier()
    alerts = MailAlerts(notifier, "", lambda uid: "Australia/Sydney", clock=clock or (lambda: at(21, 9)))
    return DigestBook(vault, notifier, tasks or Tasks(), alerts, clock=clock or (lambda: at(21, 9))), vault, notifier


# ---- the AI's judgement ----
def test_the_ai_reply_carries_act_today_and_a_reason_only_when_true():
    out = parse_reply(json.dumps({"summary": "Pay by Friday", "act_today": True, "today_reason": "Payment is due tomorrow"}))
    assert out["act_today"] is True and out["today_reason"] == "Payment is due tomorrow"
    out = parse_reply(json.dumps({"summary": "Sale", "act_today": False, "today_reason": "ignore me"}))
    assert out["act_today"] is False and out["today_reason"] is None
    out = parse_reply(json.dumps({"summary": "Old style reply"}))
    assert out["act_today"] is False


# ---- urgent mail still alerts, the rest waits for the summary ----
def test_with_the_summary_on_urgent_mail_alerts_at_once_even_from_an_unknown_sender():
    n = Notifier()
    a = MailAlerts(n, "", lambda uid: "Australia/Sydney", clock=lambda: at(21, 12))
    calm = {"account_id": "a1", "id": "m1", "sender_display": "Shop", "subject": "Sale", "priority": "normal"}
    urgent = {**calm, "id": "m2", "act_today": True}
    assert a.send("u1", [calm]) == 0 and n.sent == []
    assert a.send("u1", [calm, urgent]) == 1 and n.sent[-1]["path"].endswith("m2")


def test_with_the_summary_off_nothing_changes():
    n = Notifier(digest_inbox=False)
    a = MailAlerts(n, "", lambda uid: "Australia/Sydney", clock=lambda: at(21, 12))
    assert a.send("u1", [{"account_id": "a1", "id": "m1", "sender_display": "Shop", "subject": "Sale", "priority": "normal"}]) == 1


# ---- the summary ----
def test_one_summary_a_day_at_the_chosen_time_with_urgent_first_and_no_alert():
    messages = [msg(1, when=at(21, 6), category="Shopping"), msg(2, when=at(21, 5), act=True, reason="Payment is due tomorrow"), msg(3, when=at(20, 20), state="reviewed")]
    book, vault, notifier = make(messages, clock=lambda: at(21, 7, 30))
    assert book.maintain("u1") is False                              # before the morning time
    book.clock = lambda: at(21, 8, 5)
    assert book.maintain("u1") is True and notifier.sent == []       # making it sends nothing
    rows = book.listing("u1")
    assert len(rows) == 1 and rows[0]["count"] == 2 and rows[0]["urgent"] == 1 and rows[0]["read"] is False
    d = book.get("u1", rows[0]["id"])
    assert [i["message_id"] for i in d["items"]] == ["m2", "m1"] and d["items"][0]["reason"] == "Payment is due tomorrow" and d["items"][0]["urgent"]
    assert book.maintain("u1") is False                              # not twice in one day
    assert len(book.listing("u1")) == 1


def test_the_summary_hides_nothing_and_marks_nothing_reviewed():
    messages = [msg(1, when=at(21, 6)), msg(2, when=at(21, 5))]
    book, vault, _ = make(messages, clock=lambda: at(21, 9))
    book.maintain("u1")
    assert [m["state"] for m in vault.messages["a1"]] == ["unread", "unread"]


def test_nothing_new_means_no_summary_and_off_means_none():
    book, _, _ = make([], clock=lambda: at(21, 9))
    assert book.maintain("u1") is False and book.listing("u1") == []
    off, _, _ = make([msg(1, when=at(21, 6))], notifier=Notifier(digest_inbox=False))
    assert off.maintain("u1") is False and off.listing("u1") == []


def test_the_next_day_only_looks_at_mail_since_the_last_summary():
    messages = [msg(1, when=at(21, 6))]
    book, vault, _ = make(messages, clock=lambda: at(21, 9))
    book.maintain("u1")
    vault.messages["a1"].append(msg(2, when=at(22, 6)))
    book.clock = lambda: at(22, 9)
    assert book.maintain("u1") is True
    newest = book.listing("u1")[0]
    assert [i["message_id"] for i in book.get("u1", newest["id"])["items"]] == ["m2"]


def test_it_is_private_and_can_be_read_deleted_and_remade():
    book, _, _ = make([msg(1, when=at(21, 6))], clock=lambda: at(21, 9))
    book.maintain("u1")
    did = book.listing("u1")[0]["id"]
    assert book.listing("u2") == [] and book.get("u2", did) is None and book.delete("u2", did) is False
    assert book.mark_read("u1", did) is True and book.listing("u1")[0]["read"] is True
    assert book.build("u1", at(21, 10), replace_today=True)["read"] is False and len(book.listing("u1")) == 1
    assert book.delete("u1", did) is True and book.listing("u1") == []
    book.maintain("u1")                                              # deleting it does not bring it back the same day
    assert book.listing("u1") == []
    book.forget_user("u1")
    assert book.listing("u1") == []


# ---- a second look at mail that could wait ----
def test_a_deadline_that_arrives_makes_waiting_mail_alert_once():
    m = msg(1, when=at(20, 15))
    tasks = Tasks(due=[("a1", "m1", "2026-10-21")])
    book, _, notifier = make([m], tasks=tasks, clock=lambda: at(21, 9))
    assert book.reassess("u1") == 1 and len(notifier.sent) == 1
    assert book.reassess("u1") == 0 and len(notifier.sent) == 1       # once only
    later = Tasks(due=[("a1", "m1", "2026-10-25")])
    book2, _, n2 = make([msg(1, when=at(20, 15))], tasks=later, clock=lambda: at(21, 9))
    assert book2.reassess("u1") == 0 and n2.sent == []               # not due yet: it waits for the summary


def test_mail_already_marked_urgent_is_not_announced_a_second_time():
    book, _, notifier = make([msg(1, when=at(20, 15), act=True)], tasks=Tasks(due=[("a1", "m1", "2026-10-21")]))
    assert book.reassess("u1") == 0 and notifier.sent == []


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


def test_the_routes_make_list_open_read_and_delete_the_summary(env):
    appm, client, bridge = env
    synced(client, bridge)
    assert client.get("/api/v1/me/digests").json() == {"enabled": False, "items": []}
    assert client.post("/api/v1/me/digests/now").status_code == 403                  # off until the person turns it on
    assert client.put("/api/v1/me/notifications/settings", json={"digest_inbox": True}).json()["settings"]["digest_inbox"] is True
    assert client.put("/api/v1/me/notifications/settings", json={"digest_inbox": "yes please"}).status_code == 422
    uid = client.get("/api/v1/me").json()["id"]
    import time
    now = time.time()
    appm.vault.set_global("digest:" + uid, {"last_day": "x", "digests": [{"id": "d-2026-10-21", "day": "2026-10-21", "created_at": now, "read": False, "items": [
        {"account_id": "a", "message_id": "m", "sender": "Sam", "subject": "Hello", "summary": "A summary.", "category": "Other", "reason": "", "urgent": False, "received_at": now}]}]})
    did = "d-2026-10-21"
    listing = client.get("/api/v1/me/digests").json()
    assert listing["enabled"] is True and listing["items"][0]["id"] == did and listing["items"][0]["read"] is False
    d = client.get(f"/api/v1/me/digests/{did}").json()
    assert d["items"] and all({"account_id", "message_id", "summary", "subject"} <= set(i) for i in d["items"])
    assert client.post(f"/api/v1/me/digests/{did}/read").status_code == 200
    assert client.get("/api/v1/me/digests").json()["items"][0]["read"] is True
    assert client.post("/api/v1/me/digests/now").status_code == 200                  # makes today's from the real mailbox (may be empty)
    create_user(client, "casey")
    other = sign_in(appm, "casey")
    assert other.get(f"/api/v1/me/digests/{did}").status_code == 404
    assert other.delete(f"/api/v1/me/digests/{did}").status_code == 404
    assert other.get("/api/v1/me/digests").json()["items"] == []
    assert client.delete(f"/api/v1/me/digests/{did}").status_code == 200
    assert client.get(f"/api/v1/me/digests/{did}").status_code == 404
