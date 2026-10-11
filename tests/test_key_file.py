"""Automatic unlock from a key file, and switching an existing vault over."""
from __future__ import annotations

import os
import stat

from helpers import PASSPHRASE, SETUP_CODE, ADMIN_PASSWORD, load_app, setup_admin
from backend import keyfile
from backend.crypto_vault import InvalidPassphrase, SecureVault


def fresh(tmp_path, **env):
    (tmp_path / "keys").mkdir(exist_ok=True)
    (tmp_path / "data").mkdir(exist_ok=True)
    return load_app(tmp_path / "data", ENVELIQ_VAULT_KEY_FILE=str(tmp_path / "keys" / "vault.key"), **env)


def test_setup_without_a_passphrase_makes_the_key_file_and_unlocks_itself_after_a_restart(tmp_path):
    appm = fresh(tmp_path)
    st = appm.app.router  # noqa: F841
    from fastapi.testclient import TestClient
    client = TestClient(appm.app, raise_server_exceptions=False)
    assert client.get("/api/v1/status").json()["auto_unlock"] is True
    r = client.post("/api/v1/setup", json={"setup_code": SETUP_CODE, "username": "morgan", "password": ADMIN_PASSWORD})
    assert r.status_code == 201, r.text
    key = tmp_path / "keys" / "vault.key"
    assert key.exists() and len(key.read_text().strip()) >= 32
    assert stat.S_IMODE(key.stat().st_mode) == 0o600
    appm.vault.lock()                                              # a restart: key gone from memory
    appm2 = fresh(tmp_path)
    status = TestClient(appm2.app).get("/api/v1/status").json()
    assert status["unlocked"] is True and status["auto_unlock_problem"] is None and status["idle_lock_seconds"] == 0
    assert key.read_text().strip() not in str(status)


def test_a_missing_wrong_or_short_key_leaves_it_locked_and_says_why(tmp_path):
    from fastapi.testclient import TestClient
    appm = fresh(tmp_path)
    TestClient(appm.app).post("/api/v1/setup", json={"setup_code": SETUP_CODE, "username": "morgan", "password": ADMIN_PASSWORD})
    key = tmp_path / "keys" / "vault.key"
    good = key.read_text()
    appm.vault.lock()
    for content, problem in ((None, "missing"), ("x" * 40 + "\n", "wrong"), ("short\n", "too_short")):
        if content is None:
            key.unlink()
        else:
            key.write_text(content)
        appm2 = fresh(tmp_path)
        st = TestClient(appm2.app).get("/api/v1/status").json()
        assert st["unlocked"] is False and st["auto_unlock_problem"] == problem, (problem, st)
        assert "x" * 40 not in str(st)
    key.write_text(good)
    appm3 = fresh(tmp_path)
    assert TestClient(appm3.app).get("/api/v1/status").json()["unlocked"] is True


def test_locking_is_turned_off_and_idle_lock_is_off(tmp_path):
    appm = fresh(tmp_path)
    client, _ = setup_admin(appm, with_passphrase=False)
    r = client.post("/api/v1/lock")
    assert r.status_code == 409 and appm.vault.is_unlocked()
    assert appm.vault.idle_lock_seconds > 10 ** 6


def test_without_a_key_file_a_passphrase_is_still_required(tmp_path):
    from fastapi.testclient import TestClient
    (tmp_path / "data").mkdir()
    appm = load_app(tmp_path / "data")
    client = TestClient(appm.app, raise_server_exceptions=False)
    assert client.get("/api/v1/status").json()["auto_unlock"] is False
    r = client.post("/api/v1/setup", json={"setup_code": SETUP_CODE, "username": "morgan", "password": ADMIN_PASSWORD})
    assert r.status_code == 400 and "passphrase" in r.text.lower()


def test_key_file_helpers(tmp_path):
    path = tmp_path / "k"
    assert keyfile.read_key(path) is None
    key = keyfile.create_key(path)
    assert keyfile.read_key(path) == key and len(key) >= 60
    try:
        keyfile.create_key(path)
        assert False, "must not overwrite"
    except keyfile.KeyFileError as err:
        assert err.code == "cannot_create"
    assert keyfile.read_key(path) == key
    path.write_text("short")
    try:
        keyfile.read_key(path)
        assert False
    except keyfile.KeyFileError as err:
        assert err.code == "too_short"
    os.chmod(tmp_path / "k", 0o644)
    assert keyfile.too_open(tmp_path / "k") is True


def test_changing_the_passphrase_keeps_the_data_readable(tmp_path):
    vault = SecureVault(tmp_path / "v.sqlite3")
    vault.initialize("first passphrase 123")
    vault.set_global("note", {"a": 1})
    vault.change_passphrase("first passphrase 123", "second passphrase 456")
    vault.lock()
    try:
        vault.unlock("first passphrase 123")
        assert False
    except InvalidPassphrase:
        pass
    vault.unlock("second passphrase 456")
    assert vault.get_global("note") == {"a": 1}
    try:
        vault.change_passphrase("wrong", "third passphrase 789")
        assert False
    except InvalidPassphrase:
        pass
    vault.unlock("second passphrase 456")


def test_switching_an_existing_vault_to_a_key_file_and_back(tmp_path, monkeypatch):
    from backend import vault_key
    (tmp_path / "data").mkdir()
    (tmp_path / "keys").mkdir()
    os.environ["ENVELIQ_DATA_DIR"] = str(tmp_path / "data")
    os.environ["ENVELIQ_VAULT_KEY_FILE"] = str(tmp_path / "keys" / "vault.key")
    try:
        vault = SecureVault(tmp_path / "data" / "vault.sqlite3")
        vault.initialize(PASSPHRASE)
        vault.set_global("note", {"a": 2})
        answers = iter([PASSPHRASE])
        monkeypatch.setattr(vault_key.getpass, "getpass", lambda prompt="": next(answers))
        vault_key.adopt()
        key = keyfile.read_key(tmp_path / "keys" / "vault.key")
        v2 = SecureVault(tmp_path / "data" / "vault.sqlite3")
        v2.unlock(key)
        assert v2.get_global("note") == {"a": 2}
        try:
            v2.unlock(PASSPHRASE)
            assert False, "the old passphrase must stop working"
        except InvalidPassphrase:
            pass
        answers = iter(["a brand new passphrase", "a brand new passphrase"])
        vault_key.use_passphrase()
        v3 = SecureVault(tmp_path / "data" / "vault.sqlite3")
        v3.unlock("a brand new passphrase")
        assert v3.get_global("note") == {"a": 2}
    finally:
        os.environ.pop("ENVELIQ_DATA_DIR", None)
        os.environ.pop("ENVELIQ_VAULT_KEY_FILE", None)


def test_a_key_in_the_environment_unlocks_after_a_restart_and_the_file_wins_if_both_are_set(tmp_path):
    key = "k" * 64
    appm = load_app(tmp_path / "data", ENVELIQ_VAULT_KEY=key)
    from fastapi.testclient import TestClient
    client = TestClient(appm.app, raise_server_exceptions=False)
    assert client.get("/api/v1/status").json()["auto_unlock"] is True
    r = client.post("/api/v1/setup", json={"setup_code": SETUP_CODE, "username": "morgan", "password": ADMIN_PASSWORD})
    assert r.status_code == 201, r.text
    assert not (tmp_path / "keys").exists()
    appm.vault.lock()
    again = load_app(tmp_path / "data", ENVELIQ_VAULT_KEY=key)
    from fastapi.testclient import TestClient
    st = TestClient(again.app).get("/api/v1/status").json()
    assert st["unlocked"] is True and st["idle_lock_seconds"] == 0
    wrong = load_app(tmp_path / "data", ENVELIQ_VAULT_KEY="z" * 64)
    st = TestClient(wrong.app).get("/api/v1/status").json()
    assert st["unlocked"] is False and st["auto_unlock_problem"] == "wrong"
    short = load_app(tmp_path / "data", ENVELIQ_VAULT_KEY="short")
    st = TestClient(short.app).get("/api/v1/status").json()
    assert st["auto_unlock_problem"] == "too_short"
