"""Browser check for the setup guide (/welcome) against a fake Proton Bridge and a fake AI model.

Starts a throwaway Enveliq server, a fake Bridge and a tiny model server, signs in
over HTTP, then runs scripts/check_welcome_e2e.mjs in Chromium with that session.
Usage: python3 scripts/welcome_e2e.py   (needs requirements-dev.txt and playwright)
"""
import json, os, subprocess, sys, tempfile, threading, time, pathlib
from http.server import BaseHTTPRequestHandler, HTTPServer
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests")); sys.path.insert(0, str(ROOT))
import httpx
from fake_bridge import FakeBridge, raw_email
from backend.auth import totp

GOOD = {"summary": "Dentist appointment on Friday at 2:30 PM.", "category": "Personal", "priority": "high",
        "action_required": True, "task": {"title": "Arrive 10 minutes early", "due": "Fri 9 Oct", "detail": "Bring the health fund card."}}


class Model(BaseHTTPRequestHandler):
    def do_POST(self):
        self.rfile.read(int(self.headers["Content-Length"]))
        payload = json.dumps({"choices": [{"message": {"role": "assistant", "content": json.dumps(GOOD)}}]}).encode()
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(payload))); self.end_headers(); self.wfile.write(payload)

    def log_message(self, *a):
        pass


model = HTTPServer(("127.0.0.1", 0), Model)
threading.Thread(target=model.serve_forever, daemon=True).start()
tmp = pathlib.Path(tempfile.mkdtemp())
bridge = FakeBridge(tmp)
for uid, subject, sender in ((1, "Quarterly update", "Alice Example <alice@example.invalid>"), (2, "Weekly news", "News <news@example.invalid>"), (3, "Invoice question", "Bob <bob@example.invalid>")):
    bridge.add(uid, raw_email(subject, sender, "me@example.invalid", message_id=f"<m{uid}@example.invalid>", body="Hello.\n"))
# A Sent folder: one email from yesterday and one from a month ago (only the first may be listed)
from email.utils import format_datetime
from datetime import datetime, timedelta, timezone
bridge.folders.append(("\\HasNoChildren \\Sent", "Sent"))
for uid, subject, days in ((501, "Recent sent mail", 1), (502, "Old sent mail", 30)):
    when = format_datetime(datetime.now(timezone.utc) - timedelta(days=days))
    bridge.add(uid, f"From: me@example.invalid\r\nTo: Zed <zed@example.invalid>\r\nSubject: {subject}\r\nDate: {when}\r\nMessage-ID: <s{uid}@example.invalid>\r\n\r\nSent body text\r\n".encode(), folder="Sent")
env = dict(os.environ, ENVELIQ_DATA_DIR=str(tmp / "data"), ENVELIQ_SETUP_CODE="e2e-setup-code-12345", ENVELIQ_PORT="8797", ENVELIQ_SYNC_MINUTES="0",
           ENVELIQ_PUBLIC_URL="http://localhost:8797", ENVELIQ_BRIDGE_CA_FILE=str(bridge.cert_path), ENVELIQ_MAIL_CA_FILE=str(bridge.cert_path), ENVELIQ_MAIL_ALLOWED_HOSTS="127.0.0.1",
           PYTHONPATH=os.pathsep.join([str(ROOT), os.environ.get("PYTHONPATH", "")]))
env.pop("ENVELIQ_LLM_URL", None); env.pop("ENVELIQ_LLM_MODEL", None)
server = subprocess.Popen([sys.executable, "run.py"], cwd=ROOT, env=env, stdout=open(tmp / "server.log", "w"), stderr=subprocess.STDOUT)
try:
    for _ in range(60):
        try:
            if httpx.get("http://localhost:8797/api/v1/health").status_code == 200: break
        except Exception: time.sleep(0.3)
    c = httpx.Client(base_url="http://localhost:8797", headers={"Origin": "http://localhost:8797"})
    r = c.post("/api/v1/setup", json={"setup_code": "e2e-setup-code-12345", "passphrase": "Correct Horse Battery Staple 2026!", "username": "morgan", "password": "Admin password for tests 2026"}); assert r.status_code == 201, r.text
    secret = c.post("/api/v1/auth/totp/setup").json()["secret"]
    r = c.post("/api/v1/auth/totp/confirm", json={"code": totp.code_at(secret, totp.current_step())}); assert r.status_code == 200, r.text
    cookies = [{"name": k, "value": v, "url": "http://localhost:8797"} for k, v in c.cookies.items()]
    json.dump({"cookies": cookies, "imap": bridge.imap_port, "smtp": bridge.smtp_port, "user": bridge.user, "pw": bridge.password,
               "model_url": f"http://127.0.0.1:{model.server_address[1]}/v1/chat/completions", "shot": os.environ.get("SHOT_DIR", "")}, open(tmp / "ctx.json", "w"))
    r = subprocess.run(["node", str(ROOT / "scripts" / "check_welcome_e2e.mjs"), str(tmp / "ctx.json")], cwd=ROOT)
    sent_ok = any("dana.newperson@example.invalid" in m["to"] for m in bridge.sent)
    if r.returncode == 0 and not sent_ok:
        print("✗ the new email never reached the pretend mail server")
    sys.exit(r.returncode if sent_ok or r.returncode else 1)
finally:
    server.terminate(); bridge.close(); model.shutdown()
    if os.environ.get("ENVELIQ_E2E_VERBOSE"):
        print(open(tmp / "server.log").read()[-1500:])
