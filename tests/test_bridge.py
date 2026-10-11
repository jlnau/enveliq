"""Proton Mail Bridge connection: pinned certificate, sync, view, reply, resolve."""
from __future__ import annotations

import email
import re
from email import policy
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from fake_bridge import FakeBridge, make_cert, raw_email
from helpers import create_user, load_app, setup_admin, sign_in

MAILBOX = "me@example.invalid"
WORK = "work@example.invalid"
REVERSE = "news_at_example_invalid_k3j9@simplelogin.co"


def mails() -> dict[int, bytes]:
    return {
        1: raw_email("Quarterly update", "Alice Example <alice@example.invalid>", MAILBOX,
                     message_id="<a1@example.invalid>", body="Numbers are attached.\n"),
        2: raw_email("Weekly news", "News <news_at_example_invalid_k3j9@simplelogin.co>", "alias1@passmail.net",
                     reply_to=REVERSE, delivered_to=MAILBOX, message_id="<n2@example.invalid>",
                     references="<old1@example.invalid> <old2@example.invalid>"),
        3: raw_email("Invoice question", "Bob <bob@example.invalid>", WORK, delivered_to=WORK,
                     message_id="<b3@example.invalid>"),
    }


def html_mail() -> bytes:
    return (
        b"From: Carol <carol@example.invalid>\r\nTo: me@example.invalid\r\nSubject: Rich message\r\n"
        b"Message-ID: <c4@example.invalid>\r\nMIME-Version: 1.0\r\n"
        b'Content-Type: multipart/mixed; boundary="B"\r\n\r\n--B\r\n'
        b'Content-Type: text/html; charset=utf-8\r\n\r\n'
        b"<html><head><title>x</title><style>p{}</style></head><body><script>alert(1)</script>"
        b"<p>Hello <b>Dana</b></p><img src='http://tracker.invalid/p.gif'></body></html>\r\n"
        b"--B\r\nContent-Type: application/pdf; name=\"report.pdf\"\r\nContent-Disposition: attachment; filename=\"report.pdf\"\r\n"
        b"Content-Transfer-Encoding: base64\r\n\r\nSGVsbG8=\r\n--B--\r\n"
    )


@pytest.fixture
def env(tmp_path: Path):
    bridge = FakeBridge(tmp_path)
    for uid, raw in mails().items():
        bridge.add(uid, raw)
    appm = load_app(tmp_path / "data" if (tmp_path / "data").mkdir() is None else tmp_path,
                    ENVELIQ_BRIDGE_CA_FILE=str(bridge.cert_path))
    client, _ = setup_admin(appm)
    yield appm, client, bridge, tmp_path
    bridge.close()


def add_account(client: TestClient, bridge: FakeBridge, **over) -> str:
    body = {
        "provider": "Proton Mail", "display_name": "Proton", "email_address": MAILBOX, "auth_method": "proton_bridge",
        "server": "127.0.0.1", "port": bridge.imap_port, "username": bridge.user, "password": bridge.password,
        "settings": {"smtp_port": bridge.smtp_port, "send_identities": [WORK]},
    }
    body.update(over)
    r = client.post("/api/v1/accounts", json=body)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def synced(client, bridge):
    aid = add_account(client, bridge)
    r = client.post(f"/api/v1/accounts/{aid}/sync", json={})
    assert r.status_code == 200, r.text
    msgs = client.get(f"/api/v1/accounts/{aid}/messages").json()
    return aid, {m["subject"]: m for m in msgs}


# ---------- connection and certificate pinning ----------

def test_check_ok(env):
    _, client, bridge, _ = env
    aid = add_account(client, bridge)
    r = client.post(f"/api/v1/accounts/{aid}/bridge/check")
    assert r.status_code == 200 and r.json() == {"imap": "ok", "smtp": "ok"}
    assert all("tls=True" in line for line in bridge.log if line.startswith(("LOGIN", "SELECT", "EXAMINE")))
    assert "AUTH [tls=True]" in bridge.smtp_log


def test_wrong_password_is_login_failed(env):
    _, client, bridge, _ = env
    aid = add_account(client, bridge, password="wrong")
    r = client.post(f"/api/v1/accounts/{aid}/bridge/check").json()
    assert r["imap"] == "login_failed" and r["smtp"] == "login_failed"
    assert "wrong" not in str(r)


def test_other_certificate_is_refused_before_any_login(env, tmp_path):
    appm, client, bridge, base = env
    impostor = FakeBridge(base, cert_name="impostor")
    try:
        aid = add_account(client, impostor)
        r = client.post(f"/api/v1/accounts/{aid}/bridge/check").json()
        assert r["imap"] == "certificate_mismatch" and r["smtp"] == "certificate_mismatch"
        assert not any(line.startswith("LOGIN") for line in impostor.log)
        assert not any(line.startswith("AUTH") for line in impostor.smtp_log)
    finally:
        impostor.close()


def test_no_starttls_means_no_login(tmp_path):
    bridge = FakeBridge(tmp_path, starttls=False)
    try:
        appm = load_app(tmp_path / "d" if (tmp_path / "d").mkdir() is None else tmp_path, ENVELIQ_BRIDGE_CA_FILE=str(bridge.cert_path))
        client, _ = setup_admin(appm)
        aid = add_account(client, bridge)
        r = client.post(f"/api/v1/accounts/{aid}/bridge/check").json()
        assert r["imap"] == "protocol_error"
        assert not any(line.startswith("LOGIN") for line in bridge.log)
    finally:
        bridge.close()


def test_unreachable_and_missing_certificate(env):
    appm, client, bridge, base = env
    aid = add_account(client, bridge, port=1999)
    assert client.post(f"/api/v1/accounts/{aid}/bridge/check").json()["imap"] == "unreachable"
    appm.bridge.config.ca_file.rename(base / "moved.crt")
    aid2 = add_account(client, bridge)
    r = client.post(f"/api/v1/accounts/{aid2}/bridge/check")
    assert r.status_code == 200 and r.json()["imap"] == "no_certificate"


@pytest.mark.parametrize("host", ["8.8.8.8", "mail.example.com", "169.254.1.1x", "0.0.0.0"])
def test_destination_rules_block_public_and_unknown_hosts(env, host):
    _, client, bridge, _ = env
    try:
        aid = add_account(client, bridge, server=host)
    except AssertionError:
        return  # rejected when the mailbox was created
    r = client.post(f"/api/v1/accounts/{aid}/bridge/check").json()
    assert r["imap"] == "host_not_allowed"
    assert not bridge.log


def test_privileged_ports_refused(env):
    _, client, bridge, _ = env
    aid = add_account(client, bridge, port=25)
    assert client.post(f"/api/v1/accounts/{aid}/bridge/check").json()["imap"] == "not_configured"
    assert not bridge.log


# ---------- sync ----------

def test_sync_reads_headers_only_and_keeps_unread(env):
    _, client, bridge, _ = env
    aid, by_subject = synced(client, bridge)
    assert set(by_subject) == {"Quarterly update", "Weekly news", "Invoice question"}
    assert not any("BODY.PEEK[]" in line for line in bridge.log)         # no full bodies fetched
    assert not any("STORE" in line for line in bridge.log)               # nothing marked read
    assert all(m["summary"].startswith("Not summarised yet") for m in by_subject.values())
    assert all("source_locator" not in m for m in by_subject.values())    # backend-only
    assert "Numbers are attached" not in str(by_subject)


def test_sync_keeps_the_sent_date_for_ordering(env):
    _, client, bridge, _ = env
    _, by_subject = synced(client, bridge)
    # Every fake email is dated Wed, 07 Oct 2026 09:00:00 +1100.
    assert {m["received_at"] for m in by_subject.values()} == {1791324000.0}


def test_unusable_date_header_is_ignored():
    from backend.mail.parse import summarise_headers
    raw = b"From: A <a@example.invalid>\r\nSubject: Hi\r\nDate: not a date\r\nMessage-ID: <x@example.invalid>\r\n\r\n"
    assert summarise_headers(raw, ["me@example.invalid"])["received_at"] is None


def test_sync_is_idempotent(env):
    _, client, bridge, _ = env
    aid, _ = synced(client, bridge)
    r = client.post(f"/api/v1/accounts/{aid}/sync", json={}).json()
    assert r["added"] == 0
    assert len(client.get(f"/api/v1/accounts/{aid}/messages").json()) == 3
    bridge.add(9, raw_email("Late arrival", "Eve <eve@example.invalid>", MAILBOX, message_id="<e9@example.invalid>"))
    assert client.post(f"/api/v1/accounts/{aid}/sync", json={}).json()["added"] == 1


def test_sync_forgets_mail_read_moved_or_deleted_elsewhere(env):
    _, client, bridge, _ = env
    aid, _ = synced(client, bridge)
    bridge.messages[1]["flags"].add("\\Seen")      # read in another app
    bridge.messages[2]["folder"] = "Archive"       # archived in another app
    del bridge.messages[3]                         # deleted in another app
    r = client.post(f"/api/v1/accounts/{aid}/sync", json={}).json()
    assert r["removed"] == 3 and r["added"] == 0
    assert client.get(f"/api/v1/accounts/{aid}/messages").json() == []
    assert not any("STORE" in line or "MOVE" in line or "EXPUNGE" in line for line in bridge.log)   # the mailbox is never changed


def test_sync_keeps_mail_that_is_still_unread(env):
    _, client, bridge, _ = env
    aid, _ = synced(client, bridge)
    bridge.messages[1]["flags"].add("\\Seen")
    r = client.post(f"/api/v1/accounts/{aid}/sync", json={}).json()
    assert r["removed"] == 1
    assert {m["subject"] for m in client.get(f"/api/v1/accounts/{aid}/messages").json()} == {"Weekly news", "Invoice question"}


def test_sync_removes_nothing_when_the_mailbox_was_reset(env):
    _, client, bridge, _ = env
    aid, _ = synced(client, bridge)
    bridge.uidvalidity = 8      # UIDs now mean something else; do not guess
    r = client.post(f"/api/v1/accounts/{aid}/sync", json={}).json()
    assert r["removed"] == 0


def test_reply_context_follows_alias_rules(env):
    _, client, bridge, _ = env
    _, m = synced(client, bridge)
    plain = m["Quarterly update"]["reply_context"]
    assert plain["reply_to"] == "alice@example.invalid" and plain["via_alias"] is None
    alias = m["Weekly news"]["reply_context"]
    assert alias["reply_to"] == REVERSE                      # reverse alias kept exactly
    assert alias["via_alias"] == "SimpleLogin"
    assert alias["delivered_to"] == MAILBOX
    assert alias["references"] == ["<old1@example.invalid>", "<old2@example.invalid>"]
    assert m["Invoice question"]["reply_context"]["delivered_to"] == WORK


# ---------- view original ----------

def test_view_original_is_plain_text_and_not_stored(env):
    appm, client, bridge, _ = env
    bridge.add(4, html_mail())
    aid, m = synced(client, bridge)
    r = client.get(f"/api/v1/accounts/{aid}/messages/{m['Rich message']['id']}/original")
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
    out = r.json()
    assert "Hello Dana" in out["text"]
    for bad in ("alert(1)", "<script", "tracker.invalid", "<p>"):
        assert bad not in out["text"]
    assert out["attachments"] == [{"index": 0, "filename": "report.pdf", "mime_type": "application/pdf", "size_bytes": 5, "inline": False, "previewable": False, "viewable": True}]
    appm.vault.lock()
    assert not any(appm.vault.plaintext_scan(["Hello Dana", "Numbers are attached"]).values())


def test_view_fails_cleanly_when_mailbox_changed(env):
    _, client, bridge, _ = env
    aid, m = synced(client, bridge)
    mid = m["Quarterly update"]["id"]
    bridge.uidvalidity = 8
    r = client.get(f"/api/v1/accounts/{aid}/messages/{mid}/original")
    assert r.status_code == 404 and r.json()["detail"]["code"] == "not_found"
    bridge.uidvalidity = 7
    del bridge.messages[1]
    assert client.get(f"/api/v1/accounts/{aid}/messages/{mid}/original").status_code == 404


def test_oversized_email_refused(env):
    _, client, bridge, _ = env
    aid, m = synced(client, bridge)
    bridge.report_size = 50 * 1024 * 1024
    r = client.get(f"/api/v1/accounts/{aid}/messages/{m['Quarterly update']['id']}/original")
    assert r.status_code == 413
    assert not any("BODY.PEEK[]" in line for line in bridge.log)


# ---------- reply ----------

def sent_message(bridge: FakeBridge, index: int = -1):
    item = bridge.sent[index]
    return item, email.message_from_bytes(item["data"], policy=policy.default)


def test_reply_to_plain_sender_from_mailbox(env):
    _, client, bridge, _ = env
    aid, m = synced(client, bridge)
    r = client.post(f"/api/v1/accounts/{aid}/messages/{m['Quarterly update']['id']}/reply", json={"body": "Thanks, got it."})
    assert r.status_code == 200 and r.json() == {"sent": True, "from": MAILBOX}
    item, msg = sent_message(bridge)
    assert item["from"] == MAILBOX and item["to"] == ["alice@example.invalid"]
    assert msg["Subject"] == "Re: Quarterly update" and msg["In-Reply-To"] == "<a1@example.invalid>"
    assert "Thanks, got it." in msg.get_content()


def test_reply_to_reverse_alias_keeps_address_and_threads(env):
    _, client, bridge, _ = env
    aid, m = synced(client, bridge)
    client.post(f"/api/v1/accounts/{aid}/messages/{m['Weekly news']['id']}/reply", json={"body": "Noted."})
    item, msg = sent_message(bridge)
    assert item["to"] == [REVERSE] and msg["To"] == REVERSE
    assert item["from"] == MAILBOX                                  # forwarding alias: send from the mailbox
    assert msg["References"] == "<old1@example.invalid> <old2@example.invalid> <n2@example.invalid>"


def test_reply_sends_from_delivered_identity_when_allowed(env):
    _, client, bridge, _ = env
    aid, m = synced(client, bridge)
    client.post(f"/api/v1/accounts/{aid}/messages/{m['Invoice question']['id']}/reply", json={"body": "Will do."})
    assert sent_message(bridge)[0]["from"] == WORK


def test_cannot_send_from_a_foreign_address(env):
    _, client, bridge, _ = env
    aid, m = synced(client, bridge)
    mid = m["Quarterly update"]["id"]
    url = f"/api/v1/accounts/{aid}/messages/{mid}/reply"
    assert client.post(url, json={"body": "x", "from_address": "boss@example.invalid"}).status_code == 400
    assert client.post(url, json={"body": "x", "from_address": "a@example.invalid\r\nBcc: z@example.invalid"}).status_code == 422
    assert client.post(url, json={"body": "x", "from_address": WORK}).status_code == 200
    assert sent_message(bridge)[0]["from"] == WORK
    assert len(bridge.sent) == 1


def test_spoofed_delivered_to_cannot_pick_a_foreign_sender(env):
    _, client, bridge, _ = env
    bridge.add(5, raw_email("Hello", "Mallory <m@example.invalid>", MAILBOX, delivered_to="ceo@example.invalid",
                            message_id="<m5@example.invalid>"))
    aid, m = synced(client, bridge)
    assert m["Hello"]["reply_context"]["delivered_to"] is None or m["Hello"]["reply_context"]["delivered_to"].lower() == MAILBOX
    client.post(f"/api/v1/accounts/{aid}/messages/{m['Hello']['id']}/reply", json={"body": "hi"})
    assert sent_message(bridge)[0]["from"] == MAILBOX


def test_refused_send_reported_and_rate_limited(env):
    appm, client, bridge, _ = env
    aid, m = synced(client, bridge)
    url = f"/api/v1/accounts/{aid}/messages/{m['Quarterly update']['id']}/reply"
    bridge.smtp_reject = True
    r = client.post(url, json={"body": "x"})
    assert r.status_code == 502 and r.json()["detail"]["code"] == "send_refused"
    bridge.smtp_reject = False
    codes = [client.post(url, json={"body": "x"}).status_code for _ in range(22)]
    assert 429 in codes and codes.count(200) <= 19


def test_message_without_reply_address_cannot_be_replied_to(env):
    _, client, bridge, _ = env
    bridge.add(6, b"To: me@example.invalid\r\nSubject: No sender\r\nMessage-ID: <z6@example.invalid>\r\n\r\nhi\r\n")
    aid, m = synced(client, bridge)
    r = client.post(f"/api/v1/accounts/{aid}/messages/{m['No sender']['id']}/reply", json={"body": "x"})
    assert r.status_code == 400


# ---------- resolve: the real mailbox changes first ----------

def resolve(client, aid, mid, outcome):
    return client.post(f"/api/v1/accounts/{aid}/messages/{mid}/resolve", json={"outcome": outcome})


def test_reviewed_marks_read_and_does_not_return(env):
    _, client, bridge, _ = env
    aid, m = synced(client, bridge)
    assert resolve(client, aid, m["Quarterly update"]["id"], "reviewed").status_code == 204
    assert "\\Seen" in bridge.messages[1]["flags"] and bridge.messages[1]["folder"] == "INBOX"
    assert client.post(f"/api/v1/accounts/{aid}/sync", json={}).json()["added"] == 0
    listed = client.get(f"/api/v1/accounts/{aid}/messages").json()
    assert len([x for x in listed if x["state"] == "unread"]) == 2 and len(listed) == 3      # the reviewed one is kept for a few days


def test_archive_and_bin_move_the_email(env):
    _, client, bridge, _ = env
    aid, m = synced(client, bridge)
    assert resolve(client, aid, m["Quarterly update"]["id"], "archived").status_code == 204
    assert resolve(client, aid, m["Weekly news"]["id"], "binned").status_code == 204
    assert bridge.messages[1]["folder"] == "Archive" and bridge.messages[2]["folder"] == "Trash"


def test_move_falls_back_to_copy_and_expunge(tmp_path):
    bridge = FakeBridge(tmp_path, move=False)
    bridge.add(1, mails()[1])
    try:
        appm = load_app(tmp_path / "d" if (tmp_path / "d").mkdir() is None else tmp_path, ENVELIQ_BRIDGE_CA_FILE=str(bridge.cert_path))
        client, _ = setup_admin(appm)
        aid, m = synced(client, bridge)
        assert resolve(client, aid, m["Quarterly update"]["id"], "archived").status_code == 204
        assert 1 not in bridge.messages
        assert bridge.in_folder("Archive") and not bridge.in_folder("INBOX")
    finally:
        bridge.close()


def test_failed_provider_action_keeps_the_item(env):
    _, client, bridge, _ = env
    aid, m = synced(client, bridge)
    bridge.uidvalidity = 99
    r = resolve(client, aid, m["Quarterly update"]["id"], "archived")
    assert r.status_code == 404
    assert len(client.get(f"/api/v1/accounts/{aid}/messages").json()) == 3
    bridge.close()
    r = resolve(client, aid, m["Quarterly update"]["id"], "binned")
    assert r.status_code == 502 and len(client.get(f"/api/v1/accounts/{aid}/messages").json()) == 3


def test_expired_is_local_only(env):
    _, client, bridge, _ = env
    aid, m = synced(client, bridge)
    before = len(bridge.log)
    assert resolve(client, aid, m["Quarterly update"]["id"], "expired").status_code == 204
    assert len(bridge.log) == before


# ---------- access control ----------

def test_other_users_and_other_providers(env):
    appm, admin, bridge, _ = env
    aid, m = synced(admin, bridge)
    create_user(admin, "cara")
    cara = sign_in(appm, "cara")
    mid = m["Quarterly update"]["id"]
    for method, url, body in (
        ("post", f"/api/v1/accounts/{aid}/sync", {}),
        ("post", f"/api/v1/accounts/{aid}/bridge/check", None),
        ("get", f"/api/v1/accounts/{aid}/messages/{mid}/original", None),
        ("post", f"/api/v1/accounts/{aid}/messages/{mid}/reply", {"body": "hi"}),
    ):
        r = getattr(cara, method)(url, **({"json": body} if body is not None else {}))
        assert r.status_code == 404, (url, r.status_code)       # same as a mailbox that does not exist
    imap_acct = admin.post("/api/v1/accounts", json={
        "provider": "IMAP", "display_name": "Other", "email_address": "o@example.invalid", "auth_method": "imap",
        "server": "10.0.0.5", "port": 993, "username": "o", "password": "p"}).json()["id"]
    assert admin.post(f"/api/v1/accounts/{imap_acct}/sync", json={}).status_code == 400
    assert TestClient(appm.app).post(f"/api/v1/accounts/{aid}/sync", json={}).status_code in (401, 403)


# ---------- administrator allowlist and the command-line check ----------

def test_admin_allowlist_is_exclusive(tmp_path):
    bridge = FakeBridge(tmp_path)
    try:
        appm = load_app(tmp_path / "d" if (tmp_path / "d").mkdir() is None else tmp_path,
                        ENVELIQ_BRIDGE_CA_FILE=str(bridge.cert_path), ENVELIQ_BRIDGE_ALLOWED_HOSTS="10.9.9.9")
        client, _ = setup_admin(appm)
        aid = add_account(client, bridge)            # 127.0.0.1 is private, but not on the list
        assert client.post(f"/api/v1/accounts/{aid}/bridge/check").json()["imap"] == "host_not_allowed"
        assert not bridge.log
    finally:
        bridge.close()


def test_command_line_check(env, monkeypatch, capsys):
    appm, _, bridge, _ = env
    from backend.mail import check
    monkeypatch.setenv("ENVELIQ_BRIDGE_CA_FILE", str(bridge.cert_path))
    monkeypatch.setenv("ENVELIQ_CHECK_PASSWORD", bridge.password)
    argv = ["--host", "127.0.0.1", "--imap-port", str(bridge.imap_port), "--smtp-port", str(bridge.smtp_port), "--user", bridge.user]
    assert check.main(argv) == 0
    assert "IMAP  OK" in capsys.readouterr().out
    monkeypatch.setenv("ENVELIQ_CHECK_PASSWORD", "nope")
    assert check.main(argv) == 1
    out = capsys.readouterr().out
    assert "login_failed" in out and "nope" not in out


def test_original_text_has_no_invisible_padding_or_huge_gaps():
    from backend.mail.parse import render_original
    padded = raw_email("Padded", "Carol <carol@example.invalid>", MAILBOX, message_id="<p5@example.invalid>",
                       body="\u200c \u200c\n   \n\n\n\n\u034f\nHey Dana!\u00a0\n\n\n\n\n\nSecond line\u202e  \n\n\n")
    padded = padded.replace(b"\r\n\r\n", b"\r\nContent-Type: text/plain; charset=utf-8\r\n\r\n", 1)
    text = render_original(padded)["text"]
    assert text == "Hey Dana!\n\nSecond line"


def test_sync_fills_in_the_date_of_older_items(env):
    """Items saved before dates were kept (v0.19) get their sent date on the next sync."""
    appm, client, bridge, _ = env
    aid, _ = synced(client, bridge)
    vault = appm.vault
    for stored in vault.list_messages(aid):
        data = {k: v for k, v in stored.items() if k != "id"}
        data["received_at"] = None
        vault.update_message(aid, stored["id"], data)
    assert all(m["received_at"] is None for m in client.get(f"/api/v1/accounts/{aid}/messages").json())
    client.post(f"/api/v1/accounts/{aid}/sync", json={})
    assert {m["received_at"] for m in client.get(f"/api/v1/accounts/{aid}/messages").json()} == {1791324000.0}
