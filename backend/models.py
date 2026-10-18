from __future__ import annotations

import ipaddress
import json
import re
from typing import Annotated, Any, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, SecretStr, StrictBool, StringConstraints, field_validator

_HOSTNAME = re.compile(r"^(?=.{1,253}$)(?!-)[A-Za-z0-9-]{1,63}(?<!-)(\.(?!-)[A-Za-z0-9-]{1,63}(?<!-))*\.?$")
_EMAIL = re.compile(r"^[^@\s<>\"'`]{1,64}@[^@\s<>\"'`]{1,255}$")
_MAX_SETTINGS_DEPTH = 8


def validate_host(value: str | None) -> str | None:
    """A bare hostname or IP address. No scheme, path, port, credentials or
    whitespace, so the value cannot smuggle a URL or command fragment into a
    future provider connection."""
    if value is None or value == "":
        return None
    candidate = value.strip("[]")
    try:
        ipaddress.ip_address(candidate)
        return candidate
    except ValueError:
        pass
    if not _HOSTNAME.match(value):
        raise ValueError("must be a hostname or IP address, without scheme, port or path")
    return value


def _depth(value: Any, level: int = 0) -> int:
    if isinstance(value, dict):
        return max([_depth(v, level + 1) for v in value.values()] or [level + 1])
    if isinstance(value, list):
        return max([_depth(v, level + 1) for v in value] or [level + 1])
    return level


# The colour a person may give a mailbox's label. The page turns each name into a hue; nothing else is accepted.
MAILBOX_COLORS = ("blue", "green", "orange", "pink", "red", "teal", "purple", "lime")


def validate_settings_blob(value: dict[str, Any]) -> dict[str, Any]:
    if "color" in value and value["color"] not in MAILBOX_COLORS + ("", None):
        raise ValueError("unknown mailbox colour")
    if len(json.dumps(value, default=str)) > 50_000:
        raise ValueError("settings payload too large")
    if _depth(value) > _MAX_SETTINGS_DEPTH:
        raise ValueError("settings payload nested too deeply")
    return value


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class UnlockRequest(StrictModel):
    passphrase: SecretStr = Field(min_length=1, max_length=512)


class AccountCreate(StrictModel):
    provider: str = Field(min_length=1, max_length=64)
    display_name: str = Field(min_length=1, max_length=128)
    email_address: str = Field(min_length=3, max_length=320)
    auth_method: Literal["oauth", "imap", "proton_bridge"]
    server: str | None = Field(default=None, max_length=255)
    port: int | None = Field(default=None, ge=1, le=65535)
    username: str | None = Field(default=None, max_length=320)
    password: SecretStr | None = Field(default=None, max_length=1024)
    oauth_refresh_token: SecretStr | None = Field(default=None, max_length=4096)
    settings: dict[str, Any] = Field(default_factory=dict)

    @field_validator("settings")
    @classmethod
    def settings_size(cls, value: dict[str, Any]) -> dict[str, Any]:
        return validate_settings_blob(value)

    @field_validator("server")
    @classmethod
    def server_is_host(cls, value: str | None) -> str | None:
        return validate_host(value)

    @field_validator("email_address")
    @classmethod
    def email_shape(cls, value: str) -> str:
        if not _EMAIL.match(value):
            raise ValueError("must be an email address")
        return value


class AccountPatch(StrictModel):
    # Omitting a field, or sending null, leaves it unchanged. Credentials can
    # be replaced here but never cleared; disconnect the account instead.
    display_name: str | None = Field(default=None, min_length=1, max_length=128)
    server: str | None = Field(default=None, max_length=255)
    port: int | None = Field(default=None, ge=1, le=65535)
    username: str | None = Field(default=None, max_length=320)
    password: SecretStr | None = Field(default=None, min_length=1, max_length=1024)
    oauth_refresh_token: SecretStr | None = Field(default=None, min_length=1, max_length=4096)
    settings: dict[str, Any] | None = None

    @field_validator("settings")
    @classmethod
    def settings_size(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        return None if value is None else validate_settings_blob(value)

    @field_validator("server")
    @classmethod
    def server_is_host(cls, value: str | None) -> str | None:
        return validate_host(value)


class UpdateNoticeBody(StrictModel):
    enabled: StrictBool


class GlobalSettings(StrictModel):
    llm_provider: str = Field(min_length=1, max_length=64)
    endpoint: str | None = Field(default=None, max_length=512)
    model: str | None = Field(default=None, max_length=128)
    api_key: SecretStr | None = Field(default=None, max_length=4096)
    allow_cloud_processing: bool = True

    @field_validator("endpoint")
    @classmethod
    def endpoint_is_http_url(cls, value: str | None) -> str | None:
        """Plain http(s) URL only: no other schemes (file:, gopher:...), no
        embedded credentials, no fragments. Private-network addresses stay
        allowed because local LLMs (Ollama, LAN servers) are a supported setup."""
        if value is None or value == "":
            return None
        parts = urlsplit(value)
        if parts.scheme not in {"http", "https"} or not parts.hostname:
            raise ValueError("must be an http:// or https:// URL")
        if parts.username or parts.password:
            raise ValueError("must not contain credentials; use the API key field")
        if parts.fragment:
            raise ValueError("must not contain a #fragment")
        validate_host(parts.hostname)
        return value


class RetainedAttachmentRef(StrictModel):
    id: str = Field(min_length=1, max_length=128)
    filename: str = Field(min_length=1, max_length=512)
    mime_type: str = Field(min_length=1, max_length=255)
    size_bytes: int = Field(ge=0, le=100 * 1024 * 1024)
    summary: str | None = Field(default=None, max_length=10_000)
    preview_kind: Literal["pdf", "image", "text", "summary_only"] = "summary_only"
    # Provider-specific opaque locator. This is encrypted at rest and stripped
    # from browser-facing responses. It is not attachment content.
    remote_locator: str = Field(min_length=1, max_length=2048)


class ResolveMessageRequest(StrictModel):
    outcome: Literal["reviewed", "archived", "binned", "expired"]


class AttachmentPolicyPatch(StrictModel):
    preview_enabled: bool = True
    max_source_bytes: int = Field(default=25 * 1024 * 1024, ge=1 * 1024 * 1024, le=100 * 1024 * 1024)
    max_preview_bytes: int = Field(default=10 * 1024 * 1024, ge=1 * 1024 * 1024, le=50 * 1024 * 1024)
    preview_ttl_seconds: int = Field(default=300, ge=30, le=1800)
    global_ram_cap_bytes: int = Field(default=64 * 1024 * 1024, ge=8 * 1024 * 1024, le=512 * 1024 * 1024)


class SuggestedTask(StrictModel):
    title: str = Field(min_length=1, max_length=300)
    detail: str | None = Field(default=None, max_length=2000)
    due: str | None = Field(default=None, max_length=64)


class AttachmentPart(StrictModel):
    """One headed part of the summary of a long file."""
    title: str = Field(default="", max_length=120)
    text: str = Field(max_length=2500)


class AttachmentSummary(StrictModel):
    """What Enveliq keeps about one attached file: its name and what the AI wrote about it. Never the file or its text."""
    attachment_id: str | None = Field(default=None, max_length=128)
    filename: str = Field(min_length=1, max_length=512)
    summary: str = Field(default="", max_length=10_000)           # the one-line summary
    index: int | None = Field(default=None, ge=0, le=999)          # the file's place in the email, so View opens the right one
    mime_type: str | None = Field(default=None, max_length=255)
    size_bytes: int | None = Field(default=None, ge=0, le=1_000_000_000)
    pages: int | None = Field(default=None, ge=0, le=1_000_000)
    state: Literal["reading", "done", "failed", "skipped"] = "done"
    reason: str | None = Field(default=None, max_length=300)       # plain words for a file that was not summarised
    note: str | None = Field(default=None, max_length=300)         # for example that only the first pages were read
    parts: list[AttachmentPart] = Field(default_factory=list, max_length=8)


_HEADER_UNSAFE = re.compile(r"[\r\n\x00]")
_MESSAGE_ID = re.compile(r"^<[^<>\s]{1,994}>$")


def header_safe(value: str | None) -> str | None:
    """Values that will be written into outgoing mail headers must never
    contain CR, LF or NUL: one injected line break lets an attacker add
    recipients (Bcc) or rewrite the message."""
    if value is not None and _HEADER_UNSAFE.search(value):
        raise ValueError("must not contain line breaks or NUL characters")
    return value


class ReplyContext(StrictModel):
    """What a reply needs, captured when the email is processed.

    reply_to       Reply-To if present, otherwise From, exactly as received.
                   For alias services (Proton Pass, SimpleLogin, Firefox
                   Relay, Hide My Email) this is the long reverse-alias
                   address and must be kept verbatim.
    delivered_to   The address of ours the email was sent to. If it is one
                   of the account's sending identities the reply comes from
                   it; if it is a forwarding alias the reply comes from the
                   mailbox and the alias service rewrites the sender.
    via_alias      Name of the alias service, when the email came through one.
    message_id / references   For In-Reply-To / References threading.
    cc / also_to   The other people on the original email (Cc, and the rest of To), as bare
                   addresses without our own, so "Reply all" can fill them in. Names are not kept.
    """

    reply_to: str = Field(min_length=3, max_length=998)
    delivered_to: str | None = Field(default=None, max_length=320)
    via_alias: str | None = Field(default=None, max_length=64)
    message_id: str | None = Field(default=None, max_length=998)
    references: list[str] = Field(default_factory=list, max_length=50)
    cc: list[str] = Field(default_factory=list, max_length=20)
    also_to: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("cc", "also_to")
    @classmethod
    def other_people(cls, values: list[str]) -> list[str]:
        """Other people on the original email, kept as bare addresses only (for Reply all)."""
        for v in values:
            header_safe(v)
            if not _EMAIL.match(v) or len(v) > 320:
                raise ValueError("must be email addresses")
        return values

    @field_validator("reply_to", "delivered_to")
    @classmethod
    def address_shape(cls, value: str | None) -> str | None:
        header_safe(value)
        if value is not None and not _EMAIL.match(value):
            raise ValueError("must be an email address")
        return value

    @field_validator("via_alias")
    @classmethod
    def alias_name_safe(cls, value: str | None) -> str | None:
        return header_safe(value)

    @field_validator("message_id")
    @classmethod
    def message_id_shape(cls, value: str | None) -> str | None:
        header_safe(value)
        if value is not None and not _MESSAGE_ID.match(value):
            raise ValueError("must look like <id@host>")
        return value

    @field_validator("references")
    @classmethod
    def references_shape(cls, value: list[str]) -> list[str]:
        for ref in value:
            header_safe(ref)
            if not _MESSAGE_ID.match(ref):
                raise ValueError("each reference must look like <id@host>")
        return value


class Unsubscribe(StrictModel):
    """Where to unsubscribe from a newsletter, found in its List-Unsubscribe header (see mail/unsub.py).
    The web address was checked to be a plain public http(s) link. Enveliq never opens it: the person's browser does."""

    url: str | None = Field(default=None, max_length=2000)
    mailto: str | None = Field(default=None, max_length=320)
    subject: str | None = Field(default=None, max_length=200)
    host: str = Field(max_length=255)
    source: Literal["header", "body"] = "header"


class ScamReason(StrictModel):
    """One plain-words thing that looks odd about an email (see mail/scamcheck.py). Only host names appear in it, never a whole link."""

    code: str = Field(max_length=40)
    text: str = Field(max_length=300)
    key: str = Field(max_length=300)


class ScamWarning(StrictModel):
    """A calm "be careful" flag found by plain code (never by the AI)."""

    reasons: list[ScamReason] = Field(min_length=1, max_length=4)


class RetainedMessageCreate(StrictModel):
    # Intentionally no raw body / HTML / binary attachment fields.
    subject: str = Field(max_length=998)
    sender_display: str | None = Field(default=None, max_length=320)
    sender_address: str | None = Field(default=None, max_length=320)
    summary: str = Field(max_length=10_000)
    category: str | None = Field(default=None, max_length=128)
    priority: Literal["low", "normal", "high"] = "normal"
    action_required: bool = False
    # When the email was sent (from its Date header), as a Unix timestamp.
    received_at: float | None = Field(default=None, ge=0, le=4_102_444_800)
    # Typed, size-bounded structures rather than free-form dicts, so raw
    # message content cannot be parked under an arbitrary key name.
    suggested_task: SuggestedTask | None = None
    attachments: list[RetainedAttachmentRef] = Field(default_factory=list, max_length=100)
    attachment_summaries: list[AttachmentSummary] = Field(default_factory=list, max_length=100)
    # Whether the email has attached files, for the paperclip in the list. Only a yes/no and a number: never a name or any content.
    # `attachment_count` stays None until the whole email has been read once (when its summary is made); before that it is a guess from the headers.
    has_attachments: bool = False
    # A new email is kept out of the inbox list until its summary (and the summaries of its files) are ready. Cleared when that is done,
    # or when it has failed for good. Only ever true for unread mail that is waiting in the AI queue.
    ai_pending: bool = False
    attachment_count: int | None = Field(default=None, ge=0, le=100)
    # Needed for "View email" (fetch the original on demand, never stored)
    # and "Reply". The locator is an opaque provider id (IMAP UID + folder,
    # Gmail/Graph message id): encrypted at rest, never sent to the browser.
    reply_context: ReplyContext | None = None
    unsubscribe: Unsubscribe | None = None
    scam_warning: ScamWarning | None = None
    source_locator: str | None = Field(default=None, min_length=1, max_length=2048)
    # "unread" = in the inbox list; "reviewed" / "archived" = a card kept for a
    # few days after the item was handled (see backend/mail/review.py).
    state: Literal["unread", "reviewed", "archived"] = "unread"
    resolved_at: float | None = Field(default=None, ge=0, le=4_102_444_800)
    # Listed by the "All emails" switch (recent mail that is not in the unread list).
    from_all_mail: bool = False
    # A search result the person kept (Find any email): shown in Found emails until this Unix time, or until Reviewed.
    found_until: float | None = Field(default=None, ge=0, le=4_102_444_800)
    # The mail service's own tags (labels, keywords) on this email: names only, kept in step with the mailbox (see backend/mail/tags.py).
    tags: list[Annotated[str, StringConstraints(min_length=1, max_length=40)]] = Field(default_factory=list, max_length=20)
    # When you last replied to this email from Enveliq (a Unix timestamp).
    replied_at: float | None = Field(default=None, ge=0, le=4_102_444_800)
    # Snoozed: kept out of the inbox list until this Unix time. Only Enveliq's own list changes; the real mailbox is left alone.
    snoozed_until: float | None = Field(default=None, ge=0, le=4_102_444_800)
