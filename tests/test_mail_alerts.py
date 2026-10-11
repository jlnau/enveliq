"""New-email alerts, and the pieces that let a phone install Enveliq and open the right email from a notification."""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from backend.mail.mail_alerts import MailAlerts

ROOT = Path(__file__).resolve().parents[1]
SYD = ZoneInfo("Australia/Sydney")
ORIGIN = "https://mail.example.com"


class FakeNotifier:
    def __init__(self, **settings):
        self.s = {"mail_on": True, "mail_details": False, "quiet_on": False, "quiet_from": "21:00", "quiet_to": "07:00"} | settings
        self.channels = True
        self.sent = []

    def settings(self, uid):
        return self.s

    def has_any(self, uid):
        return self.channels

    def send_all(self, uid, note):
        self.sent.append(note)
        return {"ntfy": None}


def mail(i, sender="Zed Example", subject="Lunch on Friday", priority="normal"):
    return {"account_id": "acct1", "id": f"11111111-2222-3333-4444-55555555555{i}", "sender_display": sender, "subject": subject, "priority": priority}


def alerts(notifier, origin=ORIGIN, hour=12):
    clock = datetime(2026, 10, 12, hour, 0, tzinfo=SYD).timestamp()
    return MailAlerts(notifier, origin, lambda uid: "Australia/Sydney", clock=lambda: clock)


def test_it_is_off_until_the_person_switches_it_on():
    n = FakeNotifier(mail_on=False)
    assert alerts(n).send("u1", [mail(1)]) == 0 and n.sent == []


def test_nothing_goes_when_no_channel_is_on_or_nothing_is_new():
    n = FakeNotifier()
    n.channels = False
    assert alerts(n).send("u1", [mail(1)]) == 0
    n.channels = True
    assert alerts(n).send("u1", []) == 0 and n.sent == []


def test_by_default_it_only_says_how_many_and_keeps_names_and_subjects_out():
    n = FakeNotifier()
    a = alerts(n)
    assert a.send("u1", [mail(1, "Secret Sender", "Secret subject")]) == 1
    note = n.sent[0]
    assert note["title"] == "Enveliq" and note["body"] == "1 new email. Open Enveliq to read it."
    assert "Secret" not in note["title"] + note["body"]
    n.sent.clear()
    a.send("u1", [mail(1), mail(2), mail(3)])
    assert n.sent[0]["body"] == "3 new emails. Open Enveliq to read them." and n.sent[0]["path"] == "/" and n.sent[0]["url"] == ORIGIN + "/"


def test_with_details_on_it_names_the_sender_and_subject_but_never_an_address():
    n = FakeNotifier(mail_details=True)
    a = alerts(n)
    one = a.note([{**mail(1), "sender_address": "zed@example.invalid", "summary": "A private summary"}], True)
    assert one["title"] == "Zed Example" and one["body"] == "Lunch on Friday"
    many = a.note([mail(i) for i in range(1, 6)], True)
    assert many["title"] == "5 new emails" and many["body"].count("•") == 3 and many["body"].endswith("and 2 more")
    for text in (one["title"] + one["body"], many["title"] + many["body"]):
        assert "@" not in text and "private summary" not in text


def test_one_email_opens_that_email_and_several_open_the_inbox():
    a = alerts(FakeNotifier())
    one = a.note([mail(1)], False)
    assert one["path"] == "/?open=acct1:11111111-2222-3333-4444-555555555551"
    assert one["url"] == ORIGIN + one["path"]
    assert a.note([mail(1), mail(2)], False)["path"] == "/"


def test_on_a_local_address_only_the_browser_path_is_set():
    note = alerts(FakeNotifier(), origin="").note([mail(1)], False)
    assert note["url"] is None and note["path"].startswith("/?open=")


def test_control_characters_in_a_subject_are_removed_and_a_high_priority_email_is_urgent():
    a = alerts(FakeNotifier(mail_details=True))
    note = a.note([mail(1, "Zed\x07 Example", "Hi\x00 there", priority="high")], True)
    assert note["title"] == "Zed Example" and note["body"] == "Hi there" and note["priority"] == "high"
    assert a.note([mail(1)], False)["priority"] == "normal"


def test_quiet_hours_send_nothing_and_the_email_waits_in_the_inbox():
    n = FakeNotifier(quiet_on=True)
    assert alerts(n, hour=23).send("u1", [mail(1)]) == 0 and n.sent == []
    assert alerts(n, hour=3).send("u1", [mail(1)]) == 0
    assert alerts(n, hour=12).send("u1", [mail(1)]) == 1


def test_a_failing_channel_never_breaks_the_caller():
    n = FakeNotifier()

    def boom(uid, note):
        raise RuntimeError("down")
    n.send_all = boom
    assert alerts(n).send("u1", [mail(1)]) == 0


def test_the_service_worker_opens_the_email_and_only_on_this_origin():
    js = (ROOT / "web/static/sw.js").read_text()
    assert "enveliq-open" in js and "c.navigate(target)" in js and "openWindow(target)" in js
    assert "u.origin === self.location.origin" in js and "cu.origin !== self.location.origin" in js


def test_the_pages_link_the_manifest_and_the_icons_exist():
    for page in ("prototype/index.html", "web/auth.html"):
        assert 'rel="manifest" href="/manifest.webmanifest"' in (ROOT / page).read_text()
    from backend.app import MANIFEST
    assert MANIFEST["display"] == "standalone" and MANIFEST["start_url"] == "/"
    sizes = {(i["sizes"], i["purpose"]) for i in MANIFEST["icons"]}
    assert ("192x192", "any") in sizes and ("512x512", "any") in sizes and ("512x512", "maskable") in sizes
    for icon in MANIFEST["icons"]:
        assert (ROOT / "brand/web" / Path(icon["src"]).name).is_file()
        assert re.fullmatch(r"/brand/enveliq-icon[\w-]*\.png", icon["src"])
