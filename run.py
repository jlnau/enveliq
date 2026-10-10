import ipaddress
import os
import sys

import uvicorn

LOOPBACK_NAMES = {"localhost"}


def is_loopback(host: str) -> bool:
    if host in LOOPBACK_NAMES:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def build_config() -> dict:
    host = os.environ.get("ENVELIQ_BIND", "127.0.0.1")
    if not is_loopback(host) and os.environ.get("ENVELIQ_ALLOW_NON_LOOPBACK") != "1":
        raise SystemExit(
            f"Refusing to listen on {host}: the development backend must stay on this machine. "
            "Set ENVELIQ_ALLOW_NON_LOOPBACK=1 only behind an authenticating proxy such as Home Assistant ingress."
        )
    return {
        "app": "backend.app:app",
        "host": host,
        "port": int(os.environ.get("ENVELIQ_PORT", "8765")),
        "reload": False,
        "access_log": False,
        "server_header": False,
        "date_header": False,
        # Never trust X-Forwarded-For / X-Forwarded-Proto. Uvicorn trusts them
        # from 127.0.0.1 by default, which would let any local process pick
        # its own client address and dodge the per-client unlock limit.
        "proxy_headers": False,
        "forwarded_allow_ips": "",
        "limit_concurrency": 64,
        "timeout_keep_alive": 5,
        "h11_max_incomplete_event_size": 16 * 1024,
    }


if __name__ == "__main__":
    uvicorn.run(**build_config())
