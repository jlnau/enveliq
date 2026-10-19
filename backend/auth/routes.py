"""Sign-in, second factor, passkey, SSO and user-administration endpoints."""
from __future__ import annotations

import base64
import secrets
import time
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import Field, SecretStr, StrictInt

from ..crypto_vault import InvalidPassphrase, VaultAlreadyInitialized
from ..models import StrictModel, validate_host
from ..security import Session
from . import passkeys, passwords, profile as profiles, recovery, totp
from .oidc import OIDCError, OIDCSettings, groups_from, require_secure_url
from .users import UserError, normalise_username


# ---------- request bodies ----------

class SetupBody(StrictModel):
    setup_code: SecretStr = Field(min_length=8, max_length=256)
    passphrase: SecretStr | None = Field(default=None, min_length=12, max_length=512)   # not used when a key file is configured
    username: str = Field(min_length=1, max_length=64)
    password: SecretStr = Field(min_length=1, max_length=1024)
    display_name: str | None = Field(default=None, max_length=128)


class LoginBody(StrictModel):
    username: str = Field(min_length=1, max_length=320)
    password: SecretStr = Field(min_length=1, max_length=1024)
    remember: bool = False            # "Keep me signed in on this device"


class CodeBody(StrictModel):
    code: str = Field(min_length=6, max_length=32)


class PasskeyOptionsBody(StrictModel):
    purpose: Literal["login", "mfa"] = "login"


class CredentialBody(StrictModel):
    credential: dict[str, Any]
    name: str | None = Field(default=None, max_length=64)
    remember: bool = False            # "Keep me signed in on this device" (a passkey sign-in with no password step)


class RenameBody(StrictModel):
    name: str = Field(min_length=1, max_length=64)


class PasswordChangeBody(StrictModel):
    current_password: SecretStr = Field(min_length=1, max_length=1024)
    new_password: SecretStr = Field(min_length=1, max_length=1024)


class NewUserBody(StrictModel):
    username: str = Field(min_length=1, max_length=64)
    display_name: str | None = Field(default=None, max_length=128)
    password: SecretStr = Field(min_length=1, max_length=1024)
    role: Literal["admin", "user"] = "user"


class UserPatchBody(StrictModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=128)
    role: Literal["admin", "user"] | None = None
    disabled: bool | None = None


class SetPasswordBody(StrictModel):
    password: SecretStr = Field(min_length=1, max_length=1024)


class ProfileBody(StrictModel):
    # All optional. An empty string clears a detail; leaving it out keeps it.
    display_name: str | None = Field(default=None, max_length=128)
    email: str | None = Field(default=None, max_length=254)
    about: str | None = Field(default=None, max_length=500)
    show_in_people: bool | None = None          # appear in the list other people choose from in Messages


class AvatarBody(StrictModel):
    image: str = Field(min_length=20, max_length=200_000)


class PolicyBody(StrictModel):
    require_mfa: Literal["off", "admins", "everyone"] | None = None
    password_login: Literal["everyone", "admins"] | None = None
    remember_days: StrictInt | None = Field(default=None, ge=0, le=14)
    pw_min_length: int | None = Field(default=None, ge=8, le=128)
    pw_min_digits: int | None = Field(default=None, ge=0, le=32)
    pw_min_upper: int | None = Field(default=None, ge=0, le=32)
    pw_min_lower: int | None = Field(default=None, ge=0, le=32)
    pw_min_symbols: int | None = Field(default=None, ge=0, le=32)
    pw_forbid_username: bool | None = None


class SSOBody(StrictModel):
    enabled: bool = False
    label: str = Field(default="Sign in with single sign-on", min_length=1, max_length=64)
    issuer: str = Field(default="", max_length=512)
    client_id: str = Field(default="", max_length=256)
    client_secret: SecretStr | None = Field(default=None, max_length=1024)
    scopes: str = Field(default="openid profile email groups", max_length=256)
    auto_create: bool = True
    allowed_groups: list[str] = Field(default_factory=list, max_length=50)
    admin_groups: list[str] = Field(default_factory=list, max_length=50)
    groups_claim: str = Field(default="groups", min_length=1, max_length=64)
    username_claim: str = Field(default="preferred_username", min_length=1, max_length=64)
    require_email_verified: bool = False


def build_router(ctx) -> APIRouter:
    """`ctx` carries the app's shared objects: vault, users, sessions, flows,
    limiters, oidc client, relying party, config and helpers."""
    r = APIRouter(prefix="/api/v1")
    vault, users, sessions, flows = ctx.vault, ctx.users, ctx.sessions, ctx.flows

    # ---------- helpers ----------

    def client_key(request: Request) -> str:
        return request.client.host if request.client else "unknown"

    def remember_seconds(wanted: bool) -> int:
        """How long a "keep me signed in" session may last: only when the person asked, and the administrator allows it."""
        return ctx.remember_seconds() if wanted else 0

    def device_label(request: Request | None) -> str:
        """A plain name for where someone signed in. The Android app names itself; for a browser, a short guess from its own description."""
        if request is None:
            return ""
        named = "".join(ch for ch in request.headers.get("x-enveliq-device", "") if ch.isprintable())[:80].strip()
        if named:
            return named
        ua = request.headers.get("user-agent", "")
        system = next((n for k, n in (("Android", "Android"), ("iPhone", "iPhone"), ("iPad", "iPad"), ("Windows", "Windows"),
                                      ("Mac OS", "Mac"), ("Linux", "Linux")) if k in ua), "")
        browser = next((n for k, n in (("Edg/", "Edge"), ("Firefox/", "Firefox"), ("Chrome/", "Chrome"), ("Safari/", "Safari")) if k in ua), "")
        return " on ".join(x for x in (browser, system) if x) or "A browser"

    def set_session(response: Response, user: dict[str, Any], *, method: str, remember: bool = False, request: Request | None = None) -> dict[str, Any]:
        state = "enroll" if users.mfa_required(user) and not users.has_mfa(user) else "full"
        session = sessions.create(users.principal(user), state=state, auth_method=method, remember_seconds=remember_seconds(remember), label=device_label(request))
        ctx.set_cookie(response, ctx.session_cookie, session.token, max_age=sessions.life_of(session))
        user["last_login_at"] = time.time()
        users.save(user)
        event = {"event": "signed_in", "user_id": user["id"], "method": method, "at": time.time()}
        if session.remember_seconds:
            event["remembered_days"] = round(session.remember_seconds / 86400)
        vault.audit(event)
        return {"next": "enroll_mfa" if state == "enroll" else "done", "user": users.public(user)}

    def start_flow(response: Response, kind: str, data: dict[str, Any], ttl: int = 300) -> None:
        flow_id = flows.create(kind, data, ttl_seconds=ttl)
        ctx.set_cookie(response, ctx.flow_cookie, flow_id, max_age=ttl)

    def flow_id_of(request: Request) -> str | None:
        return request.cookies.get(ctx.flow_cookie)

    def issue_recovery_if_missing(user: dict[str, Any]) -> list[str] | None:
        if user.get("recovery"):
            return None
        codes, digests = recovery.generate()
        user["recovery"] = digests
        return codes

    def finish_enrolment(request: Request, session: Session, user: dict[str, Any]) -> None:
        if session.state == "enroll" and users.has_mfa(user):
            session.state = "full"
        sessions.revoke_user(user["id"], except_token=session.token)

    def mfa_methods(user: dict[str, Any]) -> list[str]:
        methods = []
        if user.get("totp"):
            methods.append("totp")
        if user.get("passkeys"):
            methods.append("passkey")
        if user.get("recovery"):
            methods.append("recovery")
        return methods

    # ---------- first run ----------

    @r.post("/setup", status_code=201)
    def setup(body: SetupBody, request: Request, response: Response):
        if vault.is_initialized():
            raise HTTPException(409, "Enveliq is already set up")
        ctx.setup_limiter.acquire(client_key(request))
        if not ctx.check_setup_code(body.setup_code.get_secret_value()):
            raise HTTPException(403, "That setup code is not correct. Find it in the data folder file setup-code.txt or the server log.")
        try:
            username = normalise_username(body.username)
            passwords.validate_new_password(body.password.get_secret_value(), None, username)
            vault.initialize(ctx.vault_key_for_setup(body.passphrase.get_secret_value() if body.passphrase else None))
        except (UserError, ValueError) as exc:
            raise HTTPException(400, str(exc)) from exc
        except VaultAlreadyInitialized as exc:
            raise HTTPException(409, "Enveliq is already set up") from exc
        user = users.create_local(username, body.password.get_secret_value(), role="admin",
                                  display_name=body.display_name or username)
        users.set_policy({})
        ctx.setup_completed()
        vault.audit({"event": "setup_completed", "user_id": user["id"], "at": time.time()})
        return set_session(response, user, method="password", request=request)

    # ---------- sign-in ----------

    @r.post("/auth/login")
    def login(body: LoginBody, request: Request, response: Response):
        ctx.login_limiter.acquire(client_key(request))
        ctx.login_limiter.acquire("user:" + body.username.strip().lower()[:64])
        user = users.find_by_username(body.username)
        ok = passwords.verify_password(body.password.get_secret_value(), user.get("password") if user else None)
        if not ok or not user or user.get("disabled"):
            vault.audit({"event": "sign_in_failed", "user_id": user["id"] if user else None, "at": time.time()})
            raise HTTPException(401, "Username or password is not correct")
        if not users.password_login_allowed(user):
            raise HTTPException(403, "Please sign in with single sign-on")
        ctx.login_limiter.succeeded("user:" + user["username"])
        ctx.login_limiter.succeeded(client_key(request))
        if passwords.needs_rehash(user["password"]):
            user["password"] = passwords.hash_password(body.password.get_secret_value())
            users.save(user)
        if users.has_mfa(user):
            start_flow(response, "mfa", {"user_id": user["id"], "remember": body.remember})
            return {"next": "mfa", "methods": mfa_methods(user)}
        return set_session(response, user, method="password", remember=body.remember, request=request)

    @r.post("/auth/mfa")
    def second_factor(body: CodeBody, request: Request, response: Response):
        fid = flow_id_of(request)
        flow = flows.get(fid, "mfa")
        if flow is None:
            raise HTTPException(401, "Your sign-in timed out. Enter your password again.")
        try:
            user = users.get(flow["data"]["user_id"])
        except KeyError as exc:
            raise HTTPException(401, "Your sign-in timed out. Enter your password again.") from exc
        accepted = False
        if user.get("totp") and not recovery.looks_like_recovery_code(body.code):
            step = totp.verify(user["totp"]["secret"], body.code, user["totp"].get("last_step"))
            if step is not None:
                user["totp"]["last_step"] = step
                accepted = True
        elif recovery.looks_like_recovery_code(body.code):
            remaining = recovery.consume(body.code, user.get("recovery") or [])
            if remaining is not None:
                user["recovery"] = remaining
                accepted = True
                vault.audit({"event": "recovery_code_used", "user_id": user["id"], "left": len(remaining), "at": time.time()})
        if not accepted or user.get("disabled"):
            if not flows.fail(fid):
                ctx.clear_cookie(response, ctx.flow_cookie)
                raise HTTPException(401, "Too many wrong codes. Enter your password again.")
            raise HTTPException(401, "That code is not correct")
        flows.pop(fid)
        ctx.clear_cookie(response, ctx.flow_cookie)
        users.save(user)
        return set_session(response, user, method="password+totp", remember=bool(flow["data"].get("remember")), request=request)

    @r.post("/auth/passkeys/options")
    def passkey_options(body: PasskeyOptionsBody, request: Request, response: Response):
        ctx.login_limiter.acquire("pk:" + client_key(request))
        allowed = None
        user_id = None
        mfa_flow = None
        if body.purpose == "mfa":
            mfa_flow = flow_id_of(request)
            flow = flows.get(mfa_flow, "mfa")
            if flow is None:
                raise HTTPException(401, "Your sign-in timed out. Enter your password again.")
            user_id = flow["data"]["user_id"]
            allowed = users.get(user_id).get("passkeys") or []
            if not allowed:
                raise HTTPException(400, "No passkeys are registered for this account")
        options, challenge = passkeys.authentication_options(ctx.rp, allowed)
        start_flow(response, "passkey", {"challenge": challenge.hex(), "user_id": user_id, "mfa_flow": mfa_flow}, ttl=180)
        return options

    @r.post("/auth/passkeys/verify")
    def passkey_verify(body: CredentialBody, request: Request, response: Response):
        fid = flow_id_of(request)
        flow = flows.get(fid, "passkey")
        if flow is None:
            raise HTTPException(401, "The passkey request timed out. Try again.")
        flows.pop(fid)
        ctx.clear_cookie(response, ctx.flow_cookie)
        try:
            cred_id = passkeys.credential_id_of(body.credential)
        except ValueError as exc:
            raise HTTPException(400, "That passkey response is incomplete") from exc
        user, stored = users.find_by_passkey(cred_id)
        expected_user = flow["data"].get("user_id")
        if not user or user.get("disabled") or (expected_user and user["id"] != expected_user):
            raise HTTPException(401, "That passkey is not registered with Enveliq")
        handle = (body.credential.get("response") or {}).get("userHandle")
        if handle:
            from webauthn.helpers import base64url_to_bytes
            try:
                if base64url_to_bytes(handle) != user["id"].encode("ascii"):
                    raise HTTPException(401, "That passkey belongs to a different account")
            except HTTPException:
                raise
            except Exception as exc:
                raise HTTPException(400, "That passkey response is malformed") from exc
        try:
            new_count = passkeys.verify_authentication(ctx.rp, body.credential, bytes.fromhex(flow["data"]["challenge"]), stored)
        except Exception as exc:
            vault.audit({"event": "passkey_failed", "user_id": user["id"], "at": time.time()})
            raise HTTPException(401, "The passkey could not be verified") from exc
        stored["sign_count"] = new_count
        stored["last_used_at"] = time.time()
        users.save(user)
        remember = body.remember
        if expected_user:  # second-factor step after a password: end that step too
            mfa_flow = flows.get(flow["data"].get("mfa_flow"), "mfa")
            remember = bool(mfa_flow and mfa_flow["data"].get("remember"))     # the tick was given with the password
            flows.pop(flow["data"].get("mfa_flow"))
        ctx.login_limiter.succeeded("pk:" + client_key(request))
        return set_session(response, user, method="password+passkey" if expected_user else "passkey", remember=remember, request=request)

    @r.post("/auth/logout", status_code=204)
    def logout(request: Request, response: Response):
        token = request.cookies.get(ctx.session_cookie)
        if token:
            sessions.revoke(token)
        ctx.clear_cookie(response, ctx.session_cookie)
        ctx.clear_cookie(response, ctx.flow_cookie)
        response.status_code = 204
        return response

    # ---------- your devices ----------

    @r.get("/auth/devices")
    def my_devices(request: Request, session: Session = Depends(ctx.full_session)):
        return {"items": sessions.devices_of(session.principal.user_id, session.token)}

    @r.delete("/auth/devices/{device_id}", status_code=204)
    def sign_device_out(device_id: str, request: Request, response: Response, session: Session = Depends(ctx.full_session)):
        if not sessions.revoke_device(session.principal.user_id, device_id):
            raise HTTPException(404, "Not found")
        vault.audit({"event": "device_signed_out", "user_id": session.principal.user_id, "at": time.time()})
        return Response(status_code=204)

    @r.get("/me")
    def me(session: Session = Depends(ctx.any_session)):
        user = users.get(session.principal.user_id)
        policy = users.policy()
        return {
            **users.public(user),
            "about": user.get("about") or "",
            "show_in_people": user.get("people_list") is not False,
            "session": {"state": session.state, "method": session.auth_method},
            "mfa_required": users.mfa_required(user),
            "policy": policy,
            "password_rules": passwords.describe_rules(policy),
            "sso": ctx.sso_public(),
        }

    # ---------- own profile (everything optional) ----------

    @r.patch("/me/profile")
    def update_profile(body: ProfileBody, session: Session = Depends(ctx.full_session)):
        user = users.get(session.principal.user_id)
        try:
            if body.display_name is not None:
                user["display_name"] = profiles.clean_text(body.display_name, 128) or user["username"]
            if body.email is not None:
                user["email"] = profiles.clean_email(body.email)
            if body.about is not None:
                user["about"] = profiles.clean_text(body.about, 500)
            if body.show_in_people is not None:
                user["people_list"] = bool(body.show_in_people)
        except profiles.ProfileError as exc:
            raise HTTPException(400, str(exc)) from exc
        users.save(user)
        return {**users.public(user), "about": user.get("about") or "", "show_in_people": user.get("people_list") is not False}

    @r.put("/me/avatar")
    def set_avatar(body: AvatarBody, session: Session = Depends(ctx.full_session)):
        user = users.get(session.principal.user_id)
        try:
            user["avatar"] = profiles.parse_avatar(body.image)
        except profiles.ProfileError as exc:
            raise HTTPException(400, str(exc)) from exc
        users.save(user)
        return users.public(user)

    @r.delete("/me/avatar")
    def remove_avatar(session: Session = Depends(ctx.full_session)):
        user = users.get(session.principal.user_id)
        user["avatar"] = None
        users.save(user)
        return users.public(user)

    @r.get("/users/{user_id}/avatar")
    def avatar(user_id: str, session: Session = Depends(ctx.full_session)):
        # Only the picture is ever shared between people, never anything else about them.
        try:
            user = users.get(user_id)
        except KeyError as exc:
            raise HTTPException(404, "No picture") from exc
        pic = user.get("avatar")
        if not pic or user.get("disabled"):
            raise HTTPException(404, "No picture")
        return Response(content=base64.b64decode(pic["data"]), media_type=pic["mime"],
                        headers={"Cache-Control": "private, max-age=31536000, immutable", "X-Content-Type-Options": "nosniff",
                                 "Content-Security-Policy": "default-src 'none'; sandbox"})

    # ---------- own password ----------

    @r.post("/auth/password", status_code=204)
    def change_password(body: PasswordChangeBody, request: Request, session: Session = Depends(ctx.full_session)):
        ctx.login_limiter.acquire("pw:" + session.principal.user_id)
        user = users.get(session.principal.user_id)
        if user.get("password") and not passwords.verify_password(body.current_password.get_secret_value(), user["password"]):
            raise HTTPException(401, "Your current password is not correct")
        try:
            passwords.validate_new_password(body.new_password.get_secret_value(), users.password_rules(), user["username"])
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        user["password"] = passwords.hash_password(body.new_password.get_secret_value())
        users.save(user)
        sessions.revoke_user(user["id"], except_token=session.token)
        vault.audit({"event": "password_changed", "user_id": user["id"], "at": time.time()})
        return Response(status_code=204)

    # ---------- authenticator app (TOTP) ----------

    @r.post("/auth/totp/setup")
    def totp_setup(session: Session = Depends(ctx.any_session)):
        user = users.get(session.principal.user_id)
        if user.get("totp"):
            raise HTTPException(409, "An authenticator app is already set up. Turn it off first to replace it.")
        secret = totp.new_secret()
        session.pending["totp"] = {"secret": secret, "expires": time.monotonic() + 600}
        uri = totp.provisioning_uri(secret, user["username"])
        return {"secret": secret, "otpauth_uri": uri, "qr_svg": totp.qr_svg(uri)}

    @r.post("/auth/totp/confirm")
    def totp_confirm(body: CodeBody, request: Request, session: Session = Depends(ctx.any_session)):
        pending = session.pending.get("totp")
        if not pending or pending["expires"] < time.monotonic():
            raise HTTPException(409, "Start the authenticator setup again")
        step = totp.verify(pending["secret"], body.code)
        if step is None:
            raise HTTPException(400, "That code is not correct. Check the time on your phone and try the next code.")
        user = users.get(session.principal.user_id)
        user["totp"] = {"secret": pending["secret"], "last_step": step, "created_at": time.time()}
        codes = issue_recovery_if_missing(user)
        users.save(user)
        session.pending.pop("totp", None)
        finish_enrolment(request, session, user)
        vault.audit({"event": "totp_enabled", "user_id": user["id"], "at": time.time()})
        return {"recovery_codes": codes, "session": session.state}

    @r.post("/auth/totp/disable", status_code=204)
    def totp_disable(body: CodeBody, session: Session = Depends(ctx.full_session)):
        user = users.get(session.principal.user_id)
        if not user.get("totp"):
            return Response(status_code=204)
        if totp.verify(user["totp"]["secret"], body.code, user["totp"].get("last_step")) is None:
            raise HTTPException(400, "That code is not correct")
        if users.mfa_required(user) and not user.get("passkeys"):
            raise HTTPException(409, "Two-factor sign-in is required for your account. Add a passkey before turning this off.")
        user["totp"] = None
        if not users.has_mfa(user):
            user["recovery"] = []
        users.save(user)
        vault.audit({"event": "totp_disabled", "user_id": user["id"], "at": time.time()})
        return Response(status_code=204)

    @r.post("/auth/recovery-codes")
    def new_recovery_codes(session: Session = Depends(ctx.full_session)):
        user = users.get(session.principal.user_id)
        if not users.has_mfa(user):
            raise HTTPException(409, "Set up an authenticator app or passkey first")
        codes, digests = recovery.generate()
        user["recovery"] = digests
        users.save(user)
        vault.audit({"event": "recovery_codes_regenerated", "user_id": user["id"], "at": time.time()})
        return {"recovery_codes": codes}

    # ---------- passkey management ----------

    @r.post("/auth/passkeys/register/options")
    def passkey_register_options(session: Session = Depends(ctx.any_session)):
        user = users.get(session.principal.user_id)
        if len(user.get("passkeys") or []) >= passkeys.MAX_PASSKEYS_PER_USER:
            raise HTTPException(409, "You have reached the passkey limit. Remove one first.")
        options, challenge = passkeys.registration_options(ctx.rp, user)
        session.pending["passkey"] = {"challenge": challenge.hex(), "expires": time.monotonic() + 180}
        return options

    @r.post("/auth/passkeys/register/verify")
    def passkey_register_verify(body: CredentialBody, request: Request, session: Session = Depends(ctx.any_session)):
        pending = session.pending.pop("passkey", None)
        if not pending or pending["expires"] < time.monotonic():
            raise HTTPException(409, "The passkey request timed out. Try again.")
        user = users.get(session.principal.user_id)
        try:
            record = passkeys.verify_registration(ctx.rp, body.credential, bytes.fromhex(pending["challenge"]), body.name or "Passkey")
        except Exception as exc:
            raise HTTPException(400, "The passkey could not be registered. Try again on this device.") from exc
        other, _ = users.find_by_passkey(record["id"])
        if other:
            raise HTTPException(409, "That passkey is already registered")
        user.setdefault("passkeys", []).append(record)
        codes = issue_recovery_if_missing(user)
        users.save(user)
        finish_enrolment(request, session, user)
        vault.audit({"event": "passkey_added", "user_id": user["id"], "at": time.time()})
        return {"passkey": {"id": record["id"], "name": record["name"]}, "recovery_codes": codes, "session": session.state}

    @r.patch("/auth/passkeys/{passkey_id}")
    def passkey_rename(passkey_id: str, body: RenameBody, session: Session = Depends(ctx.full_session)):
        user = users.get(session.principal.user_id)
        cred = next((c for c in user.get("passkeys", []) if c["id"] == passkey_id), None)
        if cred is None:
            raise HTTPException(404, "Passkey not found")
        cred["name"] = body.name.strip()
        users.save(user)
        return {"id": cred["id"], "name": cred["name"]}

    @r.delete("/auth/passkeys/{passkey_id}", status_code=204)
    def passkey_delete(passkey_id: str, session: Session = Depends(ctx.full_session)):
        user = users.get(session.principal.user_id)
        remaining = [c for c in user.get("passkeys", []) if c["id"] != passkey_id]
        if len(remaining) == len(user.get("passkeys", [])):
            raise HTTPException(404, "Passkey not found")
        if users.mfa_required(user) and not remaining and not user.get("totp"):
            raise HTTPException(409, "Two-factor sign-in is required for your account. Set up an authenticator app before removing your last passkey.")
        if not remaining and not user.get("password") and not user.get("oidc"):
            raise HTTPException(409, "This is your only way to sign in")
        user["passkeys"] = remaining
        if not users.has_mfa(user):
            user["recovery"] = []
        users.save(user)
        vault.audit({"event": "passkey_removed", "user_id": user["id"], "at": time.time()})
        return Response(status_code=204)

    # ---------- single sign-on ----------

    @r.get("/auth/sso/start")
    def sso_start(request: Request, link: int = 0, remember: int = 0):
        settings = ctx.sso_settings()
        if settings is None:
            return RedirectResponse("/login?error=sso_disabled", status_code=303)
        link_user = None
        if link:
            session = ctx.peek_full_session(request)
            if session is None:
                return RedirectResponse("/login", status_code=303)
            link_user = session.principal.user_id
        try:
            url, secrets_ = ctx.oidc.authorization_url(settings, ctx.sso_redirect_uri)
        except OIDCError as exc:
            return RedirectResponse(f"/login?error=sso_{exc.code}", status_code=303)
        response = RedirectResponse(url, status_code=303)
        start_flow(response, "oidc", {**secrets_, "link_user": link_user, "remember": bool(remember) and not link}, ttl=600)
        return response

    @r.get("/auth/sso/callback")
    def sso_callback(request: Request, code: str = "", state: str = "", error: str = ""):
        fid = flow_id_of(request)
        flow = flows.get(fid, "oidc")
        fail_to = "/account?error=sso_" if (flow and flow["data"].get("link_user")) else "/login?error=sso_"

        def fail(reason: str) -> RedirectResponse:
            resp = RedirectResponse(fail_to + reason, status_code=303)
            ctx.clear_cookie(resp, ctx.flow_cookie)
            return resp

        if flow is None:
            return fail("expired")
        flows.pop(fid)
        if error:
            return fail("denied")
        if not state or not secrets.compare_digest(state, flow["data"]["state"]) or not code or len(code) > 4096:
            return fail("state")
        settings = ctx.sso_settings()
        if settings is None:
            return fail("disabled")
        try:
            claims = ctx.oidc.exchange(settings, code=code, redirect_uri=ctx.sso_redirect_uri,
                                       verifier=flow["data"]["verifier"], nonce=flow["data"]["nonce"])
        except OIDCError as exc:
            vault.audit({"event": "sso_failed", "reason": exc.code, "at": time.time()})
            return fail(exc.code)

        issuer, subject = claims["_issuer"], str(claims["sub"])
        groups = groups_from(claims, settings.groups_claim)
        if settings.require_email_verified and claims.get("email") and claims.get("email_verified") is not True:
            return fail("email_unverified")
        if settings.allowed_groups and not groups.intersection(settings.allowed_groups):
            vault.audit({"event": "sso_denied_group", "at": time.time()})
            return fail("not_allowed")

        link_user = flow["data"].get("link_user")
        user = users.find_by_oidc(issuer, subject)
        if link_user:
            if user and user["id"] != link_user:
                return fail("already_linked")
            user = users.get(link_user)
            if not any(l.get("iss") == issuer and l.get("sub") == subject for l in user.get("oidc", [])):
                user.setdefault("oidc", []).append({"iss": issuer, "sub": subject})
                users.save(user)
                vault.audit({"event": "sso_linked", "user_id": user["id"], "at": time.time()})
            return RedirectResponse("/account?linked=1", status_code=303)

        wants_admin = bool(settings.admin_groups) and bool(groups.intersection(settings.admin_groups))
        if user is None:
            if not settings.auto_create:
                return fail("not_provisioned")
            hint = str(claims.get(settings.username_claim) or claims.get("preferred_username")
                       or (claims.get("email") or "").split("@")[0] or "user")
            user = users.create_from_oidc(issuer=issuer, subject=subject, username_hint=hint,
                                          display_name=claims.get("name") or hint, email=claims.get("email"),
                                          role="admin" if wants_admin else "user")
            vault.audit({"event": "user_created_by_sso", "user_id": user["id"], "role": user["role"], "at": time.time()})
        if user.get("disabled"):
            return fail("disabled_user")
        # Keep SSO-created users' role in step with the provider's groups.
        if user.get("source") == "oidc" and settings.admin_groups:
            new_role = "admin" if wants_admin else "user"
            if new_role != user.get("role"):
                try:
                    users.guard_last_admin(user, new_role=new_role)
                    user["role"] = new_role
                except UserError:
                    pass
        if claims.get("email"):
            user["email"] = str(claims["email"])[:320]
        users.save(user)
        response = RedirectResponse("/", status_code=303)
        ctx.clear_cookie(response, ctx.flow_cookie)
        # The provider is responsible for its own second factor, so an SSO
        # sign-in is a full session even when Enveliq's MFA policy applies.
        session = sessions.create(users.principal(user), state="full", auth_method="sso",
                                  remember_seconds=remember_seconds(bool(flow["data"].get("remember"))), label=device_label(request))
        ctx.set_cookie(response, ctx.session_cookie, session.token, max_age=sessions.life_of(session))
        user["last_login_at"] = time.time()
        users.save(user)
        event = {"event": "signed_in", "user_id": user["id"], "method": "sso", "at": time.time()}
        if session.remember_seconds:
            event["remembered_days"] = round(session.remember_seconds / 86400)
        vault.audit(event)
        return response

    @r.delete("/auth/sso/link", status_code=204)
    def sso_unlink(session: Session = Depends(ctx.full_session)):
        user = users.get(session.principal.user_id)
        if not user.get("password") and not user.get("passkeys"):
            raise HTTPException(409, "Set a password or add a passkey first, or you would have no way to sign in")
        user["oidc"] = []
        users.save(user)
        vault.audit({"event": "sso_unlinked", "user_id": user["id"], "at": time.time()})
        return Response(status_code=204)

    # ---------- administration ----------

    def load_user(user_id: str) -> dict[str, Any]:
        try:
            return users.get(user_id)
        except KeyError as exc:
            raise HTTPException(404, "User not found") from exc

    @r.get("/admin/users")
    def admin_list_users(session: Session = Depends(ctx.admin_session)):
        return [users.public(u) for u in users.all()]

    @r.post("/admin/users", status_code=201)
    def admin_create_user(body: NewUserBody, session: Session = Depends(ctx.admin_session)):
        try:
            user = users.create_local(body.username, body.password.get_secret_value(), role=body.role,
                                      display_name=body.display_name)
        except (UserError, ValueError) as exc:
            raise HTTPException(400, str(exc)) from exc
        vault.audit({"event": "user_created", "user_id": user["id"], "by": session.principal.user_id, "at": time.time()})
        return users.public(user)

    @r.patch("/admin/users/{user_id}")
    def admin_update_user(user_id: str, body: UserPatchBody, session: Session = Depends(ctx.admin_session)):
        user = load_user(user_id)
        try:
            users.guard_last_admin(user, new_role=body.role, disabling=bool(body.disabled))
        except UserError as exc:
            raise HTTPException(409, str(exc)) from exc
        if body.display_name is not None:
            user["display_name"] = body.display_name
        if body.role is not None:
            user["role"] = body.role
        if body.disabled is not None:
            user["disabled"] = body.disabled
        users.save(user)
        if body.disabled or body.role:
            sessions.revoke_user(user_id)
        vault.audit({"event": "user_updated", "user_id": user_id, "by": session.principal.user_id, "at": time.time()})
        return users.public(user)

    @r.delete("/admin/users/{user_id}", status_code=204)
    def admin_delete_user(user_id: str, session: Session = Depends(ctx.admin_session)):
        user = load_user(user_id)
        if user_id == session.principal.user_id:
            raise HTTPException(409, "You can't delete your own account")
        try:
            users.guard_last_admin(user, deleting=True)
        except UserError as exc:
            raise HTTPException(409, str(exc)) from exc
        ctx.delete_user_data(user_id)
        vault.delete_user(user_id)
        sessions.revoke_user(user_id)
        vault.audit({"event": "user_deleted", "user_id": user_id, "by": session.principal.user_id, "at": time.time()})
        return Response(status_code=204)

    @r.post("/admin/users/{user_id}/reset-mfa", status_code=204)
    def admin_reset_mfa(user_id: str, session: Session = Depends(ctx.admin_session)):
        user = load_user(user_id)
        user["totp"], user["passkeys"], user["recovery"] = None, [], []
        users.save(user)
        sessions.revoke_user(user_id)
        vault.audit({"event": "mfa_reset", "user_id": user_id, "by": session.principal.user_id, "at": time.time()})
        return Response(status_code=204)

    @r.post("/admin/users/{user_id}/password", status_code=204)
    def admin_set_password(user_id: str, body: SetPasswordBody, session: Session = Depends(ctx.admin_session)):
        user = load_user(user_id)
        try:
            passwords.validate_new_password(body.password.get_secret_value(), users.password_rules(), user["username"])
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        user["password"] = passwords.hash_password(body.password.get_secret_value())
        users.save(user)
        sessions.revoke_user(user_id)
        vault.audit({"event": "password_reset_by_admin", "user_id": user_id, "by": session.principal.user_id, "at": time.time()})
        return Response(status_code=204)

    @r.get("/admin/auth-policy")
    def get_policy(session: Session = Depends(ctx.admin_session)):
        return {**users.policy(), "remember_possible": ctx.remember_possible}

    @r.put("/admin/auth-policy")
    def put_policy(body: PolicyBody, session: Session = Depends(ctx.admin_session)):
        policy = users.set_policy(body.model_dump(exclude_none=True))
        vault.audit({"event": "auth_policy_updated", "by": session.principal.user_id, "at": time.time()})
        return {**policy, "remember_possible": ctx.remember_possible}

    @r.get("/admin/sso")
    def get_sso(session: Session = Depends(ctx.admin_session)):
        record = dict(vault.get_global("sso-oidc") or {})
        has_secret = bool(record.pop("client_secret", None))
        return {**SSOBody().model_dump(exclude={"client_secret"}), **record,
                "client_secret_set": has_secret, "redirect_uri": ctx.sso_redirect_uri}

    @r.put("/admin/sso")
    def put_sso(body: SSOBody, session: Session = Depends(ctx.admin_session)):
        data = body.model_dump(mode="python")
        existing = vault.get_global("sso-oidc") or {}
        data["client_secret"] = body.client_secret.get_secret_value() if body.client_secret else existing.get("client_secret")
        data["allowed_groups"] = [g.strip() for g in data["allowed_groups"] if g.strip()]
        data["admin_groups"] = [g.strip() for g in data["admin_groups"] if g.strip()]
        if data["enabled"]:
            if not data["issuer"] or not data["client_id"]:
                raise HTTPException(400, "Issuer URL and client ID are required to turn on single sign-on")
            try:
                require_secure_url(data["issuer"], ctx.oidc.allow_http)
                from urllib.parse import urlsplit
                validate_host(urlsplit(data["issuer"]).hostname)
            except (OIDCError, ValueError) as exc:
                raise HTTPException(400, "The issuer must be an https:// URL") from exc
            if "openid" not in data["scopes"].split():
                raise HTTPException(400, "Scopes must include openid")
        vault.set_global("sso-oidc", data)
        vault.audit({"event": "sso_settings_updated", "by": session.principal.user_id, "at": time.time()})
        return {"saved": True, "redirect_uri": ctx.sso_redirect_uri}

    @r.post("/admin/sso/test")
    def test_sso(session: Session = Depends(ctx.admin_session)):
        record = vault.get_global("sso-oidc") or {}
        if not record.get("issuer"):
            raise HTTPException(400, "Save an issuer URL first")
        try:
            meta = ctx.oidc.metadata(record["issuer"], refresh=True)
            keys = ctx.oidc.jwks(meta, refresh=True)
        except OIDCError as exc:
            raise HTTPException(502, f"Could not reach the provider: {exc}") from exc
        return {"ok": True, "issuer": meta["issuer"], "authorization_endpoint": meta["authorization_endpoint"],
                "signing_keys": len(keys), "redirect_uri": ctx.sso_redirect_uri}

    return r
