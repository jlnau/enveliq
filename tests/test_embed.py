"""The pop-ups on the inbox page reuse the standalone pages' code, served as one module."""
from __future__ import annotations

from helpers import load_app


def test_embed_script_is_the_two_page_files_and_the_inbox_policy_stays_tight(tmp_path):
    appm = load_app(tmp_path)
    from fastapi.testclient import TestClient
    client = TestClient(appm.app)
    r = client.get("/embed.js")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/javascript")
    assert "function welcomePage" in r.text and "function adminPage" in r.text and "window.EnveliqEmbed" in r.text
    assert "frame-ancestors 'none'" in r.headers["content-security-policy"] and r.headers["x-frame-options"] == "DENY"
    csp = appm.APP_CSP
    assert "script-src 'self' 'unsafe-inline'" in csp and "frame-ancestors 'none'" in csp
    assert "connect-src 'self'" in csp and "default-src 'none'" in csp
    assert "unsafe-eval" not in csp and "http" not in csp         # still no eval and no outside hosts
