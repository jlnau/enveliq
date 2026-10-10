"""Safe outbound requests for reporting.

Reporting sends data to an address an administrator typed in, so the address is
checked before every send, not only when it is saved:

* http or https only, no user name or password in the address;
* the name is resolved here and every address it gives must be allowed:
  never this machine itself (loopback), never a link-local address (which
  includes cloud metadata services), never unspecified, multicast or reserved
  ranges. Addresses on the owner's own network are fine;
* a server outside the owner's network (a public address) needs https;
* if ENVELIQ_REPORT_ALLOWED_HOSTS is set, only the hosts listed there;
* the connection goes to the address that was checked (so the name cannot
  change between the check and the connection), the certificate is verified for
  https, redirects are never followed, and the answer is read only up to a small limit.
"""
from __future__ import annotations

import http.client
import ipaddress
import os
import socket
import ssl
from dataclasses import dataclass
from urllib.parse import urlsplit

MAX_ANSWER = 65_536
TIMEOUT = 8.0


class DestinationError(Exception):
    """`code` is a fixed word, never anything the remote server said."""

    def __init__(self, code: str, message: str):
        super().__init__(code)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class Destination:
    scheme: str
    host: str
    port: int
    path: str
    ips: tuple[str, ...]


def allowed_hosts() -> frozenset[str]:
    return frozenset(h.strip().lower() for h in os.environ.get("ENVELIQ_REPORT_ALLOWED_HOSTS", "").split(",") if h.strip())


def check_destination(url: str, *, resolve=socket.getaddrinfo) -> Destination:
    try:
        parts = urlsplit(url.strip())
        port = parts.port
    except ValueError:
        raise DestinationError("bad_address", "That address is not valid. Write it like http://192.168.1.20:3100") from None
    host = (parts.hostname or "").lower()
    if parts.scheme not in ("http", "https") or not host or parts.username or parts.password or parts.fragment:
        raise DestinationError("bad_address", "Use an address like http://192.168.1.20:3100 (http or https, no user name or password).")
    listed = allowed_hosts()
    if listed and host not in listed:
        raise DestinationError("host_not_allowed", "This address is not on the administrator's list (ENVELIQ_REPORT_ALLOWED_HOSTS).")
    port = port or (443 if parts.scheme == "https" else 80)
    try:
        found = {item[4][0] for item in resolve(host, port, type=socket.SOCK_STREAM)}
    except OSError:
        raise DestinationError("unresolvable", "That server name could not be found. Check the spelling, or use its IP address.") from None
    if not found:
        raise DestinationError("unresolvable", "That server name could not be found.")
    public = False
    for text in found:
        ip = ipaddress.ip_address(text.split("%")[0])
        if ip.is_loopback or ip.is_unspecified or ip.is_link_local or ip.is_multicast or ip.is_reserved:
            raise DestinationError("host_not_allowed", "That address points at this machine itself or a reserved range. Use the other machine's network address (for example 192.168.1.20).")
        if ip.is_global:
            public = True
    if public and parts.scheme != "https":
        raise DestinationError("needs_https", "A server outside your own network must use https.")
    path = parts.path or "/"
    if parts.query:
        path += "?" + parts.query
    return Destination(parts.scheme, host, port, path, tuple(sorted(found)))


class _Http(http.client.HTTPConnection):
    def __init__(self, host: str, port: int, ip: str):
        super().__init__(host, port, timeout=TIMEOUT)
        self._ip = ip

    def connect(self) -> None:
        self.sock = socket.create_connection((self._ip, self.port), TIMEOUT)


class _Https(http.client.HTTPSConnection):
    def __init__(self, host: str, port: int, ip: str):
        super().__init__(host, port, timeout=TIMEOUT, context=ssl.create_default_context())
        self._ip = ip

    def connect(self) -> None:
        sock = socket.create_connection((self._ip, self.port), TIMEOUT)
        self.sock = self._context.wrap_socket(sock, server_hostname=self.host)


def request(dest: Destination, method: str, body: bytes | None, headers: dict[str, str]) -> tuple[int, bytes]:
    """Send one request to a checked destination: (HTTP status, first 64 KiB of the answer).
    Raises DestinationError with a fixed code."""
    last: DestinationError | None = None
    for ip in dest.ips:
        conn = (_Https if dest.scheme == "https" else _Http)(dest.host, dest.port, ip)
        try:
            conn.request(method, dest.path, body=body, headers=headers)
            response = conn.getresponse()
            return response.status, response.read(MAX_ANSWER)
        except ssl.SSLError:
            last = DestinationError("tls_failed", "The secure connection failed: the certificate is not trusted or does not match the address.")
        except (OSError, http.client.HTTPException):
            last = DestinationError("unreachable", "The server could not be reached or took too long to answer.")
        finally:
            conn.close()
    raise last or DestinationError("unreachable", "The server could not be reached.")


def post(dest: Destination, body: bytes, headers: dict[str, str]) -> int:
    """POST `body` to a checked destination and return the HTTP status."""
    return request(dest, "POST", body, headers)[0]
