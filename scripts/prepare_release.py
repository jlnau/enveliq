#!/usr/bin/env python3
"""Prepare release metadata together before creating a GitHub release.

Usage: python3 scripts/prepare_release.py 0.82
Run on a new branch based on main, review the diff, and merge the PR before tagging.
"""
from __future__ import annotations

import argparse
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
VERSION = ROOT / "backend/version.py"
README = ROOT / "README.md"
CHANGELOG = ROOT / "docs/CHANGELOG.md"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("version", help="New version, e.g. 0.82 or v0.82")
    parser.add_argument("--date", help="Release date YYYY-MM-DD (default: today)")
    args = parser.parse_args()
    from datetime import date
    version = args.version.removeprefix("v")
    if not re.fullmatch(r"\d+\.\d+(?:\.\d+)?", version):
        parser.error("version must look like 0.82")
    release_date = args.date or date.today().isoformat()
    try:
        date.fromisoformat(release_date)
    except ValueError:
        parser.error("date must be YYYY-MM-DD")

    ver = VERSION.read_text(encoding="utf-8")
    readme = README.read_text(encoding="utf-8")
    changelog = CHANGELOG.read_text(encoding="utf-8")
    match = re.search(r'^VERSION = "([0-9.]+)"$', ver, re.M)
    current = match.group(1) if match else None
    if current is None:
        parser.error("backend/version.py has no expected VERSION assignment")
    if current == version:
        parser.error("version is already set; nothing to prepare")
    if f"Current version: **v{current}**" not in readme:
        parser.error("README current version does not match backend/version.py")
    marker = f"## v{version}"
    if re.search(rf"^{re.escape(marker)}(?:\s|$)", changelog, re.M):
        parser.error("this version already has a changelog section")
    header = "## Unreleased\n"
    if changelog.count(header) != 1:
        parser.error("expected one Unreleased changelog section")
    start = changelog.index(header) + len(header)
    next_release = re.search(r"^## v\d", changelog[start:], re.M)
    if not next_release:
        parser.error("no existing released version section found")
    end = start + next_release.start()
    notes = changelog[start:end].strip()
    if not notes or notes == "No changes recorded yet.":
        parser.error("Unreleased section has no release notes")
    new_version = ver.replace(f'VERSION = "{current}"', f'VERSION = "{version}"', 1)
    new_readme = readme.replace(f"Current version: **v{current}**", f"Current version: **v{version}**", 1)
    new_changelog = (changelog[:start] + "\nNo changes recorded yet.\n\n" +
                     f"## v{version} ({release_date})\n\n" + notes + "\n\n" +
                     changelog[end:])
    for path, content in ((VERSION, new_version), (README, new_readme),
                          (CHANGELOG, new_changelog)):
        path.write_text(content, encoding="utf-8")
        print(f"Updated {path.relative_to(ROOT)}")
    print("Review and merge a PR before creating the matching release tag.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
