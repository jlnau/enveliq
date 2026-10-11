"""Important people: a person's own short list of addresses, kept encrypted, never shared."""
from __future__ import annotations

import pytest

from helpers import create_user, load_app, setup_admin, sign_in


@pytest.fixture
def app(tmp_path):
    appm = load_app(tmp_path / "data")
    admin, _ = setup_admin(appm)
    return appm, admin


def items(client):
    return client.get("/api/v1/me/important").json()["items"]


def test_a_new_person_has_an_empty_list_and_it_is_never_cached(app):
    _, admin = app
    r = admin.get("/api/v1/me/important")
    assert r.status_code == 200 and r.json() == {"items": []} and r.headers["cache-control"] == "no-store"


def test_adding_listing_and_removing_a_person(app):
    _, admin = app
    r = admin.post("/api/v1/me/important", json={"address": "Beth@Example.invalid", "name": "Beth Harris"})
    assert r.status_code == 200
    assert [(p["address"], p["name"]) for p in r.json()["items"]] == [("beth@example.invalid", "Beth Harris")]
    # adding the same address again keeps one entry and can update the name
    r = admin.post("/api/v1/me/important", json={"address": "beth@example.invalid", "name": "Beth H"})
    assert [(p["address"], p["name"]) for p in r.json()["items"]] == [("beth@example.invalid", "Beth H")]
    assert len(items(admin)) == 1
    r = admin.post("/api/v1/me/important/remove", json={"address": "BETH@example.invalid"})
    assert r.status_code == 200 and r.json()["items"] == []
    assert admin.post("/api/v1/me/important/remove", json={"address": "beth@example.invalid"}).status_code == 404


def test_a_bad_address_is_refused_in_plain_words(app):
    _, admin = app
    for bad in ["", "not an address", "a@b", "x@@example.invalid", "line\nbreak@example.invalid"]:
        r = admin.post("/api/v1/me/important", json={"address": bad})
        assert r.status_code == 422, bad
    r = admin.post("/api/v1/me/important", json={"address": "nope"})
    assert "email address" in str(r.json()["detail"])
    assert items(admin) == []


def test_unknown_fields_are_refused(app):
    _, admin = app
    assert admin.post("/api/v1/me/important", json={"address": "a@example.invalid", "extra": 1}).status_code == 422


def test_the_list_has_a_limit(app):
    appm, admin = app
    from backend.mail.important import MAX_PEOPLE
    me = admin.get("/api/v1/me").json()["id"]
    appm.vault.set_global("important:" + me, {"people": {f"p{n}@example.invalid": {"n": "", "t": 1.0} for n in range(MAX_PEOPLE)}})
    r = admin.post("/api/v1/me/important", json={"address": "one-more@example.invalid"})
    assert r.status_code == 422 and "up to" in str(r.json()["detail"])
    # someone already on the list can still be updated when it is full
    assert admin.post("/api/v1/me/important", json={"address": "p0@example.invalid", "name": "Zero"}).status_code == 200


def test_each_person_has_their_own_list(app):
    appm, admin = app
    create_user(admin, "second")
    other = sign_in(appm, "second")
    admin.post("/api/v1/me/important", json={"address": "gina@example.invalid"})
    assert items(other) == []
    other.post("/api/v1/me/important", json={"address": "hal@example.invalid"})
    assert [p["address"] for p in items(admin)] == ["gina@example.invalid"]
    assert other.post("/api/v1/me/important/remove", json={"address": "gina@example.invalid"}).status_code == 404
    assert [p["address"] for p in items(admin)] == ["gina@example.invalid"]


def test_it_needs_a_signed_in_person(app):
    appm, _ = app
    from fastapi.testclient import TestClient
    anon = TestClient(appm.app, raise_server_exceptions=False)
    assert anon.get("/api/v1/me/important").status_code == 401
    assert anon.post("/api/v1/me/important", json={"address": "a@example.invalid"}).status_code == 401
    assert anon.post("/api/v1/me/important/remove", json={"address": "a@example.invalid"}).status_code == 401


def test_the_list_is_stored_encrypted_and_is_in_my_export_only(app):
    appm, admin = app
    me = admin.get("/api/v1/me").json()["id"]
    admin.post("/api/v1/me/important", json={"address": "gina@example.invalid", "name": "Gina Moore"})
    stored = appm.vault.get_global("important:" + me)
    assert stored["people"]["gina@example.invalid"]["n"] == "Gina Moore"
    create_user(admin, "second")
    other = sign_in(appm, "second")
    mine = admin.get("/api/v1/me/export").text
    assert "gina@example.invalid" in mine and "important_people" in mine
    assert "gina@example.invalid" not in other.get("/api/v1/me/export").text


def test_removing_a_person_account_forgets_their_list(app):
    appm, admin = app
    me = admin.get("/api/v1/me").json()["id"]
    admin.post("/api/v1/me/important", json={"address": "gina@example.invalid"})
    appm.delete_user_data(me)
    assert not (appm.vault.get_global("important:" + me) or {}).get("people")
