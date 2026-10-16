from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


import pytest


def pytest_configure(config):
    config.addinivalue_line("markers", "real_kdf: use the real, full-strength password and vault key settings (every other test uses cheap ones)")


@pytest.fixture(autouse=True)
def cheap_key_derivation(request, monkeypatch):
    """Tests make hundreds of vaults and users, and each one runs Argon2id at full strength (64 MiB of memory, several rounds), which
    made the backend tests take about 13 minutes. Here the work is made tiny so tests stay fast. The format, the algorithm and the way
    the stored settings are read back are unchanged, and the settings are stored with each vault and password, so everything still
    round-trips. Tests marked real_kdf (see tests/test_kdf_strength.py) check the full-strength settings that production uses."""
    if request.node.get_closest_marker("real_kdf"):
        return
    monkeypatch.setattr("backend.crypto_vault.ARGON_TIME_COST", 1)
    monkeypatch.setattr("backend.crypto_vault.ARGON_MEMORY_COST_KIB", 64)
    monkeypatch.setattr("backend.crypto_vault.ARGON_PARALLELISM", 1)
    monkeypatch.setattr("backend.auth.passwords.TIME_COST", 1)
    monkeypatch.setattr("backend.auth.passwords.MEMORY_KIB", 64)
    monkeypatch.setattr("backend.auth.passwords.LANES", 1)


@pytest.fixture(autouse=True)
def no_real_update_check(monkeypatch):
    """No test ever asks GitHub whether a newer release is out."""
    from backend import update_check
    monkeypatch.setattr(update_check, "fetch_latest", lambda: None)



def pytest_terminal_summary(terminalreporter):
    """On GitHub, show each failing test and the end of its error as an annotation, so a failure can be read without opening the log."""
    import os
    if not os.environ.get("GITHUB_ACTIONS"):
        return
    for kind in ("failed", "error"):
        for report in terminalreporter.stats.get(kind, []):
            text = (getattr(report, "longreprtext", "") or "")[-900:].replace("%", "%25").replace("\r", "").replace("\n", "%0A")
            terminalreporter.write_line(f"::error title={report.nodeid}::{text}")
