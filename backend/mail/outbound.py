"""Careful outgoing requests for reminders, calendars and To-do lists.

Enveliq is asked by a person to call an address they typed. That is the classic way to make a server probe things it
should not reach, so every request here follows fixed rules:

* The address is looked up first and every answer must be acceptable. Public addresses are fine over https. An address
  on your own network (private, loopback, 100.64/10) is refused unless an administrator listed that host name, IP or
  network (ENVELIQ_NOTIFY_ALLOWED_HOSTS, or Administration, Reminders). Link-local addresses (which include cloud
  metadata services), "any" and multicast are never allowed.
* The connection goes to the address that was checked, not to the name again, so a name that changes its answer between
  the check and the connection cannot slip through. For https the certificate is still checked against the name.
* No proxy, no redirects, a short timeout, and at most 64 KB of the reply is read.
* Plain http is only for addresses the administrator allowed on the local network.
"""
from __future__ import annotations

import http.client
import ipaddress
import json
import os
import socket
import ssl
import urllib.parse
from typing import Any

MAX_REPLY = 64 * 1024
TIMEOUT = 10.0
ADMIN_RECORD = "notify_admin"


class OutboundError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code, self.message = code, message


def listed(vault: Any | None = None) -> list[str]:
    """Hosts, IPs and networks that may be on the local network, from the environment and from Administration."""
    out = [x.strip().lower() for x in os.environ.get("ENVELIQ_NOTIFY_ALLOWED_HOSTS", "").split(",") if x.strip()]
    if vault is not None:
        try:
            saved = (vault.get_global(ADMIN_RECORD) or {}).get("local_hosts") or []
            out += [str(x).strip().lower() for x in saved if str(x).strip()]
        except Exception:
            pass
    return out


def _listed(host: str, ip: Any, allow: list[str]) -> bool:
    for entry in allow:
        if entry == host.lower():
            return True
        try:
            if "/" in entry:
                if ip in ipaddress.ip_network(entry, strict=False):
                    return True
            elif ip == ipaddress.ip_address(entry):
                return True
        except ValueError:
            continue
    return False


def check_target(url: str, allow: list[str]) -> tuple[str, str, int, str, str, bool]:
    """(scheme, host, port, ip, path, is_local) for a URL that may be called, or raise OutboundError."""
    try:
        parts = urllib.parse.urlsplit(url)
        port = parts.port
    except ValueError:
        raise OutboundError("bad_address", "That address is not valid.") from None
    if parts.scheme not in ("http", "https") or not parts.hostname or parts.username or parts.password:
        raise OutboundError("bad_address", "Use an address that starts with http:// or https:// and has no user name in it.")
    host = parts.hostname
    port = port or (443 if parts.scheme == "https" else 80)
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except OSError:
        raise OutboundError("unreachable", "That address could not be found.") from None
    addresses = []
    for info in infos:
        ip = ipaddress.ip_address(info[4][0].split("%")[0])
        if getattr(ip, "ipv4_mapped", None):
            ip = ip.ipv4_mapped
        addresses.append(ip)
    if not addresses:
        raise OutboundError("unreachable", "That address could not be found.")
    local = False
    for ip in addresses:
        if ip.is_link_local or ip.is_unspecified or ip.is_multicast or ip.is_reserved:
            raise OutboundError("not_allowed", "Enveliq will not call that kind of address.")
        if not ip.is_global:
            if not _listed(host, ip, allow):
                raise OutboundError("not_allowed", "That address is on your own network. An administrator must allow it first (Administration, Reminders, local addresses).")
            local = True
    if parts.scheme == "http" and not local:
        raise OutboundError("not_allowed", "Use https:// for services on the internet. Plain http is only for addresses on your own network that an administrator allowed.")
    path = parts.path or "/"
    if parts.query:
        path += "?" + parts.query
    return parts.scheme, host, port, str(addresses[0]), path, local


class _Pinned(http.client.HTTPConnection):
    def __init__(self, host: str, port: int, ip: str, timeout: float):
        super().__init__(host, port, timeout=timeout)
        self._ip = ip

    def connect(self) -> None:
        self.sock = socket.create_connection((self._ip, self.port), self.timeout)


class _PinnedTLS(http.client.HTTPSConnection):
    def __init__(self, host: str, port: int, ip: str, timeout: float):
        super().__init__(host, port, timeout=timeout, context=ssl.create_default_context())
        self._ip = ip

    def connect(self) -> None:
        sock = socket.create_connection((self._ip, self.port), self.timeout)
        self.sock = self._context.wrap_socket(sock, server_hostname=self.host)


def request_full(method: str, url: str, *, allow: list[str], headers: dict[str, str] | None = None, body: bytes | None = None,
                 json_body: Any = None, form: dict[str, str] | None = None, timeout: float = TIMEOUT, max_bytes: int = MAX_REPLY) -> tuple[int, dict[str, str], bytes]:
    """One request. Returns (status, reply headers in lower case, the first `max_bytes` of the reply). Never follows a redirect."""
    scheme, host, port, ip, path, _ = check_target(url, allow)
    hdrs = {"User-Agent": "Enveliq", "Accept": "application/json, text/plain, */*", **(headers or {})}
    if json_body is not None:
        body = json.dumps(json_body, ensure_ascii=False).encode("utf-8")
        hdrs["Content-Type"] = "application/json; charset=utf-8"
    elif form is not None:
        body = urllib.parse.urlencode(form).encode("utf-8")
        hdrs["Content-Type"] = "application/x-www-form-urlencoded"
    conn = (_PinnedTLS if scheme == "https" else _Pinned)(host, port, ip, timeout)
    try:
        conn.request(method, path, body=body, headers=hdrs)
        resp = conn.getresponse()
        return resp.status, {k.lower(): v for k, v in resp.getheaders()}, resp.read(max_bytes)
    except ssl.SSLError:
        raise OutboundError("tls", "The secure connection could not be trusted (check the certificate).") from None
    except (OSError, http.client.HTTPException):
        raise OutboundError("unreachable", "Could not reach it.") from None
    finally:
        conn.close()


def request(method: str, url: str, *, allow: list[str], headers: dict[str, str] | None = None, body: bytes | None = None,
            json_body: Any = None, form: dict[str, str] | None = None, timeout: float = TIMEOUT) -> tuple[int, bytes]:
    """One request. Returns (status, first 64 KB of the reply). Never follows a redirect."""
    status, _, data = request_full(method, url, allow=allow, headers=headers, body=body, json_body=json_body, form=form, timeout=timeout)
    return status, data
