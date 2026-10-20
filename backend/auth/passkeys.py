"""Passkeys (WebAuthn) via py_webauthn.

Passkeys are phishing-resistant: the browser only signs for the exact site
origin, so a look-alike domain gets nothing usable. User verification
(device PIN / biometric) is required, which is why a passkey sign-in counts
as two factors and skips the authenticator-code step.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any

from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers import base64url_to_bytes, bytes_to_base64url
from webauthn.helpers.structs import (
    AttestationConveyancePreference,
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

MAX_PASSKEYS_PER_USER = 20


@dataclass(frozen=True)
class RelyingParty:
    rp_id: str      # hostname of the public URL, e.g. "enveliq.home.example"
    origin: str     # exact origin, e.g. "https://enveliq.home.example"
    name: str = "Enveliq"
    # Extra origins accepted when SIGNING IN (never when adding a passkey): the Enveliq Android app, which signs with its own key.
    extra_origins: tuple[str, ...] = ()


def registration_options(rp: RelyingParty, user: dict[str, Any]) -> tuple[dict, bytes]:
    options = generate_registration_options(
        rp_id=rp.rp_id,
        rp_name=rp.name,
        user_id=user["id"].encode("ascii"),
        user_name=user["username"],
        user_display_name=user.get("display_name") or user["username"],
        attestation=AttestationConveyancePreference.NONE,
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.REQUIRED,
            user_verification=UserVerificationRequirement.REQUIRED,
        ),
        exclude_credentials=[PublicKeyCredentialDescriptor(id=base64url_to_bytes(c["id"])) for c in user.get("passkeys", [])],
        timeout=120000,
    )
    return json.loads(options_to_json(options)), options.challenge


def verify_registration(rp: RelyingParty, credential: dict, challenge: bytes, name: str) -> dict[str, Any]:
    verified = verify_registration_response(
        credential=credential,
        expected_challenge=challenge,
        expected_rp_id=rp.rp_id,
        expected_origin=rp.origin,
        require_user_verification=True,
    )
    transports = [t for t in (credential.get("response", {}).get("transports") or []) if isinstance(t, str)][:8]
    return {
        "id": bytes_to_base64url(verified.credential_id),
        "public_key": bytes_to_base64url(verified.credential_public_key),
        "sign_count": verified.sign_count,
        "transports": transports,
        "backed_up": bool(getattr(verified, "credential_backed_up", False)),
        "name": (name or "Passkey").strip()[:64] or "Passkey",
        "created_at": time.time(),
        "last_used_at": None,
    }


def authentication_options(rp: RelyingParty, allowed: list[dict[str, Any]] | None = None) -> tuple[dict, bytes]:
    options = generate_authentication_options(
        rp_id=rp.rp_id,
        allow_credentials=[PublicKeyCredentialDescriptor(id=base64url_to_bytes(c["id"])) for c in (allowed or [])],
        user_verification=UserVerificationRequirement.REQUIRED,
        timeout=120000,
    )
    return json.loads(options_to_json(options)), options.challenge


def credential_id_of(credential: dict) -> str:
    raw = credential.get("rawId") or credential.get("id") or ""
    if not isinstance(raw, str) or not raw or len(raw) > 1400:
        raise ValueError("Missing credential id")
    return bytes_to_base64url(base64url_to_bytes(raw))


def verify_authentication(rp: RelyingParty, credential: dict, challenge: bytes, stored: dict[str, Any]) -> int:
    verified = verify_authentication_response(
        credential=credential,
        expected_challenge=challenge,
        expected_rp_id=rp.rp_id,
        expected_origin=[rp.origin, *rp.extra_origins] if rp.extra_origins else rp.origin,
        credential_public_key=base64url_to_bytes(stored["public_key"]),
        credential_current_sign_count=int(stored.get("sign_count") or 0),
        require_user_verification=True,
    )
    return verified.new_sign_count


ANDROID_PACKAGE = "app.enveliq"

# The SHA-256 fingerprint of the key that signs the official Enveliq app (public, not a secret). Everyone who installs the official app
# gets passkeys on the phone with no setting. People who build the app with their own key add its fingerprint with ENVELIQ_ANDROID_CERT_SHA256.
OFFICIAL_ANDROID_CERT = ""


def parse_cert_fingerprints(raw: str) -> list[str]:
    """SHA-256 fingerprints of the Android app's signing certificate, from a comma-separated setting (hex, with or without colons).
    Anything that is not 32 bytes of hex is ignored. Returns them as upper-case, colon-separated pairs, as Android wants them."""
    found: list[str] = []
    for part in (raw or "").replace(";", ",").replace(" ", ",").split(","):
        hexed = part.strip().replace(":", "")
        if len(hexed) != 64:
            continue
        try:
            data = bytes.fromhex(hexed)
        except ValueError:
            continue
        pretty = ":".join(f"{b:02X}" for b in data)
        if pretty not in found:
            found.append(pretty)
    return found


def android_origin(fingerprint: str) -> str:
    """The origin a passkey response carries when it was made inside the Android app: its signing certificate's hash."""
    return "android:apk-key-hash:" + bytes_to_base64url(bytes.fromhex(fingerprint.replace(":", "")))


def asset_links(fingerprints: list[str]) -> list[dict[str, Any]]:
    """The /.well-known/assetlinks.json document: it tells Android that this site trusts the Enveliq app for passkeys."""
    return [{
        "relation": ["delegate_permission/common.get_login_creds"],
        "target": {"namespace": "android_app", "package_name": ANDROID_PACKAGE, "sha256_cert_fingerprints": fingerprints},
    }]
