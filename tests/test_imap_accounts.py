"""Ordinary IMAP services (Gmail, iCloud, Yahoo, Fastmail, other): app-password sign-in over
verified TLS, the destination rules, and archive / bin using each service's own folders."""
from __future__ import annotations

from pathlib import Path

import pytest

from fake_bridge import FakeBridge, raw_email
from helpers import load_app, setup_admin
from test_bridge import mails

EMAIL = "me@example.com"
GMAIL_FOLDERS = [("\\HasNoChildren", "INBOX"), ("\\HasNoChildren \\All", "[Gmail]/All Mail"), ("\\HasNoChildren \\Trash", "[Gmail]/Trash")]


def start(tmp_path: Path, *, implicit=True, folders=None, listed=True, **bridge_kw):
    bridge = FakeBridge(tmp_path, user=EMAIL, implicit_tls=implicit, folders=folders, **bridge_kw)
    for uid, raw in mails().items():
        bridge.add(uid, raw)
    env = {"ENVELIQ_MAIL_CA_FILE": str(bridge.cert_path)}
    if listed:
        env["ENVELIQ_MAIL_ALLOWED_HOSTS"] = "127.0.0.1"        # the fake server stands in for a service the administrator approved
    (tmp_path / "data").mkdir()
    appm = load_app(tmp_path / "data", **env)
    client, _ = setup_admin(appm)
    return appm, client, bridge


def add(client, bridge, *, implicit=True, **over) -> str:
    sec = "ssl" if implicit else "starttls"
    body = {
        "provider": "Gmail", "display_name": "Gmail", "email_address": EMAIL, "auth_method": "imap",
        "server": "127.0.0.1", "port": bridge.imap_port, "username": EMAIL, "password": bridge.password,
        "settings": {"provider_id": "gmail", "imap_security": sec, "smtp_host": "127.0.0.1", "smtp_port": bridge.smtp_port, "smtp_security": sec, "send_identities": []},
    }
    body.update(over)
    r = client.post("/api/v1/accounts", json=body)
    assert r.status_code == 201, r.text
    return r.json()["id"]


@pytest.fixture(params=[True, False], ids=["implicit-tls", "starttls"])
def env(request, tmp_path):
    appm, client, bridge = start(tmp_path, implicit=request.param, folders=GMAIL_FOLDERS)
    yield client, bridge, request.param
    bridge.close()


def synced(client, bridge, implicit):
    aid = add(client, bridge, implicit=implicit)
    assert client.post(f"/api/v1/accounts/{aid}/sync", json={}).status_code == 200
    return aid, {m["subject"]: m for m in client.get(f"/api/v1/accounts/{aid}/messages").json()}


# ---------- the list of services ----------

def test_the_list_of_services(tmp_path):
    appm, client, _ = start(tmp_path, listed=False)
    r = client.get("/api/v1/mail/providers")
    assert r.status_code == 200
    by_id = {p["id"]: p for p in r.json()}
    assert {"proton", "gmail", "icloud", "yahoo", "fastmail", "other", "outlook"} <= set(by_id)
    gmail = by_id["gmail"]
    assert gmail["kind"] == "imap" and gmail["imap_host"] == "imap.gmail.com" and gmail["app_password_url"].startswith("https://")
    assert gmail["steps"] and gmail["requirements"]
    assert by_id["proton"]["kind"] == "bridge"
    assert by_id["outlook"]["status"] == "unavailable" and by_id["outlook"]["unavailable_reason"]
    assert by_id["other"]["custom"] is True
    from backend.mail import providers
    for p in providers.PROVIDERS:
        if p.kind == "imap" and p.status == "ready" and not p.custom:
            assert p.imap_host and p.smtp_host and p.steps, p.id           # a new service must be complete
    assert TestClientAnon(appm).get("/api/v1/mail/providers").status_code in (401, 403)


def TestClientAnon(appm):
    from fastapi.testclient import TestClient
    return TestClient(appm.app)


# ---------- connecting, syncing, reading, replying, resolving ----------

def test_connect_sync_view_reply(env):
    client, bridge, implicit = env
    aid = add(client, bridge, implicit=implicit)
    check = client.post(f"/api/v1/accounts/{aid}/bridge/check", json={}).json()
    assert check["imap"] == "ok" and check["smtp"] == "ok", check
    aid, m = synced(client, bridge, implicit)
    assert set(m) == {"Quarterly update", "Weekly news", "Invoice question"}
    assert not any("BODY.PEEK[]" in line for line in bridge.log)                 # headers only
    original = client.get(f"/api/v1/accounts/{aid}/messages/{m['Quarterly update']['id']}/original").json()
    assert original["text"].strip() == "Numbers are attached."
    r = client.post(f"/api/v1/accounts/{aid}/messages/{m['Quarterly update']['id']}/reply", json={"body": "Thanks."})
    assert r.status_code == 200, r.text
    assert bridge.sent and bridge.sent[-1]["to"] == ["alice@example.invalid"]


def test_archive_and_bin_use_the_services_own_folders(env):
    client, bridge, implicit = env
    aid, m = synced(client, bridge, implicit)
    assert client.post(f"/api/v1/accounts/{aid}/messages/{m['Quarterly update']['id']}/resolve", json={"outcome": "archived"}).status_code == 204
    assert client.post(f"/api/v1/accounts/{aid}/messages/{m['Weekly news']['id']}/resolve", json={"outcome": "binned"}).status_code == 204
    assert bridge.in_folder("[Gmail]/All Mail") == [1]                         # Gmail's archive
    assert bridge.in_folder("[Gmail]/Trash") == [2]
    assert "\\Seen" in bridge.messages[1]["flags"]


def test_folders_found_by_usual_name_when_not_flagged(tmp_path):
    folders = [("\\HasNoChildren", "INBOX"), ("\\HasNoChildren", "Archive"), ("\\HasNoChildren", "Deleted Messages")]
    _, client, bridge = start(tmp_path, folders=folders)
    try:
        aid, m = synced(client, bridge, True)
        client.post(f"/api/v1/accounts/{aid}/messages/{m['Quarterly update']['id']}/resolve", json={"outcome": "archived"})
        client.post(f"/api/v1/accounts/{aid}/messages/{m['Weekly news']['id']}/resolve", json={"outcome": "binned"})
        assert bridge.in_folder("Archive") == [1] and bridge.in_folder("Deleted Messages") == [2]
    finally:
        bridge.close()


def test_a_missing_folder_keeps_the_item_and_says_why(tmp_path):
    _, client, bridge = start(tmp_path, folders=[("\\HasNoChildren", "INBOX")])
    try:
        aid, m = synced(client, bridge, True)
        r = client.post(f"/api/v1/accounts/{aid}/messages/{m['Quarterly update']['id']}/resolve", json={"outcome": "archived"})
        assert r.status_code == 404 and "Archive" in r.json()["detail"]["message"]
        assert len(client.get(f"/api/v1/accounts/{aid}/messages").json()) == 3
    finally:
        bridge.close()


# ---------- sign-in problems are explained ----------

def test_wrong_password_and_app_password_required(tmp_path):
    _, client, bridge = start(tmp_path, alert_password="my-real-password")
    try:
        aid = add(client, bridge, password="not-it")
        assert client.post(f"/api/v1/accounts/{aid}/bridge/check", json={}).json()["imap"] == "login_failed"
        aid2 = add(client, bridge, password="my-real-password")
        assert client.post(f"/api/v1/accounts/{aid2}/bridge/check", json={}).json()["imap"] == "app_password_required"
    finally:
        bridge.close()


def test_a_certificate_that_is_not_trusted_is_refused_before_any_login(tmp_path):
    (tmp_path / "trusted").mkdir()
    (tmp_path / "stranger").mkdir()
    trusted = FakeBridge(tmp_path / "trusted", user=EMAIL, implicit_tls=True)
    stranger = FakeBridge(tmp_path / "stranger", user=EMAIL, implicit_tls=True)    # presents a certificate nobody vouched for
    (tmp_path / "data").mkdir()
    appm = load_app(tmp_path / "data", ENVELIQ_MAIL_ALLOWED_HOSTS="127.0.0.1", ENVELIQ_MAIL_CA_FILE=str(trusted.cert_path))
    client, _ = setup_admin(appm)
    try:
        aid = add(client, stranger)
        r = client.post(f"/api/v1/accounts/{aid}/bridge/check", json={}).json()
        assert r["imap"] == "tls_failed", r
        assert not any(line.startswith("LOGIN") for line in stranger.log)
        aid2 = add(client, trusted)
        assert client.post(f"/api/v1/accounts/{aid2}/bridge/check", json={}).json()["imap"] == "ok"
    finally:
        trusted.close(); stranger.close()


# ---------- destination rules ----------

@pytest.fixture
def open_policy(tmp_path):
    """No administrator list: only ordinary public secure servers are allowed."""
    _, client, bridge = start(tmp_path, listed=False)
    yield client, bridge
    bridge.close()


def check_of(client, bridge, **over):
    aid = add(client, bridge, **over)
    return client.post(f"/api/v1/accounts/{aid}/bridge/check", json={}).json()


def test_private_and_local_addresses_are_refused_by_default(open_policy):
    client, bridge = open_policy
    for host in ("127.0.0.1", "192.168.1.5", "10.0.0.5"):
        assert check_of(client, bridge, server=host)["imap"] == "host_not_allowed", host
    assert bridge.log == []                                                       # nothing was contacted


def test_a_name_that_points_at_a_private_address_is_refused(open_policy, monkeypatch):
    client, bridge = open_policy
    import socket
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.1.2.3", 993))])
    r = check_of(client, bridge, server="mail.example.com", port=993)
    assert r["imap"] == "host_not_allowed" and "private network" in r["imap_message"]


def test_only_secure_standard_ports_and_real_names(open_policy):
    client, bridge = open_policy
    assert check_of(client, bridge, server="mail.example.com", port=25)["imap"] == "not_configured"
    assert check_of(client, bridge, server="localhost", port=993)["imap"] == "not_configured"
    assert check_of(client, bridge, server="mail.example.com", port=993, settings={"imap_security": "none", "smtp_host": "smtp.example.com", "smtp_port": 465, "smtp_security": "ssl"})["imap"] == "not_configured"


def test_the_administrator_list_is_exclusive(tmp_path):
    _, client, bridge = start(tmp_path)
    try:
        assert check_of(client, bridge, server="mail.example.com", port=993)["imap"] == "host_not_allowed"
    finally:
        bridge.close()


def test_the_password_is_never_shown_back(env):
    client, bridge, implicit = env
    aid = add(client, bridge, implicit=implicit)
    assert bridge.password not in client.get("/api/v1/accounts").text
    assert bridge.password not in client.get(f"/api/v1/accounts/{aid}/messages").text
