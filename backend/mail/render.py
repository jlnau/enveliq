"""Viewing attachments in the page without handing the file itself to the browser.

PDFs are never sent to the browser. They are drawn as page pictures by poppler (`pdfinfo`, `pdftocairo`).
In the Docker setup that happens in a separate locked-down container (`enveliq-render`: no network, no
access to the data folder or keys, read-only, all capabilities dropped) which this server calls over a
private internal network (ENVELIQ_RENDER_URL); the main container then has no PDF parser at all. When that
address is not set, the same drawing code runs here in a short-lived child process with CPU, memory, file,
output and time limits (for development and for people not using the compose file).

Either way poppler reads the file from a pipe and writes page pictures to a pipe, so nothing touches the
disk, and whatever comes back from the render container is checked again before it is passed on.

Text, CSV and similar files are decoded here and sent as plain text for the page to show with
`textContent`; they are never sent as HTML.

Other types (Word, Excel, scripts, archives, HTML) are never opened.
"""
from __future__ import annotations

import base64
import csv
import io
import os
import re
import shutil
import subprocess
import sys
import json
import threading
import urllib.request
from typing import Any

MAX_PDF_BYTES = 10 * 1024 * 1024
MAX_PAGES = 20
PAGE_LONG_SIDE = 1000          # pixels; bounds the size of any one picture whatever the page size says
MAX_PAGE_PNG = 3 * 1024 * 1024
MAX_TOTAL_PNG = 24 * 1024 * 1024
WALL_SECONDS = 20
CPU_SECONDS = 15
MEMORY_BYTES = 1024 * 1024 * 1024
MAX_TEXT_BYTES = 200 * 1024
MAX_TABLE_ROWS = 200
MAX_TABLE_COLS = 20
MAX_CELL = 200

TEXT_TYPES = {"text/plain", "text/csv", "text/tab-separated-values", "text/markdown", "application/json", "text/x-log"}
TEXT_EXTENSIONS = {".txt": "text/plain", ".log": "text/plain", ".md": "text/markdown", ".json": "application/json",
                   ".csv": "text/csv", ".tsv": "text/tab-separated-values"}

_slots = threading.BoundedSemaphore(2)      # at most two PDFs being drawn at once on the whole server
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def render_url() -> str:
    return os.environ.get("ENVELIQ_RENDER_URL", "").strip().rstrip("/")


def pdf_tools_available() -> bool:
    return bool(shutil.which("pdfinfo") and shutil.which("pdftocairo"))


def kind_of(name: str, ctype: str, data: bytes) -> str:
    """'pdf', 'text', 'csv' or 'none' (cannot be shown here)."""
    ext = os.path.splitext(name.lower())[1]
    if ctype == "application/pdf" or (ext == ".pdf" and ctype in ("application/octet-stream", "application/pdf")):
        return "pdf" if data[:1024].lstrip(b"\x00 \t\r\n").startswith(b"%PDF-") or b"%PDF-" in data[:1024] else "none"
    guess = ctype if ctype in TEXT_TYPES else TEXT_EXTENSIONS.get(ext) if ctype in ("application/octet-stream", "text/plain") else None
    if guess is None:
        return "none"
    return "csv" if guess in ("text/csv", "text/tab-separated-values") else "text"


def can_view(name: str, ctype: str) -> bool:
    """For the attachment list: the kinds the viewer might open (decided again when the bytes are known)."""
    ext = os.path.splitext(name.lower())[1]
    return ctype == "application/pdf" or ctype in TEXT_TYPES or (ext in TEXT_EXTENSIONS and ctype in ("application/octet-stream", "text/plain")) \
        or (ext == ".pdf" and ctype == "application/octet-stream")


# The limits are applied by a tiny launcher that then replaces itself with the poppler tool. This avoids running
# Python code between fork and exec inside the busy server process.
_LAUNCHER = """
import os, resource, sys
cpu, mem, tool = int(sys.argv[1]), int(sys.argv[2]), sys.argv[3]
resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu))
resource.setrlimit(resource.RLIMIT_AS, (mem, mem))
resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))
resource.setrlimit(resource.RLIMIT_NOFILE, (32, 32))
resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
try:
    os.unshare(os.CLONE_NEWUSER | os.CLONE_NEWNET)
except Exception:
    pass
os.execv(tool, [tool] + sys.argv[4:])
"""


def _run(args: list[str], data: bytes, out_limit: int) -> bytes:
    tool = shutil.which(args[0], path="/usr/bin:/bin:/usr/local/bin")
    if tool is None:
        raise ValueError("tool missing")
    cmd = [sys.executable, "-I", "-S", "-c", _LAUNCHER, str(CPU_SECONDS), str(MEMORY_BYTES), tool, *args[1:]]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env={"LANG": "C"}, cwd="/", close_fds=True)
    try:
        out, _ = proc.communicate(data, timeout=WALL_SECONDS)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.communicate()
        raise TimeoutError("took too long") from None
    except Exception:
        proc.kill()
        raise
    if proc.returncode != 0 or len(out) > out_limit:
        raise ValueError("could not be read")
    return out


def render_pdf(data: bytes) -> dict[str, Any]:
    """Page pictures (PNG, base64) of the first pages, or {'kind': 'none', 'reason': ...}."""
    if len(data) > MAX_PDF_BYTES:
        return {"kind": "none", "reason": "This PDF is larger than 10 MB, so it cannot be shown here."}
    url = render_url()
    if url:
        return _remote_pdf(data, url)
    return draw_pdf_here(data)


def _remote_pdf(data: bytes, url: str) -> dict[str, Any]:
    """Ask the render container. Nothing it says is trusted: the answer is checked before it goes to the browser."""
    if not _slots.acquire(timeout=WALL_SECONDS):
        return {"kind": "none", "reason": "The server is busy drawing other PDFs. Try again in a moment."}
    try:
        request = urllib.request.Request(url + "/render", data=data, method="POST", headers={"Content-Type": "application/pdf"})
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))          # never through a proxy
        try:
            with opener.open(request, timeout=WALL_SECONDS + 15) as reply:
                raw = reply.read(MAX_TOTAL_PNG * 2 + 1024 * 1024)
        except Exception:
            return {"kind": "none", "reason": "The PDF viewer service could not be reached."}
    finally:
        _slots.release()
    try:
        out = json.loads(raw)
        if out.get("kind") == "none":
            return {"kind": "none", "reason": str(out.get("reason") or "This PDF could not be shown.")[:200]}
        pages = out["pages"]
        total = int(out["total"])
        if out.get("kind") != "pdf" or not isinstance(pages, list) or not 1 <= len(pages) <= MAX_PAGES or not 1 <= total <= 100_000:
            raise ValueError("shape")
        used = 0
        for page in pages:
            png = base64.b64decode(page, validate=True)
            if not png.startswith(b"\x89PNG\r\n\x1a\n") or len(png) > MAX_PAGE_PNG:
                raise ValueError("picture")
            used += len(png)
        if used > MAX_TOTAL_PNG:
            raise ValueError("size")
        return {"kind": "pdf", "pages": pages, "total": max(total, len(pages)), "shown": len(pages)}
    except Exception:
        return {"kind": "none", "reason": "The PDF viewer service gave an answer that could not be used."}


def draw_pdf_here(data: bytes) -> dict[str, Any]:
    """Draw the PDF in a limited child process of this program. This is what the render container runs."""
    if len(data) > MAX_PDF_BYTES:
        return {"kind": "none", "reason": "This PDF is larger than 10 MB, so it cannot be shown here."}
    if not pdf_tools_available():
        return {"kind": "none", "reason": "PDF viewing is not set up on this server (the PDF viewer container is missing)."}
    if not _slots.acquire(timeout=WALL_SECONDS):
        return {"kind": "none", "reason": "The server is busy drawing other PDFs. Try again in a moment."}
    try:
        try:
            info = _run(["pdfinfo", "-"], data, 64 * 1024).decode("utf-8", "replace")
        except TimeoutError:
            return {"kind": "none", "reason": "This PDF took too long to read."}
        except Exception:
            return {"kind": "none", "reason": "This PDF could not be read."}
        if re.search(r"^Encrypted:\s+yes", info, re.M):
            return {"kind": "none", "reason": "This PDF is password protected."}
        m = re.search(r"^Pages:\s+(\d+)", info, re.M)
        total = int(m.group(1)) if m else 0
        if total < 1:
            return {"kind": "none", "reason": "This PDF has no pages to show."}
        pages: list[str] = []
        used = 0
        for n in range(1, min(total, MAX_PAGES) + 1):
            try:
                png = _run(["pdftocairo", "-png", "-scale-to", str(PAGE_LONG_SIDE), "-f", str(n), "-l", str(n), "-singlefile", "-", "-"], data, MAX_PAGE_PNG)
            except TimeoutError:
                break
            except Exception:
                break
            if not png.startswith(b"\x89PNG"):
                break
            used += len(png)
            if used > MAX_TOTAL_PNG:
                break
            pages.append(base64.b64encode(png).decode("ascii"))
        if not pages:
            return {"kind": "none", "reason": "This PDF could not be drawn."}
        return {"kind": "pdf", "pages": pages, "total": total, "shown": len(pages)}
    finally:
        _slots.release()


def _plain(text: str) -> str:
    return _CONTROL.sub("", text)


def render_text(data: bytes, kind: str, ctype: str, name: str) -> dict[str, Any]:
    cut = len(data) > MAX_TEXT_BYTES
    text = _plain(data[:MAX_TEXT_BYTES].decode("utf-8", "replace"))
    if kind == "csv":
        delim = "\t" if ctype == "text/tab-separated-values" or name.lower().endswith(".tsv") else ","
        rows: list[list[str]] = []
        try:
            for row in csv.reader(io.StringIO(text), delimiter=delim):
                rows.append([c[:MAX_CELL] for c in row[:MAX_TABLE_COLS]])
                if len(rows) >= MAX_TABLE_ROWS:
                    cut = True
                    break
        except Exception:
            rows = []
        if rows:
            return {"kind": "csv", "rows": rows, "truncated": cut}
    return {"kind": "text", "text": text, "truncated": cut}


def view(data: bytes, name: str, ctype: str) -> dict[str, Any]:
    kind = kind_of(name, ctype, data)
    if kind == "pdf":
        return render_pdf(data)
    if kind in ("text", "csv"):
        return render_text(data, kind, ctype, name)
    return {"kind": "none", "reason": "This kind of file cannot be shown here. Use Save to my device."}
