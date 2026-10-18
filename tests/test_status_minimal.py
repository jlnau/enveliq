"""The public status page says only what the sign-in, setup and unlock pages need. The rest is for signed-in people."""
from __future__ import annotations

import json

from fastapi.testclient import TestClient

from helpers import create_user, load_app, setup_admin, sign_in

ALLOWED_BEFORE_SIGN_IN = {"initialized", "unlocked", "setup_required", "sign_in", "auto_unlock", "auto_unlock_problem", "vault_key_needed"}
NEVER_PUBLIC = ("version", "cipher", "kdf", "argon2", "crypto", "public_url", "memory_kib", "time_cost", "parallelism",
                "master_key_bits", "idle_lock", "raw_message", "raw_attachment", "attachments", "preview_mode")


def test_before_setup_the_status_page_says_only_what_setup_needs(tmp_path):
    (tmp_path / "data").mkdir()
    appm = load_app(tmp_path / "data")
    r = TestClient(appm.app).get("/api/v1/status")
    body = r.json()
    assert r.status_code == 200 and body["setup_required"] is True and body["initialized"] is False
    assert set(body) <= ALLOWED_BEFORE_SIGN_IN
    text = json.dumps(body).lower()
    assert not [w for w in NEVER_PUBLIC if w in text]


def test_after_setup_the_public_status_page_has_no_version_or_encryption_settings(tmp_path):
    (tmp_path / "data").mkdir()
    appm = load_app(tmp_path / "data")
    setup_admin(appm)
    body = TestClient(appm.app).get("/api/v1/status").json()
    assert set(body) <= ALLOWED_BEFORE_SIGN_IN
    assert body["setup_required"] is False and body["sign_in"]["password"] is True
    assert not [w for w in NEVER_PUBLIC if w in json.dumps(body).lower()]
    assert "auto_unlock" not in body                          # whether the vault unlocks itself is only said while it is closed


def test_the_system_page_needs_a_signed_in_person(tmp_path):
    (tmp_path / "data").mkdir()
    appm = load_app(tmp_path / "data")
    setup_admin(appm)
    assert TestClient(appm.app).get("/api/v1/system").status_code in (401, 403, 423)


def test_a_signed_in_person_sees_the_version_and_an_administrator_the_technical_detail(tmp_path):
    from backend.version import VERSION
    (tmp_path / "data").mkdir()
    appm = load_app(tmp_path / "data")
    admin, _ = setup_admin(appm)
    create_user(admin, "second")
    person = sign_in(appm, "second")
    plain = person.get("/api/v1/system")
    assert plain.status_code == 200 and plain.headers["cache-control"] == "no-store"
    body = plain.json()
    assert body["version"] == VERSION and body["cipher"] == "AES-256-GCM"
    assert not {"crypto", "public_url", "auto_unlock", "attachments"} & set(body)
    detail = admin.get("/api/v1/system").json()
    assert detail["crypto"]["argon2_memory_kib"] and "public_url" in detail and "auto_unlock" in detail
