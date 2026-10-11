"""\"Keep me signed in on this device\": an administrator allows it for up to 14 days, and it works only while Enveliq
opens its own vault from a key (otherwise the vault locks itself when idle and signs everyone out)."""
from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient
from fastapi import HTTPException

from helpers import ADMIN_PASSWORD, USER_PASSWORD, create_user, load_app, next_totp, setup_admin
from backend.crypto_vault import Principal
from backend.security import SessionManager

KEY = "r" * 64
DAY = 86400


def max_age(resp) -> int | None:
    # A response can carry several cookies (the second step also clears the temporary sign-in cookie, Max-Age=0): the session's is the longest.
    ages = [int(a) for a in re.findall(r"Max-Age=(\d+)", ", ".join(resp.headers.get_list("set-cookie")))]
    return max(ages) if ages else None


def login(appm, username="sam", remember=None):
    c = TestClient(appm.app, raise_server_exceptions=False)
    body = {"username": username, "password": USER_PASSWORD}
    if remember is not None:
        body["remember"] = remember
    return c, c.post("/api/v1/auth/login", json=body)


@pytest.fixture
def keyed(tmp_path):
    """Enveliq that opens its own vault from a key, with an administrator and one other person."""
    m = load_app(tmp_path, ENVELIQ_VAULT_KEY=KEY)
    admin, secret = setup_admin(m, with_passphrase=False)
    admin.totp_secret = secret
    create_user(admin, "sam")
    yield m, admin
    m.vault.lock()


@pytest.fixture
def plain(tmp_path):
    """Enveliq with a passphrase and no key: its vault locks itself when idle."""
    m = load_app(tmp_path)
    admin, secret = setup_admin(m)
    create_user(admin, "sam")
    yield m, admin
    m.vault.lock()


def test_it_is_off_until_an_administrator_turns_it_on(keyed):
    appm, admin = keyed
    assert TestClient(appm.app).get("/api/v1/status").json()["sign_in"]["remember"] is False
    assert admin.get("/api/v1/admin/auth-policy").json()["remember_days"] == 0
    c, r = login(appm, remember=True)
    assert r.status_code == 200 and r.json()["next"] == "done" and max_age(r) == 12 * 3600       # asked for, but not allowed: the normal 12 hours
    assert c.get("/api/v1/me").status_code == 200


def test_the_number_of_days_is_between_0_and_14(keyed):
    _, admin = keyed
    for bad in (15, -1, 100):
        assert admin.put("/api/v1/admin/auth-policy", json={"remember_days": bad}).status_code == 422
    assert admin.put("/api/v1/admin/auth-policy", json={"remember_days": "7"}).status_code == 422
    assert admin.put("/api/v1/admin/auth-policy", json={"remember_days": True}).status_code == 422
    ok = admin.put("/api/v1/admin/auth-policy", json={"remember_days": 14})
    assert ok.status_code == 200 and ok.json()["remember_days"] == 14 and ok.json()["remember_possible"] is True
    assert admin.get("/api/v1/admin/auth-policy").json()["remember_days"] == 14
    assert admin.put("/api/v1/admin/auth-policy", json={"remember_days": 0}).json()["remember_days"] == 0


def test_only_an_administrator_can_set_it(keyed):
    appm, _ = keyed
    c, _ = login(appm)
    assert c.put("/api/v1/admin/auth-policy", json={"remember_days": 7}).status_code in (401, 403)


def test_when_allowed_a_tick_keeps_you_signed_in_for_that_many_days_and_no_tick_does_not(keyed):
    appm, admin = keyed
    assert admin.put("/api/v1/admin/auth-policy", json={"remember_days": 7}).status_code == 200
    assert TestClient(appm.app).get("/api/v1/status").json()["sign_in"]["remember"] is True
    c, r = login(appm, remember=True)
    assert r.json()["next"] == "done" and max_age(r) == 7 * DAY
    assert c.get("/api/v1/me").status_code == 200
    _, plain_login = login(appm, remember=False)
    assert max_age(plain_login) == 12 * 3600
    _, untouched = login(appm)                                      # the tick is never assumed
    assert max_age(untouched) == 12 * 3600


def test_without_a_vault_key_it_never_applies_whatever_the_number(plain):
    appm, admin = plain
    r = admin.put("/api/v1/admin/auth-policy", json={"remember_days": 7})
    assert r.status_code == 200 and r.json()["remember_days"] == 7 and r.json()["remember_possible"] is False
    assert TestClient(appm.app).get("/api/v1/status").json()["sign_in"]["remember"] is False
    _, r = login(appm, remember=True)
    assert max_age(r) == 12 * 3600


def test_the_tick_given_with_the_password_carries_through_the_second_step(keyed):
    appm, admin = keyed
    assert admin.put("/api/v1/admin/auth-policy", json={"remember_days": 14}).status_code == 200
    c = TestClient(appm.app, raise_server_exceptions=False)
    r = c.post("/api/v1/auth/login", json={"username": "morgan", "password": ADMIN_PASSWORD, "remember": True})
    assert r.json()["next"] == "mfa"
    done = c.post("/api/v1/auth/mfa", json={"code": next_totp(admin.totp_secret)})
    assert done.status_code == 200 and done.json()["next"] == "done" and max_age(done) == 14 * DAY


def test_a_disabled_person_is_out_at_once_even_with_a_long_sign_in(keyed):
    appm, admin = keyed
    admin.put("/api/v1/admin/auth-policy", json={"remember_days": 7})
    c, r = login(appm, remember=True)
    assert c.get("/api/v1/me").status_code == 200
    sam = next(u for u in admin.get("/api/v1/admin/users").json() if u["username"] == "sam")
    assert admin.patch(f"/api/v1/admin/users/{sam['id']}", json={"disabled": True}).status_code == 200
    assert c.get("/api/v1/me").status_code in (401, 403)


def test_changing_the_password_signs_out_the_other_long_sign_ins(keyed):
    appm, admin = keyed
    admin.put("/api/v1/admin/auth-policy", json={"remember_days": 7})
    old, _ = login(appm, remember=True)
    new, _ = login(appm)
    r = new.post("/api/v1/auth/password", json={"current_password": USER_PASSWORD, "new_password": "A brand new password 2027!"})
    assert r.status_code in (200, 204), r.text
    assert old.get("/api/v1/me").status_code == 401


# ---- the session manager itself, with a clock we move ----

class StubVault:
    def touch(self):
        pass


@pytest.fixture
def clock(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr("backend.security.time.monotonic", lambda: now[0])
    return now


def principal():
    return Principal(user_id="u1", name="Sam", is_admin=False)


def test_a_normal_sign_in_is_out_after_half_an_hour_unused_and_after_12_hours(clock):
    sessions = SessionManager(StubVault())
    s = sessions.create(principal())
    clock[0] += 1700
    assert sessions.get(s.token)                                    # used within 30 minutes: stays
    clock[0] += 1801
    with pytest.raises(HTTPException):
        sessions.get(s.token)                                       # left for over 30 minutes
    s2 = sessions.create(principal())
    for _ in range(25):                                             # used every 29 minutes
        clock[0] += 29 * 60
        if clock[0] - s2.created_at > 12 * 3600:
            with pytest.raises(HTTPException):
                sessions.get(s2.token)
            break
        assert sessions.get(s2.token)
    else:
        raise AssertionError("the 12-hour limit never applied")


def test_a_remembered_sign_in_can_be_left_for_days_but_not_past_its_limit(clock):
    sessions = SessionManager(StubVault())
    s = sessions.create(principal(), remember_seconds=7 * DAY)
    assert s.remember_seconds == 7 * DAY
    clock[0] += 2 * DAY
    assert sessions.get(s.token)                                    # unused for two days: still signed in
    clock[0] += 4 * DAY
    assert sessions.get(s.token)                                    # day 6
    clock[0] += 2 * DAY
    with pytest.raises(HTTPException):
        sessions.get(s.token)                                       # past 7 days from sign-in: out, even though it was used
    assert sessions.life_of(s) == 7 * DAY


def test_a_sign_in_that_still_has_to_set_up_a_second_factor_is_never_remembered(clock):
    sessions = SessionManager(StubVault())
    s = sessions.create(principal(), state="enroll", remember_seconds=7 * DAY)
    assert s.remember_seconds == 0 and sessions.life_of(s) == 12 * 3600
