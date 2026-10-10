"""Reply context and original-email locator (v0.16)."""
from __future__ import annotations

from pathlib import Path

import pytest

from helpers import load_app, setup_admin
REVERSE_ALIAS = "manager_at_harbourview-strata_example_q9x4k2@reverse.alias.example"


@pytest.fixture
def env(tmp_path: Path):
    appm = load_app(tmp_path)
    client, _ = setup_admin(appm)
    headers = {}
    r = client.post("/api/v1/accounts", headers=headers, json={
        "provider": "Proton Mail", "display_name": "Jules Proton", "email_address": "jules@proton.example",
        "auth_method": "proton_bridge", "server": "127.0.0.1", "port": 1143,
        "username": "bridge-user", "password": "bridge-password"})
    yield appm, client, headers, r.json()["id"]
    appm.vault.lock()


def message(**reply_context):
    return {"subject": "Vote required", "summary": "Needs a yes or no vote",
            "source_locator": "INBOX:UID=48213-SECRET-LOCATOR",
            "reply_context": {"reply_to": REVERSE_ALIAS, "delivered_to": "strata.k7q2@alias.example",
                              "via_alias": "Proton Pass alias", "message_id": "<levy-2209@harbourview-strata.example>",
                              "references": ["<levy-2201@harbourview-strata.example>"], **reply_context}}


def test_reverse_alias_reply_address_is_kept_exactly(env):
    appm, client, headers, account_id = env
    r = client.post(f"/api/v1/accounts/{account_id}/messages", headers=headers, json=message())
    assert r.status_code == 201, r.text
    listed = client.get(f"/api/v1/accounts/{account_id}/messages", headers=headers).json()[0]
    assert listed["reply_context"]["reply_to"] == REVERSE_ALIAS
    assert listed["reply_context"]["delivered_to"] == "strata.k7q2@alias.example"


def test_source_locator_is_encrypted_and_never_sent_to_browser(env):
    appm, client, headers, account_id = env
    client.post(f"/api/v1/accounts/{account_id}/messages", headers=headers, json=message())
    r = client.get(f"/api/v1/accounts/{account_id}/messages", headers=headers)
    assert "SECRET-LOCATOR" not in r.text
    assert "source_locator" not in r.json()[0]
    appm.vault.lock()
    assert not any(appm.vault.plaintext_scan(["SECRET-LOCATOR", REVERSE_ALIAS]).values())


@pytest.mark.parametrize("field,value", [
    ("reply_to", "victim@example.com\r\nBcc: attacker@evil.example"),
    ("reply_to", "victim@example.com\nBcc: attacker@evil.example"),
    ("delivered_to", "me@example.com\r\nX-Injected: 1"),
    ("via_alias", "Proton\r\nBcc: attacker@evil.example"),
    ("message_id", "<id@host>\r\nBcc: attacker@evil.example"),
])
def test_header_injection_is_rejected(env, field, value):
    _, client, headers, account_id = env
    r = client.post(f"/api/v1/accounts/{account_id}/messages", headers=headers, json=message(**{field: value}))
    assert r.status_code == 422
    assert "attacker@evil.example" not in r.text


def test_reply_context_shapes_are_validated(env):
    _, client, headers, account_id = env
    for field, value in [("reply_to", "not-an-address"), ("message_id", "no-angle-brackets@host"),
                         ("references", ["<ok@host>", "bad ref"])]:
        r = client.post(f"/api/v1/accounts/{account_id}/messages", headers=headers, json=message(**{field: value}))
        assert r.status_code == 422, field
