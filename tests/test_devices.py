"""\"Your devices\": each person sees where they are signed in and can sign one out. Never anyone else's."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from helpers import USER_PASSWORD, create_user, load_app, setup_admin


@pytest.fixture
def app(tmp_path):
    m = load_app(tmp_path)
    admin, _ = setup_admin(m)
    create_user(admin, "sam")
    create_user(admin, "kim")
    yield m
    m.vault.lock()


def login(appm, username, headers=None):
    c = TestClient(appm.app, raise_server_exceptions=False)
    r = c.post("/api/v1/auth/login", json={"username": username, "password": USER_PASSWORD}, headers=headers or {})
    assert r.status_code == 200
    return c


def test_a_person_sees_their_devices_with_plain_names(app):
    phone = login(app, "sam", {"X-Enveliq-Device": "Enveliq app on Pixel 8"})
    web = login(app, "sam", {"User-Agent": "Mozilla/5.0 (Windows NT 10.0) Chrome/120.0 Safari/537.36"})
    items = web.get("/api/v1/auth/devices").json()["items"]
    assert {i["label"] for i in items} == {"Enveliq app on Pixel 8", "Chrome on Windows"}
    assert [i["current"] for i in items if i["label"] == "Chrome on Windows"] == [True]
    assert all(set(i) == {"id", "label", "signed_in_at", "method", "remembered", "current"} for i in items)
    assert phone.get("/api/v1/me").status_code == 200


def test_signing_a_device_out_ends_only_that_one(app):
    phone = login(app, "sam", {"X-Enveliq-Device": "Enveliq app"})
    web = login(app, "sam")
    other = next(i for i in web.get("/api/v1/auth/devices").json()["items"] if i["label"] == "Enveliq app")
    assert web.delete(f"/api/v1/auth/devices/{other['id']}").status_code == 204
    assert phone.get("/api/v1/me").status_code == 401
    assert web.get("/api/v1/me").status_code == 200


def test_nobody_can_see_or_end_someone_elses_device(app):
    sam = login(app, "sam")
    kim = login(app, "kim")
    sam_id = sam.get("/api/v1/auth/devices").json()["items"][0]["id"]
    assert [i["id"] for i in kim.get("/api/v1/auth/devices").json()["items"]] != [sam_id]
    assert kim.delete(f"/api/v1/auth/devices/{sam_id}").status_code == 404
    assert sam.get("/api/v1/me").status_code == 200


# ---------- signing in to the app through the browser ----------

import base64
import hashlib


def pair():
    verifier = base64.urlsafe_b64encode(b"v" * 32).rstrip(b"=").decode()
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return verifier, challenge


def test_the_app_signs_in_with_a_code_from_a_signed_in_browser(app):
    web = login(app, "sam")
    verifier, challenge = pair()
    code = web.post("/api/v1/auth/app-link", json={"challenge": challenge}).json()["code"]
    phone = TestClient(app.app, raise_server_exceptions=False)
    r = phone.post("/api/v1/auth/app-link/exchange", json={"code": code, "verifier": verifier}, headers={"X-Enveliq-Device": "Enveliq app on Pixel 8"})
    assert r.status_code == 200 and r.json()["next"] == "done"
    assert phone.get("/api/v1/me").json()["username"] == "sam"
    labels = {i["label"] for i in web.get("/api/v1/auth/devices").json()["items"]}
    assert "Enveliq app on Pixel 8" in labels


def test_a_code_works_once_and_only_with_the_matching_secret(app):
    web = login(app, "sam")
    verifier, challenge = pair()
    phone = TestClient(app.app, raise_server_exceptions=False)
    code = web.post("/api/v1/auth/app-link", json={"challenge": challenge}).json()["code"]
    wrong = base64.urlsafe_b64encode(b"w" * 32).rstrip(b"=").decode()
    assert phone.post("/api/v1/auth/app-link/exchange", json={"code": code, "verifier": wrong}).status_code == 401
    assert phone.post("/api/v1/auth/app-link/exchange", json={"code": code, "verifier": verifier}).status_code == 401   # a wrong try ends it
    code = web.post("/api/v1/auth/app-link", json={"challenge": challenge}).json()["code"]
    assert phone.post("/api/v1/auth/app-link/exchange", json={"code": code, "verifier": verifier}).status_code == 200
    assert phone.post("/api/v1/auth/app-link/exchange", json={"code": code, "verifier": verifier}).status_code == 401


def test_only_someone_signed_in_can_ask_for_a_code(app):
    _, challenge = pair()
    assert TestClient(app.app, raise_server_exceptions=False).post("/api/v1/auth/app-link", json={"challenge": challenge}).status_code in (401, 403)
