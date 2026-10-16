"""The password and vault key settings that production uses stay strong.

Every other test runs with cheap settings (see tests/conftest.py) so the suite is fast. These tests run with the real ones.
"""
from __future__ import annotations

import pytest

from backend import crypto_vault
from backend.auth import passwords

pytestmark = pytest.mark.real_kdf


def test_the_vault_key_settings_are_at_full_strength():
    p = crypto_vault.SecureVault.default_kdf_params()
    assert p["name"] == "argon2id"
    assert p["time_cost"] >= 3 and p["memory_kib"] >= 64 * 1024 and p["parallelism"] >= 4 and p["hash_len"] >= 32


def test_the_password_settings_are_at_full_strength():
    assert passwords.TIME_COST >= 2 and passwords.MEMORY_KIB >= 19 * 1024 and passwords.LANES >= 1 and passwords.HASH_LEN >= 32
    stored = passwords.hash_password("a long enough passphrase")
    assert stored["alg"] == "argon2id" and stored["t"] >= 2 and stored["m"] >= 19 * 1024


def test_a_password_made_at_full_strength_checks_out_and_a_wrong_one_does_not():
    stored = passwords.hash_password("a long enough passphrase")
    assert passwords.verify_password("a long enough passphrase", stored) is True
    assert passwords.verify_password("a different passphrase!", stored) is False
    assert passwords.needs_rehash(stored) is False


def test_a_hash_made_with_other_settings_is_still_accepted_and_marked_for_an_upgrade():
    cheap = {"alg": "argon2id", "t": 1, "m": 64, "p": 1}
    import base64, secrets
    salt = secrets.token_bytes(16)
    digest = passwords._derive("a long enough passphrase", salt, 1, 64, 1, 32)
    stored = {**cheap, "salt": base64.b64encode(salt).decode(), "hash": base64.b64encode(digest).decode()}
    assert passwords.verify_password("a long enough passphrase", stored) is True
    assert passwords.needs_rehash(stored) is True


def test_a_vault_made_at_full_strength_unlocks_with_its_passphrase(tmp_path):
    key = crypto_vault.SecureVault._derive_kek("a long enough passphrase", b"\x01" * 16)
    again = crypto_vault.SecureVault._derive_kek("a long enough passphrase", b"\x01" * 16)
    other = crypto_vault.SecureVault._derive_kek("a different passphrase!", b"\x01" * 16)
    assert key == again and key != other and len(key) == 32
