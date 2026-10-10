from __future__ import annotations

import secrets
import threading
import time
from dataclasses import dataclass

DEFAULT_MAX_SOURCE_BYTES = 25 * 1024 * 1024
DEFAULT_MAX_PREVIEW_BYTES = 10 * 1024 * 1024
DEFAULT_PREVIEW_TTL_SECONDS = 300
DEFAULT_GLOBAL_RAM_CAP_BYTES = 64 * 1024 * 1024

SAFE_PREVIEW_MIME_TYPES = {
    "image/png",
    "image/jpeg",
    "image/webp",
    "text/plain",
}

# These source types may be accepted by the future isolated renderer. They are
# never sent directly to the browser. PDF pages must be rendered to images;
# office files should be converted to plain text or safe image/PDF derivatives.
PROCESSABLE_SOURCE_MIME_TYPES = {
    "application/pdf",
    "image/png",
    "image/jpeg",
    "image/webp",
    "text/plain",
    "text/csv",
    "application/rtf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


class AttachmentPolicyError(ValueError):
    pass


def _looks_like(mime_type: str, content: bytes | bytearray) -> bool:
    """Check the bytes really are the declared safe type (magic numbers),
    so a mislabelled payload is never served under an image/text type."""
    head = bytes(content[:16])
    if mime_type == "image/png":
        return head.startswith(b"\x89PNG\r\n\x1a\n")
    if mime_type == "image/jpeg":
        return head.startswith(b"\xff\xd8\xff")
    if mime_type == "image/webp":
        return head[:4] == b"RIFF" and head[8:12] == b"WEBP"
    if mime_type == "text/plain":
        try:
            bytes(content).decode("utf-8")
        except UnicodeDecodeError:
            return False
        return b"\x00" not in content
    return False


@dataclass
class PreviewLease:
    lease_id: str
    owner_user_id: str
    account_id: str
    message_id: str
    attachment_id: str
    mime_type: str
    filename: str
    content: bytearray
    created_at: float
    expires_at: float

    @property
    def size_bytes(self) -> int:
        return len(self.content)


class PreviewLeaseStore:
    """RAM-only store for SAFE preview derivatives.

    Raw provider attachments must never be put in this store. The future
    attachment worker should validate and transform the source first, then place
    only a safe derivative (for example a PNG rendered from a PDF page) here.
    No bytes are written to disk by this class.
    """

    def __init__(
        self,
        ttl_seconds: int = DEFAULT_PREVIEW_TTL_SECONDS,
        max_total_bytes: int = DEFAULT_GLOBAL_RAM_CAP_BYTES,
        max_item_bytes: int = DEFAULT_MAX_PREVIEW_BYTES,
    ):
        self.ttl_seconds = ttl_seconds
        self.max_total_bytes = max_total_bytes
        self.max_item_bytes = max_item_bytes
        self.enabled = True
        self._leases: dict[str, PreviewLease] = {}
        self._lock = threading.RLock()

    def configure(
        self,
        *,
        enabled: bool,
        ttl_seconds: int,
        max_total_bytes: int,
        max_item_bytes: int,
    ) -> None:
        """Apply the administrator's attachment policy. Existing leases that no
        longer fit the new limits are wiped immediately."""
        with self._lock:
            self.enabled = enabled
            self.ttl_seconds = ttl_seconds
            self.max_total_bytes = max_total_bytes
            self.max_item_bytes = max_item_bytes
            if not enabled:
                self.clear()
                return
            now = time.monotonic()
            for key, lease in list(self._leases.items()):
                lease.expires_at = min(lease.expires_at, lease.created_at + ttl_seconds)
                if lease.size_bytes > max_item_bytes:
                    self._zero(self._leases.pop(key).content)
            self._purge_expired_locked(now)
            while self._leases and self._total_locked() > max_total_bytes:
                oldest_id = min(self._leases, key=lambda k: self._leases[k].created_at)
                self._zero(self._leases.pop(oldest_id).content)

    @staticmethod
    def _zero(buf: bytearray) -> None:
        for i in range(len(buf)):
            buf[i] = 0

    def _purge_expired_locked(self, now: float) -> None:
        expired = [key for key, lease in self._leases.items() if lease.expires_at <= now]
        for key in expired:
            lease = self._leases.pop(key)
            self._zero(lease.content)

    def _total_locked(self) -> int:
        return sum(lease.size_bytes for lease in self._leases.values())

    def put_safe_preview(
        self,
        *,
        owner_user_id: str,
        account_id: str,
        message_id: str,
        attachment_id: str,
        mime_type: str,
        filename: str,
        content: bytes | bytearray,
    ) -> PreviewLease:
        if not self.enabled:
            raise AttachmentPolicyError("Attachment previews are disabled")
        if mime_type not in SAFE_PREVIEW_MIME_TYPES:
            raise AttachmentPolicyError("Unsafe preview MIME type")
        if not _looks_like(mime_type, content):
            raise AttachmentPolicyError("Preview content does not match its declared type")
        if len(content) > self.max_item_bytes:
            raise AttachmentPolicyError("Preview derivative exceeds per-item RAM limit")

        now = time.monotonic()
        with self._lock:
            self._purge_expired_locked(now)
            while self._leases and self._total_locked() + len(content) > self.max_total_bytes:
                oldest_id = min(self._leases, key=lambda k: self._leases[k].created_at)
                old = self._leases.pop(oldest_id)
                self._zero(old.content)
            if self._total_locked() + len(content) > self.max_total_bytes:
                raise AttachmentPolicyError("Preview RAM cap exceeded")

            lease = PreviewLease(
                lease_id=secrets.token_urlsafe(24),
                owner_user_id=owner_user_id,
                account_id=account_id,
                message_id=message_id,
                attachment_id=attachment_id,
                mime_type=mime_type,
                filename=filename,
                content=bytearray(content),
                created_at=now,
                expires_at=now + self.ttl_seconds,
            )
            self._leases[lease.lease_id] = lease
            return lease

    def get(self, lease_id: str) -> PreviewLease:
        now = time.monotonic()
        with self._lock:
            self._purge_expired_locked(now)
            try:
                return self._leases[lease_id]
            except KeyError as exc:
                raise KeyError(lease_id) from exc

    def get_for_owner(self, lease_id: str, owner_user_id: str) -> PreviewLease:
        """Fetch a lease only for the user it was created for. Any preview
        endpoint must use this, never get(), so one user cannot read another
        user's attachment by guessing or replaying a lease id."""
        lease = self.get(lease_id)
        if not secrets.compare_digest(lease.owner_user_id, owner_user_id):
            raise KeyError(lease_id)
        return lease

    def delete(self, lease_id: str) -> None:
        with self._lock:
            lease = self._leases.pop(lease_id, None)
            if lease is not None:
                self._zero(lease.content)

    def purge_message(self, account_id: str, message_id: str) -> int:
        with self._lock:
            ids = [
                key for key, lease in self._leases.items()
                if lease.account_id == account_id and lease.message_id == message_id
            ]
            for key in ids:
                lease = self._leases.pop(key)
                self._zero(lease.content)
            return len(ids)

    def purge_account(self, account_id: str) -> int:
        with self._lock:
            ids = [key for key, lease in self._leases.items() if lease.account_id == account_id]
            for key in ids:
                self._zero(self._leases.pop(key).content)
            return len(ids)

    def clear(self) -> None:
        with self._lock:
            for lease in self._leases.values():
                self._zero(lease.content)
            self._leases.clear()

    def stats(self) -> dict[str, int]:
        with self._lock:
            self._purge_expired_locked(time.monotonic())
            return {
                "active_leases": len(self._leases),
                "bytes_in_ram": self._total_locked(),
                "ttl_seconds": self.ttl_seconds,
                "max_total_bytes": self.max_total_bytes,
                "max_item_bytes": self.max_item_bytes,
            }
