"""Test helpers: app loading, signed-in clients, a software passkey
authenticator and a fake OpenID Connect provider."""
from __future__ import annotations

import base64
import hashlib
import importlib
import json
import os
import secrets
import struct
import time
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

import cbor2
import httpx
import jwt
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from fastapi.testclient import TestClient

SETUP_CODE = "test-setup-code-0123456789"
PASSPHRASE = "Correct Horse Battery Staple 2026!"
ADMIN_PASSWORD = "Admin password for tests 2026"
USER_PASSWORD = "User password for tests 2026"
PUBLIC_URL = "http://localhost:8765"


def load_app(tmp_path: Path, **env: str):
    os.environ.update({
        "ENVELIQ_DATA_DIR": str(tmp_path),
        "ENVELIQ_SETUP_CODE": SETUP_CODE,
        "ENVELIQ_PUBLIC_URL": PUBLIC_URL,
        "ENVELIQ_ALLOWED_HOSTS": "testserver,localhost",
        **env,
    })
    for key in ("ENVELIQ_COOKIE_SECURE", "ENVELIQ_BRIDGE_ALLOWED_HOSTS", "ENVELIQ_BRIDGE_CA_FILE", "ENVELIQ_MAIL_ALLOWED_HOSTS", "ENVELIQ_MAIL_CA_FILE",
                "ENVELIQ_SYNC_MINUTES", "ENVELIQ_VAULT_KEY_FILE", "ENVELIQ_VAULT_KEY", "ENVELIQ_LLM_URL", "ENVELIQ_LLM_MODEL", "ENVELIQ_LLM_API_KEY", "ENVELIQ_LLM_ALLOWED_HOSTS", "ENVELIQ_LLM_PROVIDER", "ENVELIQ_REPORT_ALLOWED_HOSTS", "ENVELIQ_ALLOW_INSECURE_PUBLIC_URL", "ENVELIQ_ALLOWED_ORIGINS"):
        if key not in env:
            os.environ.pop(key, None)
    import backend.app as app_module
    return importlib.reload(app_module)


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def unb64url(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def enroll_totp(client: TestClient) -> tuple[str, list[str]]:
    from backend.auth import totp
    secret = client.post("/api/v1/auth/totp/setup").json()["secret"]
    r = client.post("/api/v1/auth/totp/confirm", json={"code": totp.code_at(secret, totp.current_step())})
    assert r.status_code == 200, r.text
    return secret, r.json()["recovery_codes"]


def next_totp(secret: str) -> str:
    """A code for the *next* time step, so tests never trip the replay guard."""
    from backend.auth import totp
    return totp.code_at(secret, totp.current_step() + 1)


def setup_admin(appm, *, username: str = "morgan", with_passphrase: bool = True) -> tuple[TestClient, str]:
    """First-run setup plus the authenticator enrolment the default policy
    requires for administrators. Returns (signed-in client, TOTP secret)."""
    client = TestClient(appm.app, raise_server_exceptions=False)
    body = {"setup_code": SETUP_CODE, "username": username, "password": ADMIN_PASSWORD, "display_name": username.title()}
    if with_passphrase:
        body["passphrase"] = PASSPHRASE
    r = client.post("/api/v1/setup", json=body)
    assert r.status_code == 201, r.text
    secret, _ = enroll_totp(client)
    return client, secret


def create_user(admin: TestClient, username: str, *, role: str = "user", password: str = USER_PASSWORD) -> dict:
    r = admin.post("/api/v1/admin/users", json={"username": username, "password": password, "role": role})
    assert r.status_code == 201, r.text
    return r.json()


def sign_in(appm, username: str, password: str = USER_PASSWORD) -> TestClient:
    client = TestClient(appm.app, raise_server_exceptions=False)
    r = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200 and r.json()["next"] == "done", r.text
    return client


class SoftAuthenticator:
    """Minimal platform authenticator: P-256 key, 'none' attestation, user
    present + verified. Enough to drive real py_webauthn verification."""

    def __init__(self, rp_id: str = "localhost", origin: str = PUBLIC_URL):
        self.rp_id, self.origin = rp_id, origin
        self.key = ec.generate_private_key(ec.SECP256R1())
        self.cred_id = secrets.token_bytes(32)
        self.sign_count = 0
        self.user_handle: bytes | None = None

    def _rp_hash(self) -> bytes:
        return hashlib.sha256(self.rp_id.encode()).digest()

    def _client_data(self, kind: str, challenge: str, origin: str | None = None) -> bytes:
        return json.dumps({"type": kind, "challenge": challenge, "origin": origin or self.origin, "crossOrigin": False}).encode()

    def create(self, options: dict) -> dict:
        self.user_handle = unb64url(options["user"]["id"])
        nums = self.key.public_key().public_numbers()
        cose = cbor2.dumps({1: 2, 3: -7, -1: 1, -2: nums.x.to_bytes(32, "big"), -3: nums.y.to_bytes(32, "big")})
        attested = b"\x00" * 16 + struct.pack(">H", len(self.cred_id)) + self.cred_id + cose
        auth_data = self._rp_hash() + bytes([0x45]) + struct.pack(">I", self.sign_count) + attested
        att = cbor2.dumps({"fmt": "none", "attStmt": {}, "authData": auth_data})
        return {"id": b64url(self.cred_id), "rawId": b64url(self.cred_id), "type": "public-key",
                "response": {"clientDataJSON": b64url(self._client_data("webauthn.create", options["challenge"])),
                             "attestationObject": b64url(att), "transports": ["internal"]},
                "clientExtensionResults": {}}

    def get(self, options: dict, *, origin: str | None = None, sign_count: int | None = None) -> dict:
        self.sign_count = self.sign_count + 1 if sign_count is None else sign_count
        auth_data = self._rp_hash() + bytes([0x05]) + struct.pack(">I", self.sign_count)
        client_data = self._client_data("webauthn.get", options["challenge"], origin)
        sig = self.key.sign(auth_data + hashlib.sha256(client_data).digest(), ec.ECDSA(hashes.SHA256()))
        return {"id": b64url(self.cred_id), "rawId": b64url(self.cred_id), "type": "public-key",
                "response": {"clientDataJSON": b64url(client_data), "authenticatorData": b64url(auth_data),
                             "signature": b64url(sig), "userHandle": b64url(self.user_handle or b"")},
                "clientExtensionResults": {}}


class FakeOIDCProvider:
    """In-memory OpenID provider (Authentik/Authelia stand-in) served through
    an httpx MockTransport. `approve()` plays the part of the user signing in
    at the provider and returns the callback query string."""

    def __init__(self, issuer: str = "https://auth.example.test/application/o/enveliq/",
                 client_id: str = "enveliq", client_secret: str = "provider-client-secret"):
        self.issuer, self.client_id, self.client_secret = issuer, client_id, client_secret
        self.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.kid = "test-key-1"
        self.codes: dict[str, dict[str, Any]] = {}
        self.tamper: dict[str, Any] = {}
        base = issuer.rstrip("/")
        self.urls = {"authorize": base + "/authorize", "token": base + "/token",
                     "jwks": base + "/jwks", "userinfo": base + "/userinfo"}
        self.transport = httpx.MockTransport(self._handle)

    def settings(self, **overrides) -> dict:
        return {"enabled": True, "label": "Sign in with Authentik", "issuer": self.issuer,
                "client_id": self.client_id, "client_secret": self.client_secret,
                "scopes": "openid profile email groups", "auto_create": True,
                "allowed_groups": [], "admin_groups": [], **overrides}

    def _jwk(self) -> dict:
        jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(self.key.public_key()))
        return {**jwk, "kid": self.kid, "use": "sig", "alg": "RS256"}

    def _handle(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.endswith("/.well-known/openid-configuration"):
            return httpx.Response(200, json={
                "issuer": self.tamper.get("metadata_issuer", self.issuer),
                "authorization_endpoint": self.urls["authorize"], "token_endpoint": self.urls["token"],
                "jwks_uri": self.urls["jwks"], "userinfo_endpoint": self.urls["userinfo"],
                "token_endpoint_auth_methods_supported": ["client_secret_basic", "client_secret_post"],
                "id_token_signing_alg_values_supported": ["RS256"]})
        if url == self.urls["jwks"]:
            return httpx.Response(200, json={"keys": [self._jwk()]})
        if url == self.urls["token"]:
            form = parse_qs(request.content.decode())
            code = form.get("code", [""])[0]
            grant = self.codes.pop(code, None)
            auth = request.headers.get("authorization", "")
            expected_auth = "Basic " + base64.b64encode(f"{self.client_id}:{self.client_secret}".encode()).decode()
            if grant is None or auth != expected_auth:
                return httpx.Response(400, json={"error": "invalid_grant"})
            verifier = form.get("code_verifier", [""])[0]
            challenge = b64url(hashlib.sha256(verifier.encode()).digest())
            if challenge != grant["code_challenge"]:
                return httpx.Response(400, json={"error": "invalid_grant", "error_description": "PKCE"})
            return httpx.Response(200, json={"access_token": "at-" + code, "token_type": "Bearer",
                                             "id_token": self.id_token(grant["claims"], grant["nonce"])})
        if url == self.urls["userinfo"]:
            return httpx.Response(200, json={})
        return httpx.Response(404)

    def id_token(self, claims: dict, nonce: str) -> str:
        now = int(time.time())
        payload = {"iss": self.issuer, "aud": self.client_id, "iat": now, "exp": now + 300, "nonce": nonce, **claims}
        payload.update(self.tamper.get("claims", {}))
        if self.tamper.get("hs256"):
            return jwt.encode(payload, "shared-secret-attack-key-long-enough-for-hs256", algorithm="HS256", headers={"kid": self.kid})
        if self.tamper.get("foreign_key"):
            other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
            return jwt.encode(payload, other, algorithm="RS256", headers={"kid": self.kid})
        return jwt.encode(payload, self.key, algorithm="RS256", headers={"kid": self.kid})

    def approve(self, authorize_url: str, claims: dict) -> str:
        q = {k: v[0] for k, v in parse_qs(urlsplit(authorize_url).query).items()}
        assert q["code_challenge_method"] == "S256" and q["client_id"] == self.client_id
        code = secrets.token_urlsafe(16)
        self.codes[code] = {"claims": claims, "nonce": q["nonce"], "code_challenge": q["code_challenge"]}
        return f"code={code}&state={q['state']}"


def sso_sign_in(appm, provider: FakeOIDCProvider, claims: dict, client: TestClient | None = None,
                *, link: bool = False) -> tuple[TestClient, httpx.Response]:
    client = client or TestClient(appm.app, raise_server_exceptions=False)
    start = client.get("/api/v1/auth/sso/start" + ("?link=1" if link else ""), follow_redirects=False)
    assert start.status_code == 303, start.text
    location = start.headers["location"]
    assert location.startswith(provider.urls["authorize"]), location
    query = provider.approve(location, claims)
    done = client.get("/api/v1/auth/sso/callback?" + query, follow_redirects=False)
    return client, done
