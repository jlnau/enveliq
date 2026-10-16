"""Talking to Proton Mail Bridge over IMAP and SMTP.

Bridge listens on the machine it runs on and presents its own self-signed
certificate. Enveliq therefore *pins* that certificate: the exact certificate
exported from Bridge is the only one trusted, and it is checked again by
fingerprint after the handshake. No username or password is sent before that
check passes, and there is no option to skip it.
"""
from __future__ import annotations

import hashlib
import hmac
import imaplib
import ipaddress
import logging
import os
import re
import smtplib
import socket
import ssl
from dataclasses import dataclass, field
from datetime import date, timedelta
from email.message import EmailMessage
from pathlib import Path
from typing import Any, Iterator

from .errors import BridgeError
from .microsoft import MESSAGES as MS_MESSAGES
from .parse import HEADER_FIELDS

log = logging.getLogger("enveliq.bridge")

_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
_LOCATOR = re.compile(r"^INBOX\|(\d{1,10})\|(\d{1,10})$")
_BAD_CRED = re.compile(r"[\r\n\x00]")
# imaplib sends the user name unquoted, so only plain address characters are accepted.
_USERNAME = re.compile(r"^[A-Za-z0-9._%+@-]{1,320}$")
_PEM = re.compile(r"-----BEGIN CERTIFICATE-----.+?-----END CERTIFICATE-----", re.S)

ARCHIVE_FOLDER = "Archive"
TRASH_FOLDER = "Trash"
SENT_FOLDER = "Sent"


@dataclass(frozen=True)
class BridgeConfig:
    ca_file: Path = Path("/etc/enveliq/proton-bridge.crt")
    allowed_hosts: frozenset[str] = frozenset()
    mail_allowed_hosts: frozenset[str] = frozenset()   # ordinary IMAP services: exclusive list set by the administrator
    mail_ca_file: Path | None = None                   # extra trusted certificate authority for ordinary IMAP services
    timeout: float = 20.0
    max_message_bytes: int = 10 * 1024 * 1024

    @classmethod
    def from_env(cls) -> "BridgeConfig":
        hosts = frozenset(h.strip().lower() for h in os.environ.get("ENVELIQ_BRIDGE_ALLOWED_HOSTS", "").split(",") if h.strip())
        mail_hosts = frozenset(h.strip().lower() for h in os.environ.get("ENVELIQ_MAIL_ALLOWED_HOSTS", "").split(",") if h.strip())
        mail_ca = os.environ.get("ENVELIQ_MAIL_CA_FILE", "").strip()
        return cls(
            ca_file=Path(os.environ.get("ENVELIQ_BRIDGE_CA_FILE", "/etc/enveliq/proton-bridge.crt")),
            allowed_hosts=hosts,
            mail_allowed_hosts=mail_hosts,
            mail_ca_file=Path(mail_ca) if mail_ca else None,
        )


@dataclass
class Target:
    """Where and how to reach one mailbox's Bridge."""
    host: str
    imap_port: int
    smtp_port: int | None
    username: str
    password: str = field(repr=False)
    # Ordinary IMAP services (Gmail, iCloud ...). Proton Bridge keeps the defaults.
    kind: str = "bridge"                     # "bridge" | "imap"
    imap_security: str = "starttls"          # "ssl" | "starttls"
    smtp_host: str | None = None
    smtp_security: str = "starttls"
    smtp_username: str | None = None
    auth: str = "password"                   # "password" | "xoauth2" (then `password` holds a short-lived access token)
    archive_hint: tuple[str, ...] = ()
    trash_hint: tuple[str, ...] = ()


def locator(uidvalidity: int, uid: int) -> str:
    return f"INBOX|{uidvalidity}|{uid}"


def parse_locator(value: str | None) -> tuple[int, int]:
    match = _LOCATOR.match(value or "")
    if not match:
        raise BridgeError("not_found", "This email can no longer be found in the mailbox. Sync again.")
    return int(match.group(1)), int(match.group(2))


# ---------- ordinary IMAP services (Gmail, iCloud, Yahoo ...) ----------

_HOSTNAME = re.compile(r"^(?=.{1,253}$)([A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,63}$")
_STANDARD_IMAP_PORTS = {"ssl": {993}, "starttls": {143}}
_STANDARD_SMTP_PORTS = {"ssl": {465}, "starttls": {587}}
_LIST_LINE = re.compile(rb'^\((?P<flags>[^)]*)\)\s+(?:"(?:[^"\\]|\\.)*"|NIL)\s+(?P<name>.+)$', re.S)
ARCHIVE_HINTS = ("Archive", "Archives")
TRASH_HINTS = ("Trash", "Deleted Messages", "Deleted Items", "Bin")
SENT_HINTS = ("Sent", "Sent Items", "Sent Mail", "Sent Messages", "[Gmail]/Sent Mail", "INBOX.Sent")


def _connect_public(host: str, port: int, timeout: float, require_public: bool) -> socket.socket:
    """Open a TCP connection to a mail server on the internet. The name is
    resolved here and every address must be a public one, so a name that points
    at a machine on your own network (or at Enveliq itself) is refused."""
    infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    if not infos:
        raise OSError("no address")
    if require_public:
        for _fam, _typ, _proto, _canon, sockaddr in infos:
            if not ipaddress.ip_address(str(sockaddr[0]).split("%")[0]).is_global:
                raise BridgeError("host_not_allowed", "That server name points to an address on a private network, so Enveliq will not connect to it. "
                                  "An administrator can allow it with ENVELIQ_MAIL_ALLOWED_HOSTS.")
    last: Exception | None = None
    for fam, typ, proto, _canon, sockaddr in infos:
        sock = socket.socket(fam, typ, proto)
        try:
            sock.settimeout(timeout)
            sock.connect(sockaddr)
            return sock
        except OSError as exc:
            sock.close()
            last = exc
    raise last or OSError("unreachable")


def _public_imap(security: str, require_public: bool):
    if security == "ssl":
        class SecureImap(imaplib.IMAP4_SSL):
            def _create_socket(self, timeout):  # type: ignore[override]
                sock = _connect_public(self.host, self.port, timeout, require_public)
                return self.ssl_context.wrap_socket(sock, server_hostname=self.host)
        return SecureImap

    class PlainImap(imaplib.IMAP4):
        def _create_socket(self, timeout):  # type: ignore[override]
            return _connect_public(self.host, self.port, timeout, require_public)
    return PlainImap


def _public_smtp(security: str, require_public: bool):
    if security == "ssl":
        class SecureSmtp(smtplib.SMTP_SSL):
            def _get_socket(self, host, port, timeout):  # type: ignore[override]
                sock = _connect_public(host, port, timeout, require_public)
                return self.context.wrap_socket(sock, server_hostname=self._host)
        return SecureSmtp

    class PlainSmtp(smtplib.SMTP):
        def _get_socket(self, host, port, timeout):  # type: ignore[override]
            return _connect_public(host, port, timeout, require_public)
    return PlainSmtp


def _xoauth2(user: str, token: str) -> str:
    return f"user={user}\x01auth=Bearer {token}\x01\x01"


def _wrap_public(exc: Exception, stage: str, oauth: bool = False) -> BridgeError:
    log.warning("mail server %s failed: %s", stage, type(exc).__name__)
    if isinstance(exc, BridgeError):
        return exc
    if stage == "login" and oauth and isinstance(exc, (imaplib.IMAP4.error, smtplib.SMTPAuthenticationError)):
        return BridgeError("ms_mailbox_refused", MS_MESSAGES["ms_mailbox_refused"])
    if stage == "login" and isinstance(exc, (imaplib.IMAP4.error, smtplib.SMTPAuthenticationError)):
        text = " ".join(str(a) for a in exc.args).lower()
        if "application-specific" in text or "app password" in text or "app-specific" in text:
            return BridgeError("app_password_required", "The mail server wants an app password, not your normal password.")
        return BridgeError("login_failed", "The mail server refused the login. Check the email address and the app password.")
    if isinstance(exc, ssl.SSLError):
        return BridgeError("tls_failed", "The secure connection to the mail server could not be verified.")
    if isinstance(exc, (socket.gaierror,)):
        return BridgeError("unreachable", "That mail server name could not be found. Check the server name for typing mistakes.")
    if isinstance(exc, (OSError, socket.timeout, TimeoutError, smtplib.SMTPServerDisconnected)):
        return BridgeError("unreachable", "Could not reach the mail server. Check the server name, the port and your internet connection.")
    return BridgeError("protocol_error", "The mail server answered in a way Enveliq did not expect.")


class Bridge:
    def __init__(self, config: BridgeConfig | None = None):
        self.config = config or BridgeConfig.from_env()
        self._pin: tuple[float, str, bytes] | None = None  # mtime, pem, der fingerprint

    # ---------- trust ----------

    def _certificate(self) -> tuple[str, bytes]:
        path = self.config.ca_file
        try:
            mtime = path.stat().st_mtime
            if self._pin is None or self._pin[0] != mtime:
                pem = path.read_text(encoding="ascii")
                block = _PEM.search(pem)
                if not block:
                    raise ValueError("no certificate")
                der = ssl.PEM_cert_to_DER_cert(block.group(0))
                self._pin = (mtime, block.group(0), hashlib.sha256(der).digest())
        except (OSError, ValueError, UnicodeDecodeError):
            raise BridgeError(
                "no_certificate",
                "The Proton Bridge certificate file is missing or unreadable. "
                "Export it from Bridge and mount it into the container (see docs/PROTON_BRIDGE.md).",
            ) from None
        return self._pin[1], self._pin[2]

    def _context(self) -> tuple[ssl.SSLContext, bytes]:
        pem, fingerprint = self._certificate()
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        ctx.verify_mode = ssl.CERT_REQUIRED
        ctx.check_hostname = False  # Bridge is reached by IP or a forwarder address; the pin below replaces name checks
        ctx.load_verify_locations(cadata=pem)
        return ctx, fingerprint

    @staticmethod
    def _check_pin(sock: Any, fingerprint: bytes) -> None:
        der = sock.getpeercert(binary_form=True) if sock is not None else None
        if not der or not hmac.compare_digest(hashlib.sha256(der).digest(), fingerprint):
            raise BridgeError(
                "certificate_mismatch",
                "The server's certificate is not the Proton Bridge certificate you exported, or it has expired. "
                "Export Bridge's certificate again if Bridge was reinstalled.",
            )

    # ---------- destination rules ----------

    def check_target(self, target: Target, need_smtp: bool = False) -> None:
        if not target.host or not target.username or not target.password:
            raise BridgeError("not_configured", "Set the Bridge address, port, username and password for this mailbox first.")
        if not _USERNAME.match(target.username) or _BAD_CRED.search(target.password):
            raise BridgeError("not_configured", "The username or password contains characters that cannot be used.")
        if target.kind == "imap":
            return self._check_public(target, need_smtp)
        ports = [target.imap_port] + ([target.smtp_port] if need_smtp else [])
        if need_smtp and not target.smtp_port:
            raise BridgeError("not_configured", "Set the SMTP port in this mailbox's settings (settings.smtp_port) to send replies.")
        for port in ports:
            if not isinstance(port, int) or isinstance(port, bool) or not 1024 <= port <= 65535:
                raise BridgeError("not_configured", "Bridge ports must be between 1024 and 65535.")
        host = target.host.strip("[]").lower()
        if self.config.allowed_hosts:
            # An administrator-set list is exclusive: nothing else is contacted.
            if host not in self.config.allowed_hosts:
                raise BridgeError("host_not_allowed", "This address is not on the administrator's list of allowed Bridge hosts.")
            return
        try:
            ip = ipaddress.ip_address(host)
        except ValueError:
            raise BridgeError(
                "host_not_allowed",
                "Use the Bridge machine's IP address, or ask the administrator to allow this name (ENVELIQ_BRIDGE_ALLOWED_HOSTS).",
            ) from None
        if ip.is_unspecified or ip.is_multicast or not (ip.is_private or ip.is_loopback):
            raise BridgeError("host_not_allowed", "Proton Bridge must be on your own network (a private or local address).")

    def _admin_listed(self, host: str) -> bool:
        return host.strip("[]").lower() in self.config.mail_allowed_hosts

    def _check_public(self, target: Target, need_smtp: bool) -> None:
        if target.imap_security not in ("ssl", "starttls") or target.smtp_security not in ("ssl", "starttls"):
            raise BridgeError("not_configured", "Choose SSL/TLS or STARTTLS. Unencrypted connections are not allowed.")
        if need_smtp and not (target.smtp_host and target.smtp_port):
            raise BridgeError("not_configured", "Set the outgoing (SMTP) server and port for this mailbox to send replies.")
        servers = [(target.host, target.imap_port, _STANDARD_IMAP_PORTS[target.imap_security])]
        if need_smtp:
            servers.append((str(target.smtp_host), int(target.smtp_port or 0), _STANDARD_SMTP_PORTS[target.smtp_security]))
        for host, port, standard in servers:
            name = host.strip("[]").lower()
            if not isinstance(port, int) or isinstance(port, bool) or not 1 <= port <= 65535:
                raise BridgeError("not_configured", "The mail server port must be a number between 1 and 65535.")
            if self.config.mail_allowed_hosts:
                # An administrator-set list is exclusive, and listed servers may use any port.
                if name not in self.config.mail_allowed_hosts:
                    raise BridgeError("host_not_allowed", "This mail server is not on the administrator's list of allowed servers.")
                continue
            try:
                ip = ipaddress.ip_address(name)
            except ValueError:
                if not _HOSTNAME.match(name):
                    raise BridgeError("not_configured", "The mail server must be written as a name such as imap.example.com.") from None
            else:
                if not ip.is_global:
                    raise BridgeError("host_not_allowed", "That is a private address. An administrator can allow servers on your own network with ENVELIQ_MAIL_ALLOWED_HOSTS.")
            if port not in standard:
                raise BridgeError("not_configured", "Use the standard secure ports: IMAP 993 (SSL/TLS) or 143 (STARTTLS), SMTP 465 (SSL/TLS) or 587 (STARTTLS).")

    def _public_context(self) -> ssl.SSLContext:
        ctx = ssl.create_default_context()
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        if self.config.mail_ca_file:
            try:
                ctx.load_verify_locations(cafile=str(self.config.mail_ca_file))
            except (OSError, ssl.SSLError):
                raise BridgeError("no_certificate", "The extra certificate file for mail servers (ENVELIQ_MAIL_CA_FILE) is missing or unreadable.") from None
        return ctx

    def _open_imap_public(self, target: Target) -> imaplib.IMAP4:
        self.check_target(target)
        ctx = self._public_context()
        cls = _public_imap(target.imap_security, not self._admin_listed(target.host))
        imap: imaplib.IMAP4 | None = None
        host = target.host.strip("[]")
        try:
            if target.imap_security == "ssl":
                imap = cls(host, target.imap_port, ssl_context=ctx, timeout=self.config.timeout)
            else:
                imap = cls(host, target.imap_port, timeout=self.config.timeout)
                if "STARTTLS" not in imap.capabilities:
                    raise BridgeError("protocol_error", "The mail server did not offer a secure connection.")
                imap.starttls(ssl_context=ctx)
        except Exception as exc:
            self._close_imap(imap)
            raise _wrap_public(exc, "connect") from None
        try:
            if target.auth == "xoauth2":
                imap.authenticate("XOAUTH2", lambda _challenge: _xoauth2(target.username, target.password).encode())
            else:
                imap.login(target.username, target.password)
        except Exception as exc:
            self._close_imap(imap)
            raise _wrap_public(exc, "login", target.auth == "xoauth2") from None
        return imap

    def _open_smtp_public(self, target: Target) -> smtplib.SMTP:
        self.check_target(target, need_smtp=True)
        ctx = self._public_context()
        cls = _public_smtp(target.smtp_security, not self._admin_listed(str(target.smtp_host)))
        smtp: smtplib.SMTP | None = None
        host = str(target.smtp_host).strip("[]")
        try:
            if target.smtp_security == "ssl":
                smtp = cls(host, target.smtp_port, timeout=self.config.timeout, context=ctx)
            else:
                smtp = cls(host, target.smtp_port, timeout=self.config.timeout)
                smtp.ehlo()
                if not smtp.has_extn("starttls"):
                    raise BridgeError("protocol_error", "The mail server did not offer a secure connection.")
                smtp.starttls(context=ctx)
            smtp.ehlo()
        except Exception as exc:
            self._close_smtp(smtp)
            raise _wrap_public(exc, "connect") from None
        try:
            if target.auth == "xoauth2":
                smtp.auth("XOAUTH2", lambda challenge=None: _xoauth2(target.username, target.password), initial_response_ok=True)
            else:
                smtp.login(target.smtp_username or target.username, target.password)
        except Exception as exc:
            self._close_smtp(smtp)
            raise _wrap_public(exc, "login", target.auth == "xoauth2") from None
        return smtp

    # ---------- connections ----------

    def _wrap(self, exc: Exception, stage: str) -> BridgeError:
        log.warning("bridge %s failed: %s", stage, type(exc).__name__)
        if isinstance(exc, BridgeError):
            return exc
        if isinstance(exc, (imaplib.IMAP4.error, smtplib.SMTPAuthenticationError)) and stage == "login":
            return BridgeError("login_failed", "Bridge refused the login. Check the Bridge username and password, and that Bridge is still signed in to Proton.")
        if isinstance(exc, ssl.SSLError):
            return BridgeError("certificate_mismatch", "The secure connection to Bridge could not be verified against the exported certificate.")
        if isinstance(exc, (OSError, socket.timeout, TimeoutError, smtplib.SMTPServerDisconnected)):
            return BridgeError("unreachable", "Could not reach Proton Bridge. Check that it is running and that the forwarder is up.")
        return BridgeError("protocol_error", "Proton Bridge answered in a way Enveliq did not expect.")

    def open_imap(self, target: Target) -> imaplib.IMAP4:
        if target.kind == "imap":
            return self._open_imap_public(target)
        self.check_target(target)
        ctx, fingerprint = self._context()
        imap: imaplib.IMAP4 | None = None
        try:
            imap = imaplib.IMAP4(target.host.strip("[]"), target.imap_port, timeout=self.config.timeout)
            if "STARTTLS" not in imap.capabilities:
                raise BridgeError("protocol_error", "Proton Bridge did not offer a secure connection.")
            imap.starttls(ssl_context=ctx)
            self._check_pin(imap.sock, fingerprint)
        except Exception as exc:
            self._close_imap(imap)
            raise self._wrap(exc, "connect") from None
        try:
            imap.login(target.username, target.password)
        except Exception as exc:
            self._close_imap(imap)
            raise self._wrap(exc, "login") from None
        return imap

    @staticmethod
    def _close_imap(imap: imaplib.IMAP4 | None) -> None:
        if imap is None:
            return
        try:
            imap.logout()
        except Exception:
            try:
                imap.shutdown()
            except Exception:
                pass

    def session(self, target: Target) -> "_ImapSession":
        return _ImapSession(self, target)

    def open_smtp(self, target: Target) -> smtplib.SMTP:
        if target.kind == "imap":
            return self._open_smtp_public(target)
        self.check_target(target, need_smtp=True)
        ctx, fingerprint = self._context()
        smtp: smtplib.SMTP | None = None
        try:
            smtp = smtplib.SMTP(target.host.strip("[]"), target.smtp_port, timeout=self.config.timeout)
            smtp.ehlo()
            if not smtp.has_extn("starttls"):
                raise BridgeError("protocol_error", "Proton Bridge did not offer a secure connection.")
            smtp.starttls(context=ctx)
            self._check_pin(smtp.sock, fingerprint)
            smtp.ehlo()
        except Exception as exc:
            self._close_smtp(smtp)
            raise self._wrap(exc, "connect") from None
        try:
            smtp.login(target.username, target.password)
        except Exception as exc:
            self._close_smtp(smtp)
            raise self._wrap(exc, "login") from None
        return smtp

    @staticmethod
    def _close_smtp(smtp: smtplib.SMTP | None) -> None:
        if smtp is None:
            return
        try:
            smtp.quit()
        except Exception:
            try:
                smtp.close()
            except Exception:
                pass

    # ---------- checks ----------

    def check(self, target: Target) -> dict[str, str]:
        """Try each connection; report ok or the safe error message per part."""
        result: dict[str, str] = {}
        try:
            with self.session(target) as s:
                s.select_inbox()
            result["imap"] = "ok"
        except BridgeError as err:
            result["imap"] = err.code
            result["imap_message"] = err.message
        if target.smtp_port and (target.kind != "imap" or target.smtp_host):
            try:
                self._close_smtp(self.open_smtp(target))
                result["smtp"] = "ok"
            except BridgeError as err:
                result["smtp"] = err.code
                result["smtp_message"] = err.message
        else:
            result["smtp"] = "not_configured"
        return result

    # ---------- sending ----------

    def send(self, target: Target, message: EmailMessage, from_addr: str, to_addrs: list[str]) -> None:
        smtp = self.open_smtp(target)
        try:
            smtp.send_message(message, from_addr=from_addr, to_addrs=to_addrs)
        except (smtplib.SMTPRecipientsRefused, smtplib.SMTPSenderRefused, smtplib.SMTPDataError, smtplib.SMTPHeloError) as exc:
            log.warning("bridge send refused: %s", type(exc).__name__)
            raise BridgeError("send_refused", "The mail server refused to send this reply.") from None
        except Exception as exc:
            raise (_wrap_public(exc, "send") if target.kind == "imap" else self._wrap(exc, "send")) from None
        finally:
            self._close_smtp(smtp)


class _ImapSession:
    """One open, logged-in IMAP connection with the operations Enveliq needs."""

    def __init__(self, bridge: Bridge, target: Target):
        self._bridge = bridge
        self._target = target
        self._imap: imaplib.IMAP4 | None = None
        self.uidvalidity = 0

    def __enter__(self) -> "_ImapSession":
        self._imap = self._bridge.open_imap(self._target)
        return self

    def __exit__(self, *exc: Any) -> None:
        self._bridge._close_imap(self._imap)
        self._imap = None

    @property
    def imap(self) -> imaplib.IMAP4:
        assert self._imap is not None
        return self._imap

    def _call(self, what: str, fn: Any, *args: Any) -> Any:
        try:
            typ, data = fn(*args)
        except Exception as exc:
            raise self._bridge._wrap(exc, what) from None
        if typ != "OK":
            log.warning("bridge %s answered %s", what, typ)
            raise BridgeError("protocol_error", "Proton Bridge answered in a way Enveliq did not expect.")
        return data

    def select_inbox(self, readonly: bool = True) -> int:
        self._call("select", self.imap.select, "INBOX", readonly)
        try:
            typ, data = self.imap.response("UIDVALIDITY")
            self.uidvalidity = int(data[0]) if data and data[0] else 0
        except (ValueError, TypeError):
            self.uidvalidity = 0
        return self.uidvalidity

    def select_folder(self, name: str, readonly: bool = True) -> int:
        """Open any folder (read-only by default) and return its UIDVALIDITY."""
        quoted = '"' + name.replace("\\", "\\\\").replace('"', '\\"') + '"'
        self._call("select", self.imap.select, quoted, readonly)
        try:
            typ, data = self.imap.response("UIDVALIDITY")
            self.uidvalidity = int(data[0]) if data and data[0] else 0
        except (ValueError, TypeError):
            self.uidvalidity = 0
        return self.uidvalidity

    def recent_uids(self, since_days: int, limit: int | None = None) -> list[int]:
        """Newest emails in the open folder from the last few days (read or not)."""
        since = date.today() - timedelta(days=since_days)
        stamp = f"{since.day:02d}-{_MONTHS[since.month - 1]}-{since.year}"
        data = self._call("search", self.imap.uid, "SEARCH", None, "SINCE", stamp)
        uids = sorted((int(x) for x in (data[0] or b"").split() if x.isdigit()), reverse=True)
        return uids[:limit] if limit is not None else uids

    def unseen_uids(self, since_days: int, limit: int) -> list[int]:
        since = date.today() - timedelta(days=since_days)
        stamp = f"{since.day:02d}-{_MONTHS[since.month - 1]}-{since.year}"
        data = self._call("search", self.imap.uid, "SEARCH", None, "UNSEEN", "SINCE", stamp)
        uids = sorted((int(x) for x in (data[0] or b"").split() if x.isdigit()), reverse=True)
        return uids[:limit]

    def all_unseen_uids(self) -> set[int]:
        """Every unread email in the inbox, whatever its age. Used to notice
        mail that has since been read, moved or deleted elsewhere."""
        data = self._call("search", self.imap.uid, "SEARCH", None, "UNSEEN")
        return {int(x) for x in (data[0] or b"").split() if x.isdigit()}

    def _folders(self) -> list[tuple[set[str], str]]:
        data = self._call("list", self.imap.list)
        found: list[tuple[set[str], str]] = []
        for item in data or []:
            raw = item[0] + b" " + item[1] if isinstance(item, tuple) else item
            if not isinstance(raw, bytes):
                continue
            match = _LIST_LINE.match(raw.strip())
            if not match:
                continue
            flags = {f.lower() for f in match.group("flags").decode("ascii", "replace").split()}
            name = match.group("name").strip().decode("ascii", "replace")
            if name.startswith('"') and name.endswith('"') and len(name) >= 2:
                name = re.sub(r"\\(.)", r"\1", name[1:-1])
            if "\\noselect" not in flags:
                found.append((flags, name))
        return found

    def folder_for(self, which: str) -> str:
        """The folder an email is moved to: 'archive' or 'trash'. Proton Bridge
        always uses Archive and Trash. Other services mark their folders with
        special-use flags (Gmail's All Mail and Trash, for example), and the
        usual names are the fallback."""
        if self._target.kind != "imap":
            return {"archive": ARCHIVE_FOLDER, "trash": TRASH_FOLDER, "sent": SENT_FOLDER}[which]
        folders = self._folders()
        flag_order = {"archive": ("\\archive", "\\all"), "trash": ("\\trash",), "sent": ("\\sent",)}[which]
        for wanted in flag_order:
            for flags, name in folders:
                if wanted in flags:
                    return name
        hints = {"archive": self._target.archive_hint or ARCHIVE_HINTS, "trash": self._target.trash_hint or TRASH_HINTS, "sent": SENT_HINTS}[which]
        by_lower = {name.lower(): name for _flags, name in folders}
        for hint in hints:
            if hint.lower() in by_lower:
                return by_lower[hint.lower()]
        label = {"archive": "Archive", "trash": "Bin (Trash)", "sent": "Sent"}[which]
        raise BridgeError("not_found", f"Enveliq could not find this mailbox's {label} folder." + ("" if which == "sent" else " Create one in your mail service first."))

    def header_blocks(self, uids: list[int], fields: str = HEADER_FIELDS) -> Iterator[tuple[int, bytes]]:
        for start in range(0, len(uids), 50):
            chunk = ",".join(str(u) for u in uids[start:start + 50])
            data = self._call("fetch", self.imap.uid, "FETCH", chunk, f"(UID BODY.PEEK[HEADER.FIELDS ({fields})])")
            for item in data:
                if isinstance(item, tuple) and len(item) == 2:
                    found = re.search(rb"UID (\d+)", item[0])
                    if found:
                        yield int(found.group(1)), bytes(item[1])

    def original(self, uid: int) -> bytes:
        data = self._call("fetch", self.imap.uid, "FETCH", str(uid), "(RFC822.SIZE)")
        found = re.search(rb"RFC822\.SIZE (\d+)", b" ".join(x if isinstance(x, bytes) else x[0] for x in data if x))
        if not found:
            raise BridgeError("not_found", "This email can no longer be found in the mailbox. Sync again.")
        if int(found.group(1)) > self._bridge.config.max_message_bytes:
            raise BridgeError("too_large", "This email is too large to display here.")
        data = self._call("fetch", self.imap.uid, "FETCH", str(uid), "(BODY.PEEK[])")
        for item in data:
            if isinstance(item, tuple) and len(item) == 2:
                return bytes(item[1])
        raise BridgeError("not_found", "This email can no longer be found in the mailbox. Sync again.")

    def mark_seen(self, uid: int) -> None:
        self._call("store", self.imap.uid, "STORE", str(uid), "+FLAGS.SILENT", "(\\Seen)")

    def move(self, uid: int, folder: str) -> None:
        caps = {c.upper() for c in self.imap.capabilities}
        quoted = '"' + folder.replace("\\", "\\\\").replace('"', '\\"') + '"'
        if "MOVE" in caps:
            self._call("move", self.imap.uid, "MOVE", str(uid), quoted)
            return
        if "UIDPLUS" not in caps:
            raise BridgeError("protocol_error", "This Bridge cannot move email safely.")
        self._call("copy", self.imap.uid, "COPY", str(uid), quoted)
        self._call("store", self.imap.uid, "STORE", str(uid), "+FLAGS.SILENT", "(\\Deleted)")
        self._call("expunge", self.imap.uid, "EXPUNGE", str(uid))
