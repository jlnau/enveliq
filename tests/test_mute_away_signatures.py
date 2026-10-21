"""Version 0.102: muted conversations, the scheduled away reply, and formatted signatures (one per sending address)."""
from __future__ import annotations

import time
from datetime import datetime, timezone

import pytest

from backend.mail.awayreply import AwayBook, AwayError, automatic, eligible
from backend.mail.muted import MutedBook, MuteError, thread_ids
from backend.mail.parse import is_automated
from backend.mail.saved_writing import SavedError, SavedWriting
from email.message import EmailMessage


class FakeVault:
    def __init__(self):
        self.data = {}

    def get_global(self, key):
        return self.data.get(key)

    def set_global(self, key, value):
        self.data[key] = value


NOW = datetime(2026, 12, 20, 12, 0, tzinfo=timezone.utc).timestamp()


# ---------- mute ----------

def test_thread_ids_use_references_and_own_id_and_skip_junk():
    ids = thread_ids({"references": ["<a@example.com>", "not an id"], "message_id": "<b@example.com>"})
    assert ids == ["<a@example.com>", "<b@example.com>"]
    assert thread_ids(None) == []


def test_a_conversation_can_be_muted_matched_widened_and_unmuted():
    book = MutedBook(FakeVault(), clock=lambda: NOW)
    e = book.add("u1", "Re: Fwd: Holiday plans", ["<a@example.com>"])
    assert e["subject"] == "Holiday plans" and e["id"].startswith("q")
    assert book.match("u1", ["<x@example.com>", "<a@example.com>"]) == e["id"]
    assert book.match("u1", ["<zzz@example.com>"]) is None
    assert book.match("u2", ["<a@example.com>"]) is None                     # one person's mutes are never another's
    again = book.add("u1", "Holiday plans", ["<a@example.com>", "<c@example.com>"])
    assert again["id"] == e["id"] and len(book.listing("u1")["items"]) == 1
    book.hit("u1", e["id"], ["<d@example.com>"])
    assert book.match("u1", ["<d@example.com>"]) == e["id"] and book.listing("u1")["items"][0]["count"] == 1
    assert book.remove("u1", e["id"]) and not book.remove("u1", e["id"])
    assert book.match("u1", ["<a@example.com>"]) is None


def test_muting_without_a_conversation_marker_is_refused_in_plain_words():
    with pytest.raises(MuteError):
        MutedBook(FakeVault()).add("u1", "x", [])


# ---------- away reply ----------

def make_book(now=NOW):
    return AwayBook(FakeVault(), lambda u: "UTC", clock=lambda: now)


def test_away_reply_needs_message_and_sensible_dates():
    b = make_book()
    with pytest.raises(AwayError):
        b.save("u", True, "2026-12-20", "2026-12-24", "  ")
    with pytest.raises(AwayError):
        b.save("u", True, "2026-12-24", "2026-12-20", "Away")
    with pytest.raises(AwayError):
        b.save("u", True, "2026-12-01", "2026-12-05", "Away")                # already over
    assert b.save("u", True, "2026-12-20", "2026-12-24", "I am away.")["state"] == "active"
    assert b.save("u", True, "2026-12-22", "2026-12-24", "I am away.")["state"] == "scheduled"
    assert b.save("u", False, "", "", "I am away.")["state"] == "off"


def test_each_sender_is_answered_once_and_only_between_the_dates():
    b = make_book()
    b.save("u", True, "2026-12-20", "2026-12-24", "I am away.")
    assert b.claim("u", "Alice@Example.com") and not b.claim("u", "alice@example.com")
    b.release("u", "alice@example.com")
    assert b.claim("u", "alice@example.com")
    assert not make_book(NOW + 10 * 86400).claim("u", "bob@example.com")      # nothing is saved there, and it is off
    b2 = AwayBook(b.vault, lambda u: "UTC", clock=lambda: NOW + 10 * 86400)
    assert b2.state_of("u") == "ended" and not b2.claim("u", "bob@example.com")


def test_there_is_an_hourly_limit_and_a_new_absence_starts_clean():
    b = make_book()
    b.save("u", True, "2026-12-20", "2026-12-24", "Away")
    assert sum(b.claim("u", f"p{i}@example.com") for i in range(40)) == 20
    b.save("u", True, "2026-12-20", "2026-12-26", "Away")
    assert b.claim("u", "p1@example.com")


def test_automatic_mail_lists_and_own_addresses_never_get_a_reply():
    ok = {"reply_to": "alice@example.com", "delivered_to": "me@example.com"}
    item = {"automated": False}
    stored = {"reply_context": ok, "sender_address": "alice@example.com", "received_at": NOW - 60}
    assert eligible(item, stored, {"me@example.com"}, NOW) == "alice@example.com"
    assert eligible({"automated": True}, stored, set(), NOW) is None
    assert eligible(item, {**stored, "reply_context": {**ok, "delivered_to": ""}}, set(), NOW) is None
    assert eligible(item, {**stored, "reply_context": {**ok, "reply_to": "noreply@example.com"}}, set(), NOW) is None
    assert eligible(item, stored, {"alice@example.com"}, NOW) is None
    assert eligible(item, {**stored, "received_at": NOW - 5 * 86400}, set(), NOW) is None
    assert automatic("no-reply@example.com") and not automatic("alice@example.com")


def test_automatic_mail_is_recognised_from_its_headers():
    for name, value in [("Auto-Submitted", "auto-generated"), ("Precedence", "bulk"), ("List-Id", "<x.example.com>")]:
        m = EmailMessage()
        m[name] = value
        assert is_automated(m)
    m = EmailMessage()
    m["Auto-Submitted"] = "no"
    assert not is_automated(m)


# ---------- signatures ----------

def test_a_formatted_default_signature_keeps_bold_italic_links_and_drops_scripts():
    w = SavedWriting(FakeVault())
    v = w.set_signature("u", "", '<b>Sam</b><br><i>Home</i> <a href="https://example.com/x">site</a><script>x()</script>')
    assert "<b>Sam</b>" in v["signature_html"] and 'href="https://example.com/x"' in v["signature_html"] and "script" not in v["signature_html"]
    assert "Sam" in v["signature"] and "<" not in v["signature"]
    assert w.set_signature("u", "Plain")["signature_html"] == ""             # an old plain signature still works


def test_each_sending_address_can_have_its_own_signature_and_the_default_stays():
    w = SavedWriting(FakeVault())
    w.set_signature("u", "Default")
    v = w.set_address_signature("u", "Me@Example.com", "<b>Work</b>")
    assert v["signature"] == "Default" and v["signatures"][0]["address"] == "me@example.com"
    assert w.set_address_signature("u", "me@example.com", "")["signatures"] == []
    with pytest.raises(SavedError):
        w.set_address_signature("u", "me@example.com", "x" * 20000)
