"""The export for the new Mail: one zip with a locked copy of the vault, a manifest and the Bridge certificate. Never the key."""
from __future__ import annotations

import io
import json
import sqlite3
import zipfile

import pytest

from backend import mail_export
from helpers import ADMIN_PASSWORD, USER_PASSWORD, PASSPHRASE, create_user, load_app, setup_admin, sign_in

CERT = b"-----BEGIN CERTIFICATE-----\nMADEUPCERTIFICATE\n-----END CERTIFICATE-----\n"


@pytest.fixture
def app(tmp_path):
    cert = tmp_path / "bridge.crt"
    cert.write_bytes(CERT)
    appm = load_app(tmp_path, ENVELIQ_BRIDGE_CA_FILE=str(cert), ENVELIQ_BRIDGE_ALLOWED_HOSTS="192.168.1.50,bridge.example.com")
    admin, _ = setup_admin(appm)
    return appm, admin, tmp_path


def make(admin):
    return admin.post("/api/v1/admin/export-for-mail", json={"password": ADMIN_PASSWORD, "confirm": "EXPORT"})


def test_the_zip_holds_the_locked_vault_a_manifest_and_the_certificate_but_not_the_key(app):
    appm, admin, tmp = app
    r = make(admin)
    assert r.status_code == 200, r.text
    made = r.json()
    assert made["vault_unlock"] == "passphrase" and made["has_bridge_certificate"] is True
    dl = admin.get(f"/api/v1/admin/export-for-mail/{made['name']}")
    assert dl.status_code == 200 and dl.headers["content-type"] == "application/zip"
    z = zipfile.ZipFile(io.BytesIO(dl.content))
    assert sorted(z.namelist()) == ["bridge-ca.pem", "manifest.json", "vault.sqlite3"]
    manifest = json.loads(z.read("manifest.json"))
    assert manifest["format"] == "enveliq-for-mail" and manifest["format_version"] == 1
    assert manifest["bridge_allowed_hosts"] == ["192.168.1.50", "bridge.example.com"]
    assert z.read("bridge-ca.pem") == CERT
    vault = z.read("vault.sqlite3")
    assert PASSPHRASE.encode() not in dl.content                           # the passphrase is never in it
    path = tmp / "copy.sqlite3"
    path.write_bytes(vault)
    con = sqlite3.connect(path)
    assert con.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert con.execute("SELECT COUNT(*) FROM vault_meta").fetchone()[0] == 1
    con.close()


def test_the_file_is_removed_after_it_is_downloaded(app):
    _, admin, tmp = app
    name = make(admin).json()["name"]
    assert admin.get(f"/api/v1/admin/export-for-mail/{name}").status_code == 200
    assert admin.get(f"/api/v1/admin/export-for-mail/{name}").status_code == 404
    assert not list((tmp / "exports").glob("*.zip"))


def test_it_asks_for_the_password_and_the_typed_word_and_only_administrators_reach_it(app):
    appm, admin, _ = app
    url = "/api/v1/admin/export-for-mail"
    assert admin.post(url, json={"password": "wrong password here", "confirm": "EXPORT"}).status_code == 401
    assert admin.post(url, json={"password": ADMIN_PASSWORD, "confirm": "yes"}).status_code == 400
    assert admin.post(url, json={"password": ADMIN_PASSWORD}).status_code == 422
    create_user(admin, "sam")
    sam = sign_in(appm, "sam")
    assert sam.post(url, json={"password": USER_PASSWORD, "confirm": "EXPORT"}).status_code == 403
    assert sam.get(f"{url}/enveliq-for-mail-20260101-000000.zip").status_code == 403
    assert admin.get(f"{url}/..%2Fvault.sqlite3").status_code in (404, 422)


def test_the_key_mode_is_named_and_old_exports_are_cleared(tmp_path):
    assert mail_export.key_mode({}) == "passphrase"
    assert mail_export.key_mode({"ENVELIQ_VAULT_KEY": "x" * 40}) == "key"
    assert mail_export.key_mode({"ENVELIQ_VAULT_KEY_FILE": "/run/key"}) == "key"
    folder = tmp_path / "exports"
    folder.mkdir()
    old = folder / "enveliq-for-mail-20200101-000000.zip"
    old.write_bytes(b"x")
    import os
    os.utime(old, (1, 1))
    mail_export.prepare_folder(folder)
    assert not old.exists()
