"""Waking the Enveliq Android app through the shared push relay.

Google's push service needs one Firebase project and one private key. They live only in the Enveliq push relay (a small Cloudflare Worker, see
`relay/` and docs/PUSH_RELAY.md), never on anyone's own Enveliq server. This server just asks the relay to wake one phone with a tiny message:
the kind ("mail" or "test") and a count. No sender, subject, summary or address is ever sent. The app wakes up and asks Enveliq for the details itself.

The official Enveliq images are built with the relay's address (the build setting ENVELIQ_PUSH_RELAY, see docs/PUSH_RELAY.md), so on an official
install there is nothing to set up. The address is not in this source code: a fork or a build from source has none, so Google push is simply not
offered until whoever runs it sets ENVELIQ_PUSH_RELAY to their own relay.
"""
from __future__ import annotations

import json
import os
import re
import urllib.parse
from typing import Any

from . import outbound
from .outbound import OutboundError

ENV = "ENVELIQ_PUSH_RELAY"   # the relay's https:// address: put into the official images when they are built, or set by someone running their own relay
DEVICE_TOKEN = re.compile(r"^[A-Za-z0-9:_\-]{20,400}$")


def relay_url() -> str:
    """The relay this server asks, or "" when there is none (then Google push is not offered)."""
    v = os.environ.get(ENV, "").strip().rstrip("/")
    if v:
        p = urllib.parse.urlsplit(v)
        if p.scheme == "https" and p.hostname and not p.username and not p.password and not p.query and not p.fragment and len(v) <= 300:
            return v
        return ""
    return ""


def send(vault: Any, device_token: str, data: dict[str, str]) -> str:
    """Ask the relay to wake one phone. Returns "sent", or "gone" when Google says the phone no longer has the app. Raises OutboundError otherwise."""
    base = relay_url()
    if not base:
        raise OutboundError("not_set", "Android alerts are not available on this server yet.")
    if not DEVICE_TOKEN.match(device_token):
        return "gone"
    body: dict[str, Any] = {"token": device_token, "kind": str(data.get("kind", "mail"))}
    if data.get("count"):
        body["count"] = int(data["count"])
    try:
        code, _, reply = outbound.request_full("POST", base + "/v1/push", allow=outbound.listed(vault), json_body=body)
    except OutboundError as err:
        raise OutboundError(err.code, "Could not reach the push relay. " + err.message) from None
    if code == 200:
        return "sent"
    if code == 410:
        return "gone"
    if code == 503:
        raise OutboundError("error", "The push relay is not set up with a Firebase key yet.")
    try:
        result = str(json.loads(reply.decode("utf-8", "replace")).get("result") or "")
    except ValueError:
        result = ""
    raise OutboundError("error", f"The push relay answered with an error ({code}{', ' + result if result else ''}).")
