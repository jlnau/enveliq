"""The PDF viewer container (render/server.py) and how the main program uses it."""
from __future__ import annotations

import base64
import importlib.util
import json
import os
import shutil
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from backend.mail import render

SAMPLE = (Path(__file__).parent / "sample.pdf").read_bytes()
PNG = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"0" * 30).decode()


def load_server():
    sys.modules["render"] = render                     # in the container the same file is installed as render.py
    spec = importlib.util.spec_from_file_location("render_server", Path(__file__).parent.parent / "render" / "server.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def serve(handler_cls):
    httpd = HTTPServer(("127.0.0.1", 0), handler_cls)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, f"http://127.0.0.1:{httpd.server_port}"


@pytest.fixture
def with_url(monkeypatch):
    def setter(url):
        monkeypatch.setenv("ENVELIQ_RENDER_URL", url)
    return setter


def fake(reply, status=200):
    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers.get("Content-Length", 0)))
            body = reply if isinstance(reply, bytes) else json.dumps(reply).encode()
            self.send_response(status)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass
    return H


@pytest.mark.skipif(not shutil.which("pdftocairo"), reason="poppler is not installed here")
def test_the_render_container_draws_pages_and_the_main_program_passes_them_on(with_url):
    httpd, url = serve(load_server().Handler)
    with_url(url)
    out = render.view(SAMPLE, "trip.pdf", "application/pdf")
    assert out["kind"] == "pdf" and out["total"] == 2 and out["shown"] == 2
    assert base64.b64decode(out["pages"][0]).startswith(b"\x89PNG")
    assert render.view(b"%PDF-1.4 not a real file", "x.pdf", "application/pdf")["kind"] == "none"
    httpd.shutdown()


def test_the_render_container_refuses_oversized_and_unknown_requests():
    import urllib.error
    import urllib.request
    httpd, url = serve(load_server().Handler)
    try:
        urllib.request.urlopen(urllib.request.Request(url + "/render", data=b"x" * (render.MAX_PDF_BYTES + 1), method="POST"), timeout=10)
        raise AssertionError("expected a refusal")
    except urllib.error.HTTPError as err:
        assert err.code == 413
    except (urllib.error.URLError, ConnectionError, OSError):
        pass                                           # the server may close the connection first; that is a refusal too
    try:
        urllib.request.urlopen(url + "/other", timeout=10)
    except urllib.error.HTTPError as err:
        assert err.code == 404
    assert json.load(urllib.request.urlopen(url + "/health", timeout=10))["ok"] is True
    httpd.shutdown()


@pytest.mark.parametrize("reply", [
    b"not json",
    {"kind": "pdf", "pages": ["!!!not base64!!!"], "total": 1},
    {"kind": "pdf", "pages": [base64.b64encode(b"<script>alert(1)</script>").decode()], "total": 1},      # not a picture
    {"kind": "pdf", "pages": [PNG] * 21, "total": 21},                                                    # more pages than allowed
    {"kind": "pdf", "pages": [], "total": 0},
    {"kind": "pdf", "pages": PNG, "total": 1},                                                            # wrong shape
    {"kind": "html", "pages": [PNG], "total": 1},
])
def test_nothing_the_render_container_says_is_trusted(with_url, reply):
    httpd, url = serve(fake(reply))
    with_url(url)
    out = render.view(SAMPLE, "x.pdf", "application/pdf")
    assert out["kind"] == "none" and "could not be used" in out["reason"]
    httpd.shutdown()


def test_a_good_reply_is_passed_on_and_the_reason_of_a_refusal_is_kept(with_url):
    httpd, url = serve(fake({"kind": "pdf", "pages": [PNG, PNG], "total": 5}))
    with_url(url)
    assert render.view(SAMPLE, "x.pdf", "application/pdf") == {"kind": "pdf", "pages": [PNG, PNG], "total": 5, "shown": 2}
    httpd.shutdown()
    httpd, url = serve(fake({"kind": "none", "reason": "This PDF is password protected."}))
    with_url(url)
    assert render.view(SAMPLE, "x.pdf", "application/pdf") == {"kind": "none", "reason": "This PDF is password protected."}
    httpd.shutdown()


def test_an_unreachable_render_container_gives_a_plain_message(with_url):
    with_url("http://127.0.0.1:9")
    out = render.view(SAMPLE, "x.pdf", "application/pdf")
    assert out["kind"] == "none" and "could not be reached" in out["reason"]


def test_without_a_render_container_or_poppler_the_message_says_what_is_missing(monkeypatch):
    monkeypatch.delenv("ENVELIQ_RENDER_URL", raising=False)
    monkeypatch.setattr(render, "pdf_tools_available", lambda: False)
    out = render.view(SAMPLE, "x.pdf", "application/pdf")
    assert out["kind"] == "none" and "not set up" in out["reason"]


def test_the_compose_file_keeps_the_viewer_locked_down():
    text = (Path(__file__).parent.parent / "docker-compose.yml").read_text()
    block = text[text.index("\n  enveliq-render:"):text.index("\nnetworks:")]
    for needed in ("networks: [render]", "read_only: true", "cap_drop: [ALL]", "no-new-privileges:true", 'user: "10002:10002"'):
        assert needed in block, needed
    assert "ports:" not in block and "volumes:" not in block and "environment:" not in block      # nothing published, no data, no secrets
    net = text[text.index("\n  render:\n"):text.index("\nvolumes:")]
    assert "internal: true" in net
    main = text[text.index("\n  enveliq:"):text.index("\n  enveliq-render:")]
    assert "networks: [enveliq, render]" in main and "ENVELIQ_RENDER_URL: http://enveliq-render:8766" in main


def test_the_main_image_has_no_pdf_parser():
    root = Path(__file__).parent.parent
    assert "poppler" not in (root / "Dockerfile").read_text()
    assert "poppler-utils" in (root / "Dockerfile.render").read_text()


def test_pages_are_drawn_large_enough_for_a_big_window_but_every_limit_still_holds():
    # The viewer window follows the size of the browser, so pages are drawn at up to 1500 pixels on the long side
    # (they used to be 1000). Nothing that bounds the work or the answer may have been loosened with it.
    assert render.PAGE_LONG_SIDE == 1500
    assert render.MAX_PAGES == 20
    assert render.MAX_PAGE_PNG == 3 * 1024 * 1024
    assert render.MAX_TOTAL_PNG == 24 * 1024 * 1024
    assert render.WALL_SECONDS == 20 and render.CPU_SECONDS == 15 and render.MEMORY_BYTES == 1024 * 1024 * 1024
