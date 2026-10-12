from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


import pytest


@pytest.fixture(autouse=True)
def no_real_update_check(monkeypatch):
    """No test ever asks GitHub whether a newer release is out."""
    from backend import update_check
    monkeypatch.setattr(update_check, "fetch_latest", lambda: None)
