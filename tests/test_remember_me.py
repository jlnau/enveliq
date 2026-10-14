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
    def __init__(self):
        self.records = {}

    def touch(self):
        pass

    def get_global(self, rid):
        return self.records.get(rid)

    def set_global(self, rid, payload):
        self.records[rid] = payload


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


# ---- a remembered sign-in survives a restart (sessions otherwise live only in memory) ----

class DictVault:
    """A stand-in vault that keeps global records in a dict, like the encrypted one does."""
    def __init__(self):
        self.records = {}
    def touch(self):
        pass
    def get_global(self, rid):
        import copy
        return copy.deepcopy(self.records.get(rid))
    def set_global(self, rid, payload):
        import copy
        self.records[rid] = copy.deepcopy(payload)


def restarted(vault, now):
    """A fresh manager over the same stored records: what Enveliq looks like right after a restart."""
    m = SessionManager(vault, clock=lambda: now[0])
    m.resolver = lambda uid: Principal(user_id=uid, name="Sam", is_admin=False) if uid == "u1" else None
    return m


@pytest.fixture
def wall():
    return [1_000_000.0]


def test_a_remembered_sign_in_is_still_valid_after_a_restart_and_keeps_its_limit(wall):
    vault = DictVault()
    first = SessionManager(vault, clock=lambda: wall[0])
    s = first.create(principal(), remember_seconds=7 * DAY, auth_method="passkey")
    stored = str(vault.records)
    assert s.token not in stored and "u1" in stored                 # only a hash of the token is kept
    wall[0] += 3 * DAY
    after = restarted(vault, wall)
    back = after.get(s.token)
    assert back.principal.user_id == "u1" and back.remember_seconds == 7 * DAY and back.auth_method == "passkey" and back.state == "full"
    wall[0] += 5 * DAY                                              # past 7 days from sign-in
    with pytest.raises(HTTPException):
        restarted(vault, wall).get(s.token)


def test_an_ordinary_sign_in_does_not_survive_a_restart(wall):
    vault = DictVault()
    s = SessionManager(vault, clock=lambda: wall[0]).create(principal())
    assert vault.records == {}
    with pytest.raises(HTTPException):
        restarted(vault, wall).get(s.token)


def test_signing_out_or_changing_the_password_forgets_a_remembered_sign_in(wall):
    vault = DictVault()
    m = SessionManager(vault, clock=lambda: wall[0])
    a = m.create(principal(), remember_seconds=DAY)
    b = m.create(principal(), remember_seconds=DAY)
    m.revoke(a.token)
    with pytest.raises(HTTPException):
        restarted(vault, wall).get(a.token)
    assert restarted(vault, wall).get(b.token)
    m.revoke_user("u1")
    with pytest.raises(HTTPException):
        restarted(vault, wall).get(b.token)


def test_revoke_everyone_clears_them_but_a_vault_lock_does_not(wall):
    vault = DictVault()
    m = SessionManager(vault, clock=lambda: wall[0])
    s = m.create(principal(), remember_seconds=DAY)
    m.revoke_all()                                                  # what a vault lock does: memory only
    assert restarted(vault, wall).get(s.token)
    m.revoke_everyone()
    with pytest.raises(HTTPException):
        restarted(vault, wall).get(s.token)


def test_a_remembered_sign_in_of_someone_gone_or_unknown_is_refused(wall):
    vault = DictVault()
    s = SessionManager(vault, clock=lambda: wall[0]).create(Principal(user_id="gone", name="X", is_admin=False), remember_seconds=DAY)
    with pytest.raises(HTTPException):
        restarted(vault, wall).get(s.token)
    with pytest.raises(HTTPException):
        restarted(vault, wall).get("not-a-real-token")


def test_in_the_app_a_remembered_sign_in_survives_a_restart_and_a_plain_one_does_not(keyed):
    appm, admin = keyed
    admin.put("/api/v1/admin/auth-policy", json={"remember_days": 14})
    kept, _ = login(appm, remember=True)
    plain_c, _ = login(appm)
    appm.sessions._sessions.clear()                                 # the process restarted: memory is gone
    assert kept.get("/api/v1/me").status_code == 200
    assert plain_c.get("/api/v1/me").status_code == 401


def test_a_passkey_sign_in_with_the_tick_is_remembered_and_survives_a_restart(keyed):
    from helpers import SoftAuthenticator
    appm, admin = keyed
    admin.put("/api/v1/admin/auth-policy", json={"remember_days": 14})
    auth = SoftAuthenticator()
    opts = admin.post("/api/v1/auth/passkeys/register/options").json()
    assert admin.post("/api/v1/auth/passkeys/register/verify", json={"credential": auth.create(opts), "name": "Phone"}).status_code == 200

    def passkey_login(**extra):
        c = TestClient(appm.app, raise_server_exceptions=False)
        o = c.post("/api/v1/auth/passkeys/options", json={"purpose": "login"}).json()
        return c, c.post("/api/v1/auth/passkeys/verify", json={"credential": auth.get(o), **extra})

    c, r = passkey_login(remember=True)
    assert r.status_code == 200 and max_age(r) == 14 * DAY
    _, plain_r = passkey_login()
    assert max_age(plain_r) == 12 * 3600                            # no tick, no long sign-in
    appm.sessions._sessions.clear()                                 # a restart
    me = c.get("/api/v1/me")
    assert me.status_code == 200 and me.json()["session"]["method"] == "passkey"
