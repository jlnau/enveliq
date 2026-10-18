"""A small fake Proton Mail Bridge: IMAP and SMTP over STARTTLS with a
self-signed certificate, enough to exercise the real client code."""
from __future__ import annotations

import base64
import datetime
import ipaddress
import re
import socket
import socketserver
import ssl
import threading
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID


def make_cert(directory: Path, name: str = "bridge") -> tuple[Path, Path]:
    key = ec.generate_private_key(ec.SECP256R1())
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "127.0.0.1")])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject).issuer_name(subject).public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1)).not_valid_after(now + datetime.timedelta(days=365))
        .add_extension(x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]), critical=False)
        .sign(key, hashes.SHA256())
    )
    cert_path, key_path = directory / f"{name}.crt", directory / f"{name}.key"
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    return cert_path, key_path


def raw_email(subject: str, sender: str, to: str, *, reply_to: str | None = None, delivered_to: str | None = None,
              message_id: str, body: str = "Hello there.\n", extra: str = "", references: str | None = None) -> bytes:
    lines = [f"From: {sender}", f"To: {to}", f"Subject: {subject}", "Date: Wed, 07 Oct 2026 09:00:00 +1100",
             f"Message-ID: {message_id}"]
    if reply_to:
        lines.append(f"Reply-To: {reply_to}")
    if delivered_to:
        lines.append(f"Delivered-To: {delivered_to}")
    if references:
        lines.append(f"References: {references}")
    head = "\r\n".join(lines) + "\r\n"
    return (head + extra + "\r\n" + body.replace("\n", "\r\n")).encode()


class FakeBridge:
    def __init__(self, directory: Path, *, user="bridge-user", password="bridge-pass-123", cert_name="bridge",
                 starttls=True, move=True, report_size: int | None = None, implicit_tls=False, folders=None,
                 alert_password: str | None = None, smtp_implicit: bool | None = None):
        self.user, self.password = user, password
        self.cert_path, key_path = make_cert(directory, cert_name)
        self._ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        self._ctx.load_cert_chain(self.cert_path, key_path)
        self.starttls, self.move_supported, self.report_size = starttls, move, report_size
        self.implicit_tls = implicit_tls                  # TLS from the first byte, like port 993 / 465
        self.smtp_implicit = implicit_tls if smtp_implicit is None else smtp_implicit
        self.oauth_tokens: set[str] = set()               # access tokens accepted by AUTHENTICATE / AUTH XOAUTH2
        self.alert_password = alert_password              # a password the server answers with "application-specific password required"
        # LIST answer: (flags, name) pairs, as a real service would report its folders
        self.folders = folders if folders is not None else [("\\HasNoChildren", "INBOX"), ("\\HasNoChildren \\Archive", "Archive"), ("\\HasNoChildren \\Trash", "Trash")]
        self.uidvalidity = 7
        self.messages: dict[int, dict] = {}          # uid -> {raw, flags, folder}
        self.log: list[str] = []                     # IMAP commands received (passwords redacted)
        self.smtp_log: list[str] = []
        self.sent: list[dict] = []
        self.smtp_reject = False
        self.lock = threading.Lock()
        self.imap_port = self._serve(self._imap_handler(), self.implicit_tls)
        self.smtp_port = self._serve(self._smtp_handler(), self.smtp_implicit)

    def _xoauth_ok(self, blob: bytes) -> bool:
        try:
            fields = dict(p.split("=", 1) for p in blob.decode().split("\x01") if "=" in p)
        except Exception:
            return False
        return fields.get("user") == self.user and fields.get("auth", "").startswith("Bearer ") and fields["auth"][7:] in self.oauth_tokens

    def add(self, uid: int, raw: bytes, folder="INBOX") -> None:
        self.messages[uid] = {"raw": raw, "flags": set(), "folder": folder}

    def in_folder(self, folder: str) -> list[int]:
        return sorted(u for u, m in self.messages.items() if m["folder"] == folder)

    # ---------- plumbing ----------

    def _serve(self, handler, implicit):
        ctx = self._ctx

        class Server(socketserver.ThreadingTCPServer):
            def get_request(self):
                sock, addr = super().get_request()
                if implicit:
                    try:
                        sock = ctx.wrap_socket(sock, server_side=True)
                    except (ssl.SSLError, OSError):
                        sock.close()
                        raise OSError("tls handshake failed")
                return sock, addr

        server = Server(("127.0.0.1", 0), handler)
        server.daemon_threads = True
        threading.Thread(target=server.serve_forever, daemon=True).start()
        if not hasattr(self, "_servers"):
            self._servers = []
        self._servers.append(server)
        return server.server_address[1]

    def close(self) -> None:
        for s in self._servers:
            s.shutdown()
            s.server_close()

    # ---------- IMAP ----------

    def _imap_handler(self):
        bridge = self

        class H(socketserver.StreamRequestHandler):
            def handle(self):
                tls = bridge.implicit_tls
                self.wfile.write(b"* OK [CAPABILITY IMAP4rev1 STARTTLS] Fake Bridge ready\r\n")
                authed = False
                self.cur = "INBOX"
                while True:
                    line = self.rfile.readline()
                    if not line:
                        return
                    text = line.decode("utf-8", "replace").rstrip("\r\n")
                    tag, _, rest = text.partition(" ")
                    cmd, _, args = rest.partition(" ")
                    cmd = cmd.upper()
                    bridge.log.append(f"{cmd} {'***' if cmd == 'LOGIN' else args}".strip() + f" [tls={tls}]")
                    w = self.wfile.write
                    if cmd == "CAPABILITY":
                        caps = "IMAP4rev1 UIDPLUS AUTH=XOAUTH2" + (" MOVE" if bridge.move_supported else "") + (" STARTTLS" if (not tls and bridge.starttls) else "")
                        w(f"* CAPABILITY {caps}\r\n{tag} OK done\r\n".encode())
                    elif cmd == "STARTTLS":
                        if not bridge.starttls:
                            w(f"{tag} BAD no\r\n".encode()); continue
                        w(f"{tag} OK Begin TLS\r\n".encode()); self.wfile.flush()
                        try:
                            raw = bridge._ctx.wrap_socket(self.connection, server_side=True)
                        except (ssl.SSLError, OSError):
                            return
                        self.connection = raw
                        self.rfile = raw.makefile("rb")
                        self.wfile = raw.makefile("wb", buffering=0)
                        tls = True
                    elif cmd == "AUTHENTICATE":
                        w(b"+ \r\n"); self.wfile.flush()
                        blob = self.rfile.readline().strip()
                        bridge.log.append("AUTH-BLOB ***")
                        try:
                            ok = tls and bridge._xoauth_ok(base64.b64decode(blob))
                        except Exception:
                            ok = False
                        if ok:
                            authed = True
                            w(f"{tag} OK authenticated\r\n".encode())
                        else:
                            w(f"{tag} NO AUTHENTICATE failed.\r\n".encode())
                    elif cmd == "LOGIN":
                        m = re.match(r'"?([^" ]*)"? "((?:[^"\\]|\\.)*)"$', args)
                        if tls and m and m.group(1) == bridge.user and m.group(2) == bridge.password:
                            authed = True
                            w(f"{tag} OK logged in\r\n".encode())
                        elif tls and m and bridge.alert_password and m.group(2) == bridge.alert_password:
                            w(f"{tag} NO [ALERT] Application-specific password required\r\n".encode())
                        else:
                            w(f"{tag} NO [AUTHENTICATIONFAILED] bad credentials\r\n".encode())
                    elif not authed:
                        w(f"{tag} BAD login first\r\n".encode())
                    elif cmd in ("SELECT", "EXAMINE"):
                        self.cur = args.strip().strip('"') or "INBOX"
                        n = len(bridge.in_folder(self.cur))
                        mode = "READ-ONLY" if cmd == "EXAMINE" else "READ-WRITE"
                        w(f"* {n} EXISTS\r\n* OK [UIDVALIDITY {bridge.uidvalidity}] ok\r\n{tag} OK [{mode}] done\r\n".encode())
                    elif cmd == "CREATE":
                        name = args.strip().strip('"')
                        if any(n == name for _f, n in bridge.folders):
                            w(f"{tag} NO [ALREADYEXISTS] exists\r\n".encode())
                        else:
                            bridge.folders.append(("\\HasNoChildren", name))
                            w(f"{tag} OK created\r\n".encode())
                    elif cmd == "LIST":
                        for flags, name in bridge.folders:
                            w(f'* LIST ({flags}) "/" "{name}"\r\n'.encode())
                        w(f"{tag} OK done\r\n".encode())
                    elif cmd == "UID":
                        self._uid(tag, args)
                    elif cmd == "NOOP":
                        w(f"{tag} OK\r\n".encode())
                    elif cmd == "LOGOUT":
                        w(f"* BYE\r\n{tag} OK bye\r\n".encode()); return
                    else:
                        w(f"{tag} BAD unknown\r\n".encode())

            def _uid(self, tag, args):
                w = self.wfile.write
                sub, _, rest = args.partition(" ")
                sub = sub.upper()
                inbox = bridge.in_folder(self.cur)
                if sub == "SEARCH":
                    hits = [u for u in inbox if "UNSEEN" not in rest or "\\Seen" not in bridge.messages[u]["flags"]]
                    wanted = re.search(r'HEADER Message-ID "([^"]+)"', rest)
                    if wanted:
                        hits = [u for u in hits if f"Message-ID: {wanted.group(1)}".encode() in bridge.messages[u]["raw"]]
                    # Find any email: TEXT "words" (all must appear) and Gmail's X-GM-RAW "words"
                    for kind, value in re.findall(r'(TEXT|X-GM-RAW) "((?:[^"\\]|\\.)*)"', rest):
                        value = re.sub(r"\\(.)", r"\1", value).lower()
                        words = [a or b for a, b in re.findall(r'"([^"]+)"|(\S+)', value)] if kind == "X-GM-RAW" else [value]
                        hits = [u for u in hits if all(word.encode("utf-8") in bridge.messages[u]["raw"].lower() for word in words)]
                    w(("* SEARCH " + " ".join(map(str, hits)) + f"\r\n{tag} OK done\r\n").encode())
                elif sub == "FETCH":
                    uidset, _, items = rest.partition(" ")
                    for uid in (int(x) for x in uidset.split(",") if x.isdigit()):
                        m = bridge.messages.get(uid)
                        if not m or m["folder"] != self.cur:
                            continue
                        seq = inbox.index(uid) + 1
                        raw = m["raw"]
                        if "RFC822.SIZE" in items:
                            size = bridge.report_size or len(raw)
                            w(f"* {seq} FETCH (UID {uid} RFC822.SIZE {size})\r\n".encode())
                        elif "HEADER.FIELDS" in items:
                            head = raw.split(b"\r\n\r\n", 1)[0] + b"\r\n\r\n"
                            w(f"* {seq} FETCH (UID {uid} BODY[HEADER.FIELDS (X)] {{{len(head)}}}\r\n".encode() + head + b")\r\n")
                        elif "BODY.PEEK[]" in items:
                            w(f"* {seq} FETCH (UID {uid} BODY[] {{{len(raw)}}}\r\n".encode() + raw + b")\r\n")
                    w(f"{tag} OK done\r\n".encode())
                elif sub == "STORE":
                    uid = int(rest.split(" ")[0])
                    if uid in bridge.messages:
                        flag = "\\Seen" if "\\Seen" in rest else "\\Deleted"
                        bridge.messages[uid]["flags"].add(flag)
                    w(f"{tag} OK done\r\n".encode())
                elif sub in ("MOVE", "COPY"):
                    uid_s, _, folder = rest.partition(" ")
                    folder = folder.strip('"')
                    uid = int(uid_s)
                    if sub == "MOVE" and not bridge.move_supported:
                        w(f"{tag} BAD no move\r\n".encode()); return
                    if uid not in bridge.messages:
                        w(f"{tag} NO no such message\r\n".encode()); return
                    if sub == "MOVE":
                        bridge.messages[uid]["folder"] = folder
                    else:
                        bridge.messages[uid + 100000] = {"raw": bridge.messages[uid]["raw"], "flags": set(), "folder": folder}
                    w(f"{tag} OK done\r\n".encode())
                elif sub == "EXPUNGE":
                    uid = int(rest.split(" ")[0])
                    m = bridge.messages.get(uid)
                    if m and "\\Deleted" in m["flags"]:
                        del bridge.messages[uid]
                    w(f"{tag} OK done\r\n".encode())
                else:
                    w(f"{tag} BAD unknown\r\n".encode())

        return H

    # ---------- SMTP ----------

    def _smtp_handler(self):
        bridge = self

        class H(socketserver.StreamRequestHandler):
            def handle(self):
                tls = bridge.smtp_implicit
                authed = False
                w = self.wfile.write
                w(b"220 fake-bridge ESMTP\r\n")
                mail_from, rcpts = None, []
                while True:
                    line = self.rfile.readline()
                    if not line:
                        return
                    text = line.decode("utf-8", "replace").rstrip("\r\n")
                    cmd = text.split(" ", 1)[0].upper()
                    bridge.smtp_log.append(f"{cmd} [tls={tls}]")
                    if cmd in ("EHLO", "HELO"):
                        ext = "250-fake-bridge\r\n" + ("250-STARTTLS\r\n" if not tls else "") + "250 AUTH PLAIN LOGIN XOAUTH2\r\n"
                        w(ext.encode())
                    elif cmd == "STARTTLS":
                        w(b"220 go ahead\r\n"); self.wfile.flush()
                        try:
                            raw = bridge._ctx.wrap_socket(self.connection, server_side=True)
                        except (ssl.SSLError, OSError):
                            return
                        self.connection, self.rfile, self.wfile = raw, raw.makefile("rb"), raw.makefile("wb", buffering=0)
                        w = self.wfile.write
                        tls = True
                    elif cmd == "AUTH" and text.split(" ")[1:2] == ["XOAUTH2"]:
                        try:
                            ok = tls and bridge._xoauth_ok(base64.b64decode(text.split(" ")[2]))
                        except Exception:
                            ok = False
                        if ok:
                            authed = True
                            w(b"235 ok\r\n")
                        else:
                            w(b"535 5.7.3 authentication unsuccessful\r\n")
                    elif cmd == "AUTH":
                        parts = text.split(" ")
                        try:
                            _, user, pw = base64.b64decode(parts[2]).decode().split("\x00")
                        except Exception:
                            user = pw = ""
                        if tls and user == bridge.user and pw == bridge.password:
                            authed = True
                            w(b"235 ok\r\n")
                        else:
                            w(b"535 bad credentials\r\n")
                    elif cmd == "MAIL":
                        mail_from = re.search(r"<([^>]*)>", text).group(1)
                        w(b"250 ok\r\n")
                    elif cmd == "RCPT":
                        if bridge.smtp_reject:
                            w(b"550 refused\r\n"); continue
                        rcpts.append(re.search(r"<([^>]*)>", text).group(1))
                        w(b"250 ok\r\n")
                    elif cmd == "DATA":
                        if not authed:
                            w(b"530 auth first\r\n"); continue
                        w(b"354 go\r\n")
                        data = b""
                        while True:
                            chunk = self.rfile.readline()
                            if chunk in (b".\r\n", b""):
                                break
                            data += chunk
                        bridge.sent.append({"from": mail_from, "to": list(rcpts), "data": data})
                        rcpts = []
                        w(b"250 queued\r\n")
                    elif cmd == "RSET":
                        w(b"250 ok\r\n")
                    elif cmd == "QUIT":
                        w(b"221 bye\r\n"); return
                    else:
                        w(b"502 no\r\n")

        return H


def raw_email_with(subject: str, sender: str, to: str, *, cc: str = "", message_id: str, delivered_to: str | None = None,
                   body: str = "Hello there.\n", file: tuple[str, bytes] | None = None) -> bytes:
    """Like raw_email, with a Cc line and, if wanted, one attached file."""
    import base64 as _b64
    head = [f"From: {sender}", f"To: {to}", f"Subject: {subject}", "Date: Wed, 07 Oct 2026 09:00:00 +1100", f"Message-ID: {message_id}"]
    if cc:
        head.append(f"Cc: {cc}")
    if delivered_to:
        head.append(f"Delivered-To: {delivered_to}")
    if file is None:
        return ("\r\n".join(head) + "\r\n\r\n" + body.replace("\n", "\r\n")).encode()
    name, data = file
    head += ["MIME-Version: 1.0", 'Content-Type: multipart/mixed; boundary="B"']
    text = ("\r\n--B\r\nContent-Type: text/plain; charset=utf-8\r\n\r\n" + body.replace("\n", "\r\n") +
            f'\r\n--B\r\nContent-Type: application/pdf; name="{name}"\r\nContent-Disposition: attachment; filename="{name}"\r\n'
            "Content-Transfer-Encoding: base64\r\n\r\n" + _b64.b64encode(data).decode() + "\r\n--B--\r\n")
    return ("\r\n".join(head) + "\r\n" + text).encode()
