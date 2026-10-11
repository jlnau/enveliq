"""Trips: flights, stays and hire cars filed from summaries, grouped and dated in code, and added to the person's calendar."""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone

import pytest

from test_bridge import mails  # noqa: F401
from test_summaries import account, start  # noqa: F401
from test_llm import FakeModel, GOOD
from test_calsync import Remote  # noqa: F401
from backend.mail import calsync, llm
from backend.mail import trips as T


class FakeVault:
    def __init__(self):
        self.g: dict = {}

    def get_global(self, k):
        return self.g.get(k)

    def set_global(self, k, v):
        self.g[k] = json.loads(json.dumps(v))

    def get_user(self, uid):
        raise KeyError(uid)


NOW = datetime(2026, 10, 11, 12, tzinfo=timezone.utc).timestamp()      # a fixed moment, so dates never depend on the day the tests run
TODAY = date(2026, 10, 11)


def when(days: int, clock: str = "") -> str:
    d = TODAY + timedelta(days=days)
    return f"{d.day} {d:%b} {d.year}" + (f" {clock}" if clock else "")


@pytest.fixture
def book():
    return T.TripBook(FakeVault(), clock=lambda: NOW)


def flight(**kw):
    return {"kind": "flight", "status": "booked", "provider": "Qantas", "reference": "QX7K2P", "detail": "QF9", "from": "Melbourne", "to": "Lisbon",
            "start": when(20, "10:45"), "end": when(21, "14:20"), **kw}


def stay(**kw):
    return {"kind": "stay", "status": "booked", "provider": "Hotel Aurora", "reference": "HA-5521", "detail": None, "from": None, "to": "Lisbon",
            "start": when(21, "3:00 pm"), "end": when(27, "11 am"), **kw}


def car(**kw):
    return {"kind": "car", "status": "booked", "provider": "Hertz", "reference": "HZ99", "detail": None, "from": "Lisbon airport", "to": None,
            "start": when(21), "end": when(27), **kw}


def seen(book, n, rows, at=NOW - 3600, user="u1"):
    return book.observe(user, "a1", f"m{n}", at, rows)


def trips(book, user="u1"):
    return book.view(user)["trips"]


# ---------- times and dates are worked out here ----------

def test_clock_times_are_read_only_when_they_are_there():
    assert T.parse_clock("Tue 3 Nov 10:45") == "10:45"
    assert T.parse_clock("3 Nov 2.35 pm") == "14:35"
    assert T.parse_clock("3 Nov 12:05 am") == "00:05"
    assert T.parse_clock("3 Nov 12:30 PM") == "12:30"
    assert T.parse_clock("check-in from 3 pm") == "15:00"
    assert T.parse_clock("11 am") == "11:00"
    for none in ("3 Nov 2026", "", None, "Tue 3 Nov", "13 pm", "3 Nov 25:00"):
        assert T.parse_clock(none) is None


def test_a_round_trip_is_two_flights_in_one_trip_with_a_stay_inside_it(book):
    assert seen(book, 1, [flight(), flight(detail="QF10", **{"from": "Lisbon", "to": "Melbourne", "start": when(27, "09:00"), "end": when(28, "06:30")}), stay()])
    got = trips(book)
    assert len(got) == 1
    trip = got[0]
    assert trip["title"] == "Trip to Lisbon"                                                  # the first booking's destination, not the way home
    assert trip["start"] == (TODAY + timedelta(days=20)).isoformat() and trip["end"] == (TODAY + timedelta(days=28)).isoformat()
    assert trip["days_to_start"] == 20 and trip["state"] == "soon"
    assert [b["kind"] for b in trip["bookings"]] == ["flight", "stay", "flight"]              # in date order
    assert trip["bookings"][1]["nights"] == 6


def test_bookings_far_apart_are_separate_trips_and_close_ones_join(book):
    seen(book, 1, [flight(), flight(detail="QF10", **{"from": "Lisbon", "to": "Melbourne", "start": when(25), "end": when(25)})])
    seen(book, 2, [flight(reference="ZZ1111", detail="QF1", **{"to": "Auckland", "start": when(100), "end": when(100)})])
    got = trips(book)
    assert [t["title"] for t in got] == ["Trip to Lisbon", "Trip to Auckland"]
    seen(book, 3, [stay(reference="NEAR1", provider="Nearby Inn", start=when(27), end=when(29))])      # two days after the first trip ends: still the same trip
    assert len(trips(book)) == 2 and len(trips(book)[0]["bookings"]) == 3


def test_a_trip_that_is_under_way_and_one_that_is_over(book):
    seen(book, 1, [stay(start=when(-2), end=when(3))])
    assert trips(book)[0]["state"] == "now"
    late = T.TripBook(book.vault, clock=lambda: NOW + 10 * 86400)
    assert late.view("u1")["trips"] == []                                                      # forgotten three days after it ends


def test_a_date_far_from_the_email_is_ignored(book):
    assert seen(book, 1, [flight(start="2031-01-01"), flight(start="no date at all")]) is False
    assert trips(book) == []


# ---------- matching ----------

def test_the_same_email_twice_and_the_same_booking_in_two_emails(book):
    assert seen(book, 1, [flight()]) is True
    assert seen(book, 1, [flight()]) is False
    seen(book, 2, [flight(detail="QF9 operated by Qantas")], at=NOW - 1800)
    assert len(trips(book)[0]["bookings"]) == 1


def test_a_changed_booking_updates_the_same_one_and_keeps_its_place(book):
    seen(book, 1, [flight()], at=NOW - 7200)
    seen(book, 2, [flight(status="changed", start=when(22, "08:15"), end=when(23, "12:00"))], at=NOW - 3600)
    b = trips(book)[0]["bookings"]
    assert len(b) == 1 and b[0]["start"] == (TODAY + timedelta(days=22)).isoformat() and b[0]["start_time"] == "08:15"


def test_an_older_email_never_overwrites_newer_facts(book):
    seen(book, 1, [flight(start=when(22, "08:15"))], at=NOW - 3600)
    seen(book, 2, [flight(start=when(20, "10:45"))], at=NOW - 86400)
    assert trips(book)[0]["bookings"][0]["start_time"] == "08:15"


def test_a_cancellation_greys_it_out_and_it_is_forgotten_a_week_later(book):
    seen(book, 1, [flight(), stay()], at=NOW - 7200)
    seen(book, 2, [flight(status="cancelled")], at=NOW - 3600)
    got = trips(book)[0]
    assert [b["status"] for b in got["bookings"]] == ["cancelled", "booked"] or [b["status"] for b in got["bookings"]] == ["booked", "cancelled"]
    assert got["cancelled"] is False
    assert seen(book, 3, [car(status="cancelled")]) is False                                   # nothing to cancel
    later = T.TripBook(book.vault, clock=lambda: NOW + 8 * 86400)
    assert [b["kind"] for t in later.view("u1")["trips"] for b in t["bookings"]] == ["stay"]


def test_not_a_booking_forgets_it_and_ignores_it_next_time(book):
    seen(book, 1, [flight()])
    bid = trips(book)[0]["bookings"][0]["id"]
    assert book.remove("u1", bid)["trips"] == []
    assert seen(book, 2, [flight()]) is False
    with pytest.raises(KeyError):
        book.remove("u1", bid)


def test_each_person_has_their_own_trips(book):
    seen(book, 1, [flight()], user="u1")
    assert book.view("u2")["trips"] == []
    with pytest.raises(KeyError):
        book.remove("u2", trips(book)[0]["bookings"][0]["id"])


# ---------- what is kept ----------

def test_values_are_cut_short_and_control_characters_removed(book):
    seen(book, 1, [flight(provider="Qan\x00tas " + "x" * 200, reference="R" * 90)])
    b = trips(book)[0]["bookings"][0]
    assert len(b["provider"]) <= 60 and len(b["reference"]) <= 30 and "\x00" not in json.dumps(book.vault.g)


def test_nothing_from_the_email_itself_is_kept(book):
    seen(book, 1, [flight()])
    stored = json.dumps(book.vault.g)
    assert "subject" not in stored and "sender" not in stored and "@" not in stored and "http" not in stored


def test_only_a_few_bookings_per_email_and_only_known_kinds(book):
    rows = [flight(reference=f"R{n}AB", start=when(20 + 5 * n)) for n in range(10)] + [{"kind": "boat", "start": when(20)}, "x", None]
    seen(book, 1, rows)
    assert len([b for t in trips(book) for b in t["bookings"]]) == 6


# ---------- the calendar ----------

def items(book):
    return {i["kind"]: i for i in book.calendar_items("u1")}


def test_the_calendar_gets_each_booking_with_words_and_no_time_zone_guessing(book):
    seen(book, 1, [flight(), stay(), car()])
    got = items(book)
    assert got["flight"]["summary"] == "Flight Melbourne to Lisbon (QF9)" and "Booking reference QX7K2P" in got["flight"]["description"]
    assert got["stay"]["summary"] == "Stay: Hotel Aurora" and got["car"]["summary"] == "Hire car: Hertz, Lisbon airport"
    first, last, timed = calsync.trip_span(got["flight"])
    assert timed and first.endswith("T104500") and last.endswith("T142000")
    first, last, timed = calsync.trip_span(got["stay"])
    assert not timed and first == (TODAY + timedelta(days=21)).strftime("%Y%m%d") and last == (TODAY + timedelta(days=27)).strftime("%Y%m%d")      # the check-out day is not a night
    first, last, timed = calsync.trip_span(got["car"])
    assert last == (TODAY + timedelta(days=28)).strftime("%Y%m%d")                                                                                  # the return day is a day with the car


def test_a_flight_with_no_time_is_an_all_day_entry_and_one_with_no_arrival_lasts_an_hour():
    base = {"id": "v" + "a" * 23, "kind": "flight", "start": "2026-11-03", "end": None, "start_time": None, "end_time": None}
    assert calsync.trip_span(base) == ("20261103", "20261104", False)
    assert calsync.trip_span({**base, "start_time": "23:30"}) == ("20261103T233000", "20261104T003000", True)


def test_the_event_text_is_escaped_and_private_when_titles_are_off(book):
    seen(book, 1, [flight(provider="Air, Line; \\ Co")])
    b = items(book)["flight"]
    text = calsync.calendar_text([calsync.trip_event_lines(b, titles=True, link="", stamp=0)])
    assert "UID:" + b["id"] + "@enveliq" in text and "DTSTART:" in text and "SUMMARY:Flight Melbourne to Lisbon" in text.replace("\r\n ", "")
    assert all(len(line.encode()) <= 75 for line in text.split("\r\n"))
    private = calsync.calendar_text([calsync.trip_event_lines(b, titles=False, link="", stamp=0)])
    assert "Lisbon" not in private and "QX7K2P" not in private and "SUMMARY:Enveliq trip" in private and "DESCRIPTION" not in private
    g = calsync.trip_google_body(b, True, "")
    assert g["start"] == {"dateTime": (TODAY + timedelta(days=20)).isoformat() + "T10:45:00"} and g["id"] == b["id"]
    assert calsync.trip_google_body(b, False, "")["summary"] == "Enveliq trip"


def test_switching_the_calendar_off_empties_it_and_a_cancelled_or_old_booking_is_never_in_it(book):
    seen(book, 1, [flight(), stay()])
    seen(book, 2, [stay(status="cancelled")], at=NOW - 60)
    assert list(items(book)) == ["flight"]
    told = []
    book.changed = told.append
    assert book.set_calendar("u1", False)["calendar"] is False and book.calendar_items("u1") == [] and told == ["u1"]
    with pytest.raises(ValueError):
        book.set_calendar("u1", "yes")
    book.set_calendar("u1", True)
    old = T.TripBook(book.vault, clock=lambda: NOW + 25 * 86400)
    assert [i["kind"] for i in old.calendar_items("u1")] == []                                 # ended more than a day ago


def test_the_calendar_mirror_is_told_when_a_booking_arrives(book):
    told = []
    book.changed = told.append
    seen(book, 1, [flight()])
    assert told == ["u1"]
    seen(book, 1, [flight()])
    assert told == ["u1"]                                                                      # nothing changed, nobody told


# ---------- reading the AI's answer ----------

def test_the_reply_may_carry_trips_and_only_valid_ones():
    base = {"summary": "s", "category": "Travel", "priority": "low", "action_required": False}
    out = llm.parse_reply(json.dumps({**base, "trips": [flight(), {**stay(), "status": "Changed"}, {"kind": "boat", "start": "x"}, {"kind": "car"}, "x", {**car(), "status": "lost"}]}))
    assert [t["kind"] for t in out["trips"]] == ["flight", "stay"] and out["trips"][1]["status"] == "changed"
    assert "trips" not in llm.parse_reply(json.dumps({**base, "trips": []}))
    assert "trips" not in llm.parse_reply(json.dumps({**base, "trips": "flight"}))
    assert len(llm.parse_reply(json.dumps({**base, "trips": [flight(reference=f"R{n}") for n in range(20)]}))["trips"]) == 6
    long = llm.parse_reply(json.dumps({**base, "trips": [flight(provider="p" * 300)]}))["trips"][0]
    assert len(long["provider"]) == 60


def test_the_prompt_asks_for_the_facts_and_forbids_working_out_dates():
    assert "trips" in llm.FIXED_PROMPT and "Do not work out any date or time yourself" in llm.FIXED_PROMPT


# ---------- through the app ----------

def real(days: int, clock: str = "") -> str:
    d = date.today() + timedelta(days=days)
    return f"{d.day} {d:%b} {d.year}" + (f" {clock}" if clock else "")


def reply_rows():
    return [flight(start=real(20, "10:45"), end=real(21, "14:20")),
            flight(detail="QF10", **{"from": "Lisbon", "to": "Melbourne", "start": real(27, "09:00"), "end": real(28, "06:30")}),
            stay(start=real(21, "3:00 pm"), end=real(27, "11 am"))]


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("ENVELIQ_NOTIFY_ALLOWED_HOSTS", "127.0.0.1")
    model = FakeModel(reply=json.dumps({**GOOD, "task": None, "action_required": False, "trips": reply_rows()}))
    appm, client, bridge = start(tmp_path, model)
    yield appm, client, bridge, model
    bridge.close()
    model.close()


def summarise(client, bridge):
    aid = account(client, bridge)
    client.post(f"/api/v1/accounts/{aid}/sync", json={})
    r = client.post(f"/api/v1/accounts/{aid}/summarise", json={})
    assert r.status_code == 200, r.text
    return aid


def test_a_summary_makes_a_trip_and_the_routes_work(env):
    appm, client, bridge, _ = env
    summarise(client, bridge)
    r = client.get("/api/v1/me/trips")
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
    body = r.json()
    assert body["enabled"] and len(body["trips"]) == 1                                  # three emails, one trip
    trip = body["trips"][0]
    assert trip["title"] == "Trip to Lisbon" and len(trip["bookings"]) == 3
    bid = trip["bookings"][0]["id"]
    assert client.put("/api/v1/me/trips/settings", json={"calendar": False}).json()["calendar"] is False
    assert client.put("/api/v1/me/trips/settings", json={"calendar": "no"}).status_code == 422
    assert client.put("/api/v1/me/trips/settings", json={"calendar": True, "x": 1}).status_code == 422
    assert client.post("/api/v1/me/trips/not-an-id/remove").status_code == 422
    assert client.post("/api/v1/me/trips/v" + "0" * 23 + "/remove").status_code == 404
    assert len(client.post(f"/api/v1/me/trips/{bid}/remove").json()["trips"][0]["bookings"]) == 2


def test_it_needs_a_signed_in_person(env):
    from fastapi.testclient import TestClient
    appm, _, _, _ = env
    anon = TestClient(appm.app)
    assert anon.get("/api/v1/me/trips").status_code in (401, 403)
    assert anon.put("/api/v1/me/trips/settings", json={"calendar": True}).status_code in (401, 403)
    assert anon.post("/api/v1/me/trips/v" + "0" * 23 + "/remove").status_code in (401, 403)


def test_turned_off_nothing_is_followed_and_nothing_is_kept(env):
    appm, client, bridge, _ = env
    assert client.put("/api/v1/me/features", json={"travel": False}).status_code == 200
    summarise(client, bridge)
    assert client.get("/api/v1/me/trips").json()["enabled"] is False and client.get("/api/v1/me/trips").json()["trips"] == []
    assert appm.vault.get_global(T.RECORD_PREFIX + client.get("/api/v1/me").json()["id"]) is None
    assert client.put("/api/v1/me/trips/settings", json={"calendar": False}).status_code == 403


def test_the_administrator_can_switch_it_off_for_everyone(env):
    appm, client, bridge, _ = env
    assert client.put("/api/v1/admin/features", json={"travel": False}).status_code == 200
    assert client.get("/api/v1/me/features").json()["effective"]["travel"] is False
    summarise(client, bridge)
    assert client.get("/api/v1/me/trips").json()["trips"] == []


def test_another_person_sees_none_of_it(env):
    from helpers import create_user, sign_in
    appm, client, bridge, _ = env
    summarise(client, bridge)
    create_user(client, "second")
    other = sign_in(appm, "second")
    assert other.get("/api/v1/me/trips").json()["trips"] == []
    bid = client.get("/api/v1/me/trips").json()["trips"][0]["bookings"][0]["id"]
    assert other.post(f"/api/v1/me/trips/{bid}/remove").status_code == 404
    assert len(client.get("/api/v1/me/trips").json()["trips"][0]["bookings"]) == 3


def test_the_private_calendar_feed_and_a_caldav_calendar_carry_the_bookings(env):
    appm, client, bridge, _ = env
    remote = Remote()
    try:
        summarise(client, bridge)
        path = client.post("/api/v1/me/sync/feed").json()["url"].split(appm.PUBLIC_ORIGIN)[1]
        feed = client.get(path).text.replace("\r\n ", "")
        assert "SUMMARY:Flight Melbourne to Lisbon (QF9)" in feed and "SUMMARY:Stay: Hotel Aurora" in feed
        r = client.put("/api/v1/me/sync/caldav", json={"enabled": True, "url": remote.url + "/dav/tasks", "user": "sam", "password": "app-password"})
        assert r.status_code == 200
        assert client.post("/api/v1/me/sync/now").json()["results"]["caldav"] is None
        trip_files = [p for p in remote.events if "/enveliq-v" in p]
        assert len(trip_files) == 3 and any("Hotel Aurora" in remote.events[p].replace("\r\n ", "") for p in trip_files)
        client.put("/api/v1/me/trips/settings", json={"calendar": False})                  # switching it off takes them out of the calendar
        client.post("/api/v1/me/sync/now")
        assert not [p for p in remote.events if "/enveliq-v" in p]
        client.put("/api/v1/me/trips/settings", json={"calendar": True})
        client.post("/api/v1/me/sync/now")
        bid = client.get("/api/v1/me/trips").json()["trips"][0]["bookings"][0]["id"]
        client.post(f"/api/v1/me/trips/{bid}/remove")
        client.post("/api/v1/me/sync/now")
        assert len([p for p in remote.events if "/enveliq-v" in p]) == 2                    # removing a booking removes its entry
    finally:
        remote.close()


def test_an_email_with_a_be_careful_flag_files_nothing(tmp_path):
    from fake_bridge import FakeBridge, raw_email
    from helpers import load_app, setup_admin
    from test_bridge import add_account
    bridge = FakeBridge(tmp_path)
    bridge.add(1, raw_email("Your flight is changed", '"PayPal" <help@gmail.example>', "me@example.invalid", message_id="<s1@example.invalid>",
                            extra="Authentication-Results: mx.example; dmarc=fail\r\n"))
    model = FakeModel(reply=json.dumps({**GOOD, "task": None, "action_required": False, "trips": reply_rows()}))
    (tmp_path / "data").mkdir()
    appm = load_app(tmp_path / "data", ENVELIQ_BRIDGE_CA_FILE=str(bridge.cert_path), ENVELIQ_LLM_URL=model.url, ENVELIQ_LLM_MODEL="test-model")
    client, _ = setup_admin(appm)
    aid = add_account(client, bridge, settings={"smtp_port": bridge.smtp_port, "send_identities": [], "ai_summaries": True})
    client.post(f"/api/v1/accounts/{aid}/sync", json={})
    assert client.post(f"/api/v1/accounts/{aid}/summarise", json={}).status_code == 200
    assert client.get("/api/v1/me/trips").json()["trips"] == []
    bridge.close()
    model.close()
