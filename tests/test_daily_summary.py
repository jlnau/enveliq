"""The daily summary: the morning note made fuller, counted by Enveliq from lists it already holds."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from backend.mail.mail_alerts import MailAlerts
from backend.mail.reminders import Reminders
from backend.mail.summary import DailySummary

SYD = ZoneInfo("Australia/Sydney")


class FakeVault:
    def __init__(self, accounts, messages):
        self.accounts, self.messages = accounts, messages

    def list_accounts(self):
        return self.accounts

    def list_messages(self, account_id):
        return self.messages.get(account_id, [])


class FakeWait:
    def __init__(self, due=0):
        self.due = due

    def view(self, uid):
        return {"notes": [{"due": True}] * self.due + [{"due": False}]}


class FakeShip:
    def __init__(self, shops=()):
        self.shops = shops

    def view(self, uid):
        return {"orders": [{"shop": s, "status": "out_for_delivery"} for s in self.shops] + [{"shop": "Old", "status": "out_for_delivery", "delivered_at": 5}, {"shop": "Later", "status": "shipped"}]}


class FakeSubs:
    def __init__(self, items=()):
        self.items = list(items)

    def due_nudges(self, uid, now=None):
        return self.items


class FakeTasks:
    def __init__(self, due=()):
        self.due = list(due)

    def reconcile(self, uid):
        pass

    def timezone_of(self, uid):
        return "Australia/Sydney"

    def open_tasks(self, uid):
        return self.due


class FakeNotifier:
    def __init__(self, channels=True, **settings):
        self.s = {"morning_on": True, "morning_time": "08:00", "due_on": True, "repeat_hours": 2, "repeat_max": 0, "quiet_on": True, "quiet_from": "21:00",
                  "quiet_to": "07:00", "show_titles": True, "digest_mail": False} | settings
        self.channels, self.state, self.sent = channels, {}, []

    def has_any(self, uid):
        return self.channels

    def get_state(self, uid):
        return self.state

    def set_state(self, uid, state):
        self.state = state

    def settings(self, uid):
        return self.s

    def send_all(self, uid, note):
        self.sent.append(note)
        return {"ntfy": None}


def task(title="Pay the electricity bill"):
    return {"id": "t1", "due": "2026-10-09", "title": title, "detail": "", "priority": "normal", "sender": "Power Co"}


def make(*, wait=0, shops=(), subs=(), tasks=(), unread=(), **settings):
    vault = FakeVault([{"id": "a1", "owner_user_id": "u1"}, {"id": "a2", "owner_user_id": "u2"}],
                      {"a1": [{"id": f"m{i}", "state": "unread"} for i in range(unread[0])] + [{"id": "r", "state": "read"}, {"id": "x", "state": "unread", "from_all_mail": True},
                                                                                              {"id": "p", "state": "unread", "ai_pending": True}] if unread else [],
                       "a2": [{"id": "other", "state": "unread"}] * 9})
    summary = DailySummary(vault, FakeShip(shops), FakeWait(wait), FakeSubs(subs), lambda uid: set())
    notifier = FakeNotifier(**settings)
    rem = Reminders(vault, FakeTasks(tasks), notifier, "")
    rem.summary = summary
    rem.subs = summary.subs
    return rem, notifier, summary


def run(rem, hour=8, minute=5):
    now = datetime(2026, 10, 9, hour, minute, tzinfo=SYD).timestamp()
    return rem.run_user("u1", now)


def test_tasks_only_keeps_the_old_morning_words():
    rem, notifier, _ = make(tasks=[task()])
    assert run(rem) == 1
    assert notifier.sent[0]["title"] == "Today: 1 thing" and "Pay the electricity bill" in notifier.sent[0]["body"]


def test_the_summary_adds_a_line_for_each_other_thing():
    subs = [{"key": "s1", "service": "Streamly", "kind": "renews", "days": 2, "amount": "$12"}]
    rem, notifier, _ = make(tasks=[task()], wait=2, shops=["Acme Shop"], subs=subs)
    assert run(rem) == 1 and len(notifier.sent) == 1                       # one note, not four
    note = notifier.sent[0]
    assert note["title"] == "Today: 5 things"
    assert "2 emails you sent still waiting for a reply" in note["body"]
    assert "Out for delivery today: Acme Shop" in note["body"]
    assert "Streamly renews in 2 days" in note["body"]
    assert notifier.state["subs"]["s1"]["count"] == 1                      # the subscription note was folded in, so it is not sent again
    assert run(rem, 9, 0) == 0 and len(notifier.sent) == 1


def test_titles_off_gives_only_counts_and_no_names():
    subs = [{"key": "s1", "service": "Streamly", "kind": "renews", "days": 2, "amount": "$12"}]
    rem, notifier, _ = make(tasks=[task()], shops=["Acme Shop"], subs=subs, show_titles=False)
    run(rem)
    note = notifier.sent[0]
    assert note["title"] == "Enveliq" and "Acme" not in note["body"] and "Streamly" not in note["body"] and "electricity" not in note["body"]
    assert "Open Enveliq" in note["body"]


def test_nothing_to_say_sends_nothing_and_does_not_try_again_today():
    rem, notifier, _ = make()
    assert run(rem) == 0 and notifier.sent == []
    assert notifier.state["morning_date"] == "2026-10-09"


def test_unread_emails_are_counted_only_when_asked_and_only_for_this_person():
    rem, notifier, summary = make(unread=(4,), digest_mail=True)
    assert summary.counts("u1", with_unread=True)["unread"] == 4           # not the other person's nine, not read, not 'include read', not pending
    assert summary.counts("u1")["unread"] == 0
    assert run(rem) == 1
    assert notifier.sent[0]["title"] == "Your day" and "4 unread emails waiting" in notifier.sent[0]["body"]


def test_the_summary_goes_once_a_day_and_holds_through_quiet_hours():
    rem, notifier, _ = make(tasks=[task()], wait=1, morning_time="06:00", quiet_from="05:00", quiet_to="07:30")
    assert run(rem, 6, 10) == 0 and notifier.sent == []
    assert run(rem, 7, 31) == 1 and len(notifier.sent) == 1
    assert run(rem, 7, 40) == 0


def test_a_person_with_no_channel_still_moves_the_number_the_android_app_watches():
    rem, notifier, _ = make(channels=False, tasks=[task()], wait=1)
    assert run(rem) == 0 and notifier.sent == []                           # nothing is sent anywhere
    assert notifier.state["summary_seq"] == 1 and notifier.state["morning_date"] == "2026-10-09"
    assert run(rem, 9, 0) == 0 and notifier.state["summary_seq"] == 1      # once a day
    rem2, notifier2, _ = make(channels=False, tasks=[task()], morning_on=False)
    assert run(rem2) == 0 and "summary_seq" not in notifier2.state


def test_sending_the_summary_moves_the_number_too():
    rem, notifier, _ = make(tasks=[task()])
    run(rem)
    assert notifier.state["summary_seq"] == 1


# ---------- new email instead of one alert each ----------

class Important:
    def contains(self, uid, address):
        return address == "boss@example.com"


def alert(sender):
    return {"account_id": "a1", "id": "11111111-2222-3333-4444-555555555551", "sender_display": "Someone", "sender_address": sender, "subject": "Hi", "priority": "normal"}


def alerts(notifier):
    return MailAlerts(notifier, "", lambda uid: "Australia/Sydney", clock=lambda: datetime(2026, 10, 9, 12, 0, tzinfo=SYD).timestamp(), important=Important())


def test_with_the_summary_on_new_email_waits_unless_it_is_from_an_important_person():
    notifier = FakeNotifier(mail_on=True, mail_details=False, quiet_on=False, digest_mail=True)
    a = alerts(notifier)
    assert a.send("u1", [alert("shop@example.com")]) == 0 and notifier.sent == []
    assert a.send("u1", [alert("shop@example.com"), alert("boss@example.com")]) == 1
    assert "1 new email." in notifier.sent[0]["body"]


def test_with_the_summary_off_alerts_work_as_before():
    notifier = FakeNotifier(mail_on=True, mail_details=False, quiet_on=False, digest_mail=False)
    assert alerts(notifier).send("u1", [alert("shop@example.com")]) == 1


def test_the_switch_does_nothing_when_the_daily_summary_itself_is_off():
    notifier = FakeNotifier(mail_on=True, mail_details=False, quiet_on=False, digest_mail=True, morning_on=False)
    assert alerts(notifier).send("u1", [alert("shop@example.com")]) == 1   # otherwise new email would never be announced at all


# ---------- what the Android app is told ----------

def test_the_phone_is_told_about_new_email_one_by_one_unless_the_summary_holds_it():
    from types import SimpleNamespace
    from backend.mail.notify_routes import digest_filter

    class V:
        def get_message(self, account_id, message_id):
            return {"sender_address": "boss@example.com" if message_id == "boss" else "shop@example.com"}

    fresh = [("a1", "boss"), ("a1", "shop")]
    ctx = SimpleNamespace(vault=V(), important=Important(), notifier=FakeNotifier(digest_mail=True))
    assert digest_filter(ctx, "u1", fresh) == [("a1", "boss")]
    ctx.notifier = FakeNotifier(digest_mail=False)
    assert digest_filter(ctx, "u1", fresh) == fresh
    ctx.notifier = FakeNotifier(digest_mail=True, morning_on=False)
    assert digest_filter(ctx, "u1", fresh) == fresh


def test_the_phone_sees_the_summary_number_go_up():
    from types import SimpleNamespace
    from backend.mail.notify_routes import grown, other_counts

    notifier = FakeNotifier()
    ctx = SimpleNamespace(messages=SimpleNamespace(enabled=lambda u: False), inbound=SimpleNamespace(unread=lambda u: 0),
                          tasks=SimpleNamespace(view=lambda u: {"tasks": []}), shipping=SimpleNamespace(view=lambda u: {"orders": []}), notifier=notifier)
    before = other_counts(ctx, "u1")
    notifier.state["summary_seq"] = 1
    assert grown(before, other_counts(ctx, "u1")) == ["summary"]
