"""User accounts kept in the encrypted vault.

A household-sized user list (tens of users) is decrypted and scanned for
lookups, which avoids keeping any plaintext index of usernames, SSO subjects
or passkey ids in the database.
"""
from __future__ import annotations

import re
import time
from typing import Any

from ..crypto_vault import Principal, SecureVault
from . import passwords

USERNAME_RE = re.compile(r"^[a-z0-9][a-z0-9._@-]{0,63}$")
ROLES = ("admin", "user")

DEFAULT_POLICY: dict[str, Any] = {
    # Who must use a second factor (authenticator code or passkey).
    "require_mfa": "admins",          # "off" | "admins" | "everyone"
    # Who may sign in with a local password. Administrators always may, so a
    # broken SSO provider can never lock the household out ("break-glass").
    "password_login": "everyone",     # "everyone" | "admins"
    # "Keep me signed in on this device": how many days such a sign-in lasts. 0 turns the tick-box off. At most 14.
    "remember_days": 0,
    # What a new password must contain (see passwords.DEFAULT_RULES).
    **passwords.DEFAULT_RULES,
}


class UserError(ValueError):
    pass


def normalise_username(value: str) -> str:
    name = (value or "").strip().lower()
    if not USERNAME_RE.match(name):
        raise UserError("Usernames are 1-64 characters: letters, numbers, dot, dash, underscore or @")
    return name


class UserService:
    def __init__(self, vault: SecureVault):
        self.vault = vault

    # ---------- policy ----------

    def policy(self) -> dict[str, Any]:
        return {**DEFAULT_POLICY, **(self.vault.get_global("auth-policy") or {})}

    def set_policy(self, policy: dict[str, Any]) -> dict[str, Any]:
        merged = {**self.policy(), **policy}
        if merged["require_mfa"] not in ("off", "admins", "everyone"):
            raise UserError("Invalid two-factor policy")
        if merged["password_login"] not in ("everyone", "admins"):
            raise UserError("Invalid password sign-in policy")
        days = merged.get("remember_days", 0)
        if isinstance(days, bool) or not isinstance(days, int) or not 0 <= days <= 14:
            raise UserError("Keep me signed in can last between 0 and 14 days")
        merged.update(passwords.clean_rules(merged))
        self.vault.set_global("auth-policy", merged)
        return merged

    def password_rules(self) -> dict[str, Any]:
        return passwords.clean_rules(self.policy())

    # ---------- lookups ----------

    def all(self) -> list[dict[str, Any]]:
        return self.vault.list_users()

    def get(self, user_id: str) -> dict[str, Any]:
        return self.vault.get_user(user_id)

    def find_by_username(self, username: str) -> dict[str, Any] | None:
        try:
            name = normalise_username(username)
        except UserError:
            return None
        return next((u for u in self.all() if u.get("username") == name), None)

    def find_by_oidc(self, issuer: str, subject: str) -> dict[str, Any] | None:
        for user in self.all():
            for link in user.get("oidc", []):
                if link.get("iss") == issuer and link.get("sub") == subject:
                    return user
        return None

    def find_by_passkey(self, credential_id: str) -> tuple[dict[str, Any], dict[str, Any]] | tuple[None, None]:
        for user in self.all():
            for cred in user.get("passkeys", []):
                if cred.get("id") == credential_id:
                    return user, cred
        return None, None

    # ---------- creation ----------

    def _unique_username(self, wanted: str) -> str:
        base = re.sub(r"[^a-z0-9._@-]", "", (wanted or "").lower())[:56] or "user"
        if not base[0].isalnum():
            base = "u" + base
        taken = {u.get("username") for u in self.all()}
        name, n = base, 2
        while name in taken:
            name, n = f"{base}{n}", n + 1
        return name

    def create_local(self, username: str, password: str, *, role: str = "user", display_name: str | None = None) -> dict[str, Any]:
        name = normalise_username(username)
        if role not in ROLES:
            raise UserError("Invalid role")
        if self.find_by_username(name):
            raise UserError("That username is already taken")
        try:
            passwords.validate_new_password(password, self.password_rules(), name)
        except ValueError as exc:
            raise UserError(str(exc)) from exc
        record = {
            "username": name, "display_name": (display_name or name)[:128], "email": None, "role": role,
            "disabled": False, "source": "local", "password": passwords.hash_password(password),
            "totp": None, "recovery": [], "passkeys": [], "oidc": [],
            "created_at": time.time(), "last_login_at": None,
        }
        user_id = self.vault.create_user(record)
        return self.get(user_id)

    def create_from_oidc(self, *, issuer: str, subject: str, username_hint: str, display_name: str | None,
                         email: str | None, role: str) -> dict[str, Any]:
        record = {
            "username": self._unique_username(username_hint), "display_name": (display_name or username_hint or "User")[:128],
            "email": email, "role": role, "disabled": False, "source": "oidc", "password": None,
            "totp": None, "recovery": [], "passkeys": [], "oidc": [{"iss": issuer, "sub": subject}],
            "created_at": time.time(), "last_login_at": None,
        }
        user_id = self.vault.create_user(record)
        return self.get(user_id)

    # ---------- updates ----------

    def save(self, user: dict[str, Any]) -> None:
        self.vault.update_user(user["id"], user)

    def active_admins(self, exclude: str | None = None) -> list[dict[str, Any]]:
        return [u for u in self.all() if u.get("role") == "admin" and not u.get("disabled") and u["id"] != exclude]

    def guard_last_admin(self, user: dict[str, Any], *, new_role: str | None = None, disabling: bool = False,
                         deleting: bool = False) -> None:
        losing_admin = user.get("role") == "admin" and (deleting or disabling or (new_role and new_role != "admin"))
        if losing_admin and not self.active_admins(exclude=user["id"]):
            raise UserError("This is the only active administrator. Make someone else an administrator first.")

    # ---------- views ----------

    @staticmethod
    def principal(user: dict[str, Any]) -> Principal:
        return Principal(user_id=user["id"], name=user.get("display_name") or user["username"], is_admin=user.get("role") == "admin")

    @staticmethod
    def has_mfa(user: dict[str, Any]) -> bool:
        return bool(user.get("totp")) or bool(user.get("passkeys"))

    def mfa_required(self, user: dict[str, Any]) -> bool:
        rule = self.policy()["require_mfa"]
        return rule == "everyone" or (rule == "admins" and user.get("role") == "admin")

    def password_login_allowed(self, user: dict[str, Any]) -> bool:
        return self.policy()["password_login"] == "everyone" or user.get("role") == "admin"

    @staticmethod
    def public(user: dict[str, Any], *, include_security: bool = True) -> dict[str, Any]:
        out = {
            "id": user["id"], "username": user["username"], "display_name": user.get("display_name"),
            "email": user.get("email"), "role": user.get("role"), "disabled": bool(user.get("disabled")),
            "source": user.get("source"), "created_at": user.get("created_at"), "last_login_at": user.get("last_login_at"),
            "avatar_v": (user.get("avatar") or {}).get("v"),
        }
        if include_security:
            out["security"] = {
                "password_set": bool(user.get("password")),
                "totp_enabled": bool(user.get("totp")),
                "recovery_codes_left": len(user.get("recovery") or []),
                "passkeys": [
                    {"id": c["id"], "name": c.get("name"), "created_at": c.get("created_at"), "last_used_at": c.get("last_used_at")}
                    for c in user.get("passkeys", [])
                ],
                "sso_linked": bool(user.get("oidc")),
            }
        return out
