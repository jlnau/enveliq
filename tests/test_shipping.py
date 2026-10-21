"""Shipping: orders followed from the emails that arrive, the Did-it-arrive question, and what is (not) kept."""
from __future__ import annotations

import json
import time

import pytest

from test_bridge import mails  # noqa: F401
from test_summaries import account, start  # noqa: F401
from test_llm import FakeModel, GOOD
from backend.mail import llm
from backend.mail import shipping as S


class FakeVault:
    def __init__(self):
        self.g: dict = {}

    def get_global(self, k):
        return self.g.get(k)

    def set_global(self, k, v):
        self.g[k] = json.loads(json.dumps(v))

    def get_user(self, uid):
        raise KeyError(uid)


NOW = 1_790_000_000.0       # a fixed moment, so dates never depend on the day the tests run


@pytest.fixture
def book():
    v = FakeVault()
    b = S.ShipBook(v, clock=lambda: NOW)
    b.vault_ = v
    return b


def ship(kind="order_confirmed", **kw):
    return {"kind": kind, "shop": "Brightwater Books", "order_number": "BB-5509", "tracking_number": None, "carrier": None, "expected": None, "items": "3 books", **kw}


def seen(book, n, shipment, subject="Hello", at=NOW - 1000, user="u1", account="a1"):
    return book.observe(user, account, f"m{n}", subject, at, shipment)


# ---------- keys, cleaning, links ----------

def test_keys_ignore_punctuation_and_case_and_need_a_digit():
    assert S.order_key("#BB-5509") == S.order_key("bb 5509") == "bb5509"
    assert S.order_key("order") is None and S.order_key("12") is None and S.order_key(None) is None
    assert S.tracking_key("hf-9984 210") == "HF9984210" and S.tracking_key("short1") is None


def test_clean_strips_controls_and_cuts_length():
    assert S.clean("a\x00b\x1b[31m  c\n d", 50) == "ab[31m c d"
    assert len(S.clean("x" * 500, 40)) == 40 and S.clean(["x"], 5) == ""


def test_track_links_come_only_from_the_fixed_list():
    assert S.track_url("Australia Post", "SP4471002318AU") == "https://auspost.com.au/mypost/track/details/SP4471002318AU"
    assert S.track_url("Evil Carrier", "SP4471002318AU") is None
    assert S.track_url("UPS", None) is None
    u = S.track_url("DHL", "1234 5678/90?x=1&y=<script>")
    assert u.startswith("https://www.dhl.com/") and "<" not in u and " " not in u and "x=1&y" not in u
    assert S.track_url("javascript:alert(1) ups", "1Z999AA10123456784").startswith("https://www.ups.com/")


# ---------- matching ----------

def test_one_order_from_several_emails(book):
    assert seen(book, 1, ship("order_confirmed"), "Thanks for your order", NOW - 300000)
    assert seen(book, 2, ship("shipped", order_number=None, tracking_number="HF-9984210", carrier="Harbour Freight", expected="Tue 13 Oct"), "On its way", NOW - 200000) is True
    # order number joins the tracking number to the same order
    assert seen(book, 3, ship("shipped", tracking_number="HF-9984210"), "Shipped", NOW - 190000)
    rows = book.view("u1")["orders"]
    assert len(rows) == 1
    o = rows[0]
    assert o["status"] == "shipped" and o["order_number"] == "BB-5509" and o["carrier"] == "Harbour Freight" and o["tracking"]
    assert [e["subject"] for e in o["events"]] == ["Shipped", "On its way", "Thanks for your order"]      # newest first
    assert not o["unsure"] and not o["needs_confirm"]


def test_two_different_orders_stay_apart(book):
    seen(book, 1, ship(order_number="BB-1111"))
    seen(book, 2, ship(order_number="BB-2222"))
    assert len(book.view("u1")["orders"]) == 2


def test_no_numbers_joins_the_only_open_order_of_that_shop(book):
    seen(book, 1, ship())
    seen(book, 2, ship("shipped", order_number=None))
    rows = book.view("u1")["orders"]
    assert len(rows) == 1 and rows[0]["status"] == "shipped"


def test_no_numbers_and_two_open_orders_asks_the_person(book):
    seen(book, 1, ship(order_number="BB-1111"))
    seen(book, 2, ship(order_number="BB-2222"))
    seen(book, 3, ship("shipped", order_number=None))
    rows = book.view("u1")["orders"]
    assert len(rows) == 3 and sum(1 for r in rows if r["unsure"]) == 1


def test_an_email_with_no_numbers_and_no_order_is_unsure(book):
    seen(book, 1, ship(order_number=None, shop="Cobalt Outfitters"))
    (o,) = book.view("u1")["orders"]
    assert o["unsure"] and o["track_url"] is None
    book.act("u1", o["id"], "track")
    assert not book.view("u1")["orders"][0]["unsure"]


def test_the_same_email_summarised_twice_is_filed_once(book):
    assert seen(book, 1, ship()) is True
    assert seen(book, 1, ship()) is False
    assert len(book.view("u1")["orders"][0]["events"]) == 1


def test_something_that_is_not_a_shipment_is_ignored(book):
    for bad in (None, "x", {}, {"kind": "refund"}, {"kind": "shipped"}, {"kind": "shipped", "shop": "", "order_number": "nope"}):
        assert seen(book, 1, bad) is False
    assert book.view("u1")["orders"] == []


# ---------- status, dates ----------

def test_status_only_moves_forward_and_a_later_date_is_delayed(book):
    seen(book, 1, ship("shipped", expected="Tue 13 Oct"), at=NOW - 5000)
    seen(book, 2, ship("order_confirmed"), at=NOW - 4000)                       # a late "order received" must not undo "shipped"
    o = book.view("u1")["orders"][0]
    assert o["status"] == "shipped" and o["expected"] and not o["delayed"]
    first = o["expected"]
    seen(book, 3, ship("delayed", expected="Thu 15 Oct"), at=NOW - 3000)
    o = book.view("u1")["orders"][0]
    assert o["status"] == "shipped" and o["delayed"] and o["prev_expected"] == first and o["expected"] > first


def test_an_earlier_date_is_not_called_delayed(book):
    seen(book, 1, ship("shipped", expected="Thu 15 Oct"), at=NOW - 5000)
    seen(book, 2, ship("out_for_delivery", expected="Tue 13 Oct"), at=NOW - 4000)
    o = book.view("u1")["orders"][0]
    assert o["status"] == "out_for_delivery" and not o["delayed"]


# ---------- Did it arrive? ----------

def test_delivered_asks_then_confirm_removes_the_question(book):
    seen(book, 1, ship("shipped"), at=NOW - 9000)
    seen(book, 2, ship("delivered"), at=NOW - 100)
    o = book.view("u1")["orders"][0]
    assert o["status"] == "delivered" and o["needs_confirm"] and o["delivered_at"]
    assert book.act("u1", o["id"], "confirm")["orders"][0]["needs_confirm"] is False
    assert book.act("u1", o["id"], "undo")["orders"][0]["needs_confirm"] is True


def test_not_yet_hides_the_question_for_a_day_then_it_returns(book):
    seen(book, 1, ship("delivered"), at=NOW - 100)
    oid = book.view("u1")["orders"][0]["id"]
    book.act("u1", oid, "not_yet")
    assert book.view("u1")["orders"][0]["needs_confirm"] is False
    book.clock = lambda: NOW + S.SNOOZE + 60
    assert book.view("u1")["orders"][0]["needs_confirm"] is True


def test_cannot_confirm_what_has_not_been_delivered(book):
    seen(book, 1, ship("shipped"))
    with pytest.raises(ValueError):
        book.act("u1", book.view("u1")["orders"][0]["id"], "confirm")


def test_arrived_orders_are_forgotten_after_14_days_and_quiet_ones_after_90(book):
    seen(book, 1, ship("delivered", order_number="BB-1111"), at=NOW - 100)
    seen(book, 2, ship("shipped", order_number="BB-2222"), at=NOW - 100)
    book.clock = lambda: NOW + 13 * 86400
    assert len(book.view("u1")["orders"]) == 2
    book.clock = lambda: NOW + 15 * 86400
    assert [o["order_number"] for o in book.view("u1")["orders"]] == ["BB-2222"]
    book.clock = lambda: NOW + 100 * 86400
    assert book.view("u1")["orders"] == []


def test_not_an_order_removes_it_and_it_is_not_made_again(book):
    seen(book, 1, ship())
    oid = book.view("u1")["orders"][0]["id"]
    book.act("u1", oid, "not_order")
    assert book.view("u1")["orders"] == []
    assert seen(book, 2, ship("shipped")) is False                              # same order number, said no
    assert seen(book, 3, ship(order_number="BB-7777")) is True                   # another order from the same shop is fine


def test_unknown_order_or_action(book):
    with pytest.raises(KeyError):
        book.act("u1", "s" + "0" * 23, "confirm")
    with pytest.raises(ValueError):
        book.act("u1", "s" + "0" * 23, "explode")


# ---------- what the order is for, and the person's own note ----------

def test_a_fuller_description_in_a_later_email_wins_and_the_total_is_kept(book):
    seen(book, 1, ship("order_confirmed", items="headphones"), at=NOW - 3000)
    seen(book, 2, ship("shipped", items="Sony WH-1000XM5 headphones (black), carry case", total="$449.00"), at=NOW - 2000)
    seen(book, 3, ship("shipped", items="parcel"), at=NOW - 1000)                  # a shorter one does not replace it
    (o,) = book.view("u1")["orders"]
    assert o["items"] == "Sony WH-1000XM5 headphones (black), carry case" and o["total"] == "$449.00"


def test_each_email_on_an_order_carries_its_one_way_mark(book):
    import hashlib
    book.observe("u1", "a1", "<m1@example.invalid>", "Thanks", NOW - 10, ship())
    (o,) = book.view("u1")["orders"]
    assert o["events"][0]["m"] == hashlib.sha256(b"a1|<m1@example.invalid>").hexdigest()[:16]


def test_the_person_can_keep_a_note_on_an_order(book):
    seen(book, 1, ship())
    oid = book.view("u1")["orders"][0]["id"]
    assert book.view("u1")["orders"][0]["note"] == ""
    out = book.set_note("u1", oid, "  Birthday present\r\nfor   Sam\x00\n\n\n\nwrap it  ")
    assert out["orders"][0]["note"] == "Birthday present\nfor Sam\n\nwrap it"
    assert len(book.set_note("u1", oid, "x" * 900)["orders"][0]["note"]) == 500
    assert book.set_note("u1", oid, "")["orders"][0]["note"] == ""
    with pytest.raises(KeyError):
        book.set_note("u1", "s" + "0" * 23, "hi")
    with pytest.raises(ValueError):
        book.set_note("u1", oid, ["not text"])


def test_a_note_survives_later_emails_about_the_order(book):
    seen(book, 1, ship())
    oid = book.view("u1")["orders"][0]["id"]
    book.set_note("u1", oid, "new headphones")
    seen(book, 2, ship("shipped"))
    assert book.view("u1")["orders"][0]["note"] == "new headphones"


# ---------- people stay apart, and what is kept ----------

def test_each_person_has_their_own_orders(book):
    seen(book, 1, ship(), user="u1")
    assert book.view("u2")["orders"] == [] and len(book.view("u1")["orders"]) == 1
    assert seen(book, 2, ship(), user=None) is False


def test_hostile_values_are_cut_down_and_nothing_else_is_kept(book):
    seen(book, 1, {"kind": "shipped", "shop": "<img src=x onerror=1>" + "A" * 300, "order_number": "9" * 200, "tracking_number": "ZZ\x00" + "1" * 90,
                   "carrier": "ups" + "x" * 99, "expected": "soon" * 40, "items": "i" * 999, "body": "THE WHOLE EMAIL", "from": "x@y.invalid"},
         subject="S" * 500)
    rec = json.dumps(book.vault_.g[S.RECORD_PREFIX + "u1"])
    assert "THE WHOLE EMAIL" not in rec and "x@y.invalid" not in rec
    o = book.view("u1")["orders"][0]
    assert len(o["shop"]) <= 60 and len(o["items"]) <= 200 and len(o["events"][0]["subject"]) <= 200 and "\x00" not in rec


def test_the_record_holds_no_message_or_account_ids(book):
    book.observe("u1", "acct-secret-77", "<msgid-secret-88@example.invalid>", "Thanks", NOW - 10, ship())
    rec = json.dumps(book.vault_.g[S.RECORD_PREFIX + "u1"])
    assert "secret" not in rec                                                   # only a short one-way mark of the email is kept


# ---------- the AI reply ----------

def test_the_reply_may_carry_a_shipment_and_only_a_valid_one():
    base = {"summary": "Your order shipped.", "category": "Information", "priority": "low", "action_required": False}
    out = llm.parse_reply(json.dumps({**base, "shipment": ship("shipped", tracking_number="HF-9984210", carrier="Harbour Freight")}))
    assert out["shipment"]["kind"] == "shipped" and out["shipment"]["tracking_number"] == "HF-9984210"
    assert "shipment" not in llm.parse_reply(json.dumps({**base, "shipment": None}))
    assert "shipment" not in llm.parse_reply(json.dumps({**base, "shipment": {"kind": "refund"}}))
    assert "shipment" not in llm.parse_reply(json.dumps({**base, "shipment": "shipped"}))
    assert set(llm.parse_reply(json.dumps(base))) == {"summary", "category", "priority", "action_required", "suggested_task", "act_today", "today_reason"}


def test_the_reply_keeps_a_fuller_item_description_and_the_total():
    base = {"summary": "Your order shipped.", "category": "Information", "priority": "low", "action_required": False}
    long_items = "Sony WH-1000XM5 headphones (black), USB-C cable, carry case and 2 more"
    out = llm.parse_reply(json.dumps({**base, "shipment": ship("shipped", items=long_items, total="$449.00 AUD")}))
    assert out["shipment"]["items"] == long_items and out["shipment"]["total"] == "$449.00 AUD"
    out = llm.parse_reply(json.dumps({**base, "shipment": ship("shipped", items="i" * 500, total="t" * 90)}))
    assert len(out["shipment"]["items"]) == 200 and len(out["shipment"]["total"]) == 30


def test_the_prompt_asks_what_the_order_is_for():
    assert "what the order is for" in llm.FIXED_PROMPT and "total" in llm.FIXED_PROMPT and "Never guess a number or a product" in llm.FIXED_PROMPT


def test_the_prompt_asks_for_the_shipment():
    assert "shipment" in llm.FIXED_PROMPT and "Never guess a number" in llm.FIXED_PROMPT


# ---------- through the app ----------

@pytest.fixture
def env(tmp_path):
    reply = {**GOOD, "task": None, "action_required": False, "shipment": ship("shipped", tracking_number="HF-9984210", carrier="Harbour Freight", expected="Thu 15 Oct")}
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


def test_a_summary_makes_an_order_and_the_routes_work(env):
    appm, client, bridge, _ = env
    summarise(client, bridge)
    r = client.get("/api/v1/me/shipping")
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
    body = r.json()
    assert body["enabled"] and len(body["orders"]) == 1                          # three emails, one order: matched by tracking number
    o = body["orders"][0]
    assert o["shop"] == "Brightwater Books" and o["status"] == "shipped" and len(o["events"]) == 3
    assert o["track_url"] is None                                                # "Harbour Freight" is not on the fixed carrier list
    assert client.post(f"/api/v1/me/shipping/{o['id']}/not_yet").status_code == 200
    assert client.post(f"/api/v1/me/shipping/{o['id']}/bogus").status_code == 422
    assert client.post("/api/v1/me/shipping/not-an-id/track").status_code == 422
    assert client.post("/api/v1/me/shipping/s" + "0" * 23 + "/track").status_code == 404
    assert client.post(f"/api/v1/me/shipping/{o['id']}/not_order").json()["orders"] == []


def test_the_note_route(env):
    appm, client, bridge, _ = env
    summarise(client, bridge)
    oid = client.get("/api/v1/me/shipping").json()["orders"][0]["id"]
    r = client.put(f"/api/v1/me/shipping/{oid}/note", json={"note": "new headphones"})
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store" and r.json()["orders"][0]["note"] == "new headphones"
    assert client.get("/api/v1/me/shipping").json()["orders"][0]["note"] == "new headphones"
    assert client.put(f"/api/v1/me/shipping/{oid}/note", json={"note": "x" * 601}).status_code == 422
    assert client.put(f"/api/v1/me/shipping/{oid}/note", json={"note": "ok", "extra": 1}).status_code == 422
    assert client.put(f"/api/v1/me/shipping/{oid}/note", json={}).status_code == 422
    assert client.put("/api/v1/me/shipping/not-an-id/note", json={"note": "x"}).status_code == 422
    assert client.put("/api/v1/me/shipping/s" + "0" * 23 + "/note", json={"note": "x"}).status_code == 404


def test_it_needs_a_signed_in_person(env):
    from fastapi.testclient import TestClient
    appm, _, _, _ = env
    anon = TestClient(appm.app)
    assert anon.get("/api/v1/me/shipping").status_code in (401, 403)
    assert anon.post("/api/v1/me/shipping/s" + "0" * 23 + "/confirm").status_code in (401, 403)
    assert anon.put("/api/v1/me/shipping/s" + "0" * 23 + "/note", json={"note": "x"}).status_code in (401, 403)


def test_turned_off_nothing_is_followed_and_nothing_is_kept(env):
    appm, client, bridge, _ = env
    assert client.put("/api/v1/me/features", json={"shipping": False}).status_code == 200
    summarise(client, bridge)
    assert client.get("/api/v1/me/shipping").json() == {"enabled": False, "orders": [], "now": pytest.approx(time.time(), abs=60)}
    assert appm.vault.get_global(S.RECORD_PREFIX + client.get("/api/v1/me").json()["id"]) is None


def test_the_administrator_can_switch_it_off_for_everyone(env):
    appm, client, bridge, _ = env
    assert client.put("/api/v1/admin/features", json={"shipping": False}).status_code == 200
    assert client.get("/api/v1/me/features").json()["effective"]["shipping"] is False
    summarise(client, bridge)
    assert client.get("/api/v1/me/shipping").json()["orders"] == []


def test_another_person_sees_none_of_it(env):
    from helpers import create_user, sign_in
    appm, client, bridge, _ = env
    summarise(client, bridge)
    create_user(client, "second")
    other = sign_in(appm, "second")
    assert other.get("/api/v1/me/shipping").json()["orders"] == []
    oid = client.get("/api/v1/me/shipping").json()["orders"][0]["id"]
    assert other.post(f"/api/v1/me/shipping/{oid}/not_order").status_code == 404
    assert other.put(f"/api/v1/me/shipping/{oid}/note", json={"note": "mine now"}).status_code == 404
    assert len(client.get("/api/v1/me/shipping").json()["orders"]) == 1


# ---------- carriers the household adds (v0.62) ----------

def test_the_built_in_list_has_more_carriers():
    assert S.track_url("Couriers Please", "CP123456789").startswith("https://www.couriersplease.com.au/")
    assert S.track_url("Evri", "H0123456789").startswith("https://www.evri.com/")
    assert "Sendle" in S.FIXED_NAMES and "Yodel" in S.FIXED_NAMES


def test_a_tracking_address_needs_exactly_one_number_place_and_must_be_a_public_https_page():
    ok = S.clean_template("https://track.zippy.example/t?id={number}&lang=en")
    assert ok == "https://track.zippy.example/t?id={n}&lang=en"
    assert S.clean_template("https://track.zippy.example/t/zp12345678?x=1", "ZP-12345678") == "https://track.zippy.example/t/{n}?x=1"   # the example number is swapped in
    assert S.clean_template("https://track.zippy.example/t/ZP-12345678", "ZP-12345678") == "https://track.zippy.example/t/{n}"        # with or without its dashes
    for bad in ("http://track.zippy.example/{n}", "https://track.zippy.example/", "https://track.zippy.example/{n}/{n}", "https://localhost/{n}", "https://printer.local/{n}",
                "https://10.0.0.1/{n}", "https://{n}.zippy.example/", "https://zippy.example:99/{n}", "https://u:p@zippy.example/{n}", "javascript:alert({n})",
                "https://zippy.example/ {n}", "https://zippy.example/<{n}>", "https://zippy.example/{n}\"onmouseover=\"x", "https://" + "a" * 300 + ".example/{n}"):
        with pytest.raises(S.CarrierError):
            S.clean_template(bad)
    with pytest.raises(S.CarrierError):
        S.clean_template("https://track.zippy.example/t/abc12", "abc12")             # too short to be trusted as the number


def test_a_carrier_one_person_adds_is_used_for_everyone_and_cannot_clash(book):
    book.add_carrier("u1", "Zippy Post", "https://track.zippy.example/t/{number}")
    assert [c["name"] for c in book.shared_carriers()] == ["Zippy Post"]
    seen(book, 1, ship("shipped", carrier="Zippy Post (AU)", tracking_number="ZP12345678"), user="u2")
    o = book.view("u2")["orders"][0]
    assert o["track_url"] == "https://track.zippy.example/t/ZP12345678"
    assert book.view("u2")["carriers"]["shared"] == [{"id": book.shared_carriers()[0]["id"], "name": "Zippy Post", "mine": False}]
    assert book.view("u1")["carriers"]["shared"][0]["mine"] is True
    for name in ("zippy post", "Sendle", "ups"):
        with pytest.raises(S.CarrierError):
            book.add_carrier("u2", name, "https://other.example/{n}")
    for name in ("", "x", "<b>Zippy</b>", "A" * 60):
        with pytest.raises(S.CarrierError):
            book.add_carrier("u2", name, "https://other.example/{n}")


def test_only_the_person_who_added_a_carrier_or_an_administrator_can_remove_it(book):
    book.add_carrier("u1", "Zippy Post", "https://track.zippy.example/t/{n}")
    cid = book.shared_carriers()[0]["id"]
    with pytest.raises(PermissionError):
        book.remove_carrier("u2", cid, False)
    with pytest.raises(KeyError):
        book.remove_carrier("u1", "c" + "0" * 16, False)
    book.remove_carrier("u3", cid, True)
    assert book.shared_carriers() == []


def test_the_shared_list_is_capped_and_damaged_entries_are_ignored(book):
    for i in range(S.MAX_SHARED):
        book.add_carrier("u1", f"Carrier {i}", f"https://track{i}.example/{{n}}")
    with pytest.raises(S.CarrierError):
        book.add_carrier("u1", "One more", "https://more.example/{n}")
    v = book.vault_
    v.g[S.SHARED_RECORD]["items"].append({"id": "c" + "1" * 16, "name": "Evil", "url": "javascript:alert(1)", "by": "u1"})
    v.g[S.SHARED_RECORD]["items"].append("not a dict")
    assert len(book.shared_carriers()) == S.MAX_SHARED


def test_an_administrator_can_correct_a_saved_carrier(book):
    book.add_carrier("u1", "Zippy Post", "https://track.zippy.example/t/{n}")
    book.add_carrier("u1", "Other Post", "https://track.other.example/{n}")
    cid = book.shared_carriers()[0]["id"]
    assert book.carrier_addresses()[0] == {"id": cid, "name": "Zippy Post", "url": "https://track.zippy.example/t/{number}"}
    book.update_carrier(cid, "Zippy Postal", "https://track.zippy.example/find?id={number}")
    again = book.shared_carriers()[0]
    assert (again["name"], again["url"], again["by"]) == ("Zippy Postal", "https://track.zippy.example/find?id={n}", "u1")
    for name, url in (("other post", "https://x.example/{n}"), ("Sendle", "https://x.example/{n}"), ("Zippy Postal", "http://x.example/{n}")):
        with pytest.raises(S.CarrierError):
            book.update_carrier(cid, name, url)
    book.update_carrier(cid, "Zippy Postal", "https://track.zippy.example/other/{n}")       # keeping its own name is fine
    with pytest.raises(KeyError):
        book.update_carrier("c" + "0" * 16, "Nobody", "https://x.example/{n}")


# ---------- an order the person types in by hand ----------

def test_an_order_can_be_added_by_hand_and_followed_by_hand(book):
    rows = book.add_by_hand("u1", "  Corner   Hardware ", "", "ordered")["orders"]
    assert len(rows) == 1
    o = rows[0]
    assert o["shop"] == "Corner Hardware" and o["status"] == "ordered" and o["manual"] and o["tracking"] is None
    assert o["events"] == [] and not o["unsure"] and not o["needs_confirm"] and not o["delivered_at"]
    oid = o["id"]
    o = book.set_status("u1", oid, "shipped")["orders"][0]
    assert o["status"] == "shipped" and not o["delivered_at"]
    o = book.set_status("u1", oid, "delivered")["orders"][0]
    assert o["status"] == "delivered" and o["delivered_at"] and o["ack"] == "got_it" and not o["needs_confirm"]     # they said so themselves: nothing to confirm
    o = book.set_status("u1", oid, "out_for_delivery")["orders"][0]
    assert o["status"] == "out_for_delivery" and not o["delivered_at"] and not o["ack"]
    assert book.act("u1", oid, "remove")["orders"] == []
    assert book.vault_.g["ship:u1"]["dismissed"] == {}                           # removing one you made up is not "not an order": nothing is remembered


def test_a_tracking_number_is_checked_and_not_added_twice(book):
    o = book.add_by_hand("u1", "Brightwater Books", "hf 9984-210", "shipped")["orders"][0]
    assert o["tracking"] == "HF9984210"
    with pytest.raises(ValueError, match="already listed"):
        book.add_by_hand("u1", "Another shop", "HF-9984210", "shipped")
    for bad, why in (("123", "bad tracking"), ("not a number", "bad tracking")):
        with pytest.raises(ValueError, match=why):
            book.add_by_hand("u1", "Shop", bad, "shipped")
    with pytest.raises(ValueError, match="no shop"):
        book.add_by_hand("u1", "   ", "", "shipped")
    with pytest.raises(ValueError, match="bad status"):
        book.add_by_hand("u1", "Shop", "", "lost")
    assert len(book.view("u1")["orders"]) == 1


def test_an_order_from_an_email_is_not_changed_by_hand(book):
    assert seen(book, 1, ship("shipped"), "On its way", NOW - 1000)
    oid = book.view("u1")["orders"][0]["id"]
    with pytest.raises(ValueError, match="not by hand"):
        book.set_status("u1", oid, "delivered")
    with pytest.raises(ValueError, match="not by hand"):
        book.act("u1", oid, "remove")                                            # the emails decide, and "Not an order" is the way to drop it
    with pytest.raises(KeyError):
        book.set_status("u1", "s" + "0" * 23, "shipped")
    with pytest.raises(KeyError):
        book.set_status("u2", oid, "shipped")                                    # someone else's order is not found


def test_a_hand_order_can_be_matched_to_nothing_else_and_kept_apart_per_person(book):
    book.add_by_hand("u1", "Corner Hardware", "", "ordered")
    assert book.view("u2")["orders"] == []


def test_the_hand_order_routes(env):
    appm, client, bridge, _ = env
    r = client.post("/api/v1/me/shipping", json={"shop": "Corner Hardware", "tracking": "AB12345678", "status": "ordered"})
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
    o = next(x for x in r.json()["orders"] if x["shop"] == "Corner Hardware")
    assert o["manual"] and o["status"] == "ordered" and o["tracking"] == "AB12345678"
    assert client.post("/api/v1/me/shipping", json={"shop": "", "status": "ordered"}).status_code == 422
    assert client.post("/api/v1/me/shipping", json={"shop": "X", "tracking": "12", "status": "ordered"}).status_code == 422
    assert client.post("/api/v1/me/shipping", json={"shop": "X", "status": "lost"}).status_code == 422
    assert client.post("/api/v1/me/shipping", json={"shop": "X", "status": "ordered", "extra": 1}).status_code == 422
    assert client.post("/api/v1/me/shipping", json={"shop": "Y", "tracking": "ab-1234-5678", "status": "shipped"}).status_code == 422     # same number again
    r = client.put(f"/api/v1/me/shipping/{o['id']}/status", json={"status": "shipped"})
    assert r.status_code == 200 and next(x for x in r.json()["orders"] if x["id"] == o["id"])["status"] == "shipped"
    assert client.put(f"/api/v1/me/shipping/{o['id']}/status", json={"status": "lost"}).status_code == 422
    assert client.put("/api/v1/me/shipping/s" + "0" * 23 + "/status", json={"status": "shipped"}).status_code == 404
    assert client.post(f"/api/v1/me/shipping/{o['id']}/remove").status_code == 200
    assert all(x["id"] != o["id"] for x in client.get("/api/v1/me/shipping").json()["orders"])


def test_the_hand_order_routes_need_a_signed_in_person(env):
    appm, _, _, _ = env
    from fastapi.testclient import TestClient
    anon = TestClient(appm.app)
    assert anon.post("/api/v1/me/shipping", json={"shop": "X", "status": "ordered"}).status_code in (401, 403)
    assert anon.put("/api/v1/me/shipping/s" + "0" * 23 + "/status", json={"status": "shipped"}).status_code in (401, 403)
