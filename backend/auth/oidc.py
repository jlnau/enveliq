"""OpenID Connect single sign-on (Authentik, Authelia, Keycloak, Pocket ID,
Zitadel, Kanidm and other standard providers).

Authorization Code flow with PKCE (S256), `state` and `nonce`. The ID token
is verified locally against the provider's published keys (JWKS): signature,
issuer, audience, expiry and nonce. Symmetric ("HS") algorithms and "none"
are refused.
"""
from __future__ import annotations

import base64
import hashlib
import secrets
import time
from dataclasses import dataclass
from typing import Any, Callable
from urllib.parse import urlencode, urlsplit

import httpx
import jwt

ALLOWED_ALGS = ["RS256", "RS384", "RS512", "PS256", "PS384", "PS512", "ES256", "ES384", "ES512", "EdDSA"]
CACHE_SECONDS = 600
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


class OIDCError(Exception):
    """`code` is a short reason shown to the user as ?error=sso_<code>."""

    def __init__(self, code: str, detail: str = ""):
        super().__init__(detail or code)
        self.code = code


@dataclass
class OIDCSettings:
    enabled: bool
    issuer: str
    client_id: str
    client_secret: str | None
    scopes: str = "openid profile email groups"
    label: str = "Sign in with single sign-on"
    auto_create: bool = True
    allowed_groups: tuple[str, ...] = ()
    admin_groups: tuple[str, ...] = ()
    groups_claim: str = "groups"
    username_claim: str = "preferred_username"
    require_email_verified: bool = False

    @classmethod
    def from_record(cls, record: dict[str, Any] | None) -> "OIDCSettings | None":
        if not record or not record.get("enabled"):
            return None
        return cls(
            enabled=True, issuer=record["issuer"], client_id=record["client_id"],
            client_secret=record.get("client_secret"), scopes=record.get("scopes") or cls.scopes,
            label=record.get("label") or cls.label, auto_create=bool(record.get("auto_create", True)),
            allowed_groups=tuple(record.get("allowed_groups") or ()), admin_groups=tuple(record.get("admin_groups") or ()),
            groups_claim=record.get("groups_claim") or "groups", username_claim=record.get("username_claim") or "preferred_username",
            require_email_verified=bool(record.get("require_email_verified")),
        )


def require_secure_url(url: str, allow_http: bool) -> None:
    parts = urlsplit(url)
    if parts.scheme == "https" and parts.hostname:
        return
    if parts.scheme == "http" and parts.hostname and (allow_http or parts.hostname in LOCAL_HOSTS):
        return
    raise OIDCError("insecure_url", f"{url} must use https://")


def _same_issuer(a: str, b: str) -> bool:
    return a.rstrip("/") == b.rstrip("/")


def pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)[:96]
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    return verifier, challenge


class OIDCClient:
    """Stateless apart from a short metadata/JWKS cache. `transport` lets
    tests plug in a fake provider."""

    def __init__(self, *, allow_http: bool = False, transport: httpx.BaseTransport | None = None,
                 clock: Callable[[], float] = time.time):
        self.allow_http = allow_http
        self.transport = transport
        self.clock = clock
        self._cache: dict[str, tuple[float, Any]] = {}

    def _http(self) -> httpx.Client:
        return httpx.Client(timeout=10.0, follow_redirects=False, transport=self.transport,
                            headers={"Accept": "application/json", "User-Agent": "Enveliq"})

    def _get_json(self, url: str) -> dict[str, Any]:
        require_secure_url(url, self.allow_http)
        try:
            with self._http() as http:
                r = http.get(url)
        except httpx.HTTPError as exc:
            raise OIDCError("provider_unreachable", str(exc)) from exc
        if r.status_code != 200:
            raise OIDCError("provider_error", f"{url} returned HTTP {r.status_code}")
        try:
            return r.json()
        except ValueError as exc:
            raise OIDCError("provider_error", f"{url} did not return JSON") from exc

    def metadata(self, issuer: str, *, refresh: bool = False) -> dict[str, Any]:
        key = "meta:" + issuer
        cached = self._cache.get(key)
        if cached and not refresh and self.clock() - cached[0] < CACHE_SECONDS:
            return cached[1]
        meta = self._get_json(issuer.rstrip("/") + "/.well-known/openid-configuration")
        if not _same_issuer(meta.get("issuer", ""), issuer):
            raise OIDCError("issuer_mismatch", "The provider's metadata names a different issuer")
        for field in ("authorization_endpoint", "token_endpoint", "jwks_uri"):
            if not meta.get(field):
                raise OIDCError("provider_error", f"Provider metadata is missing {field}")
            require_secure_url(meta[field], self.allow_http)
        self._cache[key] = (self.clock(), meta)
        return meta

    def jwks(self, meta: dict[str, Any], *, refresh: bool = False) -> list[dict[str, Any]]:
        key = "jwks:" + meta["jwks_uri"]
        cached = self._cache.get(key)
        if cached and not refresh and self.clock() - cached[0] < CACHE_SECONDS:
            return cached[1]
        keys = self._get_json(meta["jwks_uri"]).get("keys") or []
        self._cache[key] = (self.clock(), keys)
        return keys

    def authorization_url(self, settings: OIDCSettings, redirect_uri: str) -> tuple[str, dict[str, str]]:
        meta = self.metadata(settings.issuer)
        verifier, challenge = pkce_pair()
        state, nonce = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        query = urlencode({
            "response_type": "code", "client_id": settings.client_id, "redirect_uri": redirect_uri,
            "scope": settings.scopes, "state": state, "nonce": nonce,
            "code_challenge": challenge, "code_challenge_method": "S256",
        })
        sep = "&" if "?" in meta["authorization_endpoint"] else "?"
        return meta["authorization_endpoint"] + sep + query, {"state": state, "nonce": nonce, "verifier": verifier}

    def _signing_key(self, meta: dict[str, Any], token: str) -> tuple[Any, str]:
        try:
            header = jwt.get_unverified_header(token)
        except jwt.PyJWTError as exc:
            raise OIDCError("bad_token", "ID token is malformed") from exc
        alg = header.get("alg")
        if alg not in ALLOWED_ALGS:
            raise OIDCError("bad_token", f"ID token algorithm {alg!r} is not allowed")
        kid = header.get("kid")
        for refresh in (False, True):  # refetch once if the provider rotated keys
            keys = [k for k in self.jwks(meta, refresh=refresh) if k.get("use", "sig") == "sig"]
            match = [k for k in keys if kid and k.get("kid") == kid] or (keys if not kid and len(keys) == 1 else [])
            if match:
                try:
                    return jwt.PyJWK(match[0], algorithm=alg).key, alg
                except jwt.PyJWTError as exc:
                    raise OIDCError("bad_token", "Provider signing key is unusable") from exc
        raise OIDCError("bad_token", "No matching signing key from the provider")

    def exchange(self, settings: OIDCSettings, *, code: str, redirect_uri: str, verifier: str, nonce: str) -> dict[str, Any]:
        """Trade the authorization code for tokens and return verified claims."""
        meta = self.metadata(settings.issuer)
        form = {"grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri,
                "code_verifier": verifier, "client_id": settings.client_id}
        methods = meta.get("token_endpoint_auth_methods_supported") or ["client_secret_basic"]
        auth = None
        if settings.client_secret:
            if "client_secret_basic" in methods:
                auth = (settings.client_id, settings.client_secret)
            else:
                form["client_secret"] = settings.client_secret
        try:
            with self._http() as http:
                r = http.post(meta["token_endpoint"], data=form, auth=auth)
        except httpx.HTTPError as exc:
            raise OIDCError("provider_unreachable", str(exc)) from exc
        if r.status_code != 200:
            raise OIDCError("token_rejected", f"Token endpoint returned HTTP {r.status_code}")
        tokens = r.json()
        id_token = tokens.get("id_token")
        if not id_token:
            raise OIDCError("bad_token", "Provider returned no ID token")

        key, alg = self._signing_key(meta, id_token)
        try:
            claims = jwt.decode(
                id_token, key=key, algorithms=[alg], audience=settings.client_id, issuer=meta["issuer"],
                leeway=60, options={"require": ["exp", "iat", "iss", "aud", "sub"]},
            )
        except jwt.PyJWTError as exc:
            raise OIDCError("bad_token", f"ID token rejected: {exc}") from exc
        if not secrets.compare_digest(str(claims.get("nonce", "")), nonce):
            raise OIDCError("bad_token", "ID token nonce does not match this sign-in")
        aud = claims.get("aud")
        if isinstance(aud, list) and len(aud) > 1 and claims.get("azp") != settings.client_id:
            raise OIDCError("bad_token", "ID token was issued to a different client")

        # Some providers (Authelia by default) only put groups/email in userinfo.
        if meta.get("userinfo_endpoint") and tokens.get("access_token") and (
            settings.groups_claim not in claims or "email" not in claims
        ):
            require_secure_url(meta["userinfo_endpoint"], self.allow_http)
            try:
                with self._http() as http:
                    u = http.get(meta["userinfo_endpoint"], headers={"Authorization": f"Bearer {tokens['access_token']}"})
                info = u.json() if u.status_code == 200 else {}
            except (httpx.HTTPError, ValueError):
                info = {}
            if info.get("sub") == claims["sub"]:
                for k, v in info.items():
                    claims.setdefault(k, v)
        claims["_issuer"] = meta["issuer"]
        return claims


def groups_from(claims: dict[str, Any], claim: str) -> set[str]:
    value = claims.get(claim)
    if isinstance(value, str):
        return {g.strip() for g in value.replace(",", " ").split() if g.strip()}
    if isinstance(value, list):
        return {str(g) for g in value if isinstance(g, (str, int))}
    return set()
