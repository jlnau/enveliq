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



def pytest_terminal_summary(terminalreporter):
    """On GitHub, show each failing test and the end of its error as an annotation, so a failure can be read without opening the log."""
    import os
    if not os.environ.get("GITHUB_ACTIONS"):
        return
    for kind in ("failed", "error"):
        for report in terminalreporter.stats.get(kind, []):
            text = (getattr(report, "longreprtext", "") or "")[-900:].replace("%", "%25").replace("\r", "").replace("\n", "%0A")
            terminalreporter.write_line(f"::error title={report.nodeid}::{text}")
