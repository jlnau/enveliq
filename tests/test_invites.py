"""Calendar invites: the .ics reader, answering by email, proposing a new time, and the connected calendar."""
from __future__ import annotations

import email
from email import policy

from test_bridge import MAILBOX, WORK, env, synced  # noqa: F401  (the shared Bridge fixture)
from test_email_features import PREFS
from backend.mail import invites

ICS = (
    "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//Example//EN\r\nMETHOD:{method}\r\nBEGIN:VEVENT\r\nUID:meeting-1@example.com\r\nSEQUENCE:2\r\n"
    "DTSTAMP:20261029T000000Z\r\nDTSTART;TZID=Australia/Sydney:20261103T140000\r\nDTEND;TZID=Australia/Sydney:20261103T144500\r\n"
    "SUMMARY:Project catch-up\r\nLOCATION:Video call\r\nDESCRIPTION:Agenda\\nOne\\, two\r\nORGANIZER;CN=Sam Example:mailto:sam@example.com\r\n"
    "ATTENDEE;CN=Me;PARTSTAT=NEEDS-ACTION;RSVP=TRUE:mailto:{me}\r\nATTENDEE;CN=Pat;PARTSTAT=ACCEPTED:mailto:pat@example.com\r\n"
    "BEGIN:VALARM\r\nTRIGGER:-PT15M\r\nDESCRIPTION:ignore me\r\nEND:VALARM\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n"
)


def invite_mail(method="REQUEST", sender="Sam Example <sam@example.com>", me=MAILBOX, mid="<inv1@example.com>", attach=True) -> bytes:
    ics = ICS.format(method=method, me=me)
    head = (f"From: {sender}\r\nTo: {me}\r\nSubject: Invitation: Project catch-up\r\nDate: Wed, 28 Oct 2026 09:00:00 +1100\r\nMessage-ID: {mid}\r\n"
            'MIME-Version: 1.0\r\nContent-Type: multipart/mixed; boundary="B"\r\n\r\n--B\r\nContent-Type: text/plain\r\n\r\nYou are invited.\r\n')
    part = (f'--B\r\nContent-Type: text/calendar; method={method}; charset=utf-8\r\n' + ('Content-Disposition: attachment; filename="invite.ics"\r\n' if attach else "")
            + "\r\n" + ics + "--B--\r\n")
    return (head + part).encode()


def parsed(**kw):
    return invites.parse(ICS.format(method=kw.get("method", "REQUEST"), me=MAILBOX), "Australia/Sydney")


# ---------- reading ----------

def test_the_reader_gets_the_meeting_in_plain_fields():
    got = parsed()
    assert got["summary"] == "Project catch-up" and got["method"] == "REQUEST" and got["sequence"] == 2
    assert got["location"] == "Video call" and got["description"] == "Agenda\nOne, two"
    assert got["organizer"] == {"email": "sam@example.com", "name": "Sam Example"}
    assert [a["email"] for a in got["attendees"]] == [MAILBOX, "pat@example.com"]
    assert got["end"] - got["start"] == 45 * 60 and got["tz"] == "Australia/Sydney" and not got["all_day"]
    assert "ignore me" not in got["description"]                       # an alarm inside the event is not the event's text
    assert "Project catch-up" in invites.summary_text(got) and "Sam Example" in invites.summary_text(got)


def test_times_in_utc_all_day_and_windows_zone_names_are_understood():
    base = "BEGIN:VCALENDAR\r\nBEGIN:VEVENT\r\nUID:u\r\n{lines}\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n"
    utc = invites.parse(base.format(lines="DTSTART:20261103T030000Z\r\nDURATION:PT30M\r\nSUMMARY:x"), "Australia/Sydney")
    assert utc["end"] - utc["start"] == 1800 and utc["tz"] == "UTC"
    day = invites.parse(base.format(lines="DTSTART;VALUE=DATE:20261103\r\nSUMMARY:x"), None)
    assert day["all_day"] and day["start_day"] == "2026-11-03" and day["end_day"] == "2026-11-04" and day["start"] is None
    win = invites.parse(base.format(lines="DTSTART;TZID=AUS Eastern Standard Time:20261103T140000\r\nSUMMARY:x"), "UTC")
    assert win["tz"] == "Australia/Sydney" and win["start"] == utc["start"]            # 2 pm in Sydney (UTC+11) is 3 am UTC


def test_rubbish_and_hostile_files_are_refused_or_cut_down():
    assert invites.parse("not a calendar") is None
    assert invites.parse("BEGIN:VCALENDAR\r\nBEGIN:VEVENT\r\nSUMMARY:no start\r\nEND:VEVENT\r\nEND:VCALENDAR") is None
    nasty = ICS.format(method="REQUEST", me=MAILBOX).replace("SUMMARY:Project catch-up", "SUMMARY:" + "A" * 5000 + "\x00\x07").replace("RRULE", "X")
    got = invites.parse(nasty)
    assert len(got["summary"]) == 200 and "\x00" not in got["summary"] and got["rrule"] == ""
    odd = ICS.format(method="REQUEST", me=MAILBOX).replace("END:VEVENT", "RRULE:FREQ=WEEKLY;X=<script>\r\nEND:VEVENT")
    assert invites.parse(odd)["rrule"] == ""                           # only plain rule characters get through
    assert invites.organizer_differs(parsed(), "someone@other.invalid") and not invites.organizer_differs(parsed(), "sam@mail.example.com")


def test_an_ics_file_is_readable_and_previewable_as_words():
    from backend.mail import render
    data = ICS.format(method="REQUEST", me=MAILBOX).encode()
    got = render.read_text(data, "invite.ics", "application/octet-stream")
    assert got["kind"] == "text" and "Meeting invitation: Project catch-up" in got["text"]
    shown = render.view(data, "invite.ics", "text/calendar")
    assert "Project catch-up" in str(shown) and "BEGIN:VEVENT" not in str(shown)
    assert render.can_view("invite.ics", "application/octet-stream")


# ---------- the card ----------

def put_invite(bridge, uid=10, **kw):
    bridge.add(uid, invite_mail(**kw))


def open_card(client, bridge, **kw):
    put_invite(bridge, **kw)
    aid, msgs = synced(client, bridge)
    m = msgs["Invitation: Project catch-up"]
    return aid, m["id"]


def test_the_card_shows_the_meeting_and_is_for_the_owner_only(env):
    _, client, bridge, _ = env
    aid, mid = open_card(client, bridge)
    r = client.get(f"/api/v1/accounts/{aid}/messages/{mid}/invite")
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store", r.text
    card = r.json()
    assert card["summary"] == "Project catch-up" and card["can_answer"] and not card["organizer_differs"] and card["mine"] == MAILBOX
    assert card["answer"] is None and card["calendar"] == ""
    assert "uid" not in card and "attendees" not in card and card["people"] == 2
    assert client.get(f"/api/v1/accounts/{aid}/messages/{'x' * 32}/invite").status_code in (404, 422)
    client.cookies.clear()
    assert client.get(f"/api/v1/accounts/{aid}/messages/{mid}/invite").status_code in (401, 403)


def test_an_email_without_an_invite_says_not_found(env):
    _, client, bridge, _ = env
    aid, msgs = synced(client, bridge)
    m = msgs["Quarterly update"]
    assert client.get(f"/api/v1/accounts/{aid}/messages/{m['id']}/invite").status_code == 404


# ---------- answering ----------

def sent_calendar(bridge):
    msg = email.message_from_bytes(bridge.sent[-1]["data"] if isinstance(bridge.sent[-1]["data"], bytes) else bridge.sent[-1]["data"].encode(), policy=policy.default)
    cal = next(p for p in msg.walk() if p.get_content_type() == "text/calendar")
    return msg, cal.get_content()


def no_undo(client):
    assert client.put("/api/v1/me/preferences", json={**PREFS, "undo_send_seconds": 0}).status_code == 200


def test_accept_sends_the_standard_reply_to_the_organiser_and_remembers_it(env):
    _, client, bridge, _ = env
    no_undo(client)
    aid, mid = open_card(client, bridge)
    r = client.post(f"/api/v1/accounts/{aid}/messages/{mid}/invite/answer", json={"response": "accepted", "comment": "See you there"})
    assert r.status_code == 200 and r.json()["sent"] is True, r.text
    assert bridge.sent[-1]["to"] == ["sam@example.com"]
    msg, ics = sent_calendar(bridge)
    assert msg["Subject"] == "Accepted: Project catch-up" and msg["In-Reply-To"] == "<inv1@example.com>"
    assert "METHOD:REPLY" in ics and "PARTSTAT=ACCEPTED" in ics and f"mailto:{MAILBOX}" in ics and "UID:meeting-1@example.com" in ics
    assert "DTSTART;TZID=Australia/Sydney:20261103T140000" in ics and "pat@example.com" not in ics        # only our own status goes back
    assert "COMMENT:See you there" in ics
    card = client.get(f"/api/v1/accounts/{aid}/messages/{mid}/invite").json()
    assert card["answer"]["response"] == "accepted"


def test_maybe_and_decline_use_their_own_words(env):
    _, client, bridge, _ = env
    no_undo(client)
    aid, mid = open_card(client, bridge)
    for word, part in (("tentative", "TENTATIVE"), ("declined", "DECLINED")):
        assert client.post(f"/api/v1/accounts/{aid}/messages/{mid}/invite/answer", json={"response": word}).status_code == 200
        assert f"PARTSTAT={part}" in sent_calendar(bridge)[1]
    assert client.post(f"/api/v1/accounts/{aid}/messages/{mid}/invite/answer", json={"response": "maybe"}).status_code == 422
    assert client.post(f"/api/v1/accounts/{aid}/messages/{mid}/invite/answer", json={"response": "accepted", "extra": 1}).status_code == 422


def test_the_answer_comes_from_the_address_the_invite_names_when_we_can_send_from_it(env):
    _, client, bridge, _ = env
    no_undo(client)
    aid, mid = open_card(client, bridge, me=WORK)           # WORK is one of this mailbox's sending identities
    assert client.post(f"/api/v1/accounts/{aid}/messages/{mid}/invite/answer", json={"response": "accepted"}).status_code == 200
    assert bridge.sent[-1]["from"] == WORK and f"mailto:{WORK}" in sent_calendar(bridge)[1]


def test_an_organiser_who_is_not_the_sender_needs_the_person_to_agree(env):
    _, client, bridge, _ = env
    no_undo(client)
    aid, mid = open_card(client, bridge, sender="Sam Example <sam@elsewhere.invalid>")
    assert client.get(f"/api/v1/accounts/{aid}/messages/{mid}/invite").json()["organizer_differs"] is True
    r = client.post(f"/api/v1/accounts/{aid}/messages/{mid}/invite/answer", json={"response": "accepted"})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "organizer_differs" and not bridge.sent
    ok = client.post(f"/api/v1/accounts/{aid}/messages/{mid}/invite/answer", json={"response": "accepted", "confirm_organizer": True})
    assert ok.status_code == 200 and bridge.sent[-1]["to"] == ["sam@example.com"]


def test_a_cancelled_meeting_cannot_be_answered(env):
    _, client, bridge, _ = env
    aid, mid = open_card(client, bridge, method="CANCEL")
    card = client.get(f"/api/v1/accounts/{aid}/messages/{mid}/invite").json()
    assert card["cancelled"] is True and card["can_answer"] is False and card["can_add"] is False
    assert client.post(f"/api/v1/accounts/{aid}/messages/{mid}/invite/answer", json={"response": "accepted"}).status_code == 409


def test_with_undo_send_the_answer_waits_and_nothing_is_written_until_it_goes(env):
    _, client, bridge, _ = env
    assert client.put("/api/v1/me/preferences", json={**PREFS, "undo_send_seconds": 30}).status_code == 200
    aid, mid = open_card(client, bridge)
    r = client.post(f"/api/v1/accounts/{aid}/messages/{mid}/invite/answer", json={"response": "accepted"})
    assert r.status_code == 200 and r.json()["queued"] is True and not bridge.sent
    assert client.get(f"/api/v1/accounts/{aid}/messages/{mid}/invite").json()["answer"] is None
    assert client.delete(f"/api/v1/me/outbox/{r.json()['id']}").status_code == 200           # Undo
    assert not bridge.sent


# ---------- a new time ----------

def test_propose_a_new_time_sends_plain_words_and_does_not_touch_the_calendar(env):
    appm, client, bridge, _ = env
    no_undo(client)
    calls = []
    appm.sync.invite_target = lambda uid: "google"
    appm.sync.invite_put = lambda *a, **k: calls.append(a) or "Google Calendar"
    aid, mid = open_card(client, bridge)
    start = 1_794_000_000                                   # Nov 2026
    r = client.post(f"/api/v1/accounts/{aid}/messages/{mid}/invite/propose", json={"start": start, "end": start + 2700, "zone": "Australia/Sydney", "note": "Wednesday suits me better."})
    assert r.status_code == 200, r.text
    msg = email.message_from_bytes(bridge.sent[-1]["data"] if isinstance(bridge.sent[-1]["data"], bytes) else bridge.sent[-1]["data"].encode(), policy=policy.default)
    body = msg.get_body(preferencelist=("plain",)).get_content()
    assert msg["Subject"] == "New time suggested: Project catch-up" and "Australia/Sydney" in body and "Wednesday suits me better." in body
    assert not [p for p in msg.walk() if p.get_content_type() == "text/calendar"] and not calls
    url = f"/api/v1/accounts/{aid}/messages/{mid}/invite/propose"
    assert client.post(url, json={"start": start, "end": start - 1, "zone": "UTC"}).status_code == 422
    assert client.post(url, json={"start": 1000, "end": 2000, "zone": "UTC"}).status_code == 422
    assert client.post(url, json={"start": start, "end": start + 60, "zone": "Not/AZone"}).status_code == 422


# ---------- the calendar ----------

def test_accept_adds_the_meeting_and_decline_takes_it_out(env):
    appm, client, bridge, _ = env
    no_undo(client)
    log = []
    appm.sync.invite_target = lambda uid: "google"
    appm.sync.invite_place = lambda uid: "Google Calendar"
    appm.sync.invite_put = lambda uid, key, body, ics: log.append(("put", key, body, ics)) or "Google Calendar"
    appm.sync.invite_remove = lambda uid, key: log.append(("remove", key)) or "Google Calendar"
    aid, mid = open_card(client, bridge)
    assert client.get(f"/api/v1/accounts/{aid}/messages/{mid}/invite").json()["calendar"] == "Google Calendar"
    client.post(f"/api/v1/accounts/{aid}/messages/{mid}/invite/answer", json={"response": "accepted"})
    kind, key, body, ics = log[-1]
    assert kind == "put" and body["id"] == "inv" + key and body["summary"] == "Project catch-up" and body["start"]["timeZone"] == "Australia/Sydney"
    assert body["status"] == "confirmed" and "UID:meeting-1@example.com" in ics and "METHOD" not in ics
    client.post(f"/api/v1/accounts/{aid}/messages/{mid}/invite/answer", json={"response": "tentative"})
    assert log[-1][2]["status"] == "tentative"
    client.post(f"/api/v1/accounts/{aid}/messages/{mid}/invite/answer", json={"response": "declined"})
    assert log[-1] == ("remove", key)
    assert client.get(f"/api/v1/accounts/{aid}/messages/{mid}/invite").json()["answer"]["response"] == "declined"


def test_a_calendar_problem_does_not_lose_the_answer_and_is_reported(env):
    appm, client, bridge, _ = env
    no_undo(client)
    from backend.mail.outbound import OutboundError
    appm.sync.invite_target = lambda uid: "google"
    appm.sync.invite_place = lambda uid: "Google Calendar"

    def boom(*a, **k):
        raise OutboundError("error", "Google refused the meeting (500).")
    appm.sync.invite_put = boom
    aid, mid = open_card(client, bridge)
    assert client.post(f"/api/v1/accounts/{aid}/messages/{mid}/invite/answer", json={"response": "accepted"}).status_code == 200
    answer = client.get(f"/api/v1/accounts/{aid}/messages/{mid}/invite").json()["answer"]
    assert answer["response"] == "accepted" and "refused" in answer["calendar_problem"]


def test_add_and_remove_without_answering_need_a_connected_calendar(env):
    appm, client, bridge, _ = env
    aid, mid = open_card(client, bridge)
    url = f"/api/v1/accounts/{aid}/messages/{mid}/invite/calendar"
    assert client.post(url, json={"action": "add"}).status_code == 409                     # none connected
    log = []
    appm.sync.invite_target = lambda uid: "caldav"
    appm.sync.invite_put = lambda uid, key, body, ics: log.append("put") or "your calendar"
    appm.sync.invite_remove = lambda uid, key: log.append("remove") or "your calendar"
    assert client.post(url, json={"action": "add"}).json()["calendar"] == "your calendar"
    assert client.post(url, json={"action": "remove"}).status_code == 200 and log == ["put", "remove"]
    assert client.post(url, json={"action": "delete"}).status_code == 422


def test_calendar_files_have_the_right_shape():
    got = parsed()
    key = invites.key_of(got)
    assert len(key) == 40 and key == invites.key_of(parsed())
    ics = invites.calendar_file(got, key, "accepted", 0)
    assert ics.startswith("BEGIN:VCALENDAR\r\n") and "STATUS:CONFIRMED" in ics and "DTSTART;TZID=Australia/Sydney:20261103T140000" in ics
    assert all(len(line.encode()) <= 75 for line in ics.split("\r\n"))
    assert invites.google_body(got, key, "accepted")["extendedProperties"] == {"private": {"enveliq_invite": key}}


def test_only_the_answer_is_kept_never_the_meeting(env):
    appm, client, bridge, _ = env
    no_undo(client)
    aid, mid = open_card(client, bridge)
    client.post(f"/api/v1/accounts/{aid}/messages/{mid}/invite/answer", json={"response": "accepted"})
    stored = appm.vault.get_global("invites:" + client.get("/api/v1/me").json()["id"])
    assert len(stored) == 1
    entry = next(iter(stored.values()))
    assert set(entry) == {"response", "calendar", "calendar_problem", "at"} and entry["response"] == "accepted"
    text = str(stored)
    assert all(word not in text for word in ("Project catch-up", "meeting-1@example.com", "sam@example.com", "Video call"))
