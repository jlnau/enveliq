from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from helpers import PASSPHRASE, create_user, load_app, setup_admin, sign_in


def auth(token: str) -> dict[str, str]:
    # Sessions are HttpOnly cookies held by each TestClient; no header needed.
    return {}


def test_sensitive_values_not_plaintext_on_disk(tmp_path: Path):
    appm = load_app(tmp_path)
    client, _ = setup_admin(appm)
    passphrase = PASSPHRASE
    token = ""

    secret_password = "BRIDGE-PASSWORD-SHOULD-NEVER-BE-PLAINTEXT"
    sensitive_subject = "PRIVATE LAWYER SUBJECT 93bd8f"
    sensitive_summary = "Highly private medical and legal TLDR 7dd19e"
    api_key = "sk-THIS-KEY-MUST-NOT-APPEAR-IN-DATABASE"

    r = client.post(
        "/api/v1/accounts",
        headers=auth(token),
        json={
            "provider": "Proton Mail",
            "display_name": "Private Proton",
            "email_address": "private@example.invalid",
            "auth_method": "proton_bridge",
            "server": "192.168.1.20",
            "port": 1143,
            "username": "bridge-user-sensitive",
            "password": secret_password,
            "settings": {"summary": True},
        },
    )
    assert r.status_code == 201, r.text
    account_id = r.json()["id"]

    r = client.post(
        f"/api/v1/accounts/{account_id}/messages",
        headers=auth(token),
        json={
            "subject": sensitive_subject,
            "sender_display": "Private Sender",
            "sender_address": "sender@example.invalid",
            "summary": sensitive_summary,
            "category": "legal",
            "priority": "high",
            "action_required": True,
            "suggested_task": {"title": "Private action"},
            "attachment_summaries": [{"filename": "private.pdf", "summary": "Attachment private text"}],
        },
    )
    assert r.status_code == 201, r.text

    r = client.put(
        "/api/v1/admin/global-settings",
        headers=auth(token),
        json={
            "llm_provider": "openai_compatible",
            "endpoint": "https://llm.example.invalid",
            "model": "secure-model",
            "api_key": api_key,
            "allow_cloud_processing": False,
        },
    )
    assert r.status_code == 200, r.text

    # Force WAL contents to disk, then scan DB/WAL/SHM bytes for known sensitive markers.
    appm.vault.lock()
    scan = appm.vault.plaintext_scan([
        passphrase,
        secret_password,
        sensitive_subject,
        sensitive_summary,
        api_key,
        "private@example.invalid",
        "bridge-user-sensitive",
    ])
    assert not any(scan.values()), scan


def test_wrong_passphrase_rejected(tmp_path: Path):
    appm = load_app(tmp_path)
    client, _ = setup_admin(appm)
    assert client.post("/api/v1/lock").status_code == 204
    r = client.post("/api/v1/unlock", json={"passphrase": "wrong-password"})
    assert r.status_code == 401
    assert client.post("/api/v1/unlock", json={"passphrase": PASSPHRASE}).status_code == 200


def test_raw_email_body_persistence_is_forbidden(tmp_path: Path):
    appm = load_app(tmp_path)
    client, _ = setup_admin(appm)
    token = ""
    r = client.post(
        "/api/v1/accounts",
        headers=auth(token),
        json={
            "provider": "IMAP",
            "display_name": "Test",
            "email_address": "test@example.invalid",
            "auth_method": "imap",
            "server": "imap.example.invalid",
            "port": 993,
            "username": "test@example.invalid",
            "password": "application-password-value",
        },
    )
    account_id = r.json()["id"]

    # Pydantic rejects an extra raw_body field before it can reach storage.
    r = client.post(
        f"/api/v1/accounts/{account_id}/messages",
        headers=auth(token),
        json={
            "subject": "subject",
            "summary": "summary",
            "priority": "normal",
            "action_required": False,
            "raw_body": "THIS MUST NEVER BE STORED",
        },
    )
    assert r.status_code == 422


def test_secret_fields_never_echo_to_browser(tmp_path: Path):
    appm = load_app(tmp_path)
    client, _ = setup_admin(appm)
    token = ""
    secret = "never-echo-this-provider-secret"
    r = client.post(
        "/api/v1/accounts",
        headers=auth(token),
        json={
            "provider": "IMAP",
            "display_name": "Test",
            "email_address": "test@example.invalid",
            "auth_method": "imap",
            "server": "imap.example.invalid",
            "port": 993,
            "username": "test@example.invalid",
            "password": secret,
        },
    )
    assert r.status_code == 201
    assert secret not in r.text
    r = client.get("/api/v1/accounts", headers=auth(token))
    assert r.status_code == 200
    assert secret not in r.text


def test_non_admin_cannot_modify_global_ai_settings(tmp_path: Path):
    appm = load_app(tmp_path)
    admin, _ = setup_admin(appm)
    create_user(admin, "cara")
    cara = sign_in(appm, "cara")
    r = cara.put("/api/v1/admin/global-settings", json={"llm_provider": "openai", "api_key": "sk-cara-should-not-set"})
    assert r.status_code == 403
    # And setup cannot be run again to take over the instance.
    assert cara.post("/api/v1/setup", json={"setup_code": "x" * 10, "passphrase": "p" * 12, "username": "cara2",
                                            "password": "q" * 12}).status_code == 409


def test_nested_raw_attachment_content_is_rejected(tmp_path: Path):
    appm = load_app(tmp_path)
    client, _ = setup_admin(appm)
    token = ""
    r = client.post(
        "/api/v1/accounts",
        headers=auth(token),
        json={
            "provider": "IMAP",
            "display_name": "Test",
            "email_address": "test@example.invalid",
            "auth_method": "imap",
            "server": "imap.example.invalid",
            "port": 993,
            "username": "test@example.invalid",
            "password": "app-password",
        },
    )
    account_id = r.json()["id"]

    # Extra nested fields are rejected by the strict attachment model before
    # storage. The vault also independently performs recursive key rejection.
    r = client.post(
        f"/api/v1/accounts/{account_id}/messages",
        headers=auth(token),
        json={
            "subject": "subject",
            "summary": "summary",
            "attachments": [{
                "id": "att-1",
                "filename": "file.pdf",
                "mime_type": "application/pdf",
                "size_bytes": 100,
                "summary": "safe summary",
                "preview_kind": "pdf",
                "remote_locator": "opaque-provider-part-1",
                "attachment_bytes": "SHOULD-NOT-PERSIST",
            }],
        },
    )
    assert r.status_code == 422


def test_attachment_locator_is_encrypted_and_never_echoed(tmp_path: Path):
    appm = load_app(tmp_path)
    client, _ = setup_admin(appm)
    token = ""
    r = client.post(
        "/api/v1/accounts",
        headers=auth(token),
        json={
            "provider": "Proton Mail",
            "display_name": "Proton",
            "email_address": "private@example.invalid",
            "auth_method": "proton_bridge",
            "server": "192.168.1.20",
            "port": 1143,
            "username": "bridge-user",
            "password": "bridge-password",
        },
    )
    account_id = r.json()["id"]
    locator = "IMAP-PART-4.2-VERY-SENSITIVE-LOCATOR"
    r = client.post(
        f"/api/v1/accounts/{account_id}/messages",
        headers=auth(token),
        json={
            "subject": "subject",
            "summary": "summary",
            "attachments": [{
                "id": "att-1",
                "filename": "file.pdf",
                "mime_type": "application/pdf",
                "size_bytes": 100,
                "summary": "summary",
                "preview_kind": "pdf",
                "remote_locator": locator,
            }],
        },
    )
    assert r.status_code == 201, r.text
    message_id = r.json()["id"]

    r = client.get(f"/api/v1/accounts/{account_id}/messages", headers=auth(token))
    assert r.status_code == 200
    assert locator not in r.text
    assert r.json()[0]["attachments"][0]["filename"] == "file.pdf"

    appm.vault.lock()
    scan = appm.vault.plaintext_scan([locator, "file.pdf"])
    assert not any(scan.values()), scan


def test_resolving_message_purges_attachment_metadata(tmp_path: Path):
    appm = load_app(tmp_path)
    client, _ = setup_admin(appm)
    token = ""
    r = client.post(
        "/api/v1/accounts",
        headers=auth(token),
        json={
            "provider": "IMAP",
            "display_name": "Test",
            "email_address": "test@example.invalid",
            "auth_method": "imap",
            "server": "imap.example.invalid",
            "port": 993,
            "username": "test@example.invalid",
            "password": "app-password",
        },
    )
    account_id = r.json()["id"]
    r = client.post(
        f"/api/v1/accounts/{account_id}/messages",
        headers=auth(token),
        json={
            "subject": "subject",
            "summary": "summary",
            "attachments": [{
                "id": "att-1",
                "filename": "private.pdf",
                "mime_type": "application/pdf",
                "size_bytes": 1234,
                "summary": "private attachment summary",
                "preview_kind": "pdf",
                "remote_locator": "opaque-1",
            }],
        },
    )
    message_id = r.json()["id"]
    r = client.post(
        f"/api/v1/accounts/{account_id}/messages/{message_id}/resolve",
        headers=auth(token),
        json={"outcome": "reviewed"},
    )
    assert r.status_code == 204
    r = client.get(f"/api/v1/accounts/{account_id}/messages", headers=auth(token))
    assert r.status_code == 200
    # A reviewed card is kept for a few days, but with no attachment details and no mailbox link.
    kept = r.json()
    assert len(kept) == 1 and kept[0]["state"] == "reviewed"
    assert kept[0]["attachments"] == [] and kept[0]["attachment_summaries"] == [] and "source_locator" not in kept[0]
    assert "private.pdf" not in r.text and "opaque-1" not in r.text


def test_preview_leases_are_ram_only_and_zeroized(tmp_path: Path):
    # This directly tests the preview RAM store. It accepts only safe rendered
    # derivatives, not raw PDFs/Office documents.
    from backend.attachments import PreviewLeaseStore

    store = PreviewLeaseStore(ttl_seconds=300, max_total_bytes=1024 * 1024, max_item_bytes=1024 * 1024)
    # Starts with the real PNG signature: the store now checks magic bytes.
    marker = b"\x89PNG\r\n\x1a\n" + b"SAFE-DERIVATIVE-RAM-ONLY-TEST-123"
    lease = store.put_safe_preview(
        owner_user_id="ha_user_morgan",
        account_id="acct",
        message_id="msg",
        attachment_id="att",
        mime_type="image/png",
        filename="page-1.png",
        content=marker,
    )
    assert bytes(store.get(lease.lease_id).content) == marker
    backing = lease.content
    store.delete(lease.lease_id)
    assert all(b == 0 for b in backing)
    assert marker not in b"".join(p.read_bytes() for p in tmp_path.glob("**/*") if p.is_file())
