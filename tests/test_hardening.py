"""Regression tests for the v0.13 security review.

Each test is named after the weakness it guards against. They all failed (or
the weakness was demonstrated) against v0.12 and pass from v0.13 on.
"""
from __future__ import annotations

import concurrent.futures as cf
import importlib
import logging
import os
import sqlite3
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.crypto_vault import Principal

from helpers import PASSPHRASE  # noqa: E402
IMAP_ACCOUNT = {
    "provider": "IMAP",
    "display_name": "Test",
    "email_address": "test@example.invalid",
    "auth_method": "imap",
    "server": "imap.example.invalid",
    "port": 993,
    "username": "test@example.invalid",
    "password": "original-app-password",
}
PNG = b"\x89PNG\r\n\x1a\n"


from helpers import create_user, load_app, setup_admin, sign_in  # noqa: E402


def auth(token: str) -> dict[str, str]:
    # Sessions are HttpOnly cookies held by each TestClient; no header needed.
    return {}


@pytest.fixture
def env(tmp_path: Path):
    appm = load_app(tmp_path)
    client, _ = setup_admin(appm)
    yield appm, client, ""
    appm.vault.lock()


def make_account(client, token, **overrides) -> str:
    r = client.post("/api/v1/accounts", headers=auth(token), json={**IMAP_ACCOUNT, **overrides})
    assert r.status_code == 201, r.text
    return r.json()["id"]


# ---------- Request handling ----------

def test_validation_errors_never_echo_submitted_values(env):
    _, client, token = env
    r = client.post("/api/v1/unlock", json={"passphrase": "P" * 600})
    assert r.status_code == 422
    assert "P" * 600 not in r.text
    r = client.post("/api/v1/accounts", headers=auth(token), json={**IMAP_ACCOUNT, "unexpected": "LEAKED-VALUE-123"})
    assert r.status_code == 422
    assert "LEAKED-VALUE-123" not in r.text
    assert "original-app-password" not in r.text


def test_malformed_content_length_is_rejected_not_crashed(env):
    _, client, _ = env
    r = client.post("/api/v1/unlock", content=b'{"passphrase":"abc"}',
                    headers={"content-type": "application/json", "content-length": "abc"})
    assert r.status_code == 400


def test_chunked_body_cannot_bypass_size_limit(env):
    _, client, _ = env
    big = b'{"passphrase":"' + b"a" * (3 * 1024 * 1024) + b'"}'

    def chunks():
        for i in range(0, len(big), 65536):
            yield big[i:i + 65536]

    r = client.post("/api/v1/unlock", content=chunks(), headers={"content-type": "application/json"})
    assert r.status_code == 413


def test_body_must_be_json_and_cross_origin_is_refused(env):
    _, client, _ = env
    body = ('{"passphrase":"%s"}' % PASSPHRASE).encode()
    assert client.post("/api/v1/unlock", content=body, headers={"content-type": "text/plain"}).status_code == 415
    r = client.get("/api/v1/status", headers={"origin": "https://evil.example"})
    assert r.status_code == 403
    r = client.get("/api/v1/status", headers={"origin": "http://127.0.0.1:8765"})
    assert r.status_code == 200
    assert client.get("/api/v1/status", headers={"host": "evil.example"}).status_code == 400


def test_invalid_ids_are_rejected_before_lookup(env):
    _, client, token = env
    assert client.get("/api/v1/accounts/not-a-uuid/messages", headers=auth(token)).status_code == 422
    assert client.get("/api/v1/accounts/%C3%A9t%C3%A9/messages", headers=auth(token)).status_code == 422


def test_server_and_llm_endpoint_values_are_validated(env):
    _, client, token = env
    for bad in ["imap.example.com/evil", "imap.example.com:993", "imap://x", "host name", "a;rm -rf"]:
        r = client.post("/api/v1/accounts", headers=auth(token), json={**IMAP_ACCOUNT, "server": bad})
        assert r.status_code == 422, bad
    assert make_account(client, token, server="192.168.1.20")
    assert make_account(client, token, server="fd00::1")
    for bad in ["file:///etc/passwd", "gopher://x", "https://user:pw@llm.example", "https://llm.example/#x", "notaurl"]:
        r = client.put("/api/v1/admin/global-settings", headers=auth(token),
                       json={"llm_provider": "compatible", "endpoint": bad})
        assert r.status_code == 422, bad
    r = client.put("/api/v1/admin/global-settings", headers=auth(token),
                   json={"llm_provider": "ollama", "endpoint": "http://192.168.1.60:11434"})
    assert r.status_code == 200


def test_retained_message_structures_are_typed(env):
    _, client, token = env
    account_id = make_account(client, token)
    base = {"subject": "s", "summary": "s"}
    r = client.post(f"/api/v1/accounts/{account_id}/messages", headers=auth(token),
                    json={**base, "suggested_task": {"title": "t", "notes": "RAW BODY PARKED HERE"}})
    assert r.status_code == 422
    r = client.post(f"/api/v1/accounts/{account_id}/messages", headers=auth(token),
                    json={**base, "attachment_summaries": [{"filename": "a.pdf", "summary": "x", "text": "RAW"}]})
    assert r.status_code == 422
    r = client.post(f"/api/v1/accounts/{account_id}/messages", headers=auth(token),
                    json={**base, "suggested_task": {"title": "Reply", "due": "Fri"}})
    assert r.status_code == 201


# ---------- Accounts ----------

def test_patch_null_password_keeps_stored_credential(env):
    appm, client, token = env
    account_id = make_account(client, token)
    r = client.patch(f"/api/v1/accounts/{account_id}", headers=auth(token), json={"password": None})
    assert r.status_code == 200
    assert appm.vault.get_account(account_id)["password"] == "original-app-password"
    assert r.json()["password_set"] is True
    r = client.patch(f"/api/v1/accounts/{account_id}", headers=auth(token), json={"password": "replacement-password"})
    assert r.status_code == 200
    assert appm.vault.get_account(account_id)["password"] == "replacement-password"
    assert "replacement-password" not in r.text


def _second_user(appm, admin_client):
    create_user(admin_client, "cara")
    return sign_in(appm, "cara")


def test_private_mailbox_is_indistinguishable_from_missing(env):
    appm, client, token = env
    account_id = make_account(client, token)
    cara = _second_user(appm, client)
    missing = "00000000-0000-4000-8000-000000000000"
    for path in (f"/api/v1/accounts/{account_id}/messages", f"/api/v1/accounts/{missing}/messages"):
        assert cara.get(path).status_code == 404
    r = cara.patch(f"/api/v1/accounts/{account_id}", json={"display_name": "x"})
    assert r.status_code == 404
    r = cara.post(f"/api/v1/accounts/{account_id}/messages/{missing}/resolve", json={"outcome": "reviewed"})
    assert r.status_code == 404


def test_shared_mailbox_hides_connection_details_from_other_users(env):
    appm, client, token = env
    account_id = make_account(client, token)
    account = appm.vault.get_account(account_id)
    account["privacy"] = {"visibility": "household", "shared_with": []}
    account.pop("id")
    appm.vault.update_account(account_id, account)

    cara = _second_user(appm, client)
    listed = cara.get("/api/v1/accounts").json()
    assert len(listed) == 1
    assert "server" not in listed[0] and "username" not in listed[0] and "settings" not in listed[0]
    assert "password_set" not in listed[0]
    r = cara.delete(f"/api/v1/accounts/{account_id}")
    assert r.status_code == 403


# ---------- Vault and sessions ----------

def test_non_admin_cannot_lock_the_vault(env):
    appm, client, _ = env
    cara = _second_user(appm, client)
    assert cara.post("/api/v1/lock").status_code == 403
    assert appm.vault.is_unlocked()


def test_parallel_guesses_cannot_bypass_unlock_limit(env):
    appm, client, token = env

    def attempt(i: int) -> int:
        return client.post("/api/v1/unlock", json={"passphrase": f"wrong passphrase {i:04d}"}).status_code

    with cf.ThreadPoolExecutor(16) as pool:
        codes = list(pool.map(attempt, range(16)))
    assert codes.count(401) <= 5
    assert codes.count(429) >= 11


def test_unlock_limit_has_global_budget():
    from fastapi import HTTPException
    from backend.security import UnlockRateLimiter

    limiter = UnlockRateLimiter(max_attempts=5, global_max_attempts=20)
    for i in range(20):
        limiter.acquire(f"10.0.0.{i}")  # a different "client" each time
    with pytest.raises(HTTPException) as exc:
        limiter.acquire("10.0.0.250")
    assert exc.value.status_code == 429


def test_server_config_ignores_forwarded_headers_and_stays_local(monkeypatch):
    import run

    monkeypatch.delenv("ENVELIQ_BIND", raising=False)
    cfg = run.build_config()
    assert cfg["proxy_headers"] is False
    assert cfg["host"] == "127.0.0.1"
    monkeypatch.setenv("ENVELIQ_BIND", "0.0.0.0")
    monkeypatch.delenv("ENVELIQ_ALLOW_NON_LOOPBACK", raising=False)
    with pytest.raises(SystemExit):
        run.build_config()


def test_session_count_is_capped(env):
    appm, _, _ = env
    for _ in range(100):
        appm.sessions.create(Principal("u", "U", False))
    assert appm.sessions.count() <= appm.sessions.max_sessions


def test_lock_revokes_sessions_and_wipes_previews(env):
    appm, client, token = env
    lease = appm.preview_leases.put_safe_preview(
        owner_user_id="ha_user_morgan", account_id="a", message_id="m", attachment_id="x",
        mime_type="image/png", filename="p.png", content=PNG + b"DECRYPTED-PREVIEW")
    backing = lease.content
    assert client.post("/api/v1/lock", headers=auth(token)).status_code == 204
    assert appm.preview_leases.stats()["active_leases"] == 0
    assert all(b == 0 for b in backing)
    assert client.get("/api/v1/me").status_code in (401, 423)


def test_idle_auto_lock_wipes_previews_and_sessions(env):
    appm, client, token = env
    appm.preview_leases.put_safe_preview(
        owner_user_id="ha_user_morgan", account_id="a", message_id="m", attachment_id="x",
        mime_type="image/png", filename="p.png", content=PNG + b"DECRYPTED-PREVIEW")
    appm.vault.idle_lock_seconds = 0
    time.sleep(0.01)
    client.get("/api/v1/status")
    assert appm.preview_leases.stats()["active_leases"] == 0
    assert appm.sessions.count() == 0


def test_idle_watchdog_locks_without_any_request(env):
    appm, _, _ = env
    appm.vault.idle_lock_seconds = 0.05
    appm.vault.start_idle_watchdog(interval_seconds=0.02)
    try:
        deadline = time.monotonic() + 2
        while appm.vault._master_key is not None and time.monotonic() < deadline:
            time.sleep(0.02)
        assert appm.vault._master_key is None
    finally:
        appm.vault.stop_idle_watchdog()


def test_kdf_is_rfc9106_argon2id_and_parameters_are_stored(env):
    from cryptography.hazmat.primitives.kdf.argon2 import Argon2id

    tag = Argon2id(salt=b"\x02" * 16, length=32, iterations=3, lanes=4, memory_cost=32,
                   ad=b"\x04" * 12, secret=b"\x03" * 8).derive(b"\x01" * 32)
    assert tag.hex() == "0d640df58d78766c08c037a34a8b53c9d01ef0452d75b65eb52520e96b01e659"

    appm, _, _ = env
    with sqlite3.connect(appm.DB_PATH) as con:
        stored = con.execute("SELECT kdf_params FROM vault_meta").fetchone()[0]
    assert '"argon2id"' in stored and '"memory_kib": 65536' in stored


def test_old_development_identity_settings_grant_nothing(tmp_path: Path):
    # v0.12 trusted a server-side development identity; v0.17 removed it.
    os.environ.update({"ENVELIQ_DEV_MODE": "1", "ENVELIQ_DEV_USER_ID": "ha_user_morgan", "ENVELIQ_DEV_IS_ADMIN": "1"})
    try:
        appm = load_app(tmp_path)
        c = TestClient(appm.app, raise_server_exceptions=False)
        assert c.post("/api/v1/setup", json={"passphrase": PASSPHRASE}).status_code == 422
        assert c.get("/api/v1/accounts").status_code in (401, 423)
    finally:
        for k in ("ENVELIQ_DEV_MODE", "ENVELIQ_DEV_USER_ID", "ENVELIQ_DEV_IS_ADMIN"):
            os.environ.pop(k, None)


def test_symlinked_or_foreign_data_dir_is_refused(tmp_path: Path):
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    link.symlink_to(real, target_is_directory=True)
    with pytest.raises(RuntimeError, match="symlink"):
        load_app(link)
    load_app(tmp_path / "ok")


def test_created_files_are_private(env, tmp_path: Path):
    appm, client, token = env
    make_account(client, token)
    for p in Path(appm.DATA_DIR).iterdir():
        assert (p.stat().st_mode & 0o077) == 0, p


# ---------- Attachments ----------

def test_status_does_not_reveal_preview_activity(env):
    _, client, token = env
    r = client.get("/api/v1/status")
    assert "active_leases" not in r.text and "bytes_in_ram" not in r.text
    r = client.get("/api/v1/admin/attachment-policy", headers=auth(token))
    assert "active_leases" in r.text  # still visible to administrators


def test_saved_attachment_policy_is_enforced(env):
    from backend.attachments import AttachmentPolicyError

    appm, client, token = env
    r = client.put("/api/v1/admin/attachment-policy", headers=auth(token), json={
        "preview_enabled": True, "max_source_bytes": 1048576, "max_preview_bytes": 1048576,
        "preview_ttl_seconds": 30, "global_ram_cap_bytes": 8388608})
    assert r.status_code == 200
    assert appm.preview_leases.ttl_seconds == 30
    assert appm.preview_leases.max_item_bytes == 1048576

    r = client.put("/api/v1/admin/attachment-policy", headers=auth(token), json={
        "preview_enabled": False, "max_source_bytes": 1048576, "max_preview_bytes": 1048576,
        "preview_ttl_seconds": 30, "global_ram_cap_bytes": 8388608})
    with pytest.raises(AttachmentPolicyError):
        appm.preview_leases.put_safe_preview(
            owner_user_id="ha_user_morgan", account_id="a", message_id="m", attachment_id="x",
            mime_type="image/png", filename="p.png", content=PNG)

    # Policy survives a lock/unlock cycle.
    appm.vault.lock()
    appm.preview_leases.configure(enabled=True, ttl_seconds=300, max_total_bytes=1 << 26, max_item_bytes=1 << 23)
    client.post("/api/v1/unlock", json={"passphrase": PASSPHRASE})
    assert appm.preview_leases.enabled is False


def test_account_delete_purges_its_previews(env):
    appm, client, token = env
    account_id = make_account(client, token)
    appm.preview_leases.put_safe_preview(
        owner_user_id="ha_user_morgan", account_id=account_id, message_id="m", attachment_id="x",
        mime_type="image/png", filename="p.png", content=PNG)
    assert client.delete(f"/api/v1/accounts/{account_id}", headers=auth(token)).status_code == 204
    assert appm.preview_leases.stats()["active_leases"] == 0


def test_disconnecting_an_account_really_deletes_it_and_its_messages(env):
    # v0.12 and earlier crashed here and rolled the delete back, leaving the
    # account, its encrypted credentials and its messages in the database.
    appm, client, token = env
    account_id = make_account(client, token, password="DELETE-ME-CREDENTIAL")
    r = client.post(f"/api/v1/accounts/{account_id}/messages", headers=auth(token),
                    json={"subject": "s", "summary": "DELETE-ME-SUMMARY"})
    assert r.status_code == 201
    assert client.delete(f"/api/v1/accounts/{account_id}", headers=auth(token)).status_code == 204
    assert client.get("/api/v1/accounts", headers=auth(token)).json() == []
    with sqlite3.connect(appm.DB_PATH) as con:
        assert con.execute("SELECT COUNT(*) FROM accounts").fetchone()[0] == 0
        assert con.execute("SELECT COUNT(*) FROM messages").fetchone()[0] == 0


def test_preview_bytes_must_match_declared_type_and_owner():
    from backend.attachments import AttachmentPolicyError, PreviewLeaseStore

    store = PreviewLeaseStore()
    common = dict(owner_user_id="ha_user_morgan", account_id="a", message_id="m", attachment_id="x", filename="f")
    with pytest.raises(AttachmentPolicyError):
        store.put_safe_preview(mime_type="image/png", content=b"<script>alert(1)</script>", **common)
    with pytest.raises(AttachmentPolicyError):
        store.put_safe_preview(mime_type="text/plain", content=b"\xff\xfe\x00binary", **common)
    lease = store.put_safe_preview(mime_type="image/png", content=PNG + b"ok", **common)
    assert store.get_for_owner(lease.lease_id, "ha_user_morgan") is lease
    with pytest.raises(KeyError):
        store.get_for_owner(lease.lease_id, "ha_user_cara")


# ---------- Logging ----------

def test_log_redaction_covers_tokens_and_keys():
    from backend.security import RedactingFilter

    record = logging.LogRecord("enveliq", logging.INFO, __file__, 1,
                               "auth Bearer abcdefghijklmnopqrstuvwxyz012345 key sk-live-SECRETKEY123 session_token=XYZ", (), None)
    RedactingFilter().filter(record)
    text = record.getMessage()
    assert "abcdefghijklmnopqrstuvwxyz012345" not in text
    assert "SECRETKEY123" not in text
    assert "XYZ" not in text


def test_framework_versions_are_past_known_advisories():
    # Starlette < 1.1.0 has published advisories (Host header URL rebuild,
    # HTTPEndpoint method lookup); pyasn1 < 0.6.4 has decoder DoS bugs.
    import pyasn1
    import starlette

    def ver(s: str) -> tuple[int, ...]:
        return tuple(int(p) for p in s.split(".")[:3])

    assert ver(starlette.__version__) >= (1, 1, 0)
    assert ver(pyasn1.__version__) >= (0, 6, 4)


def test_a_mailbox_can_be_renamed_and_nothing_else_changes(env):
    appm, client, token = env
    account_id = make_account(client, token)
    before = appm.vault.get_account(account_id)
    r = client.patch(f"/api/v1/accounts/{account_id}", headers=auth(token), json={"display_name": "  Personal  "})
    assert r.status_code == 200
    assert r.json()["display_name"] == "Personal"
    after = appm.vault.get_account(account_id)
    assert after["display_name"] == "Personal"
    assert {k: v for k, v in after.items() if k != "display_name"} == {k: v for k, v in before.items() if k != "display_name"}
    for bad in ("", "   ", "x" * 129):
        assert client.patch(f"/api/v1/accounts/{account_id}", headers=auth(token), json={"display_name": bad}).status_code == 422
    assert appm.vault.get_account(account_id)["display_name"] == "Personal"


def test_only_the_owner_can_rename_a_mailbox(env):
    appm, client, token = env
    account_id = make_account(client, token)
    cara = _second_user(appm, client)
    r = cara.patch(f"/api/v1/accounts/{account_id}", json={"display_name": "Mine now"})
    assert r.status_code == 404
    assert appm.vault.get_account(account_id)["display_name"] == IMAP_ACCOUNT["display_name"]


def test_a_mailbox_label_colour_is_one_of_the_offered_names(env):
    appm, client, token = env
    account_id = make_account(client, token)
    keep = dict(appm.vault.get_account(account_id)["settings"])
    r = client.patch(f"/api/v1/accounts/{account_id}", headers=auth(token), json={"settings": {**keep, "color": "teal"}})
    assert r.status_code == 200 and r.json()["settings"]["color"] == "teal"
    assert appm.vault.get_account(account_id)["password"] == "original-app-password"
    for bad in ("#ff0000", "red; background:url(x)", "chartreuse", 5):
        r = client.patch(f"/api/v1/accounts/{account_id}", headers=auth(token), json={"settings": {**keep, "color": bad}})
        assert r.status_code == 422, bad
    assert appm.vault.get_account(account_id)["settings"]["color"] == "teal"
    assert client.patch(f"/api/v1/accounts/{account_id}", headers=auth(token), json={"settings": {**keep, "color": ""}}).status_code == 200
