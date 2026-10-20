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


def test_link_file_is_not_found_when_no_fingerprint_is_known(tmp_path, monkeypatch):
    from backend.auth import passkeys
    monkeypatch.setattr(passkeys, "OFFICIAL_ANDROID_CERT", "")
    m = load_app(tmp_path)
    c = TestClient(m.app, raise_server_exceptions=False)
    assert c.get("/.well-known/assetlinks.json").status_code == 404
    assert m.relying_party.extra_origins == ()


def test_the_official_apps_key_is_built_in_and_works_with_no_setting(tmp_path, monkeypatch):
    from backend.auth import passkeys
    monkeypatch.setattr(passkeys, "OFFICIAL_ANDROID_CERT", FP)
    m = load_app(tmp_path)
    c = TestClient(m.app, raise_server_exceptions=False)
    r = c.get("/.well-known/assetlinks.json")
    assert r.status_code == 200
    assert r.json()[0]["target"]["sha256_cert_fingerprints"] == [FP]
    assert m.relying_party.extra_origins == (passkeys.android_origin(FP),)


def test_the_built_in_fingerprint_is_a_real_one():
    from backend.auth import passkeys
    assert len(passkeys.parse_cert_fingerprints(passkeys.OFFICIAL_ANDROID_CERT)) == 1


def test_the_setting_adds_another_key_next_to_the_built_in_one(tmp_path, monkeypatch):
    from backend.auth import passkeys
    other = ":".join(["11"] * 32)
    monkeypatch.setattr(passkeys, "OFFICIAL_ANDROID_CERT", FP)
    m = load_app(tmp_path, ENVELIQ_ANDROID_CERT_SHA256=other)
    c = TestClient(m.app, raise_server_exceptions=False)
    doc = c.get("/.well-known/assetlinks.json").json()
    assert doc[0]["target"]["sha256_cert_fingerprints"] == [FP, other]
    assert doc[0]["relation"] == ["delegate_permission/common.get_login_creds"]
    assert doc[0]["target"]["package_name"] == "app.enveliq"
    assert len(m.relying_party.extra_origins) == 2 and all(o.startswith("android:apk-key-hash:") for o in m.relying_party.extra_origins)
