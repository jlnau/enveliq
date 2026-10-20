"""Reminder channels: where a task reminder can be sent besides the page itself.

Each person turns on the channels they want and fills in one or two fields. Every channel has a Send test button.
Tokens, webhook addresses and keys are write-only: they are stored encrypted and never sent back to the browser.
An administrator can switch a channel off for everyone and decides which addresses on the local network may be called.

Messages hold the task title (or just a count, if the person chose "Keep titles private"). Never email text, never the
sender's address.
"""
from __future__ import annotations

import re
import threading
import time
import urllib.parse
from typing import Any, Callable

from . import outbound
from .outbound import OutboundError

RECORD_PREFIX = "notify:"
SETTINGS_DEFAULT = {"morning_on": True, "morning_time": "08:00", "due_on": True, "repeat_hours": 2, "repeat_max": 2,
                    "quiet_on": True, "quiet_from": "21:00", "quiet_to": "07:00", "show_titles": True,
                    "mail_on": False, "mail_details": False, "mail_filter": "all", "mail_muted_accounts": [], "digest_mail": False}
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_TIME = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def _clean(value: Any, limit: int) -> str:
    return _CONTROL.sub("", str(value or "")).strip()[:limit]


def _url(value: str, label: str, *, https_only: bool = False) -> str:
    v = _clean(value, 300).rstrip("/")
    p = urllib.parse.urlsplit(v)
    if p.scheme not in ("https",) + (() if https_only else ("http",)) or not p.hostname or p.username or p.password or re.search(r"\s", v):
        raise ValueError(f"{label} must be a full address starting with {'https://' if https_only else 'http:// or https://'}")
    return v


def f(key: str, label: str, *, secret: bool = False, required: bool = True, placeholder: str = "", help: str = "", default: str = "") -> dict[str, Any]:
    return {"key": key, "label": label, "secret": secret, "required": required, "placeholder": placeholder, "help": help, "default": default}


# Each channel: its fields, how to check them, a few setup steps for the screen, and the function that sends.
CHANNELS: dict[str, dict[str, Any]] = {}


def channel(cid: str, label: str, blurb: str, fields: list[dict[str, Any]], steps: list[str], local_ok: bool = False):
    def wrap(fn: Callable[..., None]) -> Callable[..., None]:
        CHANNELS[cid] = {"id": cid, "label": label, "blurb": blurb, "fields": fields, "steps": steps, "send": fn, "local_ok": local_ok}
        return fn
    return wrap


def _status(code: int) -> None:
    if 200 <= code < 300:
        return
    if code in (401, 403):
        raise OutboundError("refused", "The service refused the login details. Check the token or key.")
    if code == 404:
        raise OutboundError("not_found", "The service did not find that address, topic or room. Check what you typed.")
    if code == 429:
        raise OutboundError("busy", "The service says too many messages were sent. Try again in a minute.")
    raise OutboundError("error", f"The service answered with an error ({code}).")


def _post(url: str, ctx: dict[str, Any], **kw: Any) -> None:
    code, _ = outbound.request(kw.pop("method", "POST"), url, allow=ctx["allow"], **kw)
    _status(code)


# ---------- ntfy ----------
@channel("ntfy", "ntfy", "Phone notifications. Free: use ntfy.sh or run your own.",
         [f("server", "Server", placeholder="https://ntfy.sh", default="https://ntfy.sh", required=False, help="Leave as is to use the free ntfy.sh service, or enter your own server address."),
          f("topic", "Topic", placeholder="enveliq-your-secret-name", help="A private name only you know. Anyone who knows it can read your reminders, so make it long and random."),
          f("token", "Access token", secret=True, required=False, help="Only if your server needs a login.")],
         ["Install the ntfy app on your phone (free).", "In the app, press +, and type a long random topic name.", "Type the same topic name here, then press Save and send a test."], local_ok=True)
def send_ntfy(v: dict[str, Any], note: dict[str, Any], ctx: dict[str, Any]) -> None:
    server = _url(v.get("server") or "https://ntfy.sh", "Server")
    body: dict[str, Any] = {"topic": v["topic"], "title": note["title"], "message": note["body"], "priority": 4 if note.get("priority") == "high" else 3}
    if note.get("url"):
        body["click"] = note["url"]
    _post(server, ctx, json_body=body, headers={"Authorization": "Bearer " + v["token"]} if v.get("token") else None)


def _check_ntfy(v: dict[str, str]) -> dict[str, str]:
    out = {"server": _url(v.get("server") or "https://ntfy.sh", "Server"), "topic": _clean(v.get("topic"), 64)}
    if not re.fullmatch(r"[A-Za-z0-9_-]{3,64}", out["topic"]):
        raise ValueError("The topic can use letters, numbers, - and _ (3 to 64 characters).")
    if v.get("token"):
        out["token"] = _clean(v["token"], 200)
    return out


# ---------- Gotify ----------
@channel("gotify", "Gotify", "Phone notifications from your own Gotify server.",
         [f("server", "Server address", placeholder="http://192.168.1.20:8080"), f("token", "Application token", secret=True, help="Create an application in Gotify and copy its token.")],
         ["In Gotify open Apps, press Create application and name it Enveliq.", "Copy the token it shows.", "Enter your Gotify address and that token here, then Save and send a test."], local_ok=True)
def send_gotify(v: dict[str, Any], note: dict[str, Any], ctx: dict[str, Any]) -> None:
    _post(_url(v["server"], "Server address") + "/message", ctx, json_body={"title": note["title"], "message": note["body"], "priority": 8 if note.get("priority") == "high" else 5},
          headers={"X-Gotify-Key": v["token"]})


def _check_gotify(v: dict[str, str]) -> dict[str, str]:
    return {"server": _url(v.get("server") or "", "Server address"), **({"token": _clean(v["token"], 200)} if v.get("token") else {})}


# ---------- Home Assistant ----------
@channel("home_assistant", "Home Assistant", "A phone notification or a spoken message through your Home Assistant.",
         [f("server", "Home Assistant address", placeholder="http://192.168.1.10:8123"),
          f("token", "Long-lived access token", secret=True, help="Home Assistant: your profile, Security, Long-lived access tokens, Create token."),
          f("service", "Notify service", placeholder="notify.mobile_app_your_phone", default="notify.notify", help="The name of the service that should send it. Find it in Home Assistant under Developer tools, Actions, by typing notify.")],
         ["In Home Assistant open your profile (bottom left), then Security.", "Under Long-lived access tokens press Create token and copy it.", "Enter your Home Assistant address, the token and the notify service name (for example notify.mobile_app_your_phone).", "Press Save and send a test."], local_ok=True)
def send_ha(v: dict[str, Any], note: dict[str, Any], ctx: dict[str, Any]) -> None:
    name = v["service"].split(".", 1)[1]
    data: dict[str, Any] = {"title": note["title"], "message": note["body"]}
    if note.get("url"):
        data["data"] = {"url": note["url"], "clickAction": note["url"]}
    _post(_url(v["server"], "Home Assistant address") + f"/api/services/notify/{name}", ctx, json_body=data, headers={"Authorization": "Bearer " + v["token"]})


def _check_ha(v: dict[str, str]) -> dict[str, str]:
    service = _clean(v.get("service") or "notify.notify", 80)
    if not re.fullmatch(r"notify\.[a-z0-9_]{1,64}", service):
        raise ValueError("The notify service looks like notify.mobile_app_your_phone")
    return {"server": _url(v.get("server") or "", "Home Assistant address"), "service": service, **({"token": _clean(v["token"], 600)} if v.get("token") else {})}


# ---------- Discord ----------
@channel("discord", "Discord", "A message in a private Discord channel.",
         [f("webhook", "Webhook address", secret=True, placeholder="https://discord.com/api/webhooks/…")],
         ["In Discord open the channel's settings (the gear), then Integrations, then Webhooks.", "Press New Webhook, then Copy Webhook URL.", "Paste it here, then Save and send a test."])
def send_discord(v: dict[str, Any], note: dict[str, Any], ctx: dict[str, Any]) -> None:
    text = f"**{note['title']}**\n{note['body']}"[:1900]
    _post(v["webhook"], ctx, json_body={"content": text, "username": "Enveliq", "allowed_mentions": {"parse": []}})


def _check_discord(v: dict[str, str]) -> dict[str, str]:
    w = _clean(v.get("webhook"), 300)
    if w and not re.fullmatch(r"https://(?:discord|discordapp)\.com/api/webhooks/\d{5,25}/[\w-]{20,200}", w):
        raise ValueError("That does not look like a Discord webhook address.")
    return {"webhook": w} if w else {}


# ---------- Telegram ----------
@channel("telegram", "Telegram", "A message from your own Telegram bot.",
         [f("bot_token", "Bot token", secret=True, placeholder="123456789:AA…"), f("chat_id", "Chat id", placeholder="123456789", help="The number of your chat with the bot.")],
         ["In Telegram, message @BotFather and send /newbot. Copy the token it gives you.", "Open your new bot and press Start, then send it any message.", "To find your chat id, message @userinfobot (it replies with your id).", "Enter the token and the chat id here, then Save and send a test."])
def send_telegram(v: dict[str, Any], note: dict[str, Any], ctx: dict[str, Any]) -> None:
    _post(f"https://api.telegram.org/bot{v['bot_token']}/sendMessage", ctx, json_body={"chat_id": v["chat_id"], "text": f"{note['title']}\n{note['body']}"[:3900], "disable_web_page_preview": True})


def _check_telegram(v: dict[str, str]) -> dict[str, str]:
    out: dict[str, str] = {}
    if v.get("bot_token"):
        if not re.fullmatch(r"\d{5,12}:[\w-]{30,60}", _clean(v["bot_token"], 100)):
            raise ValueError("That does not look like a Telegram bot token.")
        out["bot_token"] = _clean(v["bot_token"], 100)
    chat = _clean(v.get("chat_id"), 40)
    if not re.fullmatch(r"-?\d{3,20}|@\w{5,32}", chat):
        raise ValueError("The chat id is a number (for a group it starts with -).")
    out["chat_id"] = chat
    return out


# ---------- Slack ----------
@channel("slack", "Slack", "A message in a Slack channel.",
         [f("webhook", "Incoming webhook address", secret=True, placeholder="https://hooks.slack.com/services/…")],
         ["In Slack open api.slack.com/apps and create an app, then turn on Incoming Webhooks.", "Press Add New Webhook to Workspace and choose the channel.", "Copy the webhook address, paste it here, then Save and send a test."])
def send_slack(v: dict[str, Any], note: dict[str, Any], ctx: dict[str, Any]) -> None:
    _post(v["webhook"], ctx, json_body={"text": f"*{note['title']}*\n{note['body']}"[:3000]})


def _check_slack(v: dict[str, str]) -> dict[str, str]:
    w = _clean(v.get("webhook"), 300)
    if w and not re.fullmatch(r"https://hooks\.slack\.com/services/[\w/-]{20,200}", w):
        raise ValueError("That does not look like a Slack webhook address.")
    return {"webhook": w} if w else {}


# ---------- Pushover ----------
@channel("pushover", "Pushover", "Phone notifications through Pushover (paid app, one-off).",
         [f("user_key", "User key", secret=True), f("app_token", "Application token", secret=True)],
         ["In Pushover copy your User Key from the front page.", "Create an application at pushover.net/apps/build and copy its API token.", "Enter both here, then Save and send a test."])
def send_pushover(v: dict[str, Any], note: dict[str, Any], ctx: dict[str, Any]) -> None:
    form = {"token": v["app_token"], "user": v["user_key"], "title": note["title"][:250], "message": note["body"][:1000], "priority": "1" if note.get("priority") == "high" else "0"}
    if note.get("url"):
        form["url"] = note["url"]
    _post("https://api.pushover.net/1/messages.json", ctx, form=form)


def _check_pushover(v: dict[str, str]) -> dict[str, str]:
    out = {}
    for k in ("user_key", "app_token"):
        if v.get(k):
            if not re.fullmatch(r"[A-Za-z0-9]{20,40}", _clean(v[k], 40)):
                raise ValueError("Pushover keys are 30 letters and numbers.")
            out[k] = _clean(v[k], 40)
    return out


# ---------- Matrix ----------
@channel("matrix", "Matrix", "A message in a Matrix room.",
         [f("server", "Homeserver address", placeholder="https://matrix.example.org"), f("token", "Access token", secret=True, help="For a bot account: Element, Settings, Help & About, Advanced, Access Token."),
          f("room", "Room id", placeholder="!abc123:example.org", help="Element: room settings, Advanced, Internal room ID.")],
         ["Make a bot account (or use your own) and invite it to a room.", "In Element copy the account's access token and the room's internal ID.", "Enter them here, then Save and send a test."], local_ok=True)
def send_matrix(v: dict[str, Any], note: dict[str, Any], ctx: dict[str, Any]) -> None:
    txn = f"enveliq{int(time.time() * 1000)}"
    room = urllib.parse.quote(v["room"], safe="")
    _post(_url(v["server"], "Homeserver address") + f"/_matrix/client/v3/rooms/{room}/send/m.room.message/{txn}", ctx, method="PUT",
          json_body={"msgtype": "m.text", "body": f"{note['title']}\n{note['body']}"}, headers={"Authorization": "Bearer " + v["token"]})


def _check_matrix(v: dict[str, str]) -> dict[str, str]:
    room = _clean(v.get("room"), 200)
    if not re.fullmatch(r"![^\s:]{1,80}:[A-Za-z0-9.\-]{1,100}(?::\d{1,5})?", room):
        raise ValueError("A room id looks like !abc123:example.org")
    return {"server": _url(v.get("server") or "", "Homeserver address"), "room": room, **({"token": _clean(v["token"], 300)} if v.get("token") else {})}


# ---------- generic webhook ----------
@channel("webhook", "Webhook", "Your own automation (Node-RED, n8n, a Home Assistant webhook).",
         [f("url", "Webhook address", secret=True, placeholder="http://192.168.1.10:8123/api/webhook/…", help="Enveliq sends a small JSON message: title, message, priority, url.")],
         ["Create a webhook trigger in your automation tool and copy its address.", "Paste it here, then Save and send a test.", "The message is JSON: {\"title\", \"message\", \"priority\", \"url\"}."], local_ok=True)
def send_webhook(v: dict[str, Any], note: dict[str, Any], ctx: dict[str, Any]) -> None:
    _post(v["url"], ctx, json_body={"title": note["title"], "message": note["body"], "priority": note.get("priority", "normal"), "url": note.get("url")})


def _check_webhook(v: dict[str, str]) -> dict[str, str]:
    return {"url": _url(v["url"], "Webhook address")} if v.get("url") else {}


CHECKS: dict[str, Callable[[dict[str, str]], dict[str, str]]] = {
    "ntfy": _check_ntfy, "gotify": _check_gotify, "home_assistant": _check_ha, "discord": _check_discord, "telegram": _check_telegram,
    "slack": _check_slack, "pushover": _check_pushover, "matrix": _check_matrix, "webhook": _check_webhook,
}


def register_extra(cid: str, spec: dict[str, Any], check: Callable[[dict[str, str]], dict[str, str]]) -> None:
    """Channels that need more than a web request (browser push, email) add themselves here."""
    CHANNELS[cid] = spec
    CHECKS[cid] = check


def clean_time(value: Any, default: str) -> str:
    return value if isinstance(value, str) and _TIME.match(value) else default


class Notifier:
    def __init__(self, vault: Any):
        self.vault = vault
        self._lock = threading.RLock()
        self.mailer: Any = None          # set by the app: lets the Email channel write to the person's own mailbox

    # ---------- administrator ----------
    def admin(self) -> dict[str, Any]:
        saved = self.vault.get_global(outbound.ADMIN_RECORD) or {}
        chans = saved.get("channels") if isinstance(saved.get("channels"), dict) else {}
        return {"channels": {c: chans.get(c) is not False for c in CHANNELS}, "local_hosts": [str(x) for x in (saved.get("local_hosts") or [])][:50],
                "from_environment": outbound.listed(None)}

    def save_admin(self, channels: dict[str, bool] | None, local_hosts: list[str] | None) -> dict[str, Any]:
        with self._lock:
            saved = dict(self.vault.get_global(outbound.ADMIN_RECORD) or {})
            if channels is not None:
                cur = dict(saved.get("channels") or {})
                for c, on in channels.items():
                    if c in CHANNELS:
                        cur[c] = bool(on)
                saved["channels"] = cur
            if local_hosts is not None:
                clean = []
                for h in local_hosts[:50]:
                    h = _clean(h, 100).lower()
                    if not h:
                        continue
                    if re.fullmatch(r"[a-z0-9.\-:/]+", h) is None:
                        raise ValueError(f"'{h}' is not a host name, IP address or network.")
                    clean.append(h)
                saved["local_hosts"] = clean
            self.vault.set_global(outbound.ADMIN_RECORD, saved)
        return self.admin()

    def allow(self) -> list[str]:
        return outbound.listed(self.vault)

    # ---------- a person's own settings ----------
    def _load(self, user_id: str) -> dict[str, Any]:
        raw = self.vault.get_global(RECORD_PREFIX + user_id) or {}
        return {"channels": raw.get("channels") if isinstance(raw.get("channels"), dict) else {},
                "settings": raw.get("settings") if isinstance(raw.get("settings"), dict) else {},
                "state": raw.get("state") if isinstance(raw.get("state"), dict) else {}}

    def _save(self, user_id: str, rec: dict[str, Any]) -> None:
        self.vault.set_global(RECORD_PREFIX + user_id, rec)

    def settings(self, user_id: str) -> dict[str, Any]:
        raw = self._load(user_id)["settings"]
        out = dict(SETTINGS_DEFAULT)
        for k in ("morning_on", "due_on", "quiet_on", "show_titles", "mail_on", "mail_details", "digest_mail"):
            if isinstance(raw.get(k), bool):
                out[k] = raw[k]
        for k in ("morning_time", "quiet_from", "quiet_to"):
            out[k] = clean_time(raw.get(k), SETTINGS_DEFAULT[k])
        for k, lo, hi in (("repeat_hours", 1, 12), ("repeat_max", 0, 5)):
            if isinstance(raw.get(k), int) and not isinstance(raw.get(k), bool):
                out[k] = max(lo, min(hi, raw[k]))
        if raw.get("mail_filter") in ("all", "important", "action"):
            out["mail_filter"] = raw["mail_filter"]
        muted = raw.get("mail_muted_accounts")
        if isinstance(muted, list):
            out["mail_muted_accounts"] = [x for x in muted if isinstance(x, str) and len(x) <= 128][:100]
        return out

    def save_settings(self, user_id: str, body: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            rec = self._load(user_id)
            cur = self.settings(user_id)
            for k, v in body.items():
                if v is None or k not in SETTINGS_DEFAULT:
                    continue
                cur[k] = v
            rec["settings"] = cur
            self._save(user_id, rec)
        return self.settings(user_id)

    def overview(self, user_id: str) -> dict[str, Any]:
        rec = self._load(user_id)
        admin = self.admin()
        out = []
        for cid, spec in CHANNELS.items():
            mine = rec["channels"].get(cid) or {}
            values = mine.get("values") or {}
            fields = []
            for fld in spec["fields"]:
                row = {k: fld[k] for k in ("key", "label", "secret", "required", "placeholder", "help", "default")}
                if fld["secret"]:
                    row["set"] = bool(values.get(fld["key"]))
                    row["value"] = ""
                else:
                    row["value"] = values.get(fld["key"], "")
                fields.append(row)
            item = {"id": cid, "label": spec["label"], "blurb": spec["blurb"], "steps": spec["steps"], "fields": fields,
                    "enabled": bool(mine.get("enabled")), "allowed": admin["channels"].get(cid, True), "configured": bool(values),
                    "last_ok": mine.get("last_ok"), "last_error": mine.get("last_error")}
            if spec.get("describe"):
                item.update(spec["describe"](values, self))
            out.append(item)
        return {"channels": out, "settings": self.settings(user_id)}

    def save_channel(self, user_id: str, cid: str, enabled: bool, values: dict[str, str]) -> None:
        if cid not in CHANNELS:
            raise KeyError(cid)
        with self._lock:
            rec = self._load(user_id)
            mine = dict(rec["channels"].get(cid) or {})
            old = dict(mine.get("values") or {})
            merged = {k: _clean(v, 600) for k, v in values.items() if isinstance(v, str) and k in {fl["key"] for fl in CHANNELS[cid]["fields"]}}
            for fld in CHANNELS[cid]["fields"]:
                if fld["secret"] and not merged.get(fld["key"]) and old.get(fld["key"]):
                    merged[fld["key"]] = old[fld["key"]]                   # a blank secret box keeps the saved one
            if CHANNELS[cid].get("keep"):                     # browser push: devices are added one by one, this only switches it on or off
                if enabled and not old:
                    raise ValueError(CHANNELS[cid]["keep"])
                mine.update(enabled=bool(enabled) and bool(old))
                rec["channels"][cid] = mine
                self._save(user_id, rec)
                return
            checked = CHECKS[cid](merged)
            if CHANNELS[cid].get("post"):
                checked = CHANNELS[cid]["post"](self, user_id, checked)
            for fld in CHANNELS[cid]["fields"]:
                if fld["required"] and not checked.get(fld["key"]) and not fld["default"]:
                    raise ValueError(f"{fld['label']} is needed.")
            mine.update(enabled=bool(enabled), values=checked, last_error=None if checked != old else mine.get("last_error"))
            rec["channels"][cid] = mine
            self._save(user_id, rec)

    def get_values(self, user_id: str, cid: str) -> dict[str, str]:
        return dict((self._load(user_id)["channels"].get(cid) or {}).get("values") or {})

    def set_values(self, user_id: str, cid: str, values: dict[str, str], enabled: bool | None = None) -> None:
        with self._lock:
            rec = self._load(user_id)
            mine = dict(rec["channels"].get(cid) or {})
            mine["values"] = values
            if enabled is not None:
                mine["enabled"] = enabled
            if not values:
                mine["enabled"] = False
            rec["channels"][cid] = mine
            self._save(user_id, rec)

    def clear_channel(self, user_id: str, cid: str) -> None:
        with self._lock:
            rec = self._load(user_id)
            rec["channels"].pop(cid, None)
            self._save(user_id, rec)

    def _record_result(self, user_id: str, cid: str, error: str | None) -> None:
        with self._lock:
            rec = self._load(user_id)
            mine = rec["channels"].get(cid)
            if mine is None:
                return
            mine["last_ok"] = None if error else time.time()
            mine["last_error"] = error
            self._save(user_id, rec)

    def get_state(self, user_id: str) -> dict[str, Any]:
        return self._load(user_id)["state"]

    def set_state(self, user_id: str, state: dict[str, Any]) -> None:
        with self._lock:
            rec = self._load(user_id)
            rec["state"] = state
            self._save(user_id, rec)

    def enabled_channels(self, user_id: str) -> list[str]:
        rec = self._load(user_id)
        admin = self.admin()["channels"]
        return [c for c, m in rec["channels"].items() if c in CHANNELS and m.get("enabled") and admin.get(c, True) and m.get("values")]

    def has_any(self, user_id: str) -> bool:
        return bool(self.enabled_channels(user_id))

    # ---------- sending ----------
    def send_one(self, user_id: str, cid: str, note: dict[str, Any], *, force: bool = False) -> None:
        """Send to one channel. Raises OutboundError with something the person can act on."""
        if cid not in CHANNELS:
            raise OutboundError("unknown", "Unknown channel.")
        if not self.admin()["channels"].get(cid, True):
            raise OutboundError("switched_off", "Your administrator has switched this channel off.")
        mine = self._load(user_id)["channels"].get(cid) or {}
        if not mine.get("values"):
            raise OutboundError("not_set", "Fill in the details and save first.")
        if not force and not mine.get("enabled"):
            raise OutboundError("not_on", "This channel is switched off.")
        values = {fl["key"]: (mine["values"].get(fl["key"]) or fl["default"]) for fl in CHANNELS[cid]["fields"]}
        note = {**note, "title": _clean(note.get("title"), 120) or "Enveliq", "body": _clean(note.get("body"), 600)}
        try:
            CHANNELS[cid]["send"](values, note, {"allow": self.allow(), "user_id": user_id, "vault": self.vault, "notifier": self, "mailer": self.mailer})
        except OutboundError as err:
            self._record_result(user_id, cid, err.message)
            raise
        except Exception:
            self._record_result(user_id, cid, "Sending failed.")
            raise OutboundError("error", "Sending failed.") from None
        self._record_result(user_id, cid, None)

    def send_all(self, user_id: str, note: dict[str, Any]) -> dict[str, str | None]:
        """Send to every channel the person has on. Returns {channel: None when sent, else the problem}."""
        results: dict[str, str | None] = {}
        for cid in self.enabled_channels(user_id):
            try:
                self.send_one(user_id, cid, note)
                results[cid] = None
            except OutboundError as err:
                results[cid] = err.message
        return results
