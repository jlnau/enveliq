"""What the Agent chat is shown: only the signed-in person's own Enveliq, small, labelled as data, and never invented."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from backend.mail.agent_context import MAX_CONTEXT, Sources, build, terms

SYD = ZoneInfo("Australia/Sydney")


def at(day, hour=9, minute=0):
    return datetime(2026, 11, day, hour, minute, tzinfo=SYD).timestamp()


class Vault:
    def __init__(self, messages):
        self.messages = messages

    def list_accounts(self):
        return [{"id": "a1", "owner_user_id": "u1", "email_address": "me@example.com"}, {"id": "a2", "owner_user_id": "u2", "email_address": "other@example.com"}]

    def list_messages(self, account_id):
        return self.messages.get(account_id, [])


class Tasks:
    def timezone_of(self, uid):
        return "Australia/Sydney"

    def view(self, uid):
        rows = {"u1": [{"state": "open", "title": "Pay the water bill", "due": "2026-11-09", "sender": "Water Co", "detail": ""},
                       {"state": "done", "title": "Old finished thing", "due": "2026-10-01", "sender": "", "detail": ""}], "u2": [{"state": "open", "title": "Other person's task", "due": "2026-11-09", "sender": "", "detail": ""}]}
        return {"tasks": rows.get(uid, [])}


class Trips:
    def view(self, uid):
        if uid != "u1":
            return {"trips": []}
        return {"trips": [{"state": "soon", "cancelled": False, "bookings": [
            {"kind": "flight", "provider": "Example Air", "from": "Sydney", "to": "Perth", "start": "2026-11-12", "start_time": "14:05", "end": None, "reference": "ABC123", "detail": "Check-in closes 60 minutes before.", "status": "booked"}]},
            {"state": "past", "cancelled": False, "bookings": [{"kind": "flight", "provider": "Old Air", "from": "A", "to": "B", "start": "2026-01-01", "status": "booked"}]}]}


def mail(i, subject, sender, summary, day, **more):
    return {"id": f"m{i}", "subject": subject, "sender_display": sender, "sender_address": "x@example.com", "summary": summary, "received_at": at(day), "state": "unread", **more}


def sources(messages):
    return Sources(Vault(messages), tasks=Tasks(), trips=Trips())


NOW = at(6, 11, 20)


def test_it_shows_the_persons_trips_tasks_and_newest_email_with_the_real_names():
    src = sources({"a1": [mail(1, "Your booking", "Belinda Example", "Your flight is booked.", 5), mail(2, "Lunch?", "Sam", "Sam asks about lunch.", 6)]})
    text = build(src, "u1", "whats the newest email", now=NOW)
    assert "Friday 6 November 2026" in text and "Australia/Sydney" in text
    assert "Flight Example Air, Sydney to Perth, Thu 12 Nov 2026 at 14:05, reference ABC123" in text and "Check-in closes 60 minutes before." in text
    assert "Old Air" not in text                                      # a trip that is over is left out
    assert "Pay the water bill" in text and "Old finished thing" not in text
    assert text.index("Lunch?") < text.index("Your booking")           # newest first
    assert "Sam" in text and "Sarah" not in text


def test_nothing_of_another_person_is_ever_included():
    src = sources({"a1": [mail(1, "Mine", "Sam", "My email.", 5)], "a2": [mail(2, "Secret", "Other", "The other person's private email.", 6)]})
    text = build(src, "u1", "secret private other", now=NOW)
    assert "Mine" in text and "Secret" not in text and "private email" not in text and "Other person's task" not in text
    assert "Mine" not in build(src, "u2", "mine", now=NOW)


def test_emails_that_match_the_question_are_found_even_when_old():
    old = [mail(i, f"Newsletter {i}", "Shop", "Specials this week.", 1) for i in range(10, 30)]
    old.append(mail(99, "Flight confirmation", "Example Air", "Flight QF12 to Perth on Thursday.", 1))
    new = [mail(i, f"Hello {i}", "Friend", "Just saying hi.", 5) for i in range(1, 8)]
    text = build(sources({"a1": new + old}), "u1", "which flight am I on?", now=NOW)
    assert "Flight confirmation" in text and "QF12" in text
    assert "Hello" in text                                            # the newest few are always there


def test_a_follow_up_question_still_finds_the_email_from_the_one_before():
    old = [mail(i, f"Newsletter {i}", "Shop", "Specials.", 1) for i in range(10, 30)]
    old.append(mail(99, "Dentist booking", "Sunny Dental", "Appointment Friday 2:30 PM.", 1))
    new = [mail(i, f"Hello {i}", "Friend", "Hi.", 5) for i in range(1, 8)]
    src = sources({"a1": new + old})
    assert "Dentist booking" not in build(src, "u1", "what time is it?", now=NOW)
    assert "Dentist booking" in build(src, "u1", "what time is it?", earlier="when is my dentist appointment", now=NOW)


def test_it_is_small_clean_and_marked_as_data():
    long = "word " * 3000
    msgs = [mail(i, f"Subject {i}", "A" * 500, long + "\x00\x07 hidden", 5) for i in range(40)]
    text = build(sources({"a1": msgs}), "u1", "subject", now=NOW)
    assert len(text) <= MAX_CONTEXT + 400 and "\x00" not in text and "\x07" not in text
    assert "not the email itself" in text and "[E1]" in text


def test_missing_parts_and_an_empty_mailbox_are_said_plainly():
    text = build(Sources(Vault({})), "u1", "anything", now=NOW)
    assert "TRIPS AND BOOKINGS (from the person's email):\n- none" in text and "EMAILS ENVELIQ HAS KEPT: none." in text


def test_a_broken_part_does_not_stop_the_rest():
    class Broken:
        def view(self, uid):
            raise RuntimeError("boom")
    src = Sources(Vault({"a1": [mail(1, "Hi", "Sam", "Hello.", 5)]}), tasks=Broken(), trips=Broken())
    assert "Hi" in build(src, "u1", "hi", now=NOW)


def test_question_words_ignore_filler():
    assert terms("Do I have any flights booked") == {"flight", "booked"}
