"""A signature and saved replies: a person's own text, kept encrypted, never shared."""
from __future__ import annotations

import pytest

from helpers import create_user, load_app, setup_admin, sign_in


@pytest.fixture
def app(tmp_path):
    appm = load_app(tmp_path / "data")
    admin, _ = setup_admin(appm)
    return appm, admin


def view(client):
    return client.get("/api/v1/me/saved").json()


def test_a_new_person_has_nothing_saved_and_it_is_never_cached(app):
    _, admin = app
    r = admin.get("/api/v1/me/saved")
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
    body = r.json()
    assert body["signature"] == "" and body["replies"] == [] and body["limits"]["replies"] == 30


def test_the_signature_is_saved_cleaned_and_can_be_removed(app):
    _, admin = app
    r = admin.put("/api/v1/me/saved/signature", json={"text": "  Thanks,\r\nMorgan\x00\x07  "})
    assert r.status_code == 200 and r.json()["signature"] == "Thanks,\nMorgan"
    assert view(admin)["signature"] == "Thanks,\nMorgan"
    assert admin.put("/api/v1/me/saved/signature", json={"text": ""}).json()["signature"] == ""


def test_the_signature_is_cut_to_its_limit(app):
    _, admin = app
    r = admin.put("/api/v1/me/saved/signature", json={"text": "x" * 1500})
    assert r.status_code == 200 and len(r.json()["signature"]) == 1000
    assert admin.put("/api/v1/me/saved/signature", json={"text": "x" * 5000}).status_code == 422


def test_adding_editing_and_removing_a_saved_reply(app):
    _, admin = app
    r = admin.post("/api/v1/me/saved/replies", json={"title": "Running late", "text": "I am running a little late."})
    assert r.status_code == 200
    reply = r.json()["replies"][0]
    assert reply["title"] == "Running late" and reply["id"].startswith("r") and len(reply["id"]) == 17
    r = admin.put(f"/api/v1/me/saved/replies/{reply['id']}", json={"title": "Late", "text": "Running late, sorry."})
    assert r.status_code == 200 and r.json()["replies"][0]["title"] == "Late" and len(r.json()["replies"]) == 1
    r = admin.delete(f"/api/v1/me/saved/replies/{reply['id']}")
    assert r.status_code == 200 and r.json()["replies"] == []
    assert admin.delete(f"/api/v1/me/saved/replies/{reply['id']}").status_code == 404
    assert admin.put(f"/api/v1/me/saved/replies/{reply['id']}", json={"title": "a", "text": "b"}).status_code == 404


def test_a_reply_needs_a_name_and_some_text_and_a_title_is_one_line(app):
    _, admin = app
    for body in ({"title": "", "text": "x"}, {"title": "x", "text": ""}, {"title": "   ", "text": "   "}):
        r = admin.post("/api/v1/me/saved/replies", json=body)
        assert r.status_code == 422 and "short name and some text" in str(r.json()["detail"])
    r = admin.post("/api/v1/me/saved/replies", json={"title": "Two\nlines", "text": "Hello"})
    assert r.json()["replies"][0]["title"] == "Two lines"
    assert admin.post("/api/v1/me/saved/replies", json={"title": "x", "text": "y", "extra": 1}).status_code == 422


def test_a_bad_reply_id_is_refused(app):
    _, admin = app
    assert admin.delete("/api/v1/me/saved/replies/not-an-id").status_code == 422
    assert admin.put("/api/v1/me/saved/replies/r123", json={"title": "a", "text": "b"}).status_code == 422


def test_there_is_a_limit_on_saved_replies(app):
    appm, admin = app
    from backend.mail.saved_writing import MAX_REPLIES
    me = admin.get("/api/v1/me").json()["id"]
    appm.vault.set_global("saved:" + me, {"signature": "", "replies": [{"id": f"r{n:016x}", "title": f"t{n}", "text": "x"} for n in range(MAX_REPLIES)]})
    r = admin.post("/api/v1/me/saved/replies", json={"title": "one more", "text": "x"})
    assert r.status_code == 422 and "up to" in str(r.json()["detail"])
    assert len(view(admin)["replies"]) == MAX_REPLIES


def test_each_person_has_their_own_text(app):
    appm, admin = app
    create_user(admin, "second")
    other = sign_in(appm, "second")
    admin.put("/api/v1/me/saved/signature", json={"text": "Morgan's signature"})
    rid = admin.post("/api/v1/me/saved/replies", json={"title": "Mine", "text": "Only for Morgan"}).json()["replies"][0]["id"]
    assert view(other)["signature"] == "" and view(other)["replies"] == []
    assert other.delete(f"/api/v1/me/saved/replies/{rid}").status_code == 404
    assert other.put(f"/api/v1/me/saved/replies/{rid}", json={"title": "x", "text": "y"}).status_code == 404
    assert view(admin)["replies"][0]["text"] == "Only for Morgan"


def test_it_needs_a_signed_in_person(app):
    appm, _ = app
    from fastapi.testclient import TestClient
    anon = TestClient(appm.app, raise_server_exceptions=False)
    assert anon.get("/api/v1/me/saved").status_code == 401
    assert anon.put("/api/v1/me/saved/signature", json={"text": "x"}).status_code == 401
    assert anon.post("/api/v1/me/saved/replies", json={"title": "x", "text": "y"}).status_code == 401
    assert anon.delete("/api/v1/me/saved/replies/r0123456789abcdef").status_code == 401


def test_it_is_stored_encrypted_exported_for_me_only_and_forgotten_with_the_person(app):
    appm, admin = app
    me = admin.get("/api/v1/me").json()["id"]
    admin.put("/api/v1/me/saved/signature", json={"text": "Warm regards, Morgan"})
    stored = appm.vault.get_global("saved:" + me)
    assert stored["signature"] == "Warm regards, Morgan"
    create_user(admin, "second")
    other = sign_in(appm, "second")
    assert "Warm regards, Morgan" in admin.get("/api/v1/me/export").text
    assert "Warm regards, Morgan" not in other.get("/api/v1/me/export").text
    appm.delete_user_data(me)
    assert not (appm.vault.get_global("saved:" + me) or {}).get("signature")
