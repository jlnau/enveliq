"""Waking the Enveliq Android app through the shared push relay.

Google's push service needs one Firebase project and one private key. They live only in the Enveliq push relay (a small Cloudflare Worker, see
`relay/` and docs/PUSH_RELAY.md), never on anyone's own Enveliq server. This server just asks the relay to wake one phone with a tiny message:
the kind ("mail" or "test") and a count. No sender, subject, summary or address is ever sent. The app wakes up and asks Enveliq for the details itself.

The relay's address is built in (`DEFAULT_RELAY`), so there is nothing to set up. Someone who runs their own relay can set ENVELIQ_PUSH_RELAY.
"""
from __future__ import annotations

import json
import os
import re
import urllib.parse
from typing import Any

from . import outbound
from .outbound import OutboundError

DEFAULT_RELAY = ""        # the official relay's address goes here once it is deployed (docs/PUSH_RELAY.md)
ENV = "ENVELIQ_PUSH_RELAY"   # only for someone who runs their own relay (and their own build of the app): their relay's https:// address
DEVICE_TOKEN = re.compile(r"^[A-Za-z0-9:_\-]{20,400}$")


def relay_url() -> str:
    """The relay this server asks. Built in; nobody has to set anything up."""
    v = os.environ.get(ENV, "").strip().rstrip("/")
    if v:
        p = urllib.parse.urlsplit(v)
        if p.scheme == "https" and p.hostname and not p.username and not p.password and not p.query and not p.fragment and len(v) <= 300:
            return v
        return ""
    return DEFAULT_RELAY


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
