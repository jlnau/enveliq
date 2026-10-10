"""Build the hosted preview version of the UI prototype.

The preview host wraps published pages in its own <!doctype>/<html>/
<head>/<body> skeleton, so the published file must start at <title>/<style>
and contain only page content. This strips that outer wrapper from
prototype/index.html (the full standalone page kept in the repo).

Usage: python scripts/build_artifact.py [output_path]
Default output: build/enveliq.html (git-ignored)
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "prototype" / "index.html"


def build(src: str) -> str:
    head_start = src.index("<head>") + len("<head>")
    head_end = src.index("</head>")
    head = src[head_start:head_end]
    # Drop the meta tags the artifact skeleton already provides.
    head = re.sub(r"<meta[^>]*>\n?", "", head).lstrip("\n")
    body_start = src.index("<body>") + len("<body>")
    body_end = src.rindex("</body>")
    body = src[body_start:body_end].strip("\n")
    return head.rstrip("\n") + "\n" + body


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "build" / "enveliq.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build(SOURCE.read_text(encoding="utf-8")), encoding="utf-8")
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
