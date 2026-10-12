"""The settings reference lists every ENVELIQ_ setting the program reads, so a new one cannot be forgotten."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_every_setting_the_code_reads_is_in_the_settings_reference():
    used = set()
    for path in list((ROOT / "backend").rglob("*.py")) + [ROOT / "Dockerfile"]:
        used |= set(re.findall(r"ENVELIQ_[A-Z_]+", path.read_text(encoding="utf-8")))
    documented = set(re.findall(r"ENVELIQ_[A-Z_]+", (ROOT / "docs" / "ENVIRONMENT.md").read_text(encoding="utf-8")))
    assert not used - documented, f"add these to docs/ENVIRONMENT.md: {sorted(used - documented)}"
