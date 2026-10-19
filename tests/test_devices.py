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
