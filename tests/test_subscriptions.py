"""Subscriptions and free trials: filed from summaries, dates worked out in code, nudged before they happen."""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from test_bridge import mails  # noqa: F401
from test_summaries import account, start  # noqa: F401
from test_llm import FakeModel, GOOD
from backend.mail import llm
from backend.mail import subscriptions as S


class FakeVault:
    def __init__(self):
        self.g: dict = {}

    def get_global(self, k):
        return self.g.get(k)

    def set_global(self, k, v):
        self.g[k] = json.loads(json.dumps(v))

    def get_user(self, uid):
        raise KeyError(uid)


def stamp(y, m, d, h=12):
    return datetime(y, m, d, h, tzinfo=timezone.utc).timestamp()


NOW = stamp(2026, 10, 11)            # a fixed moment, so dates never depend on the day the tests run


@pytest.fixture
def book():
    return S.SubBook(FakeVault(), clock=lambda: NOW)


def sub(kind="receipt", **kw):
    return {"kind": kind, "service": "Streamly", "amount": "$12.99", "period": "monthly", "renews_on": None, "trial_ends_on": None, "trial_days": None, **kw}


def seen(book, n, raw, at=NOW - 3600, user="u1", link=None):
    return book.observe(user, "a1", f"m{n}", at, raw, link)


def only(book, user="u1"):
    items = book.view(user)["items"]
    assert len(items) == 1
    return items[0]


# ---------- dates are worked out here ----------

def test_a_stated_renewal_date_is_used_and_counted_in_days(book):
    assert seen(book, 1, sub("renewal_notice", renews_on="14 Oct 2026"))
    nxt = only(book)["next"]
    assert nxt == {"kind": "renews", "on": "2026-10-14", "days": 3}


def test_a_receipt_with_no_date_gives_an_estimate_one_period_later_and_says_so(book):
    seen(book, 1, sub("receipt"), at=stamp(2026, 10, 8))
    row = only(book)
    assert row["next"]["on"] == "2026-11-08" and row["estimated"] is True
    seen(book, 2, sub("renewal_notice", renews_on="9 Nov 2026"), at=stamp(2026, 10, 9))
    row = only(book)
    assert row["next"]["on"] == "2026-11-09" and row["estimated"] is False         # a real date replaces the estimate


def test_a_date_that_has_passed_rolls_forward_by_the_billing_period():
    assert S.roll_forward(date(2026, 1, 31), "monthly", date(2026, 3, 1)) == date(2026, 3, 31)       # the 31st stays the 31st where it can
    assert S.roll_forward(date(2026, 1, 31), "monthly", date(2026, 2, 10)) == date(2026, 2, 28)
    assert S.roll_forward(date(2025, 10, 14), "yearly", date(2026, 10, 11)) == date(2026, 10, 14)
    assert S.roll_forward(date(2026, 9, 1), "weekly", date(2026, 10, 11)) == date(2026, 10, 13)
    assert S.roll_forward(date(2026, 9, 1), "fortnightly", date(2026, 10, 11)) == date(2026, 10, 13)
    assert S.roll_forward(date(2026, 6, 1), "quarterly", date(2026, 10, 11)) == date(2026, 12, 1)
    assert S.roll_forward(date(2026, 9, 1), None, date(2026, 10, 11)) is None                          # no period: nothing is guessed
    assert S.roll_forward(date(2026, 10, 11), None, date(2026, 10, 11)) == date(2026, 10, 11)


def test_a_free_trial_counts_days_from_the_email_date_when_only_a_length_is_given(book):
    seen(book, 1, sub("trial_started", trial_days=30, amount=None, period=None), at=stamp(2026, 10, 1))
    row = only(book)
    assert row["status"] == "trial" and row["next"] == {"kind": "trial_ends", "on": "2026-10-31", "days": 20}


def test_a_stated_trial_end_wins_over_a_length(book):
    seen(book, 1, sub("trial_started", trial_ends_on="25 Oct 2026", trial_days=30), at=stamp(2026, 10, 1))
    assert only(book)["next"]["on"] == "2026-10-25"


def test_the_first_charge_ends_the_trial(book):
    seen(book, 1, sub("trial_started", trial_ends_on="14 Oct 2026"), at=stamp(2026, 10, 1))
    seen(book, 2, sub("receipt", renews_on="14 Nov 2026"), at=stamp(2026, 10, 14))
    row = only(book)
    assert row["status"] == "active" and row["next"] == {"kind": "renews", "on": "2026-11-14", "days": 34}


def test_a_trial_that_ended_shows_no_date(book):
    seen(book, 1, sub("trial_started", trial_ends_on="5 Oct 2026"), at=stamp(2026, 10, 1))
    row = only(book)
    assert row["next"] is None and row["trial_over"] is True


def test_a_date_far_from_the_email_is_ignored(book):
    seen(book, 1, sub("renewal_notice", renews_on="2031-01-01"))
    assert only(book)["next"] is None


def test_the_day_is_the_persons_own(book):
    seen(book, 1, sub("renewal_notice", renews_on="12 Oct 2026"))
    late = stamp(2026, 10, 11, 20)                               # still the 11th in London, already the 12th in Melbourne
    for zone, days in (("Europe/London", 1), ("Australia/Melbourne", 0)):
        b = S.SubBook(book.vault, tz_of=lambda uid, z=zone: z, clock=lambda: late)
        assert b.view("u1")["items"][0]["next"]["days"] == days


# ---------- matching ----------

def test_emails_about_one_service_make_one_subscription(book):
    seen(book, 1, sub("started", amount="$10.00"), at=NOW - 5 * 86400)
    seen(book, 2, sub("receipt", amount="$12.99"), at=NOW - 3600)
    row = only(book)
    assert row["service"] == "Streamly" and row["amount"] == "$12.99"
    assert seen(book, 2, sub("receipt")) is False                                  # the very same email twice
    seen(book, 3, sub("receipt", service="STREAMLY!"), at=NOW - 7200)
    assert len(book.view("u1")["items"]) == 1                                      # punctuation and case do not matter


def test_an_older_email_never_overwrites_newer_facts(book):
    seen(book, 1, sub("renewal_notice", renews_on="14 Nov 2026", amount="$15.00"), at=NOW - 3600)
    seen(book, 2, sub("renewal_notice", renews_on="14 Oct 2026", amount="$10.00"), at=NOW - 5 * 86400)
    row = only(book)
    assert row["next"]["on"] == "2026-11-14" and row["amount"] == "$15.00"


def test_cancelling_is_remembered_and_a_new_start_brings_it_back(book):
    seen(book, 1, sub("receipt"), at=NOW - 5 * 86400)
    seen(book, 2, sub("cancelled"), at=NOW - 3 * 86400)
    row = only(book)
    assert row["status"] == "cancelled" and row["next"] is None
    seen(book, 3, sub("receipt"), at=NOW - 86400)
    assert only(book)["status"] == "cancelled"                                     # a last bill is not a restart
    seen(book, 4, sub("started"), at=NOW - 3600)
    assert only(book)["status"] == "active"


def test_something_that_is_not_a_subscription_is_ignored(book):
    for raw in (None, "x", {"kind": "refund", "service": "Streamly"}, sub(service=""), sub(service="  \x00 "), sub(kind="unknown")):
        assert seen(book, 9, raw) is False
    assert book.view("u1")["items"] == []


def test_each_person_has_their_own_list(book):
    seen(book, 1, sub("receipt"), user="u1")
    assert book.view("u2")["items"] == []
    with pytest.raises(KeyError):
        book.act("u2", book.view("u1")["items"][0]["id"], "cancelled")


# ---------- what is kept ----------

def test_values_are_cut_short_and_control_characters_removed(book):
    seen(book, 1, sub("receipt", service="Stream\x00ly " + "x" * 200, amount="$" + "9" * 90))
    raw = json.dumps(book.vault.g)
    assert "\\u0000" not in raw
    row = only(book)
    assert len(row["service"]) <= 60 and len(row["amount"]) <= 30


def test_no_email_text_subject_or_sender_is_kept(book):
    seen(book, 1, sub("receipt"), link="https://streamly.example/")
    stored = json.dumps(book.vault.g)
    assert "subject" not in stored and "sender" not in stored and "@" not in stored


def test_the_link_is_the_senders_own_public_home_page_only():
    assert S.company_link("Streamly <billing@mail.streamly.example>") == "https://streamly.example/"
    assert S.company_link("billing@streamly.co.uk") == "https://streamly.co.uk/"
    for odd in ("billing@gmail.com", "x@mail.sendgrid.net", "pay@stripe.com", "a@192.168.1.5", "a@printer.local", "a@localhost", "nobody", None, "", "a@b"):
        assert S.company_link(odd) is None


def test_a_link_that_is_not_a_public_address_is_never_stored_or_shown(book):
    seen(book, 1, sub("receipt"), link="http://192.168.1.10/admin")
    assert only(book)["link"] is None
    seen(book, 2, sub("receipt"), link="https://streamly.example/")
    row = only(book)
    assert row["link"] == {"url": "https://streamly.example/", "host": "streamly.example"}


def test_old_things_are_forgotten():
    v = FakeVault()
    early = S.SubBook(v, clock=lambda: NOW)
    early.observe("u1", "a1", "m1", NOW - 3600, sub("cancelled"))
    early.observe("u1", "a1", "m2", NOW - 3600, sub("receipt", service="Otherly"))
    later = S.SubBook(v, clock=lambda: NOW + 31 * 86400)
    names = [i["service"] for i in later.view("u1")["items"]]
    assert names == ["Otherly"]                                                    # cancelled ones go after 30 days
    gone = S.SubBook(v, clock=lambda: NOW + 401 * 86400)
    assert gone.view("u1")["items"] == []


# ---------- what the person can do ----------

def test_not_a_subscription_forgets_it_and_ignores_it_next_time(book):
    seen(book, 1, sub("receipt"))
    sid = only(book)["id"]
    assert book.act("u1", sid, "not_subscription")["items"] == []
    assert seen(book, 2, sub("receipt")) is False


def test_cancelled_and_keep(book):
    seen(book, 1, sub("receipt"))
    sid = only(book)["id"]
    assert book.act("u1", sid, "cancelled")["items"][0]["status"] == "cancelled"
    assert book.act("u1", sid, "keep")["items"][0]["status"] == "active"
    with pytest.raises(ValueError):
        book.act("u1", sid, "keep")                                                # only a cancelled one can be kept
    with pytest.raises(ValueError):
        book.act("u1", sid, "explode")
    with pytest.raises(KeyError):
        book.act("u1", "b" + "0" * 23, "cancelled")


def test_the_number_of_days_is_one_to_fourteen(book):
    assert book.view("u1")["nudge_days"] == 3
    assert book.set_nudge_days("u1", 14)["nudge_days"] == 14
    for bad in (0, 15, -1, True, "3", None, 2.5):
        with pytest.raises(ValueError):
            book.set_nudge_days("u1", bad)
    assert book.view("u1")["nudge_days"] == 14


def test_the_nudge_list_holds_what_is_inside_the_window_and_changes_with_the_date(book):
    seen(book, 1, sub("renewal_notice", renews_on="14 Oct 2026"))
    seen(book, 2, sub("renewal_notice", service="Faraway", renews_on="24 Oct 2026"))
    due = book.due_nudges("u1")
    assert [d["service"] for d in due] == ["Streamly"] and due[0]["days"] == 3 and due[0]["key"].endswith("|2026-10-14")
    book.set_nudge_days("u1", 1)
    assert book.due_nudges("u1") == []
    book.set_nudge_days("u1", 14)
    assert [d["service"] for d in book.due_nudges("u1")] == ["Streamly", "Faraway"]


# ---------- reading the AI's answer ----------

def test_the_reply_may_carry_a_subscription_and_only_a_valid_one():
    base = {"summary": "s", "category": "Finance", "priority": "low", "action_required": False}
    out = llm.parse_reply(json.dumps({**base, "subscription": {**sub("trial_started", trial_days=30, period="Monthly"), "kind": "Trial Started"}}))
    assert out["subscription"]["kind"] == "trial_started" and out["subscription"]["trial_days"] == 30 and out["subscription"]["period"] == "monthly"
    assert llm.parse_reply(json.dumps({**base, "subscription": sub(period="every 2 months")}))["subscription"]["period"] is None
    assert llm.parse_reply(json.dumps({**base, "subscription": sub(trial_days=9999)}))["subscription"]["trial_days"] is None
    assert llm.parse_reply(json.dumps({**base, "subscription": sub(trial_days=True)}))["subscription"]["trial_days"] is None
    for bad in (None, "receipt", {"kind": "refund", "service": "x"}, sub(service="")):
        assert "subscription" not in llm.parse_reply(json.dumps({**base, "subscription": bad}))


def test_the_prompt_asks_for_the_facts_and_forbids_working_out_dates():
    assert "subscription" in llm.FIXED_PROMPT and "Do not work out any date yourself" in llm.FIXED_PROMPT


# ---------- through the app ----------

SYD = ZoneInfo("Australia/Sydney")
SOON = (date.today() + timedelta(days=5)).isoformat()          # the app runs on the real day, so these dates follow it


@pytest.fixture
def env(tmp_path):
    reply = {**GOOD, "task": None, "action_required": False, "subscription": sub("renewal_notice", renews_on=SOON)}
    model = FakeModel(reply=json.dumps(reply))
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


def test_a_summary_makes_a_subscription_and_the_routes_work(env):
    appm, client, bridge, _ = env
    summarise(client, bridge)
    r = client.get("/api/v1/me/subscriptions")
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
    body = r.json()
    assert body["enabled"] and len(body["items"]) == 1                              # three emails, one subscription
    s = body["items"][0]
    assert s["service"] == "Streamly" and s["next"]["on"] == SOON and s["link"]["host"] == "example.invalid"
    assert client.put("/api/v1/me/subscriptions/settings", json={"nudge_days": 5}).json()["nudge_days"] == 5
    assert client.put("/api/v1/me/subscriptions/settings", json={"nudge_days": 0}).status_code == 422
    assert client.put("/api/v1/me/subscriptions/settings", json={"nudge_days": 3, "x": 1}).status_code == 422
    assert client.post(f"/api/v1/me/subscriptions/{s['id']}/bogus").status_code == 422
    assert client.post("/api/v1/me/subscriptions/not-an-id/cancelled").status_code == 422
    assert client.post("/api/v1/me/subscriptions/b" + "0" * 23 + "/cancelled").status_code == 404
    assert client.post(f"/api/v1/me/subscriptions/{s['id']}/cancelled").json()["items"][0]["status"] == "cancelled"
    assert client.post(f"/api/v1/me/subscriptions/{s['id']}/not_subscription").json()["items"] == []


def test_it_needs_a_signed_in_person(env):
    from fastapi.testclient import TestClient
    appm, _, _, _ = env
    anon = TestClient(appm.app)
    assert anon.get("/api/v1/me/subscriptions").status_code in (401, 403)
    assert anon.put("/api/v1/me/subscriptions/settings", json={"nudge_days": 3}).status_code in (401, 403)
    assert anon.post("/api/v1/me/subscriptions/b" + "0" * 23 + "/keep").status_code in (401, 403)


def test_turned_off_nothing_is_followed_and_nothing_is_kept(env):
    appm, client, bridge, _ = env
    assert client.put("/api/v1/me/features", json={"subscriptions": False}).status_code == 200
    summarise(client, bridge)
    assert client.get("/api/v1/me/subscriptions").json()["items"] == []
    assert client.get("/api/v1/me/subscriptions").json()["enabled"] is False
    assert appm.vault.get_global(S.RECORD_PREFIX + client.get("/api/v1/me").json()["id"]) is None
    assert client.put("/api/v1/me/subscriptions/settings", json={"nudge_days": 4}).status_code == 403


def test_the_administrator_can_switch_it_off_for_everyone(env):
    appm, client, bridge, _ = env
    assert client.put("/api/v1/admin/features", json={"subscriptions": False}).status_code == 200
    assert client.get("/api/v1/me/features").json()["effective"]["subscriptions"] is False
    summarise(client, bridge)
    assert client.get("/api/v1/me/subscriptions").json()["items"] == []


def test_another_person_sees_none_of_it(env):
    from helpers import create_user, sign_in
    appm, client, bridge, _ = env
    summarise(client, bridge)
    create_user(client, "second")
    other = sign_in(appm, "second")
    assert other.get("/api/v1/me/subscriptions").json()["items"] == []
    sid = client.get("/api/v1/me/subscriptions").json()["items"][0]["id"]
    assert other.post(f"/api/v1/me/subscriptions/{sid}/not_subscription").status_code == 404
    assert len(client.get("/api/v1/me/subscriptions").json()["items"]) == 1


def test_an_email_with_a_be_careful_flag_files_nothing(tmp_path):
    from fake_bridge import FakeBridge, raw_email
    from helpers import load_app, setup_admin
    from test_bridge import add_account
    bridge = FakeBridge(tmp_path)
    bridge.add(1, raw_email("Your subscription renews", '"PayPal" <help@gmail.example>', "me@example.invalid", message_id="<s1@example.invalid>",
                            extra="Authentication-Results: mx.example; dmarc=fail\r\n"))
    model = FakeModel(reply=json.dumps({**GOOD, "task": None, "action_required": False, "subscription": sub("renewal_notice", renews_on=SOON)}))
    (tmp_path / "data").mkdir()
    appm = load_app(tmp_path / "data", ENVELIQ_BRIDGE_CA_FILE=str(bridge.cert_path), ENVELIQ_LLM_URL=model.url, ENVELIQ_LLM_MODEL="test-model")
    client, _ = setup_admin(appm)
    aid = add_account(client, bridge, settings={"smtp_port": bridge.smtp_port, "send_identities": [], "ai_summaries": True})
    client.post(f"/api/v1/accounts/{aid}/sync", json={})
    assert client.post(f"/api/v1/accounts/{aid}/summarise", json={}).status_code == 200
    assert client.get("/api/v1/me/subscriptions").json()["items"] == []
    bridge.close()
    model.close()
