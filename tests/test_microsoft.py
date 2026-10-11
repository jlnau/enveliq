"""Outlook, Hotmail and Microsoft 365: sign in on Microsoft's page, then IMAP and SMTP with XOAUTH2.
A fake Microsoft sign-in service and a fake mail server stand in for the real ones."""
from __future__ import annotations

import base64
import json
from contextlib import contextmanager
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest

from fake_bridge import FakeBridge
from helpers import PUBLIC_URL, create_user, load_app, setup_admin, sign_in
from test_bridge import mails
from backend.mail import microsoft as ms

EMAIL = "morgan@outlook.example"
CLIENT_ID = "12345678-abcd-1234-abcd-1234567890ab"
CALLBACK = PUBLIC_URL + "/api/v1/mail/microsoft/callback"


class FakeMicrosoft:
    """Microsoft's token address. Issues numbered tokens and tells the fake mail server which are valid."""

    def __init__(self, mail: FakeBridge | None = None, email: str = EMAIL):
        self.mail, self.email = mail, email
        self.forms: list[dict[str, str]] = []
        self.fail: dict | None = None
        self.n = 0
        self.transport = httpx.MockTransport(self.handle)

    def handle(self, request: httpx.Request) -> httpx.Response:
        assert request.url.host == "login.microsoftonline.com" and request.url.path.endswith("/oauth2/v2.0/token")
        form = {k: v[0] for k, v in parse_qs(request.content.decode()).items()}
        self.forms.append(form)
        if self.fail:
            return httpx.Response(400, json=self.fail)
        self.n += 1
        access = f"at-{self.n}"
        if self.mail:
            self.mail.oauth_tokens.add(access)
        out = {"access_token": access, "refresh_token": f"rt-secret-{self.n}", "expires_in": 3600, "token_type": "Bearer"}
        if form["grant_type"] == "authorization_code":
            payload = base64.urlsafe_b64encode(json.dumps({"email": self.email}).encode()).decode().rstrip("=")
            out["id_token"] = f"e30.{payload}.sig"
        return httpx.Response(200, json=out)


@contextmanager
def microsoft_servers(bridge: FakeBridge):
    """Point the fixed Microsoft mail addresses at the fake mail server for the duration of a test."""
    saved = (ms.IMAP_HOST, ms.IMAP_PORT, ms.SMTP_HOST, ms.SMTP_PORT)
    ms.IMAP_HOST, ms.IMAP_PORT, ms.SMTP_HOST, ms.SMTP_PORT = "127.0.0.1", bridge.imap_port, "127.0.0.1", bridge.smtp_port
    try:
        yield
    finally:
        ms.IMAP_HOST, ms.IMAP_PORT, ms.SMTP_HOST, ms.SMTP_PORT = saved


@pytest.fixture
def env(tmp_path):
    bridge = FakeBridge(tmp_path, user=EMAIL, implicit_tls=True, smtp_implicit=False,
                        folders=[("\\HasNoChildren", "INBOX"), ("\\HasNoChildren \\Archive", "Archive"), ("\\HasNoChildren", "Deleted Items")])
    for uid, raw in mails().items():
        bridge.add(uid, raw)
    (tmp_path / "data").mkdir()
    appm = load_app(tmp_path / "data", ENVELIQ_MAIL_CA_FILE=str(bridge.cert_path), ENVELIQ_MAIL_ALLOWED_HOSTS="127.0.0.1")
    client, _ = setup_admin(appm)
    fake = FakeMicrosoft(bridge)
    appm.microsoft.transport = fake.transport
    with microsoft_servers(bridge):
        yield appm, client, bridge, fake
    bridge.close()


def configure(client, **over):
    body = {"enabled": True, "client_id": CLIENT_ID, "tenant": "common", "client_secret": None, **over}
    return client.put("/api/v1/admin/microsoft", json=body)


def sign_in_at_microsoft(client, code="the-code", name="Outlook", **extra):
    started = client.post("/api/v1/mail/microsoft/start", json={"display_name": name, **extra})
    assert started.status_code == 200, started.text
    url = started.json()["url"]
    state = parse_qs(urlsplit(url).query)["state"][0]
    return url, client.get(f"/api/v1/mail/microsoft/callback?code={code}&state={state}", follow_redirects=False)


def accounts(client):
    return client.get("/api/v1/accounts").json()


# ---------- the administrator's settings ----------

def test_outlook_is_unavailable_until_an_administrator_sets_up_microsoft_sign_in(env):
    appm, admin, _, _ = env
    create_user(admin, "cara")
    cara = sign_in(appm, "cara")
    by_id = lambda c: {p["id"]: p for p in c.get("/api/v1/mail/providers").json()}
    assert by_id(admin)["outlook"]["status"] == "unavailable" and "Administration" in by_id(admin)["outlook"]["unavailable_reason"]
    assert "Ask an administrator" in by_id(cara)["outlook"]["unavailable_reason"]
    assert configure(admin).status_code == 200
    for c in (admin, cara):
        outlook = by_id(c)["outlook"]
        assert outlook["status"] == "ready" and outlook["oauth"] == "microsoft" and outlook["steps"]


def test_settings_are_for_administrators_are_checked_and_the_secret_is_never_returned(env):
    appm, admin, _, _ = env
    create_user(admin, "cara")
    cara = sign_in(appm, "cara")
    assert cara.get("/api/v1/admin/microsoft").status_code == 403 and cara.put("/api/v1/admin/microsoft", json={"enabled": True, "client_id": CLIENT_ID}).status_code == 403
    assert configure(admin, client_id="not-a-guid").status_code == 400
    assert configure(admin, client_id="").status_code == 400
    assert configure(admin, tenant="bad tenant!").status_code == 400
    r = configure(admin, client_secret="very-secret-value")
    assert r.status_code == 200 and r.json()["has_secret"] is True and "very-secret-value" not in r.text
    assert r.json()["redirect_uri"] == CALLBACK
    assert "very-secret-value" not in admin.get("/api/v1/admin/microsoft").text
    assert appm.vault.get_global("microsoft_oauth")["client_secret"] == "very-secret-value"
    configure(admin)                                                   # keeps it
    assert appm.vault.get_global("microsoft_oauth")["client_secret"] == "very-secret-value"
    configure(admin, client_secret="")                                 # removes it
    assert appm.vault.get_global("microsoft_oauth")["client_secret"] == ""
    assert not any(appm.vault.plaintext_scan(["very-secret-value"]).values())


# ---------- signing in ----------

def test_the_sign_in_address_uses_pkce_state_and_the_right_scopes(env):
    _, admin, _, _ = env
    configure(admin, tenant="consumers")
    url, _ = sign_in_at_microsoft(admin)
    parts = urlsplit(url)
    q = {k: v[0] for k, v in parse_qs(parts.query).items()}
    assert parts.scheme == "https" and parts.netloc == "login.microsoftonline.com" and parts.path == "/consumers/oauth2/v2.0/authorize"
    assert q["client_id"] == CLIENT_ID and q["redirect_uri"] == CALLBACK and q["response_type"] == "code" and q["code_challenge_method"] == "S256"
    assert len(q["state"]) >= 32 and len(q["code_challenge"]) >= 43
    scopes = q["scope"].split()
    assert "offline_access" in scopes and "https://outlook.office.com/IMAP.AccessAsUser.All" in scopes and "https://outlook.office.com/SMTP.Send" in scopes
    assert "client_secret" not in q


def test_starting_without_setup_is_refused_plainly(env):
    _, admin, _, _ = env
    r = admin.post("/api/v1/mail/microsoft/start", json={"display_name": "Outlook"})
    assert r.status_code == 400 and r.json()["detail"]["code"] == "ms_not_set_up"


def test_a_full_sign_in_adds_a_working_mailbox_and_keeps_the_token_safe(env):
    appm, admin, bridge, fake = env
    configure(admin)
    url, done = sign_in_at_microsoft(admin, name="My Outlook", send_identities=["alias@outlook.example"], ai_summaries=False)
    assert done.status_code == 303 and done.headers["location"] == "/welcome?ms=ok"
    form = fake.forms[0]
    q = parse_qs(urlsplit(url).query)
    import hashlib
    challenge = base64.urlsafe_b64encode(hashlib.sha256(form["code_verifier"].encode()).digest()).decode().rstrip("=")
    assert form["grant_type"] == "authorization_code" and form["code"] == "the-code" and form["redirect_uri"] == CALLBACK and challenge == q["code_challenge"][0]
    assert form["client_id"] == CLIENT_ID and "client_secret" not in form
    mine = accounts(admin)
    assert len(mine) == 1 and mine[0]["email_address"] == EMAIL and mine[0]["display_name"] == "My Outlook" and mine[0]["oauth_connected"] is True
    assert mine[0]["settings"]["send_identities"] == ["alias@outlook.example"] and mine[0]["settings"]["auth"] == "microsoft"
    shown = json.dumps(accounts(admin))
    assert "rt-secret" not in shown and "at-" not in shown
    assert not any(appm.vault.plaintext_scan(["rt-secret-1"]).values())
    assert appm.vault.get_account(mine[0]["id"])["oauth_refresh_token"] == "rt-secret-1"
    # It really reads mail with the access token.
    assert admin.post(f"/api/v1/accounts/{mine[0]['id']}/sync", json={}).json()["added"] == 3
    assert any(l.startswith("AUTHENTICATE") for l in bridge.log) and not any("LOGIN" in l for l in bridge.log)


def test_replies_are_sent_with_the_token_and_the_original_can_be_read(env):
    _, admin, bridge, _ = env
    configure(admin)
    sign_in_at_microsoft(admin)
    aid = accounts(admin)[0]["id"]
    admin.post(f"/api/v1/accounts/{aid}/sync", json={})
    msgs = {m["subject"]: m for m in admin.get(f"/api/v1/accounts/{aid}/messages").json()}
    mid = msgs["Quarterly update"]["id"]
    assert admin.get(f"/api/v1/accounts/{aid}/messages/{mid}/original").status_code == 200
    r = admin.post(f"/api/v1/accounts/{aid}/messages/{mid}/reply", json={"body": "Thanks, got it."})
    assert r.status_code == 200, r.text
    assert len(bridge.sent) == 1 and bridge.sent[0]["from"] == EMAIL


def test_an_expired_access_token_is_refreshed_and_the_new_refresh_token_is_kept(env):
    appm, admin, _, fake = env
    configure(admin)
    sign_in_at_microsoft(admin)
    aid = accounts(admin)[0]["id"]
    appm.microsoft.forget()                                         # as if the access token had expired
    assert admin.post(f"/api/v1/accounts/{aid}/sync", json={}).status_code == 200
    refresh = [f for f in fake.forms if f["grant_type"] == "refresh_token"]
    assert len(refresh) == 1 and refresh[0]["refresh_token"] == "rt-secret-1" and "https://outlook.office.com/IMAP.AccessAsUser.All" in refresh[0]["scope"]
    assert appm.vault.get_account(aid)["oauth_refresh_token"] == "rt-secret-2"
    admin.post(f"/api/v1/accounts/{aid}/sync", json={})              # cached now: no second refresh
    assert len([f for f in fake.forms if f["grant_type"] == "refresh_token"]) == 1


def test_a_client_secret_is_sent_only_when_one_was_saved(env):
    _, admin, _, fake = env
    configure(admin, client_secret="app-secret-1")
    sign_in_at_microsoft(admin)
    assert fake.forms[0]["client_secret"] == "app-secret-1"


def test_microsoft_servers_are_fixed_so_a_token_cannot_be_sent_elsewhere(env):
    _, admin, bridge, _ = env
    configure(admin)
    sign_in_at_microsoft(admin)
    aid = accounts(admin)[0]["id"]
    admin.patch(f"/api/v1/accounts/{aid}", json={"server": "evil.example.com", "port": 993, "settings": {"auth": "microsoft", "smtp_host": "evil.example.com", "smtp_port": 587, "smtp_security": "starttls", "imap_security": "ssl"}})
    assert admin.post(f"/api/v1/accounts/{aid}/sync", json={}).status_code == 200      # still went to the (fake) Microsoft address


# ---------- when it goes wrong ----------

def test_each_failure_comes_back_with_a_code_and_leaves_nothing_behind(env):
    appm, admin, bridge, fake = env
    configure(admin)

    def code_of(done):
        assert done.status_code == 303
        loc = urlsplit(done.headers["location"])
        return parse_qs(loc.query).get("code", [""])[0]

    # no sign-in was started here (or it timed out)
    assert code_of(admin.get("/api/v1/mail/microsoft/callback?code=x&state=y", follow_redirects=False)) == "ms_expired"
    # Microsoft says the person cancelled
    admin.post("/api/v1/mail/microsoft/start", json={"display_name": "Outlook"})
    assert code_of(admin.get("/api/v1/mail/microsoft/callback?error=access_denied&state=x", follow_redirects=False)) == "ms_denied"
    # state that does not match
    admin.post("/api/v1/mail/microsoft/start", json={"display_name": "Outlook"})
    assert code_of(admin.get("/api/v1/mail/microsoft/callback?code=x&state=forged", follow_redirects=False)) == "ms_state"
    # a flow is single use
    _, done = sign_in_at_microsoft(admin)
    assert done.headers["location"].endswith("ms=ok")
    assert code_of(admin.get("/api/v1/mail/microsoft/callback?code=x&state=y", follow_redirects=False)) == "ms_expired"
    for failure, expected in (({"error": "invalid_grant", "error_codes": [70008]}, "ms_signin_needed"), ({"error": "invalid_client", "error_codes": [7000218]}, "ms_public_client"),
                              ({"error": "unauthorized_client", "error_codes": [700016]}, "ms_bad_client"), ({"error": "invalid_client", "error_codes": [7000215]}, "ms_bad_secret"),
                              ({"error": "invalid_request", "error_codes": [999999]}, "ms_rejected")):
        fake.fail = failure
        _, done = sign_in_at_microsoft(admin)
        assert code_of(done) == expected
    fake.fail = None
    assert len(accounts(admin)) == 1                                   # only the good one from earlier


def test_a_mailbox_that_refuses_the_connection_is_not_kept(env):
    appm, admin, bridge, fake = env
    configure(admin)
    fake.mail = None                                                    # tokens are issued but the mail server does not accept them
    _, done = sign_in_at_microsoft(admin)
    assert "code=ms_mailbox_refused" in done.headers["location"]
    assert accounts(admin) == []
    assert not any(appm.vault.plaintext_scan(["rt-secret-1"]).values())


def test_someone_elses_browser_cannot_finish_my_sign_in(env):
    appm, admin, _, _ = env
    configure(admin)
    create_user(admin, "cara")
    cara = sign_in(appm, "cara")
    started = admin.post("/api/v1/mail/microsoft/start", json={"display_name": "Outlook"}).json()["url"]
    state = parse_qs(urlsplit(started).query)["state"][0]
    cara.cookies.set("enveliq_flow", admin.cookies.get("enveliq_flow") or "")
    done = cara.get(f"/api/v1/mail/microsoft/callback?code=x&state={state}", follow_redirects=False)
    assert "ms_expired" in done.headers["location"] and accounts(cara) == []


def test_a_locked_vault_forgets_the_access_tokens_and_signed_out_people_cannot_start(env):
    appm, admin, _, _ = env
    configure(admin)
    sign_in_at_microsoft(admin)
    aid = accounts(admin)[0]["id"]
    admin.post(f"/api/v1/accounts/{aid}/sync", json={})
    assert appm.microsoft._tokens
    appm.vault.lock()
    assert not appm.microsoft._tokens
    from fastapi.testclient import TestClient
    assert TestClient(appm.app).post("/api/v1/mail/microsoft/start", json={"display_name": "x"}).status_code in (401, 403, 423)


def test_nothing_secret_reaches_the_audit_log_or_reports(env):
    appm, admin, _, _ = env
    configure(admin, client_secret="app-secret-9")
    sign_in_at_microsoft(admin)
    log = json.dumps(appm.vault.audit_entries() if hasattr(appm.vault, "audit_entries") else [])
    for word in ("rt-secret", "at-1", "app-secret-9", "the-code"):
        assert word not in log
    text = appm.reporter.metrics_text()
    for word in ("rt-secret", "app-secret-9", EMAIL):
        assert word not in text
