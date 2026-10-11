"""Accounts, sign-in, two-factor, passkeys and single sign-on (v0.17)."""
from __future__ import annotations

import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from helpers import (
    ADMIN_PASSWORD, PASSPHRASE, SETUP_CODE, USER_PASSWORD, FakeOIDCProvider, SoftAuthenticator,
    create_user, enroll_totp, load_app, next_totp, setup_admin, sign_in, sso_sign_in,
)


@pytest.fixture
def appm(tmp_path: Path):
    m = load_app(tmp_path)
    yield m
    m.vault.lock()


@pytest.fixture
def admin(appm):
    client, secret = setup_admin(appm)
    client.totp_secret = secret
    return client


# ---------- first run ----------

def test_nothing_is_reachable_before_setup_and_there_is_no_default_identity(appm):
    c = TestClient(appm.app, raise_server_exceptions=False)
    assert c.get("/api/v1/status").json()["setup_required"] is True
    for path in ("/api/v1/me", "/api/v1/accounts", "/api/v1/admin/users"):
        assert c.get(path).status_code in (401, 423)
    page = c.get("/", follow_redirects=False)
    assert page.status_code == 303 and page.headers["location"] == "/setup"


def test_setup_requires_the_one_time_code_and_runs_once(appm):
    c = TestClient(appm.app, raise_server_exceptions=False)
    body = {"setup_code": "not-the-right-code", "passphrase": PASSPHRASE, "username": "morgan", "password": ADMIN_PASSWORD}
    assert c.post("/api/v1/setup", json=body).status_code == 403
    assert appm.SETUP_CODE_PATH.exists()
    assert c.post("/api/v1/setup", json={**body, "setup_code": SETUP_CODE}).status_code == 201
    assert not appm.SETUP_CODE_PATH.exists()
    assert c.post("/api/v1/setup", json={**body, "setup_code": SETUP_CODE, "username": "eve"}).status_code == 409


def test_setup_code_file_is_private(tmp_path: Path):
    import os
    os.environ.pop("ENVELIQ_SETUP_CODE", None)
    m = load_app(tmp_path)
    os.environ["ENVELIQ_SETUP_CODE"] = SETUP_CODE
    assert m.SETUP_CODE_PATH.exists()
    assert (m.SETUP_CODE_PATH.stat().st_mode & 0o077) == 0
    assert len(m.SETUP_CODE_PATH.read_text().strip()) >= 20


# ---------- two-factor policy ----------

def test_admin_must_set_up_two_factor_before_using_anything(appm):
    c = TestClient(appm.app, raise_server_exceptions=False)
    r = c.post("/api/v1/setup", json={"setup_code": SETUP_CODE, "passphrase": PASSPHRASE, "username": "morgan", "password": ADMIN_PASSWORD})
    assert r.json()["next"] == "enroll_mfa"
    assert c.get("/api/v1/accounts").status_code == 403
    assert c.get("/api/v1/admin/users").status_code == 403
    assert c.get("/", follow_redirects=False).headers["location"] == "/account?enroll=1"
    assert c.get("/api/v1/me").json()["session"]["state"] == "enroll"
    enroll_totp(c)
    assert c.get("/api/v1/accounts").status_code == 200


def test_tightened_policy_applies_to_existing_sessions(appm, admin):
    create_user(admin, "cara")
    cara = sign_in(appm, "cara")
    assert cara.get("/api/v1/accounts").status_code == 200
    assert admin.put("/api/v1/admin/auth-policy", json={"require_mfa": "everyone"}).status_code == 200
    assert cara.get("/api/v1/accounts").status_code == 403
    enroll_totp(cara)
    assert cara.get("/api/v1/accounts").status_code == 200


# ---------- passwords and TOTP ----------

def test_sign_in_with_password_and_authenticator_code(appm, admin):
    admin.post("/api/v1/auth/logout")
    c = TestClient(appm.app, raise_server_exceptions=False)
    r = c.post("/api/v1/auth/login", json={"username": "MORGAN", "password": ADMIN_PASSWORD})
    assert r.json() == {"next": "mfa", "methods": ["totp", "recovery"]}
    assert c.get("/api/v1/accounts").status_code == 401  # password alone is not enough
    code = next_totp(admin.totp_secret)
    assert c.post("/api/v1/auth/mfa", json={"code": code}).json()["next"] == "done"
    assert c.get("/api/v1/accounts").status_code == 200
    # The same code cannot be replayed in another sign-in.
    c2 = TestClient(appm.app, raise_server_exceptions=False)
    c2.post("/api/v1/auth/login", json={"username": "morgan", "password": ADMIN_PASSWORD})
    assert c2.post("/api/v1/auth/mfa", json={"code": code}).status_code == 401


def test_wrong_codes_end_the_sign_in_after_five_tries(appm, admin):
    c = TestClient(appm.app, raise_server_exceptions=False)
    c.post("/api/v1/auth/login", json={"username": "morgan", "password": ADMIN_PASSWORD})
    for _ in range(4):
        assert c.post("/api/v1/auth/mfa", json={"code": "000000"}).json()["detail"] == "That code is not correct"
    assert "Too many" in c.post("/api/v1/auth/mfa", json={"code": "000000"}).json()["detail"]
    assert c.post("/api/v1/auth/mfa", json={"code": next_totp(admin.totp_secret)}).status_code == 401


def test_unknown_user_and_wrong_password_look_the_same(appm, admin):
    c = TestClient(appm.app, raise_server_exceptions=False)
    a = c.post("/api/v1/auth/login", json={"username": "nobody", "password": "whatever-password-1"})
    b = c.post("/api/v1/auth/login", json={"username": "morgan", "password": "wrong-password-123"})
    assert a.status_code == b.status_code == 401 and a.json() == b.json()


def test_password_guessing_is_rate_limited(appm, admin):
    c = TestClient(appm.app, raise_server_exceptions=False)
    codes = [c.post("/api/v1/auth/login", json={"username": "morgan", "password": f"guess-{i:04d}-xx"}).status_code for i in range(12)]
    assert 429 in codes and codes.count(401) <= 10


def test_session_cookie_is_new_on_every_sign_in_and_http_only(appm, admin):
    create_user(admin, "cara")
    c = TestClient(appm.app, raise_server_exceptions=False)
    c.cookies.set(appm.SESSION_COOKIE, "attacker-chosen-token")
    r = c.post("/api/v1/auth/login", json={"username": "cara", "password": USER_PASSWORD})
    set_cookie = r.headers["set-cookie"]
    assert "HttpOnly" in set_cookie and "SameSite=lax" in set_cookie
    issued = r.cookies.get(appm.SESSION_COOKIE)
    assert issued and issued != "attacker-chosen-token"
    assert appm.sessions.peek("attacker-chosen-token") is None


def test_cookies_are_secure_with_an_https_public_url(tmp_path: Path):
    m = load_app(tmp_path, ENVELIQ_PUBLIC_URL="https://enveliq.example.test", ENVELIQ_ALLOWED_HOSTS="enveliq.example.test")
    c = TestClient(m.app, base_url="https://enveliq.example.test", raise_server_exceptions=False)
    r = c.post("/api/v1/setup", json={"setup_code": SETUP_CODE, "passphrase": PASSPHRASE, "username": "morgan", "password": ADMIN_PASSWORD})
    assert r.status_code == 201
    assert "__Host-enveliq_session=" in r.headers["set-cookie"] and "Secure" in r.headers["set-cookie"]
    assert "Strict-Transport-Security" in r.headers
    m.vault.lock()


def test_plain_http_public_url_is_refused(tmp_path: Path):
    with pytest.raises(RuntimeError, match="https"):
        load_app(tmp_path, ENVELIQ_PUBLIC_URL="http://enveliq.lan")
    load_app(tmp_path / "ok")


def test_plain_http_on_a_trusted_network_is_an_explicit_opt_in(tmp_path: Path):
    m = load_app(tmp_path, ENVELIQ_PUBLIC_URL="http://192.168.1.50:8765", ENVELIQ_ALLOW_INSECURE_PUBLIC_URL="1", ENVELIQ_ALLOWED_HOSTS="192.168.1.50,localhost")
    assert m.PUBLIC_ORIGIN == "http://192.168.1.50:8765" and m.COOKIE_SECURE is False and m.SESSION_COOKIE == "enveliq_session"
    assert "192.168.1.50" in m.ALLOWED_HOSTS and "http://192.168.1.50:8765" in m.ALLOWED_ORIGINS
    c = TestClient(m.app, raise_server_exceptions=False)
    assert c.get("/api/v1/health", headers={"Host": "192.168.1.50:8765"}).status_code == 200
    assert c.get("/api/v1/health", headers={"Host": "192.168.1.99:8765"}).status_code == 400
    assert "Strict-Transport-Security" not in c.get("/api/v1/health", headers={"Host": "192.168.1.50:8765"}).headers


def test_recovery_codes_work_once(appm, admin):
    codes = admin.post("/api/v1/auth/recovery-codes").json()["recovery_codes"]
    c = TestClient(appm.app, raise_server_exceptions=False)
    c.post("/api/v1/auth/login", json={"username": "morgan", "password": ADMIN_PASSWORD})
    assert c.post("/api/v1/auth/mfa", json={"code": codes[0].upper()}).status_code == 200
    c2 = TestClient(appm.app, raise_server_exceptions=False)
    c2.post("/api/v1/auth/login", json={"username": "morgan", "password": ADMIN_PASSWORD})
    assert c2.post("/api/v1/auth/mfa", json={"code": codes[0]}).status_code == 401
    me = admin.get("/api/v1/me").json()
    assert me["security"]["recovery_codes_left"] == 9


def test_required_second_factor_cannot_be_removed(appm, admin):
    r = admin.post("/api/v1/auth/totp/disable", json={"code": next_totp(admin.totp_secret)})
    assert r.status_code == 409


def test_password_change_signs_out_other_sessions(appm, admin):
    create_user(admin, "cara")
    first = sign_in(appm, "cara")
    second = sign_in(appm, "cara")
    r = second.post("/api/v1/auth/password", json={"current_password": USER_PASSWORD, "new_password": "A brand new password 2026"})
    assert r.status_code == 204
    assert first.get("/api/v1/me").status_code == 401
    assert second.get("/api/v1/me").status_code == 200


# ---------- password requirements (v0.59) ----------

def test_password_requirements_default_to_twelve_characters(appm, admin):
    policy = admin.get("/api/v1/admin/auth-policy").json()
    assert policy["pw_min_length"] == 12 and policy["pw_min_digits"] == 0
    r = admin.post("/api/v1/admin/users", json={"username": "sam", "password": "short"})
    assert r.status_code == 400 and "at least 12 characters" in r.json()["detail"]


def test_admin_can_require_numbers_capitals_and_symbols(appm, admin):
    r = admin.put("/api/v1/admin/auth-policy", json={"pw_min_length": 14, "pw_min_digits": 2, "pw_min_upper": 1, "pw_min_symbols": 1})
    assert r.status_code == 200 and r.json()["pw_min_length"] == 14
    weak = admin.post("/api/v1/admin/users", json={"username": "sam", "password": "alllowercaseletters"})
    assert weak.status_code == 400
    detail = weak.json()["detail"]
    assert "2 numbers" in detail and "1 capital letter" in detail and "1 symbol" in detail
    ok = admin.post("/api/v1/admin/users", json={"username": "sam", "password": "Strong pass 12 here!"})
    assert ok.status_code == 201, ok.text
    assert "at least 14 characters long" in admin.get("/api/v1/me").json()["password_rules"][0]


def test_password_rules_apply_to_changes_and_admin_resets(appm, admin):
    create_user(admin, "cara")
    admin.put("/api/v1/admin/auth-policy", json={"pw_min_digits": 3})
    cara = sign_in(appm, "cara")
    r = cara.post("/api/v1/auth/password", json={"current_password": USER_PASSWORD, "new_password": "No digits in this one"})
    assert r.status_code == 400 and "3 numbers" in r.json()["detail"]
    ok = cara.post("/api/v1/auth/password", json={"current_password": USER_PASSWORD, "new_password": "Has digits 123 in it"})
    assert ok.status_code == 204
    uid = next(u["id"] for u in admin.get("/api/v1/admin/users").json() if u["username"] == "cara")
    assert admin.post(f"/api/v1/admin/users/{uid}/password", json={"password": "twelve letters"}).status_code == 400


def test_password_may_not_contain_the_username_unless_allowed(appm, admin):
    bad = admin.post("/api/v1/admin/users", json={"username": "robert", "password": "my-robert-is-great-1"})
    assert bad.status_code == 400 and "username" in bad.json()["detail"]
    admin.put("/api/v1/admin/auth-policy", json={"pw_forbid_username": False})
    assert admin.post("/api/v1/admin/users", json={"username": "robert", "password": "my-robert-is-great-1"}).status_code == 201


def test_password_rule_limits_are_enforced(appm, admin):
    assert admin.put("/api/v1/admin/auth-policy", json={"pw_min_length": 3}).status_code == 422
    assert admin.put("/api/v1/admin/auth-policy", json={"pw_min_digits": 99}).status_code == 422


# ---------- profile (v0.59) ----------

TINY_PNG = ("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==")


def test_profile_details_are_all_optional_and_can_be_cleared(appm, admin):
    me = admin.get("/api/v1/me").json()
    assert me["email"] is None and me["about"] == ""
    r = admin.patch("/api/v1/me/profile", json={"display_name": "Morgan N", "email": "j@example.com", "about": "Hi there"})
    assert r.status_code == 200 and r.json()["email"] == "j@example.com" and r.json()["about"] == "Hi there"
    cleared = admin.patch("/api/v1/me/profile", json={"display_name": "", "email": "", "about": ""}).json()
    assert cleared["display_name"] == "morgan" and cleared["email"] is None and cleared["about"] == ""
    assert admin.patch("/api/v1/me/profile", json={"email": "not an email"}).status_code == 400
    assert admin.patch("/api/v1/me/profile", json={}).status_code == 200


def test_profile_picture_is_checked_by_content_and_can_be_removed(appm, admin):
    ok = admin.put("/api/v1/me/avatar", json={"image": "data:image/png;base64," + TINY_PNG})
    assert ok.status_code == 200 and ok.json()["avatar_v"]
    pic = admin.get(f"/api/v1/users/{ok.json()['id']}/avatar")
    assert pic.status_code == 200 and pic.headers["content-type"] == "image/png" and pic.content[:4] == b"\x89PNG"
    import base64
    svg = base64.b64encode(b"<svg xmlns='http://www.w3.org/2000/svg'><script>alert(1)</script></svg>").decode()
    assert admin.put("/api/v1/me/avatar", json={"image": "data:image/svg+xml;base64," + svg}).status_code == 400
    assert admin.put("/api/v1/me/avatar", json={"image": "data:image/png;base64," + base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"0" * 130000).decode()}).status_code == 400
    assert admin.delete("/api/v1/me/avatar").json()["avatar_v"] is None
    assert admin.get(f"/api/v1/users/{ok.json()['id']}/avatar").status_code == 404


def test_other_people_only_ever_get_your_picture_never_your_details(appm, admin):
    admin.patch("/api/v1/me/profile", json={"email": "private@example.com", "about": "secret note"})
    admin.put("/api/v1/me/avatar", json={"image": TINY_PNG})
    create_user(admin, "cara")
    cara = sign_in(appm, "cara")
    morgan_id = admin.get("/api/v1/me").json()["id"]
    assert cara.get(f"/api/v1/users/{morgan_id}/avatar").status_code == 200
    assert cara.get("/api/v1/admin/users").status_code == 403
    assert "private@example.com" not in cara.get("/api/v1/me").text
    assert cara.patch("/api/v1/me/profile", json={"about": "mine"}).json()["about"] == "mine"
    assert admin.get("/api/v1/me").json()["about"] == "secret note"
    assert TestClient(appm.app).get(f"/api/v1/users/{morgan_id}/avatar").status_code == 401


# ---------- passkeys ----------

def register_passkey(client: TestClient, auth: SoftAuthenticator, name: str = "Phone") -> dict:
    options = client.post("/api/v1/auth/passkeys/register/options").json()
    assert options["authenticatorSelection"]["residentKey"] == "required"
    assert options["authenticatorSelection"]["userVerification"] == "required"
    r = client.post("/api/v1/auth/passkeys/register/verify", json={"credential": auth.create(options), "name": name})
    assert r.status_code == 200, r.text
    return r.json()


def passkey_sign_in(appm, auth: SoftAuthenticator, **kw) -> tuple[TestClient, int]:
    c = TestClient(appm.app, raise_server_exceptions=False)
    options = c.post("/api/v1/auth/passkeys/options", json={"purpose": "login"}).json()
    r = c.post("/api/v1/auth/passkeys/verify", json={"credential": auth.get(options, **kw)})
    return c, r.status_code


def test_passkey_registration_and_passwordless_sign_in(appm, admin):
    auth = SoftAuthenticator()
    register_passkey(admin, auth)
    c, status = passkey_sign_in(appm, auth)
    assert status == 200
    me = c.get("/api/v1/me").json()
    assert me["username"] == "morgan" and me["session"]["method"] == "passkey"
    assert c.get("/api/v1/admin/users").status_code == 200  # passkey with user verification counts as two factors


def test_passkey_is_enough_to_meet_the_two_factor_requirement(appm):
    c = TestClient(appm.app, raise_server_exceptions=False)
    c.post("/api/v1/setup", json={"setup_code": SETUP_CODE, "passphrase": PASSPHRASE, "username": "morgan", "password": ADMIN_PASSWORD})
    result = register_passkey(c, SoftAuthenticator())
    assert result["session"] == "full" and len(result["recovery_codes"]) == 10
    assert c.get("/api/v1/accounts").status_code == 200


def test_passkey_from_another_site_is_rejected(appm, admin):
    auth = SoftAuthenticator()
    register_passkey(admin, auth)
    _, status = passkey_sign_in(appm, auth, origin="https://enveliq-login.evil.example")
    assert status == 401


def test_cloned_passkey_is_detected_by_signature_counter(appm, admin):
    auth = SoftAuthenticator()
    register_passkey(admin, auth)
    assert passkey_sign_in(appm, auth, sign_count=10)[1] == 200
    assert passkey_sign_in(appm, auth, sign_count=5)[1] == 401


def test_unregistered_passkey_is_rejected(appm, admin):
    stranger = SoftAuthenticator()
    stranger.user_handle = b"someone-else"
    assert passkey_sign_in(appm, stranger)[1] == 401


def test_passkey_as_second_step_after_password(appm, admin):
    auth = SoftAuthenticator()
    register_passkey(admin, auth)
    c = TestClient(appm.app, raise_server_exceptions=False)
    r = c.post("/api/v1/auth/login", json={"username": "morgan", "password": ADMIN_PASSWORD})
    assert "passkey" in r.json()["methods"]
    options = c.post("/api/v1/auth/passkeys/options", json={"purpose": "mfa"}).json()
    assert len(options["allowCredentials"]) == 1
    r = c.post("/api/v1/auth/passkeys/verify", json={"credential": auth.get(options)})
    assert r.status_code == 200
    assert c.get("/api/v1/me").json()["session"]["method"] == "password+passkey"


def test_passkey_challenge_cannot_be_reused(appm, admin):
    auth = SoftAuthenticator()
    register_passkey(admin, auth)
    c = TestClient(appm.app, raise_server_exceptions=False)
    options = c.post("/api/v1/auth/passkeys/options", json={"purpose": "login"}).json()
    assertion = auth.get(options)
    assert c.post("/api/v1/auth/passkeys/verify", json={"credential": assertion}).status_code == 200
    assert c.post("/api/v1/auth/passkeys/verify", json={"credential": assertion}).status_code == 401


# ---------- single sign-on (Authentik / Authelia) ----------

@pytest.fixture
def provider(appm, admin):
    p = FakeOIDCProvider()
    appm.oidc_client.transport = p.transport
    return p


def configure_sso(admin, provider, **overrides):
    r = admin.put("/api/v1/admin/sso", json=provider.settings(**overrides))
    assert r.status_code == 200, r.text
    return r.json()


def test_sso_settings_show_redirect_uri_and_hide_secret(appm, admin, provider):
    saved = configure_sso(admin, provider)
    assert saved["redirect_uri"] == "http://localhost:8765/api/v1/auth/sso/callback"
    shown = admin.get("/api/v1/admin/sso").json()
    assert shown["client_secret_set"] is True and provider.client_secret not in str(shown)
    assert admin.post("/api/v1/admin/sso/test").json()["signing_keys"] == 1
    status = TestClient(appm.app).get("/api/v1/status").json()
    assert status["sign_in"]["sso"] == {"enabled": True, "label": "Sign in with Authentik"}


def test_first_sso_sign_in_creates_the_user(appm, admin, provider):
    configure_sso(admin, provider)
    claims = {"sub": "ak-uid-cara", "preferred_username": "cara", "name": "Cara", "email": "cara@example.test", "groups": ["family"]}
    c, done = sso_sign_in(appm, provider, claims)
    assert done.status_code == 303 and done.headers["location"] == "/"
    me = c.get("/api/v1/me").json()
    assert (me["username"], me["display_name"], me["role"], me["source"]) == ("cara", "Cara", "user", "oidc")
    # Second sign-in finds the same user instead of creating another.
    sso_sign_in(appm, provider, claims)
    assert len(admin.get("/api/v1/admin/users").json()) == 2


def test_sso_admin_group_maps_to_administrator(appm, admin, provider):
    configure_sso(admin, provider, admin_groups=["enveliq-admins"])
    c, _ = sso_sign_in(appm, provider, {"sub": "ak-uid-sam", "preferred_username": "sam", "groups": ["enveliq-admins"]})
    assert c.get("/api/v1/me").json()["role"] == "admin"
    # Removed from the admin group at the provider: demoted at next sign-in.
    c, _ = sso_sign_in(appm, provider, {"sub": "ak-uid-sam", "preferred_username": "sam", "groups": []})
    assert c.get("/api/v1/me").json()["role"] == "user"


def test_sso_allowed_groups_restrict_who_gets_in(appm, admin, provider):
    configure_sso(admin, provider, allowed_groups=["enveliq-users"])
    _, done = sso_sign_in(appm, provider, {"sub": "ak-uid-guest", "preferred_username": "guest", "groups": ["guests"]})
    assert done.headers["location"] == "/login?error=sso_not_allowed"
    assert len(admin.get("/api/v1/admin/users").json()) == 1


def test_sso_without_auto_create_needs_an_existing_link(appm, admin, provider):
    configure_sso(admin, provider, auto_create=False)
    _, done = sso_sign_in(appm, provider, {"sub": "ak-uid-new", "preferred_username": "new"})
    assert done.headers["location"] == "/login?error=sso_not_provisioned"


def test_sso_never_takes_over_an_account_by_matching_email(appm, admin, provider):
    configure_sso(admin, provider)
    c, _ = sso_sign_in(appm, provider, {"sub": "attacker", "preferred_username": "morgan",
                                        "email": "morgan@example.test", "email_verified": True})
    me = c.get("/api/v1/me").json()
    assert me["username"] != "morgan" and me["role"] == "user"


def test_user_links_sso_to_their_existing_account(appm, admin, provider):
    configure_sso(admin, provider)
    _, done = sso_sign_in(appm, provider, {"sub": "ak-uid-morgan", "preferred_username": "morgan"}, client=admin, link=True)
    assert done.headers["location"] == "/account?linked=1"
    c, _ = sso_sign_in(appm, provider, {"sub": "ak-uid-morgan", "preferred_username": "morgan"})
    me = c.get("/api/v1/me").json()
    assert me["username"] == "morgan" and me["role"] == "admin" and me["session"]["method"] == "sso"


@pytest.mark.parametrize("tamper,reason", [
    ({"hs256": True}, "bad_token"),
    ({"foreign_key": True}, "bad_token"),
    ({"claims": {"aud": "some-other-app"}}, "bad_token"),
    ({"claims": {"iss": "https://evil.example.test/"}}, "bad_token"),
    ({"claims": {"exp": int(time.time()) - 3600}}, "bad_token"),
    ({"claims": {"nonce": "replayed-nonce"}}, "bad_token"),
    ({"metadata_issuer": "https://evil.example.test/"}, "issuer_mismatch"),
])
def test_forged_or_mismatched_tokens_are_rejected(appm, admin, provider, tamper, reason):
    configure_sso(admin, provider)
    provider.tamper = tamper
    appm.oidc_client._cache.clear()
    c = TestClient(appm.app, raise_server_exceptions=False)
    start = c.get("/api/v1/auth/sso/start", follow_redirects=False)
    if reason == "issuer_mismatch":
        assert start.headers["location"] == "/login?error=sso_issuer_mismatch"
        return
    done = c.get("/api/v1/auth/sso/callback?" + provider.approve(start.headers["location"], {"sub": "x", "preferred_username": "x"}),
                 follow_redirects=False)
    assert done.headers["location"] == f"/login?error=sso_{reason}"
    assert c.get("/api/v1/me").status_code == 401


def test_sso_state_must_match(appm, admin, provider):
    configure_sso(admin, provider)
    c = TestClient(appm.app, raise_server_exceptions=False)
    start = c.get("/api/v1/auth/sso/start", follow_redirects=False)
    query = provider.approve(start.headers["location"], {"sub": "x"}).split("&state=")[0] + "&state=forged"
    done = c.get("/api/v1/auth/sso/callback?" + query, follow_redirects=False)
    assert done.headers["location"] == "/login?error=sso_state"


def test_sso_callback_without_a_started_sign_in_is_rejected(appm, admin, provider):
    configure_sso(admin, provider)
    c = TestClient(appm.app, raise_server_exceptions=False)
    done = c.get("/api/v1/auth/sso/callback?code=abc&state=def", follow_redirects=False)
    assert done.headers["location"] == "/login?error=sso_expired"


def test_disabled_sso_user_cannot_sign_in(appm, admin, provider):
    configure_sso(admin, provider)
    c, _ = sso_sign_in(appm, provider, {"sub": "ak-uid-cara", "preferred_username": "cara"})
    cara_id = c.get("/api/v1/me").json()["id"]
    admin.patch(f"/api/v1/admin/users/{cara_id}", json={"disabled": True})
    assert c.get("/api/v1/me").status_code == 401
    _, done = sso_sign_in(appm, provider, {"sub": "ak-uid-cara", "preferred_username": "cara"})
    assert done.headers["location"] == "/login?error=sso_disabled_user"


def test_sso_issuer_must_be_https(appm, admin):
    r = admin.put("/api/v1/admin/sso", json={"enabled": True, "issuer": "http://auth.lan/", "client_id": "x"})
    assert r.status_code == 400


def test_password_sign_in_can_be_limited_to_administrators(appm, admin):
    create_user(admin, "cara")
    admin.put("/api/v1/admin/auth-policy", json={"password_login": "admins"})
    c = TestClient(appm.app, raise_server_exceptions=False)
    r = c.post("/api/v1/auth/login", json={"username": "cara", "password": USER_PASSWORD})
    assert r.status_code == 403 and "single sign-on" in r.json()["detail"]
    r = c.post("/api/v1/auth/login", json={"username": "morgan", "password": ADMIN_PASSWORD})
    assert r.json()["next"] == "mfa"  # administrators always keep password sign-in (break-glass)


# ---------- administration ----------

def test_regular_users_cannot_administer(appm, admin):
    create_user(admin, "cara")
    cara = sign_in(appm, "cara")
    for method, path in (("get", "/api/v1/admin/users"), ("get", "/api/v1/admin/sso"), ("post", "/api/v1/lock")):
        assert getattr(cara, method)(path).status_code == 403


def test_last_administrator_is_protected(appm, admin):
    me = admin.get("/api/v1/me").json()
    for body in ({"role": "user"}, {"disabled": True}):
        assert admin.patch(f"/api/v1/admin/users/{me['id']}", json=body).status_code == 409
    second = create_user(admin, "sam", role="admin")
    assert admin.patch(f"/api/v1/admin/users/{second['id']}", json={"role": "user"}).status_code == 200


def test_disabling_a_user_signs_them_out_immediately(appm, admin):
    cara_id = create_user(admin, "cara")["id"]
    cara = sign_in(appm, "cara")
    admin.patch(f"/api/v1/admin/users/{cara_id}", json={"disabled": True})
    assert cara.get("/api/v1/me").status_code == 401
    r = TestClient(appm.app).post("/api/v1/auth/login", json={"username": "cara", "password": USER_PASSWORD})
    assert r.status_code == 401


def test_deleting_a_user_deletes_their_mailboxes(appm, admin):
    cara_id = create_user(admin, "cara")["id"]
    cara = sign_in(appm, "cara")
    r = cara.post("/api/v1/accounts", json={"provider": "IMAP", "display_name": "Cara", "email_address": "cara@example.test",
                                            "auth_method": "imap", "server": "imap.example.test", "password": "cara-mail-pw"})
    assert r.status_code == 201
    assert admin.delete(f"/api/v1/admin/users/{cara_id}").status_code == 204
    assert appm.vault.list_accounts() == []


def test_admin_reset_of_two_factor_signs_the_user_out(appm, admin):
    cara_id = create_user(admin, "cara")["id"]
    cara = sign_in(appm, "cara")
    enroll_totp(cara)
    assert admin.post(f"/api/v1/admin/users/{cara_id}/reset-mfa").status_code == 204
    assert cara.get("/api/v1/me").status_code == 401
    user = appm.vault.get_user(cara_id)
    assert user["totp"] is None and user["recovery"] == []


# ---------- vault and storage ----------

def test_unlocking_does_not_sign_anyone_in_and_locking_signs_everyone_out(appm, admin):
    assert admin.post("/api/v1/lock").status_code == 204
    assert admin.get("/api/v1/me").status_code in (401, 423)
    c = TestClient(appm.app, raise_server_exceptions=False)
    r = c.post("/api/v1/unlock", json={"passphrase": PASSPHRASE})
    assert r.status_code == 200 and "session_token" not in r.text
    assert c.get("/api/v1/me").status_code == 401
    assert appm.SESSION_COOKIE not in c.cookies


def test_user_records_are_encrypted_at_rest(appm, admin, tmp_path):
    create_user(admin, "uniquecaraname")
    secret = admin.totp_secret
    appm.vault.lock()
    scan = appm.vault.plaintext_scan(["uniquecaraname", secret, "Morgan", '"username"', '"totp"'])
    assert not any(scan.values()), scan


def test_pages_are_served_with_strict_security_headers(appm, admin):
    r = admin.get("/login")
    assert r.status_code == 200
    csp = r.headers["content-security-policy"]
    assert "script-src 'self'" in csp and "unsafe-inline" not in csp and "frame-ancestors 'none'" in csp
    app_page = admin.get("/")
    assert app_page.status_code == 200 and "frame-ancestors 'none'" in app_page.headers["content-security-policy"]


def test_cross_site_state_changes_are_refused(appm, admin):
    r = admin.post("/api/v1/lock", headers={"sec-fetch-site": "cross-site"})
    assert r.status_code == 403
    r = admin.post("/api/v1/lock", headers={"origin": "https://evil.example"})
    assert r.status_code == 403


def test_a_placeholder_or_short_setup_code_is_ignored(tmp_path: Path):
    m = load_app(tmp_path, ENVELIQ_SETUP_CODE="CHANGE-ME-make-this-long-and-random")
    written = m.SETUP_CODE_PATH.read_text().strip()
    assert written and "change-me" not in written.lower()          # a random code was made instead
    assert len(written) >= 20
    assert m.check_setup_code("CHANGE-ME-make-this-long-and-random") is False
    assert m.check_setup_code(written) is True


def test_usable_setup_code_rules(appm):
    assert appm.usable_setup_code(None) == ""
    assert appm.usable_setup_code("   ") == ""
    assert appm.usable_setup_code("short-code") == ""
    assert appm.usable_setup_code("please-CHANGE-ME-now-1234567890") == ""
    assert appm.usable_setup_code("  9f2c1e7a4b6d03885c2e1f77a9b04d6e  ") == "9f2c1e7a4b6d03885c2e1f77a9b04d6e"
