"""The "a new version is out" notice: Enveliq's server asks GitHub once a day for the newest release number and tells
administrators (only) when it is newer than the one running. An administrator can switch it off."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from helpers import USER_PASSWORD, create_user, load_app, setup_admin
from backend import update_check as uc
from backend.update_check import UpdateChecker, accept, parse_version

LINK = uc.RELEASE_URL_PREFIX + "tag/v9.9"
NEWER = {"version": "9.9", "url": LINK}


# ---------- the checker on its own ----------

def test_version_numbers_are_compared_as_numbers_not_text():
    assert parse_version("v0.81") == (0, 81) and parse_version("0.9") == (0, 9)
    assert parse_version("v0.100") > parse_version("0.99") > parse_version("0.9")
    for bad in ("", "latest", "v1", "1.2.3.4.5", "0.81-beta", "<script>", "v0.81.x", None):
        assert parse_version(bad) is None, bad


def test_only_a_plain_version_and_a_link_to_enveliqs_own_releases_are_accepted():
    good = {"tag_name": "v0.82", "html_url": uc.RELEASE_URL_PREFIX + "tag/v0.82"}
    assert accept(good) == {"version": "0.82", "url": uc.RELEASE_URL_PREFIX + "tag/v0.82"}
    for change in ({"html_url": "https://evil.example/releases/tag/v0.82"}, {"html_url": "http://github.com/jlnau/enveliq/releases/tag/v0.82"},
                   {"html_url": "https://github.com/other/enveliq/releases/tag/v0.82"}, {"html_url": uc.RELEASE_URL_PREFIX + "tag/v0.82?x=<b>"},
                   {"html_url": uc.RELEASE_URL_PREFIX + "x" * 300}, {"tag_name": "latest"}, {"tag_name": "v0.82<script>"},
                   {"draft": True}, {"prerelease": True}, {"html_url": None}):
        assert accept({**good, **change}) is None, change
    assert accept("nope") is None and accept(None) is None and accept([]) is None


def test_only_a_newer_release_counts_and_a_failed_check_is_quiet():
    clock = [1000.0]
    c = UpdateChecker("0.81", fetch=lambda: {"version": "0.82", "url": LINK}, now=lambda: clock[0])
    assert c.newer() is None and c.due()
    c.refresh()
    assert c.newer() == {"version": "0.82", "url": LINK} and not c.due()
    clock[0] += uc.CHECK_EVERY + 1
    assert c.due()
    for same in ("0.81", "0.80", "0.9"):
        c.fetch = lambda same=same: {"version": same, "url": LINK}
        c.refresh()
        assert c.newer() is None, same

    def boom():
        raise OSError("no internet")
    c2 = UpdateChecker("0.81", fetch=boom, now=lambda: clock[0])
    c2.refresh()                                            # no exception, nothing to show
    assert c2.newer() is None and not c2.due()               # and it waits an hour before trying again
    clock[0] += uc.RETRY_AFTER + 1
    assert c2.due()
    c3 = UpdateChecker("0.81", fetch=lambda: None, now=lambda: clock[0])
    c3.refresh()
    assert c3.newer() is None


def test_a_check_in_the_background_does_not_run_twice_at_once():
    calls = []
    c = UpdateChecker("0.81", fetch=lambda: calls.append(1) or {"version": "0.82", "url": LINK})
    c.maybe_refresh(); c.maybe_refresh(); c.maybe_refresh()
    for _ in range(100):
        if c.newer():
            break
        import time; time.sleep(0.02)
    assert len(calls) == 1 and c.newer()


# ---------- through the server ----------

@pytest.fixture
def env(tmp_path):
    m = load_app(tmp_path)
    admin, _ = setup_admin(m)
    create_user(admin, "sam")
    m.update_checker.fetch = lambda: dict(NEWER)
    m.update_checker.refresh()                              # as if the daily check had just run, so no thread starts
    yield m, admin
    m.vault.lock()


def sam(m):
    c = TestClient(m.app, raise_server_exceptions=False)
    assert c.post("/api/v1/auth/login", json={"username": "sam", "password": USER_PASSWORD}).json()["next"] == "done"
    return c


def test_an_administrator_is_told_and_gets_a_link_to_the_release(env):
    m, admin = env
    out = admin.get("/api/v1/system").json()
    assert out["update"] == NEWER


def test_nobody_else_is_told(env):
    m, admin = env
    assert "update" not in sam(m).get("/api/v1/system").json()
    assert TestClient(m.app).get("/api/v1/system").status_code in (401, 403)
    assert "update" not in str(TestClient(m.app).get("/api/v1/status").json())


def test_it_says_nothing_when_you_are_up_to_date(env):
    m, admin = env
    m.update_checker.fetch = lambda: {"version": "0.1", "url": LINK}
    m.update_checker.refresh()
    assert "update" not in admin.get("/api/v1/system").json()


def test_it_is_on_until_an_administrator_switches_it_off_and_only_they_can(env):
    m, admin = env
    assert admin.get("/api/v1/admin/update-notice").json() == {"enabled": True, "current": m.VERSION, "update": NEWER}
    assert sam(m).put("/api/v1/admin/update-notice", json={"enabled": False}).status_code == 403
    assert sam(m).get("/api/v1/admin/update-notice").status_code == 403
    assert admin.put("/api/v1/admin/update-notice", json={"enabled": "no"}).status_code == 422
    r = admin.put("/api/v1/admin/update-notice", json={"enabled": False})
    assert r.status_code == 200 and r.json() == {"enabled": False, "current": m.VERSION, "update": None}
    assert "update" not in admin.get("/api/v1/system").json()


def test_switched_off_means_no_request_to_github_at_all(env):
    m, admin = env
    asked = []
    m.update_checker.fetch = lambda: asked.append(1) or dict(NEWER)
    m.update_checker.checked_at = m.update_checker.tried_at = 0.0       # a check would be due
    assert admin.put("/api/v1/admin/update-notice", json={"enabled": False}).status_code == 200
    admin.get("/api/v1/system"); admin.get("/api/v1/admin/update-notice")
    import time; time.sleep(0.3)
    assert asked == []


def test_a_broken_check_does_not_break_the_page(env):
    m, admin = env
    def boom():
        raise OSError("no internet")
    m.update_checker.fetch = boom
    m.update_checker.latest = None
    m.update_checker.checked_at = m.update_checker.tried_at = 0.0
    r = admin.get("/api/v1/system")
    assert r.status_code == 200 and "update" not in r.json() and r.json()["version"] == m.VERSION


def test_the_change_is_recorded_in_the_audit_log(env):
    m, admin = env
    seen, original = [], m.vault.audit
    m.vault.audit = lambda payload: (seen.append(payload), original(payload))[1]
    admin.put("/api/v1/admin/update-notice", json={"enabled": False})
    assert any(e.get("event") == "update_notice_changed" and e.get("enabled") is False for e in seen)
