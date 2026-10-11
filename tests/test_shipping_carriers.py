"""Shipping carriers added by the household: who may add and remove them, and that the list is shared."""
from __future__ import annotations

import pytest

from helpers import create_user, load_app, setup_admin, sign_in

API = "/api/v1/shipping/carriers"
ZIPPY = {"name": "Zippy Post", "url": "https://track.zippy.example/t/{number}"}


@pytest.fixture
def home(tmp_path):
    appm = load_app(tmp_path)
    boss, _ = setup_admin(appm)
    for name in ("cara", "sam"):
        create_user(boss, name)
    h = type("Home", (), {})()
    h.appm, h.boss, h.cara, h.sam = appm, boss, sign_in(appm, "cara"), sign_in(appm, "sam")
    yield h
    appm.vault.lock()


def test_anyone_can_add_a_carrier_and_everyone_sees_it(home):
    r = home.cara.post(API, json=ZIPPY)
    assert r.status_code == 201
    mine = r.json()["carriers"]["shared"]
    assert [c["name"] for c in mine] == ["Zippy Post"] and mine[0]["mine"] is True
    theirs = home.sam.get("/api/v1/me/shipping").json()["carriers"]["shared"]
    assert [c["name"] for c in theirs] == ["Zippy Post"] and theirs[0]["mine"] is False
    assert "url" not in theirs[0] and "by" not in theirs[0]                    # who added it, and the address, are not sent around
    assert home.boss.get("/api/v1/me/shipping").json()["carriers"]["shared"][0]["name"] == "Zippy Post"


def test_bad_addresses_names_and_repeats_are_refused_with_a_plain_reason(home):
    for body in ({"name": "Zippy", "url": "http://track.zippy.example/{n}"}, {"name": "Zippy", "url": "https://track.zippy.example/"},
                 {"name": "Zippy", "url": "https://192.168.1.1/{n}"}, {"name": "<b>", "url": "https://track.zippy.example/{n}"}):
        r = home.cara.post(API, json=body)
        assert r.status_code == 422 and r.json()["detail"]
    assert home.cara.post(API, json={**ZIPPY, "extra": 1}).status_code == 422
    assert home.cara.post(API, json=ZIPPY).status_code == 201
    assert home.sam.post(API, json={"name": "zippy post", "url": "https://other.example/{n}"}).status_code == 422
    assert home.sam.post(API, json={"name": "Sendle", "url": "https://other.example/{n}"}).status_code == 422


def test_removing_is_for_the_person_who_added_it_or_an_administrator(home):
    cid = home.cara.post(API, json=ZIPPY).json()["carriers"]["shared"][0]["id"]
    assert home.sam.delete(f"{API}/{cid}").status_code == 403
    assert home.sam.get("/api/v1/me/shipping").json()["carriers"]["shared"]
    assert home.cara.delete(f"{API}/{cid}").json()["carriers"]["shared"] == []
    again = home.cara.post(API, json=ZIPPY).json()["carriers"]["shared"][0]["id"]
    assert home.boss.delete(f"{API}/{again}").status_code == 200
    assert home.cara.delete(f"{API}/{again}").status_code == 404
    assert home.cara.delete(f"{API}/not-an-id").status_code == 422


def test_it_is_off_when_shipping_is_off_and_needs_a_sign_in(home):
    from fastapi.testclient import TestClient
    assert TestClient(home.appm.app, raise_server_exceptions=False).post(API, json=ZIPPY).status_code == 401
    assert home.boss.put("/api/v1/admin/features", json={"shipping": False}).status_code == 200
    assert home.cara.post(API, json=ZIPPY).status_code == 403


def test_only_an_administrator_can_see_addresses_and_correct_a_carrier(home):
    cid = home.cara.post(API, json=ZIPPY).json()["carriers"]["shared"][0]["id"]
    assert home.cara.get(API).status_code == 403 and home.sam.get(API).status_code == 403
    assert home.cara.put(f"{API}/{cid}", json={"name": "Zippy Postal", "url": "https://track.zippy.example/{n}"}).status_code == 403   # not even the person who added it
    listed = home.boss.get(API).json()["carriers"]
    assert listed == [{"id": cid, "name": "Zippy Post", "url": "https://track.zippy.example/t/{number}"}]
    r = home.boss.put(f"{API}/{cid}", json={"name": "Zippy Postal", "url": "https://track.zippy.example/find?id={number}"})
    assert r.status_code == 200 and r.json()["carriers"]["shared"][0]["name"] == "Zippy Postal"
    assert home.boss.get(API).json()["carriers"][0]["url"] == "https://track.zippy.example/find?id={number}"
    assert home.boss.put(f"{API}/{cid}", json={"name": "Zippy Postal", "url": "https://track.zippy.example/"}).status_code == 422
    assert home.boss.put(f"{API}/c{'0' * 16}", json={"name": "Nobody", "url": "https://x.example/{n}"}).status_code == 404
    assert home.sam.get("/api/v1/me/shipping").json()["carriers"]["shared"][0]["name"] == "Zippy Postal"
