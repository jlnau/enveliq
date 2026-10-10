"""The PDF viewer container: draws PDF pages as pictures, nothing else.

It listens only on the private internal network of the compose file, has no way out to the internet or
to the main container's data, and uses nothing but the Python standard library plus poppler.
POST /render with the PDF as the request body; the answer is JSON (page pictures, or a plain reason).
"""
from __future__ import annotations

import json
import os
import socketserver
from http.server import BaseHTTPRequestHandler, HTTPServer

import render

MAX_BODY = render.MAX_PDF_BYTES


class Handler(BaseHTTPRequestHandler):
    server_version = "enveliq-render"
    sys_version = ""
    timeout = 30                      # a client that stalls is dropped

    def log_message(self, *_args) -> None:        # no request logging: nothing about the files is written anywhere
        pass

    def _send(self, status: int, body: dict) -> None:
        data = json.dumps(body, separators=(",", ":")).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        if self.path == "/health":
            self._send(200, {"ok": True, "poppler": render.pdf_tools_available()})
        else:
            self._send(404, {"detail": "not found"})

    def do_POST(self) -> None:
        if self.path != "/render":
            return self._send(404, {"detail": "not found"})
        try:
            length = int(self.headers.get("Content-Length", ""))
        except ValueError:
            return self._send(411, {"detail": "length required"})
        if not 0 < length <= MAX_BODY:
            return self._send(413, {"kind": "none", "reason": "This PDF is larger than 10 MB, so it cannot be shown here."})
        data = self.rfile.read(length)
        if len(data) != length:
            return self._send(400, {"detail": "short body"})
        self._send(200, render.draw_pdf_here(data))


class Server(socketserver.ThreadingMixIn, HTTPServer):
    daemon_threads = True
    request_queue_size = 8


if __name__ == "__main__":
    port = int(os.environ.get("ENVELIQ_RENDER_PORT", "8766"))
    Server(("0.0.0.0", port), Handler).serve_forever()
