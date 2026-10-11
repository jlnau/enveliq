"""Backup and restore of the vault, and Export my data."""
from __future__ import annotations

import os
import sqlite3
import time

import pytest

from backend.backup import BackupError, BackupManager, DAY
from backend.crypto_vault import SecureVault
from helpers import ADMIN_PASSWORD, PASSPHRASE, USER_PASSWORD, create_user, load_app, setup_admin, sign_in


class Clock:
    def __init__(self, t: float):
        self.t = t

    def __call__(self) -> float:
        return self.t


def make_vault(folder):
    vault = SecureVault(folder / "vault.sqlite3")
    vault.initialize(PASSPHRASE)
    return vault


@pytest.fixture
def box(tmp_path):
    vault = make_vault(tmp_path)
    clock = Clock(time.time())
    return vault, BackupManager(vault, tmp_path / "backups", clock), clock, tmp_path


def test_a_backup_is_a_private_verified_copy_of_the_vault(box):
    vault, mgr, _, tmp = box
    vault.set_global("note", {"x": "a made-up value"})
    made = mgr.create("manual")
    path = mgr.folder / made["name"]
    assert path.is_file() and (path.stat().st_mode & 0o777) == 0o600
    assert (mgr.folder.stat().st_mode & 0o777) == 0o700
    assert not list(mgr.folder.glob("*.partial"))
    assert [b["name"] for b in mgr.list()] == [made["name"]]
    con = sqlite3.connect(path)
    assert con.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert b"a made-up value" not in path.read_bytes()                  # ciphertext only
    con.close()


def test_restore_puts_back_what_was_there_and_keeps_the_history(box):
    vault, mgr, _, _ = box
    uid = vault.create_user({"username": "morgan"})
    vault.set_global("note", {"v": 1})
    aid = vault.create_account({"owner_user_id": uid, "email_address": "a@example.invalid"})
    vault.create_message(aid, {"subject": "Hello"})
    made = mgr.create("manual")
    vault.set_global("note", {"v": 2})
    vault.delete_account(aid)
    vault.audit({"event": "after_backup"})
    out = mgr.restore(made["name"], uid)
    assert vault.get_global("note") == {"v": 1}
    assert len(vault.list_accounts()) == 1 and len(vault.list_messages(aid)) == 1
    assert out["counts"] == {"accounts": 1, "messages": 1, "users": 1}
    kinds = [b["kind"] for b in mgr.list()]
    assert "before-restore" in kinds                                    # today's vault was saved first
    safety = next(b for b in mgr.list() if b["kind"] == "before-restore")
    assert out["safety_copy"] == safety["name"]
    con = sqlite3.connect(vault.db_path)
    assert con.execute("SELECT COUNT(*) FROM audit_events").fetchone()[0] >= 1       # the history is not replaced
    con.close()


def test_the_passphrase_you_have_today_still_works_after_a_restore(box):
    vault, mgr, _, tmp = box
    uid = vault.create_user({"username": "morgan"})
    made = mgr.create("manual")
    vault.change_passphrase(PASSPHRASE, "A different long passphrase 2027!")
    mgr.restore(made["name"], uid)
    vault.lock()
    vault.unlock("A different long passphrase 2027!")
    assert vault.is_unlocked()


def test_a_backup_from_a_different_vault_is_refused(box, tmp_path_factory):
    vault, mgr, _, _ = box
    uid = vault.create_user({"username": "morgan"})
    other_dir = tmp_path_factory.mktemp("other")
    other = make_vault(other_dir)
    other_uid = other.create_user({"username": "morgan"})
    foreign = BackupManager(other, other_dir / "backups").create("manual")
    os.makedirs(mgr.folder, exist_ok=True)
    (mgr.folder / foreign["name"]).write_bytes((other_dir / "backups" / foreign["name"]).read_bytes())
    with pytest.raises(BackupError) as err:
        mgr.restore(foreign["name"], other_uid)
    assert err.value.code == "other_vault"
    assert vault.list_users()[0]["id"] == uid                           # nothing changed


def test_someone_who_is_not_in_the_backup_cannot_restore_it(box):
    vault, mgr, _, _ = box
    vault.create_user({"username": "morgan"})
    made = mgr.create("manual")
    newer = vault.create_user({"username": "newcomer"})
    with pytest.raises(BackupError) as err:
        mgr.restore(made["name"], newer)
    assert err.value.code == "not_in_backup"
    assert not [b for b in mgr.list() if b["kind"] == "before-restore"]


def test_only_names_the_manager_made_can_be_used(box):
    _, mgr, _, tmp = box
    mgr.create("manual")
    for bad in ("../vault.sqlite3", "/etc/passwd", "enveliq-20260101-000000-manual.sqlite3", "x", "enveliq-../../a-manual.sqlite3"):
        with pytest.raises(BackupError):
            mgr.path_of(bad)
        with pytest.raises(BackupError):
            mgr.delete(bad)


def test_old_automatic_backups_are_pruned_but_manual_ones_stay(box):
    vault, mgr, clock, _ = box
    vault.set_global("x", {})
    t0 = clock.t
    clock.t = t0 - 30 * DAY
    old_auto, old_manual = mgr.create("auto"), mgr.create("manual")
    clock.t = t0 - 2 * DAY
    recent_auto = mgr.create("auto")
    clock.t = t0
    mgr.save_settings(True, 7)
    assert mgr.prune() == 1
    names = {b["name"] for b in mgr.list()}
    assert old_auto["name"] not in names and old_manual["name"] in names and recent_auto["name"] in names


def test_the_daily_backup_is_made_once_a_day_and_only_when_switched_on(box):
    vault, mgr, clock, _ = box
    assert mgr.run_due() is False                                       # off by default
    mgr.save_settings(True, 3)
    assert mgr.run_due() is True and mgr.run_due() is False
    clock.t += DAY + 5
    assert mgr.run_due() is True
    assert sum(1 for b in mgr.list() if b["kind"] == "auto") == 2


def test_settings_are_kept_inside_limits(box):
    _, mgr, _, _ = box
    assert mgr.settings() == {"daily": False, "keep_days": 7}
    assert mgr.save_settings(True, 500)["keep_days"] == 60
    assert mgr.save_settings(True, 0)["keep_days"] == 1


def test_there_is_a_limit_to_saved_backups(box):
    _, mgr, clock, _ = box
    for i in range(20):
        clock.t += 2
        mgr.create("manual")
    with pytest.raises(BackupError) as err:
        mgr.create("manual")
    assert err.value.code == "too_many"


# ---------- the routes ----------

@pytest.fixture
def app(tmp_path):
    appm = load_app(tmp_path / "data")
    admin, _ = setup_admin(appm)
    return appm, admin


def test_only_administrators_reach_backups(app):
    appm, admin = app
    create_user(admin, "sam")
    sam = sign_in(appm, "sam")
    for method, path in (("get", "/api/v1/admin/backups"), ("post", "/api/v1/admin/backups"),
                         ("get", "/api/v1/admin/backups/enveliq-20260101-000000-manual.sqlite3/download"),
                         ("delete", "/api/v1/admin/backups/enveliq-20260101-000000-manual.sqlite3")):
        assert getattr(sam, method)(path).status_code == 403
    assert sam.put("/api/v1/admin/backups/settings", json={"daily": True, "keep_days": 7}).status_code == 403
    assert sam.post("/api/v1/admin/backups/enveliq-20260101-000000-manual.sqlite3/restore", json={"password": USER_PASSWORD, "confirm": "RESTORE"}).status_code == 403


def test_make_list_download_and_delete(app):
    appm, admin = app
    r = admin.post("/api/v1/admin/backups")
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
    name = r.json()["made"]
    assert [b["name"] for b in r.json()["backups"]] == [name]
    d = admin.get(f"/api/v1/admin/backups/{name}/download")
    assert d.status_code == 200 and d.content[:15] == b"SQLite format 3"
    assert "attachment" in d.headers["content-disposition"]
    assert b"morgan" not in d.content                                   # ciphertext, not names
    assert admin.get("/api/v1/admin/backups/enveliq-20200101-000000-manual.sqlite3/download").status_code == 404
    assert admin.get("/api/v1/admin/backups/..%2Fvault.sqlite3/download").status_code in (404, 422)
    assert admin.delete(f"/api/v1/admin/backups/{name}").json()["backups"] == []


def test_settings_save_and_are_checked(app):
    _, admin = app
    r = admin.put("/api/v1/admin/backups/settings", json={"daily": True, "keep_days": 14})
    assert r.json()["settings"] == {"daily": True, "keep_days": 14}
    assert admin.put("/api/v1/admin/backups/settings", json={"daily": True, "keep_days": 999}).status_code == 422
    assert admin.put("/api/v1/admin/backups/settings", json={"daily": True, "keep_days": 7, "extra": 1}).status_code == 422


def test_restore_needs_the_password_and_the_typed_word(app):
    appm, admin = app
    name = admin.post("/api/v1/admin/backups").json()["made"]
    url = f"/api/v1/admin/backups/{name}/restore"
    assert admin.post(url, json={"password": "wrong password here", "confirm": "RESTORE"}).status_code == 401
    assert admin.post(url, json={"password": ADMIN_PASSWORD, "confirm": "restore it"}).status_code == 400
    assert admin.post(url, json={"password": ADMIN_PASSWORD}).status_code == 422
    assert admin.get("/api/v1/admin/backups").status_code == 200        # still signed in: nothing happened


def test_a_restore_works_and_everyone_signs_in_again(app):
    appm, admin = app
    sam_user = create_user(admin, "sam")
    sam = sign_in(appm, "sam")
    appm.vault.set_global("probe", {"v": 1})
    name = admin.post("/api/v1/admin/backups").json()["made"]
    appm.vault.set_global("probe", {"v": 2})
    r = admin.post(f"/api/v1/admin/backups/{name}/restore", json={"password": ADMIN_PASSWORD, "confirm": "RESTORE"})
    assert r.status_code == 200 and r.json()["restored"] is True and r.json()["safety_copy"].endswith("-before-restore.sqlite3")
    assert appm.vault.get_global("probe") == {"v": 1}
    assert sam.get("/api/v1/me").status_code == 401 and admin.get("/api/v1/admin/backups").status_code == 401
    again = sign_in(appm, "sam")
    assert again.get("/api/v1/me").json()["id"] == sam_user["id"]


# ---------- Export my data ----------

def test_export_holds_only_my_data_and_no_secrets(app):
    appm, admin = app
    sam_user = create_user(admin, "sam")
    sam = sign_in(appm, "sam")
    me = admin.get("/api/v1/me").json()["id"]
    appm.vault.set_global("tasks:" + sam_user["id"], {"items": {"t1": {"title": "Sam's own task"}}, "tz": None})
    appm.vault.set_global("tasks:" + me, {"items": {"t9": {"title": "Morgan's private task"}}, "tz": None})
    appm.vault.create_account({"owner_user_id": me, "email_address": "morgan@example.invalid", "password": "mail-password-xyz",
                               "oauth_refresh_token": "refresh-token-xyz", "auth_method": "password", "settings": {}, "privacy": {"visibility": "private", "shared_with": []}})
    r = sam.get("/api/v1/me/export")
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
    assert "attachment" in r.headers["content-disposition"] and r.headers["content-disposition"].endswith('.json"')
    text = r.text
    assert "Sam's own task" in text
    assert "Morgan's private task" not in text and "morgan@example.invalid" not in text
    assert USER_PASSWORD not in text and "argon2" not in text and "$argon" not in text
    data = r.json()
    assert data["you"]["username"] == "sam" and data["mailboxes"] == []
    mine = admin.get("/api/v1/me/export").text
    assert "mail-password-xyz" not in mine and "refresh-token-xyz" not in mine and "morgan@example.invalid" in mine
    assert "Sam's own task" not in mine and ADMIN_PASSWORD not in mine


def test_export_needs_a_sign_in_and_is_rate_limited(app):
    appm, admin = app
    from fastapi.testclient import TestClient
    assert TestClient(appm.app).get("/api/v1/me/export").status_code == 401
    codes = [admin.get("/api/v1/me/export").status_code for _ in range(8)]
    assert codes[:6] == [200] * 6 and 429 in codes[6:]
