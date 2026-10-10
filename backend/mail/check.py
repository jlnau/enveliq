"""Command-line connection test for Proton Mail Bridge.

Run it inside the container to confirm the forwarder, the certificate and the
Bridge login work before adding the mailbox in the app:

    docker compose exec enveliq python -m backend.mail.check \\
        --host 172.30.0.1 --imap-port 1144 --smtp-port 1026 --user BRIDGE_USERNAME

The Bridge password is read from ENVELIQ_CHECK_PASSWORD or asked for; it is
never taken from the command line, so it stays out of shell history.
"""
from __future__ import annotations

import argparse
import getpass
import os
import sys

from .bridge import Bridge, Target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m backend.mail.check", description=__doc__.split("\n\n")[0])
    parser.add_argument("--host", required=True)
    parser.add_argument("--imap-port", type=int, required=True)
    parser.add_argument("--smtp-port", type=int)
    parser.add_argument("--user", required=True)
    args = parser.parse_args(argv)
    password = os.environ.get("ENVELIQ_CHECK_PASSWORD") or getpass.getpass("Bridge password: ")
    result = Bridge().check(Target(args.host, args.imap_port, args.smtp_port, args.user, password))
    ok = True
    for part in ("imap", "smtp"):
        status = result.get(part, "not_configured")
        line = "OK" if status == "ok" else f"FAILED ({status}): {result.get(part + '_message', 'not tested')}"
        print(f"{part.upper():5} {line}")
        ok = ok and (status == "ok" or (part == "smtp" and args.smtp_port is None))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
