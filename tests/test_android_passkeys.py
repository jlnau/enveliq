"""Passkeys on the Android phone: Enveliq publishes the link file and accepts the app's own origin only when the app's key fingerprint is set."""
from __future__ import annotations

import base64

from fastapi.testclient import TestClient

from helpers import load_app

FP = "AB:CD:EF:01:23:45:67:89:AB:CD:EF:01:23:45:67:89:AB:CD:EF:01:23:45:67:89:AB:CD:EF:01:23:45:67:89"
FP_RAW = FP.replace(":", "").lower()


def test_fingerprints_are_cleaned_and_bad_ones_ignored():
    from backend.auth import passkeys
    got = passkeys.parse_cert_fingerprints(f"{FP_RAW}, nonsense, {FP}, 1234")
    assert got == [FP]
    assert passkeys.parse_cert_fingerprints("") == []


def test_android_origin_is_the_hash_of_the_certificate():
    from backend.auth import passkeys
    expected = "android:apk-key-hash:" + base64.urlsafe_b64encode(bytes.fromhex(FP_RAW)).decode().rstrip("=")
    assert passkeys.android_origin(FP) == expected


def test_link_file_is_not_found_until_the_fingerprint_is_set(tmp_path):
    m = load_app(tmp_path)
    c = TestClient(m.app, raise_server_exceptions=False)
    assert c.get("/.well-known/assetlinks.json").status_code == 404
    assert m.relying_party.extra_origins == ()


def test_link_file_names_the_app_and_its_fingerprint(tmp_path):
    m = load_app(tmp_path, ENVELIQ_ANDROID_CERT_SHA256=FP_RAW)
    c = TestClient(m.app, raise_server_exceptions=False)
    r = c.get("/.well-known/assetlinks.json")
    assert r.status_code == 200
    doc = r.json()
    assert doc[0]["relation"] == ["delegate_permission/common.get_login_creds"]
    assert doc[0]["target"]["package_name"] == "app.enveliq"
    assert doc[0]["target"]["sha256_cert_fingerprints"] == [FP]
    assert len(m.relying_party.extra_origins) == 1 and m.relying_party.extra_origins[0].startswith("android:apk-key-hash:")
