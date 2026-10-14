"""Drafts: unfinished emails kept for 14 days, encrypted, one person's own."""
from __future__ import annotations

import time

import pytest

from helpers import create_user, load_app, setup_admin, sign_in


@pytest.fixture
def app(tmp_path):
    appm = load_app(tmp_path / "data")
    admin, _ = setup_admin(appm)
    return appm, admin


NEW = {"kind": "new", "to": ["Mum <mum@example.invalid>"], "cc": ["sam@example.invalid"], "bcc": [], "subject": "Sunday lunch", "body": "Hi all,\nlunch is at one."}


def listing(client):
    return client.get("/api/v1/me/drafts").json()


def test_a_new_person_has_no_drafts_and_the_list_is_never_cached(app):
    _, admin = app
    r = admin.get("/api/v1/me/drafts")
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
    assert r.json()["items"] == [] and r.json()["keep_days"] == 14


def test_a_draft_is_saved_listed_updated_and_deleted(app):
    _, admin = app
    made = admin.post("/api/v1/me/drafts", json=NEW)
    assert made.status_code == 201, made.text
    d = made.json()
    assert d["kind"] == "new" and d["to"] == ["Mum <mum@example.invalid>"] and d["body"] == "Hi all,\nlunch is at one."
    assert abs((d["expires"] - d["updated"]) - 14 * 86400) < 1
    assert [x["id"] for x in listing(admin)["items"]] == [d["id"]]
    again = admin.put(f"/api/v1/me/drafts/{d['id']}", json={**NEW, "body": "Changed"})
    assert again.status_code == 200 and again.json()["id"] == d["id"] and again.json()["created"] == d["created"]
    assert [x["body"] for x in listing(admin)["items"]] == ["Changed"]
    assert admin.delete(f"/api/v1/me/drafts/{d['id']}").status_code == 204
    assert listing(admin)["items"] == []
    assert admin.delete(f"/api/v1/me/drafts/{d['id']}").status_code == 404
    assert admin.put(f"/api/v1/me/drafts/{d['id']}", json=NEW).status_code == 404


def test_a_reply_draft_remembers_which_email_it_answers(app):
    _, admin = app
    d = admin.post("/api/v1/me/drafts", json={"kind": "reply_all", "account_id": "a" * 8, "message_id": "m" * 8, "to": ["a@example.invalid"], "cc": ["b@example.invalid"], "subject": "Re: Plan", "body": "Agreed."}).json()
    assert d["kind"] == "reply_all" and d["message_id"] == "m" * 8 and d["cc"] == ["b@example.invalid"]


def test_an_empty_draft_and_odd_input_are_refused_or_cleaned(app):
    _, admin = app
    r = admin.post("/api/v1/me/drafts", json={"kind": "new"})
    assert r.status_code == 422 and "nothing to save" in str(r.json()["detail"])
    assert admin.post("/api/v1/me/drafts", json={**NEW, "kind": "other"}).status_code == 422
    assert admin.post("/api/v1/me/drafts", json={**NEW, "extra": 1}).status_code == 422
    assert admin.post("/api/v1/me/drafts", json={**NEW, "to": [f"p{i}@example.invalid" for i in range(51)]}).status_code == 422
    d = admin.post("/api/v1/me/drafts", json={**NEW, "subject": "Line\r\nBcc: x@example.invalid", "body": "Hi\x00\x07 there\r\nbye"}).json()
    assert "\r" not in d["subject"] and "\n" not in d["subject"] and d["body"] == "Hi there\nbye"


def test_there_is_a_limit_on_drafts(app):
    appm, admin = app
    from backend.mail.drafts import MAX_DRAFTS
    for n in range(MAX_DRAFTS):
        assert admin.post("/api/v1/me/drafts", json={**NEW, "subject": f"s{n}"}).status_code == 201
    r = admin.post("/api/v1/me/drafts", json=NEW)
    assert r.status_code == 422 and "up to" in str(r.json()["detail"])
    first = listing(admin)["items"][0]["id"]
    assert admin.put(f"/api/v1/me/drafts/{first}", json=NEW).status_code == 200          # changing one is still fine


def test_a_draft_goes_after_14_days(app):
    appm, admin = app
    me = admin.get("/api/v1/me").json()["id"]
    d = admin.post("/api/v1/me/drafts", json=NEW).json()
    stored = appm.vault.get_global("drafts:" + me)
    stored["items"][0]["updated"] = time.time() - 14 * 86400 - 60
    appm.vault.set_global("drafts:" + me, stored)
    assert listing(admin)["items"] == []
    assert appm.vault.get_global("drafts:" + me)["items"] == []                          # removed, not only hidden
    assert admin.put(f"/api/v1/me/drafts/{d['id']}", json=NEW).status_code == 404
    kept = admin.post("/api/v1/me/drafts", json=NEW).json()
    stored = appm.vault.get_global("drafts:" + me)
    stored["items"][0]["updated"] = time.time() - 13 * 86400
    appm.vault.set_global("drafts:" + me, stored)
    assert [x["id"] for x in listing(admin)["items"]] == [kept["id"]]


def test_saving_again_starts_the_14_days_again(app):
    appm, admin = app
    me = admin.get("/api/v1/me").json()["id"]
    d = admin.post("/api/v1/me/drafts", json=NEW).json()
    stored = appm.vault.get_global("drafts:" + me)
    stored["items"][0]["updated"] = time.time() - 13 * 86400
    appm.vault.set_global("drafts:" + me, stored)
    assert admin.put(f"/api/v1/me/drafts/{d['id']}", json=NEW).status_code == 200
    assert listing(admin)["items"][0]["expires"] - time.time() > 13.9 * 86400


def test_each_person_has_their_own_drafts(app):
    appm, admin = app
    create_user(admin, "second")
    other = sign_in(appm, "second")
    d = admin.post("/api/v1/me/drafts", json=NEW).json()
    assert listing(other)["items"] == []
    assert other.delete(f"/api/v1/me/drafts/{d['id']}").status_code == 404
    assert other.put(f"/api/v1/me/drafts/{d['id']}", json=NEW).status_code == 404
    assert len(listing(admin)["items"]) == 1


def test_a_bad_id_is_refused_and_it_needs_a_signed_in_person(app):
    appm, admin = app
    assert admin.delete("/api/v1/me/drafts/not-an-id").status_code == 422
    from fastapi.testclient import TestClient
    anon = TestClient(appm.app, raise_server_exceptions=False)
    assert anon.get("/api/v1/me/drafts").status_code == 401
    assert anon.post("/api/v1/me/drafts", json=NEW).status_code == 401
    assert anon.delete("/api/v1/me/drafts/d0123456789abcdef").status_code == 401


def test_it_is_stored_encrypted_exported_for_me_only_and_forgotten_with_the_person(app):
    appm, admin = app
    me = admin.get("/api/v1/me").json()["id"]
    admin.post("/api/v1/me/drafts", json={**NEW, "body": "A private plan about the surprise party"})
    create_user(admin, "second")
    other = sign_in(appm, "second")
    assert "surprise party" in admin.get("/api/v1/me/export").text
    assert "surprise party" not in other.get("/api/v1/me/export").text
    appm.vault.lock()
    assert not any(appm.vault.plaintext_scan(["surprise party", "mum@example.invalid"]).values())
