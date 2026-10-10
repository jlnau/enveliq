"""Browser check for the Mailboxes page against a fake Proton Bridge.

Starts a throwaway Enveliq server and a fake Bridge, signs in over HTTP, then
runs scripts/check_mailbox_e2e.mjs in Chromium with that session.
Usage: python3 scripts/mailbox_e2e.py   (needs requirements-dev.txt and playwright)
"""
import json, os, subprocess, sys, tempfile, time, pathlib
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests")); sys.path.insert(0, str(ROOT))
import httpx
from fake_bridge import FakeBridge, raw_email
from backend.auth import totp

tmp = pathlib.Path(tempfile.mkdtemp())
bridge = FakeBridge(tmp)
hostile = '<img src=x onerror="window.__pwned=1"><script>window.__pwned=1</script>'
bridge.add(1, raw_email("Quarterly update", "Alice Example <alice@example.invalid>", "me@example.invalid", message_id="<a1@example.invalid>", body="Numbers are attached.\n"))
bridge.add(2, raw_email("Weekly news", "News <news_at_example_invalid_k3j9@simplelogin.co>", "me@example.invalid", reply_to="news_at_example_invalid_k3j9@simplelogin.co", message_id="<n2@example.invalid>"))
bridge.add(3, raw_email(hostile, f'"{hostile}" <evil@example.invalid>', "me@example.invalid", message_id="<h3@example.invalid>", body=hostile + "\n"))
env = dict(os.environ, ENVELIQ_DATA_DIR=str(tmp / "data"), ENVELIQ_SETUP_CODE="e2e-setup-code-12345", ENVELIQ_PORT="8798", ENVELIQ_SYNC_MINUTES="0",
           ENVELIQ_PUBLIC_URL="http://localhost:8798", ENVELIQ_BRIDGE_CA_FILE=str(bridge.cert_path),
           PYTHONPATH=os.pathsep.join([str(ROOT), os.environ.get("PYTHONPATH", "")]))
server = subprocess.Popen([sys.executable, "run.py"], cwd=ROOT, env=env, stdout=open(tmp / "server.log", "w"), stderr=subprocess.STDOUT)
try:
    for _ in range(60):
        try:
            if httpx.get("http://localhost:8798/api/v1/health").status_code == 200: break
        except Exception: time.sleep(0.3)
    c = httpx.Client(base_url="http://localhost:8798", headers={"Origin": "http://localhost:8798"})
    r = c.post("/api/v1/setup", json={"setup_code": "e2e-setup-code-12345", "passphrase": "Correct Horse Battery Staple 2026!", "username": "jules", "password": "Admin password for tests 2026"}); assert r.status_code == 201, r.text
    secret = c.post("/api/v1/auth/totp/setup").json()["secret"]
    r = c.post("/api/v1/auth/totp/confirm", json={"code": totp.code_at(secret, totp.current_step())}); assert r.status_code == 200, r.text
    cookies = [{"name": k, "value": v, "url": "http://localhost:8798"} for k, v in c.cookies.items()]
    json.dump({"cookies": cookies, "imap": bridge.imap_port, "smtp": bridge.smtp_port, "user": bridge.user, "pw": bridge.password, "out": str(tmp)}, open(tmp / "ctx.json", "w"))
    r = subprocess.run(["node", str(ROOT / "scripts" / "check_mailbox_e2e.mjs"), str(tmp / "ctx.json")], cwd=ROOT)
    ok = r.returncode == 0
    sent = [(m["from"], m["to"]) for m in bridge.sent]
    for label, good in (("reply went to the reverse-alias address from the mailbox", sent == [("me@example.invalid", ["news_at_example_invalid_k3j9@simplelogin.co"])]),
                        ("archived email moved on the server", bridge.in_folder("Archive") == [1] and 1 not in bridge.in_folder("INBOX"))):
        print(("✓ " if good else "✗ ") + label); ok = ok and good
    sys.exit(0 if ok else 1)
finally:
    server.terminate(); bridge.close()
    if os.environ.get("ENVELIQ_E2E_VERBOSE"):
        print(open(tmp / "server.log").read()[-1500:])
