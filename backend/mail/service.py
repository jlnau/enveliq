"""Mailbox operations built on the Bridge client: sync, view, reply, resolve."""
from __future__ import annotations

import logging
import re
import threading
import time
from email.message import EmailMessage
from email.policy import SMTP as SMTP_POLICY
from email.utils import format_datetime, make_msgid
from datetime import datetime, timezone
import base64
from email.headerregistry import Address
from email.utils import parseaddr
from typing import Any

from ..models import RetainedMessageCreate
from .bridge import Bridge, Target, locator, parse_folder_locator, parse_locator
from .errors import BridgeError
from . import attach_service, llm_providers, marks, review
from . import microsoft as ms
from .llm import LlmConfig, Summariser
from ..reporting import NULL, Reporter

AI_CONFIG_RECORD = "ai_config"
MAIL_METHODS = ("proton_bridge", "imap")   # account types that sync
from . import scamcheck
from . import subscriptions as subscriptions_mod
from .parse import _addresses, clean, forward_files, forward_quote, parse_headers, received_at_of, render_original, reply_quote, sending_identities, summarise_headers

log = logging.getLogger("enveliq.mail")
PLACEHOLDER_SUMMARY = "Not summarised yet."
_ANGLE_ID = re.compile(r"^<[^<>\s]{1,994}>$")


def target_for(account: dict[str, Any], microsoft: Any = None) -> Target:
    method = account.get("auth_method")
    if method not in MAIL_METHODS:
        raise BridgeError("not_configured", "This kind of account cannot sync in this version.")
    settings = account.get("settings") or {}
    if method == "imap" and settings.get("auth") == "microsoft":
        # Microsoft's servers are fixed here, whatever the record says, so a sign-in token can only ever go to Microsoft.
        if microsoft is None:
            raise BridgeError("ms_not_set_up", ms.MESSAGES["ms_not_set_up"])
        try:
            token = microsoft.access_token(account)
        except ms.MsError as err:
            raise BridgeError(err.code, err.message) from None
        return Target(host=ms.IMAP_HOST, imap_port=ms.IMAP_PORT, smtp_port=ms.SMTP_PORT, username=str(account.get("email_address") or ""), password=token,
                      kind="imap", auth="xoauth2", imap_security="ssl", smtp_host=ms.SMTP_HOST, smtp_security="starttls")
    smtp_port = settings.get("smtp_port")
    common: dict[str, Any] = dict(
        host=str(account.get("server") or ""),
        imap_port=account.get("port") if isinstance(account.get("port"), int) else 0,
        smtp_port=smtp_port if isinstance(smtp_port, int) and not isinstance(smtp_port, bool) else None,
        username=str(account.get("username") or ""),
        password=str(account.get("password") or ""),
    )
    if method == "imap":
        return Target(**common, kind="imap",
                      imap_security=str(settings.get("imap_security") or "ssl"),
                      smtp_host=str(settings.get("smtp_host") or "") or None,
                      smtp_security=str(settings.get("smtp_security") or "ssl"),
                      smtp_username=str(settings.get("smtp_username") or "") or None)
    return Target(**common)


class AccountLocks:
    """One mailbox operation at a time per account."""

    def __init__(self) -> None:
        self._guard = threading.Lock()
        self._locks: dict[str, threading.Lock] = {}

    def acquire(self, account_id: str) -> threading.Lock:
        with self._guard:
            lock = self._locks.setdefault(account_id, threading.Lock())
        if not lock.acquire(blocking=False):
            raise BridgeError("busy", "This mailbox is already syncing. Try again in a moment.")
        return lock


SENT_FIELDS = "FROM TO CC SUBJECT DATE MESSAGE-ID"
_CTRL = re.compile(r"[\x00-\x1f\x7f]")
_MIME = re.compile(r"^[a-z0-9][a-z0-9.+-]{0,60}/[a-z0-9][a-z0-9.+-]{0,100}$")


class MailService:
    def __init__(self, bridge: Bridge, summariser: Summariser | None = None, reporter: Reporter | None = None):
        self.bridge = bridge
        self.reporter = reporter or NULL
        self.summariser = summariser or Summariser()
        self.env_ai = self.summariser.config      # set by the server's environment
        self.microsoft: Any = None                # set by the application: gives access tokens for Microsoft mailboxes
        self.trips: Any = None                    # set by the application: files bookings found in summaries (mail/trips.py)
        self.subscriptions: Any = None            # set by the application: files subscription facts found in summaries (mail/subscriptions.py)
        self.shipments: Any = None                # set by the application: files order facts found in summaries (mail/shipping.py)
        self.waits: Any = None                    # set by the application: notes for sent emails that wait on an answer (mail/waiting.py)
        self.holds: Any = None                    # set by the application: (account, message) pairs that have an open task and must not be removed
        self.check_id: Any = None                 # set by the application: the id of the mailbox that is the check address (mail/checkbox.py)
        self.on_people: Any = None                # set by the application: told which senders were seen, to build the address book
        self.tags_sync: Any = None                # set by the application: brings the emails' tags in line with the mailbox (mail/tags.py)
        self.on_new: Any = None                   # set by the application: told which emails just arrived (sender and subject), to apply the person's rules
        self.ai_source = "environment" if self.env_ai.enabled else "none"
        self.locks = AccountLocks()
        self.hold_new_mail = True                 # new mail waits out of the inbox list until its summary and files are ready
        self.on_pending: Any = None               # set by the application: (account, [message ids]) put in the AI queue
        self.retries: dict[str, list[float]] = {}   # unread emails still without a summary: message id -> [automatic tries so far, earliest next try]; ids only
        self.problems: dict[str, str] = {}        # why the last attempt on an email failed, in plain words (message id -> reason); never email content

    def _held(self, account: dict[str, Any]) -> set[tuple[str, str]]:
        try:
            return set(self.holds(account.get("owner_user_id"))) if self.holds else set()
        except Exception:
            return set()

    def refresh_ai(self, vault: Any) -> None:
        """Pick the AI settings in force: the server environment wins, otherwise
        the encrypted settings an administrator saved in the app."""
        if self.env_ai.enabled:
            self.summariser.config, self.ai_source = self.env_ai, "environment"
            return
        saved = vault.get_global(AI_CONFIG_RECORD) or {}
        if saved.get("url") and saved.get("model"):
            self.summariser.config = LlmConfig(url=str(saved["url"]), model=str(saved["model"]), api_key=str(saved.get("api_key") or ""),
                                               allowed_hosts=self.env_ai.allowed_hosts, provider=str(saved.get("provider") or ""))
            self.ai_source = "saved"
        else:
            self.summariser.config, self.ai_source = LlmConfig(), "none"

    # ---------- sync ----------

    def is_check_address(self, account: dict[str, Any]) -> bool:
        try:
            return bool(self.check_id and account.get("id") == self.check_id())
        except Exception:
            return False

    def _not_check_address(self, account: dict[str, Any]) -> None:
        """The check address is for forwarded emails only. Nothing in it is ever listed or kept for anyone."""
        if self.is_check_address(account):
            raise BridgeError("check_address", "This mailbox is the check address, so it is not read as an inbox.")

    def sync(self, vault: Any, account: dict[str, Any], **kw: Any) -> dict[str, int]:
        """Sync one mailbox and report how it went (counts and timing only)."""
        self._not_check_address(account)
        started = time.monotonic()
        try:
            result = self._sync(vault, account, **kw)
        except BridgeError as err:
            if err.code != "busy":
                self.reporter.event("sync_failed", mailbox=account["id"], code=err.code, duration_ms=(time.monotonic() - started) * 1000)
            raise
        except Exception:
            self.reporter.event("sync_failed", mailbox=account["id"], code="error", duration_ms=(time.monotonic() - started) * 1000)
            raise
        self.reporter.event("sync_completed", mailbox=account["id"], added=result["added"], removed=result["removed"], duration_ms=(time.monotonic() - started) * 1000)
        self.enqueue_held(vault, account)
        self.enqueue_unsummarised(vault, account)
        return result

    # ---------- the AI queue: new mail waits for its summary ----------

    def _holds(self, account: dict[str, Any]) -> bool:
        """Does new mail of this mailbox wait out of the inbox until the AI has read it? Only when there is a queue to do the reading."""
        return bool(self.hold_new_mail and self.on_pending is not None and self.summariser.enabled and (account.get("settings") or {}).get("ai_summaries"))

    def held_ids(self, vault: Any, account_id: str) -> list[str]:
        return [m["id"] for m in vault.list_messages(account_id) if m.get("ai_pending") and m.get("state", "unread") == "unread"]

    def enqueue_held(self, vault: Any, account: dict[str, Any]) -> int:
        """Put every held email of this mailbox in the AI queue (already queued ones stay where they are). If the AI is no longer
        available, or the mailbox no longer wants summaries, nothing is kept waiting: they are shown as they are."""
        ids = self.held_ids(vault, account["id"])
        if not ids:
            return 0
        if not self._holds(account):
            self.release(vault, account, ids)
            return 0
        try:
            self.on_pending(account, ids)
        except Exception:
            log.warning("could not queue held mail", exc_info=True)
            self.release(vault, account, ids)
            return 0
        return len(ids)

    RETRY_DELAYS = (120.0, 600.0, 1800.0, 7200.0)    # seconds to wait before the 2nd, 3rd, 4th and 5th automatic try; after that Enveliq says why it stopped
    RETRY_PER_PASS = 20

    def unsummarised(self, vault: Any, account_id: str) -> list[dict[str, Any]]:
        """Unread inbox emails that are shown but still have no summary (a failed try, or they arrived before summaries were switched on)."""
        return [m for m in vault.list_messages(account_id) if m.get("state", "unread") == "unread" and str(m.get("summary") or "").startswith(PLACEHOLDER_SUMMARY)
                and m.get("source_locator") and not m.get("from_all_mail") and not m.get("found_until") and not m.get("ai_pending")]

    def enqueue_unsummarised(self, vault: Any, account: dict[str, Any], now: float | None = None) -> int:
        """Put unread emails that still have no summary back in the AI queue, with growing waits between tries and a limit, so a model that
        was busy or switched off a moment ago is not left forgotten. Does nothing while there is a genuine reason it cannot work
        (no model set up, or summaries switched off for this mailbox): `summary_notice` says so."""
        if not self.hold_new_mail or self.on_pending is None or not self.summariser.enabled or not (account.get("settings") or {}).get("ai_summaries"):
            return 0
        now = time.time() if now is None else now
        ids: list[str] = []
        for m in sorted(self.unsummarised(vault, account["id"]), key=lambda m: m.get("received_at") or 0, reverse=True):
            tries, due = self.retries.get(m["id"], [0.0, 0.0])
            if tries > len(self.RETRY_DELAYS) or now < due:
                continue
            self.retries[m["id"]] = [tries + 1, now + self.RETRY_DELAYS[min(int(tries), len(self.RETRY_DELAYS) - 1)]]
            ids.append(m["id"])
            if len(ids) >= self.RETRY_PER_PASS:
                break
        if not ids:
            return 0
        try:
            self.on_pending(account, ids)
        except Exception:
            log.warning("could not queue unsummarised mail", exc_info=True)
            return 0
        return len(ids)

    def retry_now(self, message_id: str) -> None:
        """Someone pressed Generate or Try again: the automatic count starts over for this email."""
        self.retries.pop(message_id, None)

    def summary_notice(self, vault: Any, user_id: str) -> dict[str, Any] | None:
        """Plain words about unread emails that have no summary and why, or None when there is nothing to say. Never email content."""
        count, reasons = 0, []
        for account in vault.list_accounts():
            if account.get("owner_user_id") != user_id or self.is_check_address(account):
                continue
            left = self.unsummarised(vault, account["id"])
            if not left:
                continue
            count += len(left)
            if not self.summariser.enabled:
                reasons.append("No AI model is set up yet. An administrator can add one under Administration, AI model.")
            elif not (account.get("settings") or {}).get("ai_summaries"):
                reasons.append("AI summaries are switched off for this mailbox. Turn them on in Settings.")
            else:
                stuck = [m for m in left if self.retries.get(m["id"], [0.0, 0.0])[0] > len(self.RETRY_DELAYS)]
                if stuck:
                    why = next((self.problems[m["id"]] for m in stuck if m["id"] in self.problems), "The AI model did not answer.")
                    reasons.append(f"Enveliq tried several times and could not summarise {len(stuck)} of them. {why} Press Try again on an email to try once more.")
        if not count:
            return None
        if not reasons:
            return {"count": count, "retrying": True, "text": f"{count} {'email is' if count == 1 else 'emails are'} waiting for a summary. Enveliq will keep trying."}
        return {"count": count, "retrying": False, "text": " ".join(dict.fromkeys(reasons))}

    def release(self, vault: Any, account: dict[str, Any], ids: list[str]) -> list[dict[str, Any]]:
        """Show these emails in the inbox now (their summary is ready, or has failed for good). Returns the small facts a new-mail alert needs."""
        ready: list[dict[str, Any]] = []
        for message_id in ids:
            try:
                current = vault.get_message(account["id"], message_id)
            except KeyError:
                continue
            if not current.get("ai_pending"):
                continue
            data = {k: v for k, v in current.items() if k != "id"}
            data["ai_pending"] = False
            try:
                vault.update_message(account["id"], message_id, RetainedMessageCreate(**data).model_dump(mode="python"))
            except (ValueError, KeyError):
                continue
            if current.get("state", "unread") == "unread" and not current.get("from_all_mail"):
                ready.append({"account_id": account["id"], "id": message_id, "sender_display": current.get("sender_display"),
                              "subject": current.get("subject"), "priority": current.get("priority")})
        return ready

    def _sync(self, vault: Any, account: dict[str, Any], *, since_days: int = 14, limit: int = 50) -> dict[str, int]:
        """Pull new unread mail from the inbox. Only headers are read; the
        message body is never fetched, and nothing but the summary fields is
        stored."""
        target = self.target(account)
        identities = sending_identities(account)
        account_id = account["id"]
        known_locators: set[str] = set()
        known_ids: set[str] = set()
        people: list[tuple[str, str]] = []
        arrived: list[dict[str, Any]] = []
        hold = self._holds(account)
        stored_all = vault.list_messages(account_id)
        for stored in stored_all:
            if stored.get("source_locator"):
                known_locators.add(stored["source_locator"])
            mid = (stored.get("reply_context") or {}).get("message_id")
            if mid:
                known_ids.add(mid)

        lock = self.locks.acquire(account_id)
        try:
            with self.bridge.session(target) as s:
                validity = s.select_inbox(readonly=True)
                uids = s.unseen_uids(since_days, limit)
                added = skipped = 0
                fresh = [u for u in uids if locator(validity, u) not in known_locators]
                for uid, raw in s.header_blocks(fresh):
                    info = summarise_headers(raw, identities)
                    if info is None or (info["message_id"] and info["message_id"] in known_ids) or marks.ours(vault, info["message_id"], info.get("reminder_mark")):
                        skipped += 1
                        continue
                    body = RetainedMessageCreate(
                        subject=info["subject"],
                        sender_display=info["sender_display"],
                        sender_address=info["sender_address"],
                        summary=PLACEHOLDER_SUMMARY,
                        reply_context=info["reply_context"],
                        unsubscribe=info["unsubscribe"],
                        scam_warning=info["scam_warning"],
                        received_at=info["received_at"],
                        has_attachments=info["has_attachments"],
                        source_locator=locator(validity, uid),
                        ai_pending=hold,
                    )
                    new_id = vault.create_message(account_id, body.model_dump(mode="python"))
                    arrived.append({"id": new_id, "sender_address": info["sender_address"], "subject": info["subject"]})
                    people.append((info["sender_display"], info["sender_address"]))
                    if info["message_id"]:
                        known_ids.add(info["message_id"])
                    added += 1
                # Forget items that are no longer unread in the inbox: read,
                # archived or deleted in another app. Only the local summary
                # is removed; the mailbox itself is never changed here.
                still_unread = s.all_unseen_uids()
                removed = 0
                gone: set[str] = set()
                held = self._held(account)
                for stored in stored_all:
                    if stored.get("from_all_mail"):
                        continue                   # kept by "All emails": not unread, so not judged by the unread list
                    if stored.get("state", "unread") != "unread":
                        continue                   # a Reviewed card keeps its pointer (for Mark unread) but is already read: not judged either
                    if (account_id, stored["id"]) in held:
                        continue                   # it has an open task: it stays until the task is done or removed
                    parts = str(stored.get("source_locator") or "").split("|")
                    if len(parts) != 3 or parts[0] != "INBOX" or not parts[1].isdigit() or not parts[2].isdigit():
                        continue
                    if int(parts[1]) != validity or int(parts[2]) in still_unread:
                        continue
                    vault.delete_message(account_id, stored["id"])
                    removed += 1
                    gone.add(stored["id"])
                # Items saved before dates were kept have no sent date: fill it in
                # from the headers so every card can show when it arrived.
                undated = {}
                for stored in stored_all:
                    if stored["id"] in gone or stored.get("received_at"):
                        continue
                    parts = str(stored.get("source_locator") or "").split("|")
                    if len(parts) == 3 and parts[1].isdigit() and parts[2].isdigit() and int(parts[1]) == validity and int(parts[2]) in still_unread:
                        undated[int(parts[2])] = stored
                for uid, raw in s.header_blocks(sorted(undated)[:100]):
                    when = received_at_of(raw)
                    stored = undated.get(uid)
                    if when is None or stored is None:
                        continue
                    try:
                        data = RetainedMessageCreate(**{**{k: v for k, v in stored.items() if k != "id"}, "received_at": when}).model_dump(mode="python")
                        vault.update_message(account_id, stored["id"], data)
                    except (ValueError, KeyError):
                        continue
                if self.tags_sync:
                    try:
                        self.tags_sync(s, account, validity)
                    except Exception:
                        log.warning("tags could not be read after a sync", exc_info=True)        # tags never break a sync
        finally:
            lock.release()
        if people and self.on_people:
            try:
                self.on_people(account, people)
            except Exception:
                pass                       # the address book never breaks a sync
        if arrived and self.on_new:
            try:
                self.on_new(account, arrived)
            except Exception:
                log.warning("rules could not be applied after a sync", exc_info=True)       # rules never break a sync
        return {"added": added, "skipped": skipped, "removed": removed, "unread_seen": len(uids)}

    # ---------- AI summaries ----------

    def summarise_pending(self, vault: Any, account: dict[str, Any], *, limit: int = 10) -> dict[str, int]:
        """Give the newest unsummarised emails a short summary, category,
        priority and suggested task from the AI model, then forget the email
        text. Only runs for mailboxes the owner switched AI summaries on for."""
        if not self.summariser.enabled:
            raise BridgeError("ai_not_configured", "No AI model is set up yet. An administrator can add one under Administration, AI model.")
        if not (account.get("settings") or {}).get("ai_summaries"):
            raise BridgeError("ai_disabled", "AI summaries are switched off for this mailbox.")
        self.summariser.check_url()
        account_id = account["id"]
        pending = [m for m in vault.list_messages(account_id) if m.get("state", "unread") == "unread" and str(m.get("summary") or "").startswith(PLACEHOLDER_SUMMARY) and m.get("source_locator")
                   and not m.get("from_all_mail")]
        pending.sort(key=lambda m: m.get("received_at") or 0, reverse=True)
        batch = pending[:limit]
        done, failed = self._summarise_batch(vault, account, batch)
        if done or failed:
            self.reporter.event("summaries_completed", summarised=done, failed=failed)
        return {"summarised": done, "failed": failed, "remaining": max(0, len(pending) - done - failed)}

    def _summarise_batch(self, vault: Any, account: dict[str, Any], batch: list[dict[str, Any]], release: bool = True) -> tuple[int, int]:
        """Read these emails' text, have the model summarise each, store the summaries and forget the text. Returns (done, failed)."""
        account_id = account["id"]
        target = self.target(account)
        texts: dict[str, str] = {}
        warnings: dict[str, Any] = {}
        counts: dict[str, int] = {}
        raws: dict[str, bytes] = {}
        unread: dict[str, tuple[str, bytes | None, int]] = {}      # emails whose files were not read, with why (and the email itself while it is small)
        summarised: set[str] = set()
        files_on = attach_service.allowed(vault, self.summariser)
        failed = 0
        instructions = review.instructions_for(vault, account.get("owner_user_id"))
        prompt = review.active_prompt(vault)
        lock = self.locks.acquire(account_id)
        try:
            # Read the texts first and close Bridge, so a slow model never holds the mailbox connection open.
            with self.bridge.session(target) as s:
                for m in batch:
                    try:
                        uid = self.open_location(s, m["source_locator"])
                        raw = s.original(uid)
                        shown = render_original(raw)
                        if shown.get("file_count"):
                            why = None
                            if not files_on:
                                why = "Summarising attached files is switched off. An administrator can turn it on under Administration, AI model."
                            elif len(raw) > attach_service.MAX_RAW:
                                why = "This email is too large to read the files of."
                            elif sum(len(b) for b in raws.values()) + len(raw) > attach_service.MAX_RAW_TOTAL:
                                why = "Too many large emails arrived together to read this one's files. Press Read the files again."
                            if why is None:
                                raws[m["id"]] = raw         # kept in memory only until its files have been read
                            else:
                                log.info("files of %s not read: %s", m["id"], why)
                                unread[m["id"]] = (why, raw if len(raw) <= attach_service.MAX_RAW else None, int(shown["file_count"]))
                        del raw
                        body = shown["text"][: self.summariser.config.max_chars]
                        if not body.strip():             # an email that is only files: say so, rather than send the model an empty box
                            n = int(shown.get("file_count") or 0)
                            body = "(This email has no written text." + (f" It has {n} attached {'file' if n == 1 else 'files'}.)" if n else ")")
                        texts[m["id"]] = body
                        warnings[m["id"]] = shown.get("warning")
                        counts[m["id"]] = int(shown.get("file_count") or 0)
                    except BridgeError as err:
                        failed += 1
                        self.problems[m["id"]] = f"The email could not be read from your mailbox ({err.message})."
            done = 0
            for m in batch:
                if m["id"] not in texts:
                    continue
                sender = f'{m.get("sender_display") or ""} <{m.get("sender_address") or ""}>'
                asked = time.monotonic()
                provider = self.summariser.config.provider or "custom"
                cloud = llm_providers.get(provider).cloud
                try:
                    text = texts.pop(m["id"])
                    try:
                        result = self.summariser.summarise(m.get("subject") or "", sender, text, instructions, prompt)
                    except BridgeError as first:
                        if first.code != "ai_bad_reply":
                            raise
                        result = self.summariser.summarise(m.get("subject") or "", sender, text, instructions, prompt)    # a small model sometimes answers badly once
                    self.reporter.event("ai_request", provider=provider, cloud=cloud, ok=True, duration_ms=(time.monotonic() - asked) * 1000)
                except BridgeError as err:
                    self.reporter.event("ai_request_failed", provider=provider, cloud=cloud, ok=False, code=err.code, duration_ms=(time.monotonic() - asked) * 1000)
                    if err.code == "ai_bad_reply":
                        failed += 1
                        self.problems[m["id"]] = "The AI model answered, but not in a form Enveliq could use as a summary."
                        continue
                    raise  # model unreachable or refusing: stop, nothing is lost
                shipment = result.pop("shipment", None)
                subscription = result.pop("subscription", None)
                trips = result.pop("trips", None)
                data = {k: v for k, v in m.items() if k != "id"}
                data.update(result)
                if m["id"] in counts:                  # the whole email has been read now: the exact number replaces the guess
                    data["attachment_count"] = counts[m["id"]]
                    data["has_attachments"] = counts[m["id"]] > 0
                found = scamcheck.merge((m.get("scam_warning") or {}).get("reasons"), (warnings.get(m["id"]) or {}).get("reasons"))
                data["scam_warning"] = {"reasons": found} if found else None
                try:
                    stored = RetainedMessageCreate(**data).model_dump(mode="python")
                    vault.update_message(account_id, m["id"], stored)
                except (ValueError, KeyError) as err:
                    failed += 1
                    self.problems[m["id"]] = f"The summary could not be saved ({type(err).__name__})."
                    continue
                done += 1
                self.problems.pop(m["id"], None)
                self.retries.pop(m["id"], None)
                summarised.add(m["id"])
                if shipment and self.shipments is not None:
                    try:
                        self.shipments.observe(account.get("owner_user_id"), account_id, m["id"], m.get("subject") or "", m.get("received_at"), shipment)
                    except Exception:                  # a problem filing an order never loses the summary
                        pass
                if subscription and self.subscriptions is not None and not found:      # an email with a "Be careful" flag never files anything
                    try:
                        self.subscriptions.observe(account.get("owner_user_id"), account_id, m["id"], m.get("received_at"), subscription,
                                                   subscriptions_mod.company_link(m.get("sender_address")))
                    except Exception:                  # a problem filing a subscription never loses the summary
                        pass
                if trips and self.trips is not None and not found:                      # an email with a "Be careful" flag never files anything
                    try:
                        self.trips.observe(account.get("owner_user_id"), account_id, m["id"], m.get("received_at"), trips)
                    except Exception:                  # a problem filing a booking never loses the summary
                        pass
        finally:
            lock.release()
        # The files are read after the mailbox is free again, so a long document never holds up Reviewed, Archive or a sync.
        for message_id, raw in raws.items():
            if message_id not in summarised:
                continue
            try:
                attach_service.run(vault, account_id, message_id, raw, self.summariser, instructions)
            except Exception as exc:                 # a problem with a file never loses the email's own summary
                log.warning("attachment summaries failed: %s", type(exc).__name__)
                attach_service.mark_unread(vault, account_id, message_id, raw, "Something went wrong while reading these files. Press Try again.", "failed", counts.get(message_id, 0))
        raws.clear()
        for message_id, (why, raw, n) in unread.items():     # files that were left alone say so on the card
            if message_id in summarised:
                attach_service.mark_unread(vault, account_id, message_id, raw, why, "skipped", n)
        unread.clear()
        if release:                              # summary and files are as ready as they will get: show the emails
            self.release(vault, account, [m["id"] for m in batch])
        return done, failed

    # ---------- all emails (recent mail that is not in the unread list) ----------

    ALL_DAYS = 60
    ALL_LIMIT = None  # All matching inbox messages, with no count cap

    def keep_recent(self, vault: Any, account: dict[str, Any]) -> dict[str, int]:
        """Add the last 60 days of the inbox (with no count cap) as quiet entries: sender, subject and date only,
        read from the headers. Mail already listed is left alone. Entries older than 60 days are dropped. Nothing is
        summarised here: that only happens when the person presses Generate summary."""
        self._not_check_address(account)
        target = self.target(account)
        identities = sending_identities(account)
        account_id = account["id"]
        stored_all = vault.list_messages(account_id)
        known_locators = {m["source_locator"] for m in stored_all if m.get("source_locator")}
        known_ids = {(m.get("reply_context") or {}).get("message_id") for m in stored_all} - {None, ""}
        added = 0
        lock = self.locks.acquire(account_id)
        try:
            with self.bridge.session(target) as s:
                validity = s.select_inbox(readonly=True)
                uids = s.recent_uids(self.ALL_DAYS, self.ALL_LIMIT)
                fresh = [u for u in uids if locator(validity, u) not in known_locators]
                cutoff = time.time() - self.ALL_DAYS * 86400
                for uid, raw in s.header_blocks(fresh):
                    info = summarise_headers(raw, identities)
                    if info is None or (info["message_id"] and info["message_id"] in known_ids) or marks.ours(vault, info["message_id"], info.get("reminder_mark")):
                        continue
                    if info["received_at"] and info["received_at"] < cutoff:
                        continue
                    body = RetainedMessageCreate(subject=info["subject"], sender_display=info["sender_display"], sender_address=info["sender_address"],
                                                 summary=PLACEHOLDER_SUMMARY, reply_context=info["reply_context"], unsubscribe=info["unsubscribe"], scam_warning=info["scam_warning"], received_at=info["received_at"],
                                                 source_locator=locator(validity, uid), from_all_mail=True, has_attachments=info["has_attachments"])
                    vault.create_message(account_id, body.model_dump(mode="python"))
                    if info["message_id"]:
                        known_ids.add(info["message_id"])
                    added += 1
        finally:
            lock.release()
        removed = 0
        cutoff = time.time() - self.ALL_DAYS * 86400
        held = self._held(account)
        for m in stored_all:
            if (account_id, m["id"]) in held:
                continue
            if m.get("from_all_mail") and not m.get("found_until") and m.get("state", "unread") == "unread" and (m.get("received_at") or 0) and m["received_at"] < cutoff:
                vault.delete_message(account_id, m["id"])
                removed += 1
        return {"added": added, "removed": removed}

    FOUND_DAYS = 60

    def keep_found(self, vault: Any, account: dict[str, Any], raw_headers: bytes, folder: str, validity: int, uid: int) -> str:
        """Keep one email a search found, as a quiet entry in Found emails for 60 days. Headers only; nothing is summarised here.
        Returns the new entry's id (or the existing one when it was kept already)."""
        account_id = account["id"]
        where = locator(validity, uid, folder)
        for stored in vault.list_messages(account_id):
            if stored.get("source_locator") == where:
                if not stored.get("found_until"):
                    raise BridgeError("already_listed", "This email is already in your lists.")
                return stored["id"]
        info = summarise_headers(raw_headers, sending_identities(account))
        if info is None:
            raise BridgeError("not_found", "This email could not be read.")
        body = RetainedMessageCreate(subject=info["subject"], sender_display=info["sender_display"], sender_address=info["sender_address"],
                                     summary=PLACEHOLDER_SUMMARY, reply_context=info["reply_context"], unsubscribe=info["unsubscribe"], scam_warning=info["scam_warning"],
                                     received_at=info["received_at"], source_locator=where, from_all_mail=True, has_attachments=info["has_attachments"],
                                     found_until=time.time() + self.FOUND_DAYS * 86400)
        return vault.create_message(account_id, body.model_dump(mode="python"))

    def drop_expired_found(self, vault: Any, account: dict[str, Any]) -> int:
        removed = 0
        now = time.time()
        for m in vault.list_messages(account["id"]):
            if m.get("found_until") and m["found_until"] < now:
                vault.delete_message(account["id"], m["id"])
                removed += 1
        return removed

    def summarise_one(self, vault: Any, account: dict[str, Any], message_id: str, release: bool = True) -> None:
        """Summarise one listed email now (the person pressed Generate summary). Raises BridgeError with a plain reason."""
        if not self.summariser.enabled:
            raise BridgeError("ai_not_configured", "No AI model is set up yet. An administrator can add one under Administration, AI model.")
        self.summariser.check_url()
        try:
            message = vault.get_message(account["id"], message_id)
        except KeyError:
            raise BridgeError("not_found", "That email is no longer in your list.") from None
        if not message.get("source_locator"):
            raise BridgeError("not_found", "That email is no longer in your mailbox.")
        self.problems.pop(message_id, None)
        done, _failed = self._summarise_batch(vault, account, [message], release)
        if not done:
            raise BridgeError("ai_bad_reply", self.problems.pop(message_id, None) or "The email could not be read or the model gave no usable summary.")

    def target(self, account: dict[str, Any]) -> Target:
        return target_for(account, self.microsoft)

    # ---------- view ----------

    def original_raw(self, account: dict[str, Any], message: dict[str, Any]) -> bytes:
        """The whole email as it sits in the mailbox, fetched now and never kept."""
        target = self.target(account)
        with self.bridge.session(target) as s:
            uid = self.open_location(s, message.get("source_locator"))
            return s.original(uid)

    @staticmethod
    def open_location(s: Any, value: str | None) -> int:
        """Open the folder an email lives in (the Inbox, or another folder for a found email) and return its message number."""
        if str(value or "").startswith("FOLDER|"):
            folder, validity, uid = parse_folder_locator(value)
            opened = s.select_folder(folder, True)
        else:
            validity, uid = parse_locator(value)
            opened = s.select_inbox(readonly=True)
        if opened != validity:
            raise BridgeError("not_found", "The mailbox was reset on the server. Sync again.")
        return uid

    def view(self, account: dict[str, Any], message: dict[str, Any]) -> dict[str, Any]:
        return render_original(self.original_raw(account, message))

    # ---------- sent (read-only, live from the mailbox, never kept) ----------

    SENT_DAYS = 14
    SENT_LIMIT = 100

    def sent_list(self, account: dict[str, Any], days: int = SENT_DAYS, limit: int = SENT_LIMIT, with_ids: bool = False) -> dict[str, Any]:
        days = max(1, min(int(days), self.SENT_DAYS))
        cutoff = time.time() - days * 86400
        items: list[dict[str, Any]] = []
        with self.bridge.session(self.target(account)) as s:
            folder = s.folder_for("sent")
            validity = s.select_folder(folder, True)
            uids = s.recent_uids(days, limit + 1)
            more = len(uids) > limit
            for uid, raw in s.header_blocks(uids[:limit], SENT_FIELDS):
                msg = parse_headers(raw)
                when = received_at_of(raw) or 0
                if when and when < cutoff:
                    continue
                to = [{"name": n, "address": a} for n, a in _addresses(msg, "To")[:20]]
                item = {"uid": uid, "to": to, "subject": clean(msg.get("Subject"), 998) or "(no subject)", "date": when}
                if with_ids:
                    item["mid"] = clean(msg.get("Message-ID"), 320)
                items.append(item)
        items.sort(key=lambda i: (i["date"], i["uid"]), reverse=True)
        return {"validity": validity, "days": days, "more": more, "items": items}

    def sent_raw(self, account: dict[str, Any], validity: int, uid: int) -> bytes:
        with self.bridge.session(self.target(account)) as s:
            folder = s.folder_for("sent")
            if s.select_folder(folder, True) != validity:
                raise BridgeError("not_found", "Your Sent folder was reset on the server. Open Sent again.")
            return s.original(uid)

    # ---------- waiting for a reply (sent mail that asks for something) ----------

    WAIT_DAYS = 14             # how far back replies are looked for, and how far back "what is already in Sent" reaches
    WAIT_JUDGE = 5             # new sent emails shown to the model per pass; the rest wait for the next one

    def waiting_scan(self, vault: Any, account: dict[str, Any], judge: int | None = None) -> dict[str, int]:
        """Watch the Sent folder for NEW emails and note the ones that wait on an answer; close notes that were answered.
        With the mailbox switch on, the first look only records what is already in Sent (nothing old is read or shown to the
        model); after that each newly sent email is shown to the model once. Closing notes needs no model and no switch."""
        out = {"judged": 0, "added": 0, "closed": 0, "started": 0}
        book = self.waits
        user = account.get("owner_user_id")
        if book is None or not book.enabled(user):
            return out
        account_id = account["id"]
        watching = bool((account.get("settings") or {}).get("waiting"))
        if not watching and not book.waiting_ids(user, account_id):
            return out
        from .waiting import mark_of, message_ids
        target = self.target(account)
        mine = {a.lower() for a in sending_identities(account)}
        limit = max(0, self.WAIT_JUDGE if judge is None else judge)
        fresh = watching and book.starting_fresh(user, account_id)
        judging = watching and not fresh and self.summariser.enabled
        pending: list[dict[str, Any]] = []
        old: list[str] = []
        replied: set[str] = set()
        lock = self.locks.acquire(account_id)
        try:
            if watching:
                with self.bridge.session(target) as s:
                    s.select_folder(s.folder_for("sent"), True)
                    uids = s.recent_uids(self.WAIT_DAYS, 100)
                    for uid, raw in s.header_blocks(uids, "TO CC SUBJECT DATE MESSAGE-ID IN-REPLY-TO X-ENVELIQ-REMINDER"):
                        msg = parse_headers(raw)
                        mid = clean(msg.get("Message-ID"), 320)
                        if not mid:
                            continue
                        mark = mark_of(account_id, mid)
                        if fresh:
                            old.append(mark)                                            # already in Sent when it was switched on: old, never read
                            continue
                        if not judging or sum(1 for i in pending if not i.get("skip")) >= limit or book.judged(user, mark):
                            continue
                        if marks.ours(vault, mid, clean(msg.get("X-Enveliq-Reminder"), 200)):
                            pending.append({"mark": mark, "skip": True})                # Enveliq's own reminder emails
                            continue
                        to = _addresses(msg, "To")[:20] + _addresses(msg, "Cc")[:20]
                        others = [(n, a) for n, a in to if a.lower() not in mine]
                        if not others or len(others) > 10:
                            pending.append({"mark": mark, "skip": True})                # to yourself, or to a crowd: never waiting
                            continue
                        pending.append({"mark": mark, "uid": uid, "mid": mid, "subject": clean(msg.get("Subject"), 998), "when": received_at_of(raw),
                                        "to": [f"{n} <{a}>" if n else a for n, a in others]})
                    for item in pending:
                        if item.get("skip"):
                            continue
                        try:
                            item["text"] = render_original(s.original(item["uid"]))["text"][: self.summariser.config.max_chars]
                        except BridgeError:
                            item["skip"] = True                                         # too large or gone: left alone, judged once
            if book.waiting_ids(user, account_id) or any(not i.get("skip") for i in pending):
                with self.bridge.session(target) as s:
                    s.select_inbox(readonly=True)
                    for _uid, raw in s.header_blocks(s.recent_uids(self.WAIT_DAYS, 300), "IN-REPLY-TO REFERENCES"):
                        msg = parse_headers(raw)
                        replied |= message_ids(msg.get("In-Reply-To"), msg.get("References"))
        finally:
            lock.release()
        if fresh:
            book.remember_judged(user, old)
            out["started"] = len(old)
        judged: list[str] = []
        try:
            for item in pending:
                if item.get("skip") or item["mid"].lower() in replied:
                    judged.append(item["mark"])                                         # nothing to ask, or answered before it was ever noted
                    continue
                try:
                    verdict = self.summariser.judge_sent(item["subject"], ", ".join(item["to"]), item.pop("text", ""))
                except BridgeError as err:
                    if err.code == "ai_bad_reply":
                        judged.append(item["mark"])
                        continue
                    raise                                                               # model unreachable: stop; nothing is lost
                out["judged"] += 1
                judged.append(item["mark"])
                if verdict["waiting"] and book.add(user, account_id, item["mid"], item["to"], item["subject"], item["when"], verdict["ask"]):
                    out["added"] += 1
        finally:
            book.remember_judged(user, judged)
            if watching:
                book.mark_scanned(user, account_id)
        out["closed"] = book.replies(user, account_id, replied)
        return out

    def follow_sent(self, vault: Any, account: dict[str, Any], validity: int, uid: int, force: bool = False) -> dict[str, Any]:
        """The person asked to follow one sent email (any age): show it to the model once and note it if it waits on an answer.
        `force` notes it even when the model sees nothing being asked."""
        from .waiting import mark_of
        book = self.waits
        user = account.get("owner_user_id")
        if book is None or not book.enabled(user):
            raise BridgeError("not_configured", "Waiting for reply is switched off.")
        raw = self.sent_raw(account, validity, uid)
        msg = parse_headers(raw)
        mid = clean(msg.get("Message-ID"), 320)
        if not mid:
            return {"result": "no_id"}
        if book.note_for(user, account["id"], mid):
            return {"result": "already"}
        mine = {a.lower() for a in sending_identities(account)}
        others = [(n, a) for n, a in _addresses(msg, "To")[:20] + _addresses(msg, "Cc")[:20] if a.lower() not in mine]
        if not others:
            return {"result": "no_recipient"}
        to = [f"{n} <{a}>" if n else a for n, a in others][:10]
        subject = clean(msg.get("Subject"), 998)
        text = render_original(raw)["text"][: self.summariser.config.max_chars]
        verdict = {"waiting": True, "ask": "Waiting for a reply."}
        if not force:
            asked = time.monotonic()
            provider = self.summariser.config.provider or "custom"
            cloud = llm_providers.get(provider).cloud
            try:
                verdict = self.summariser.judge_sent(subject, ", ".join(to), text)
                self.reporter.event("ai_request", provider=provider, cloud=cloud, ok=True, duration_ms=(time.monotonic() - asked) * 1000)
            except BridgeError as err:
                self.reporter.event("ai_request_failed", provider=provider, cloud=cloud, ok=False, code=err.code, duration_ms=(time.monotonic() - asked) * 1000)
                raise
        book.remember_judged(user, [mark_of(account["id"], mid)])
        if not verdict["waiting"]:
            return {"result": "not_waiting"}
        added = book.add(user, account["id"], mid, to, subject, received_at_of(raw), verdict["ask"])
        return {"result": "added" if added else "already", "ask": verdict["ask"]}

    # ---------- new email ----------

    MAX_RECIPIENTS = 50
    MAX_FILES = 10
    MAX_FILE_BYTES = 10 * 1024 * 1024

    @staticmethod
    def _recipients(values: list[str]) -> list[Address]:
        out: list[Address] = []
        for raw in values:
            name, addr = parseaddr(str(raw))
            addr = addr.strip()
            if not addr or _CTRL.search(addr) or _CTRL.search(name) or len(addr) > 320:
                raise BridgeError("not_configured", f"“{clean(raw, 80)}” is not a valid email address.")
            try:
                out.append(Address(display_name=clean(name, 120), addr_spec=addr))
            except Exception:
                raise BridgeError("not_configured", f"“{clean(raw, 80)}” is not a valid email address.") from None
        return out

    def attach_files(self, msg: EmailMessage, files: list[dict[str, str]], already: int = 0, already_bytes: int = 0) -> None:
        """Add the files a person chose (name, type, base64 data) to a message. Counted together with any [already] on it."""
        if already + len(files) > self.MAX_FILES:
            raise BridgeError("too_large", f"Attach at most {self.MAX_FILES} files.")
        total = already_bytes
        for f in files:
            try:
                data = base64.b64decode(f.get("data", ""), validate=True)
            except Exception:
                raise BridgeError("not_configured", "An attachment could not be read.") from None
            total += len(data)
            if total > self.MAX_FILE_BYTES:
                raise BridgeError("too_large", "Attachments can total at most 10 MB.")
            ctype = str(f.get("type") or "").lower()
            main, _, sub = (ctype if _MIME.match(ctype) else "application/octet-stream").partition("/")
            name = clean(str(f.get("name") or "attachment").replace("\\", "/").split("/")[-1], 200) or "attachment"
            msg.add_attachment(data, maintype=main, subtype=sub, filename=name)

    def build_new(self, account: dict[str, Any], to: list[str], cc: list[str], bcc: list[str], subject: str, body: str,
                  from_address: str | None, files: list[dict[str, str]]) -> tuple[EmailMessage, str, list[str]]:
        identities = {i.lower(): i for i in sending_identities(account)}
        mailbox = str(account.get("email_address") or "")
        chosen = identities.get((from_address or mailbox).lower())
        if chosen is None:
            raise BridgeError("not_configured", "That address is not one this mailbox can send from.")
        to_a, cc_a, bcc_a = self._recipients(to), self._recipients(cc), self._recipients(bcc)
        if not to_a and not cc_a and not bcc_a:
            raise BridgeError("not_configured", "Add at least one person to send this to.")
        if len(to_a) + len(cc_a) + len(bcc_a) > self.MAX_RECIPIENTS:
            raise BridgeError("not_configured", f"A message can go to at most {self.MAX_RECIPIENTS} people.")
        msg = EmailMessage(policy=SMTP_POLICY)
        msg["From"] = chosen
        if to_a:
            msg["To"] = to_a
        if cc_a:
            msg["Cc"] = cc_a
        msg["Subject"] = clean(subject, 900) or "(no subject)"
        msg["Date"] = format_datetime(datetime.now(timezone.utc))
        msg["Message-ID"] = make_msgid(domain=chosen.rsplit("@", 1)[1])
        msg.set_content(body.replace("\r\n", "\n"))
        self.attach_files(msg, files)
        recipients = [a.addr_spec for a in to_a + cc_a + bcc_a]
        return msg, chosen, recipients

    # ---------- reply ----------

    def _pick_from(self, account: dict[str, Any], from_address: str | None, delivered_to: str | None) -> str:
        identities = {i.lower(): i for i in sending_identities(account)}
        mailbox = str(account.get("email_address") or "")
        if from_address is not None:
            chosen = identities.get(from_address.lower())
            if chosen is None:
                raise BridgeError("not_configured", "That address is not one this mailbox can send from.")
            return chosen
        # Reply from the address the email was sent to, if this mailbox can
        # send from it; for forwarding aliases the mailbox address is used.
        return identities.get((delivered_to or "").lower(), mailbox)

    def _people(self, to: list[str], cc: list[str], bcc: list[str]) -> tuple[list[Address], list[Address], list[Address]]:
        """Check every address, drop repeats (To wins over Cc, Cc over Bcc) and enforce the size limit."""
        seen: set[str] = set()
        out: list[list[Address]] = []
        for group in (to, cc, bcc):
            kept: list[Address] = []
            for a in self._recipients(group):
                key = a.addr_spec.lower()
                if key not in seen:
                    seen.add(key)
                    kept.append(a)
            out.append(kept)
        if not any(out):
            raise BridgeError("not_configured", "Add at least one person to send this to.")
        if sum(len(g) for g in out) > self.MAX_RECIPIENTS:
            raise BridgeError("not_configured", f"A message can go to at most {self.MAX_RECIPIENTS} people.")
        return out[0], out[1], out[2]

    def build_reply(self, account: dict[str, Any], message: dict[str, Any], body: str, from_address: str | None,
                    to: list[str] | None = None, cc: list[str] | None = None, bcc: list[str] | None = None,
                    kind: str = "reply", add_original: bool = True, files: list[dict[str, str]] | None = None) -> tuple[EmailMessage, str, list[str]]:
        """A reply. Unless the person already put the original into their own message (add_original False), the whole
        original email is fetched from the mailbox now and quoted under their words. It is never kept."""
        ctx = message.get("reply_context")
        if not ctx or not ctx.get("reply_to"):
            raise BridgeError("not_configured", "This email has no address to reply to.")
        if kind == "reply_all" and not ctx.get("cc"):
            raise BridgeError("not_configured", "This email has no one on Cc, so there is no one else to reply to.")
        chosen = self._pick_from(account, from_address, ctx.get("delivered_to"))
        if to is None:
            to = [ctx["reply_to"]] + (list(ctx.get("also_to") or []) if kind == "reply_all" else [])
        if cc is None:
            cc = list(ctx.get("cc") or []) if kind == "reply_all" else []
        to_a, cc_a, bcc_a = self._people(to, cc, bcc or [])

        msg = EmailMessage(policy=SMTP_POLICY)
        msg["From"] = chosen
        if to_a:
            msg["To"] = to_a
        if cc_a:
            msg["Cc"] = cc_a
        subject = clean(message.get("subject"), 900) or "(no subject)"
        msg["Subject"] = subject if re.match(r"(?i)^re:", subject) else f"Re: {subject}"
        msg["Date"] = format_datetime(datetime.now(timezone.utc))
        msg["Message-ID"] = make_msgid(domain=chosen.rsplit("@", 1)[1])
        original_id = ctx.get("message_id")
        if original_id and _ANGLE_ID.match(original_id):
            msg["In-Reply-To"] = original_id
            refs = [r for r in ctx.get("references", []) if _ANGLE_ID.match(r)][-49:] + [original_id]
            msg["References"] = " ".join(refs)
        text = body.replace("\r\n", "\n").rstrip()
        if add_original:
            try:
                quoted = reply_quote(self.original_raw(account, message))
            except BridgeError as err:
                if err.code == "not_found":
                    raise BridgeError("not_found", "Enveliq could not find the original email to quote, so nothing was sent. Sync and try again.") from None
                raise
            text = text + "\n\n" + quoted
        msg.set_content(text)
        if files:
            self.attach_files(msg, files)
        return msg, chosen, [a.addr_spec for a in to_a + cc_a + bcc_a]

    def build_forward(self, account: dict[str, Any], message: dict[str, Any], body: str, from_address: str | None,
                      to: list[str], cc: list[str], bcc: list[str], keep_files: list[int] | None,
                      extra_files: list[dict[str, str]] | None = None) -> tuple[EmailMessage, str, list[str]]:
        """Forward an email: the original is fetched from the mailbox now, quoted under the person's note, and never kept.
        keep_files are the numbers of the original's files to send along (None sends all of them)."""
        ctx = message.get("reply_context") or {}
        chosen = self._pick_from(account, from_address, ctx.get("delivered_to"))
        to_a, cc_a, bcc_a = self._people(to, cc, bcc)
        raw = self.original_raw(account, message)
        original = parse_headers(raw)
        quoted = forward_quote(raw)
        msg = EmailMessage(policy=SMTP_POLICY)
        msg["From"] = chosen
        if to_a:
            msg["To"] = to_a
        if cc_a:
            msg["Cc"] = cc_a
        subject = clean(original.get("Subject"), 900) or clean(message.get("subject"), 900) or "(no subject)"
        msg["Subject"] = subject if re.match(r"(?i)^fwd?:", subject) else f"Fwd: {subject}"
        msg["Date"] = format_datetime(datetime.now(timezone.utc))
        msg["Message-ID"] = make_msgid(domain=chosen.rsplit("@", 1)[1])
        note = body.replace("\r\n", "\n").rstrip()
        msg.set_content((note + "\n\n" if note else "") + quoted)
        files = forward_files(raw, keep_files)
        if len(files) > self.MAX_FILES:
            raise BridgeError("too_large", f"Attach at most {self.MAX_FILES} files.")
        total = 0
        for data, name, ctype in files:
            total += len(data)
            if total > self.MAX_FILE_BYTES:
                raise BridgeError("too_large", "Attachments can total at most 10 MB.")
            ctype = ctype.lower()
            main, _, sub = (ctype if _MIME.match(ctype) else "application/octet-stream").partition("/")
            msg.add_attachment(data, maintype=main, subtype=sub, filename=clean(name, 200) or "attachment")
        if extra_files:
            self.attach_files(msg, extra_files, already=len(files), already_bytes=total)
        return msg, chosen, [a.addr_spec for a in to_a + cc_a + bcc_a]

    def reply(self, account: dict[str, Any], message: dict[str, Any], body: str, from_address: str | None,
              built: tuple[EmailMessage, str, list[str]] | None = None) -> str:
        msg, chosen, recipients = built or self.build_reply(account, message, body, from_address)
        self.bridge.send(self.target(account), msg, chosen, recipients)
        return chosen

    @staticmethod
    def mark_replied(vault: Any, account_id: str, message_id: str, now: float | None = None) -> None:
        """Remember that this email was replied to, so the list can say so after a reload."""
        try:
            stored = vault.get_message(account_id, message_id)
        except KeyError:
            return
        data = {k: v for k, v in stored.items() if k != "id"}
        data["replied_at"] = time.time() if now is None else now
        vault.update_message(account_id, message_id, RetainedMessageCreate(**data).model_dump(mode="python"))

    @staticmethod
    def mark_snoozed(vault: Any, account_id: str, message_id: str, until: float | None) -> dict[str, Any]:
        """Hide an email from the inbox list until `until` (a Unix time), or bring it back now with None. Only Enveliq's own record changes."""
        stored = vault.get_message(account_id, message_id)
        data = {k: v for k, v in stored.items() if k != "id"}
        data["snoozed_until"] = until
        vault.update_message(account_id, message_id, RetainedMessageCreate(**data).model_dump(mode="python"))
        return {"snoozed_until": until}

    # ---------- resolve ----------

    def mark_unread(self, account: dict[str, Any], message: dict[str, Any]) -> None:
        """Put the unread mark back on a Reviewed email, in the real mailbox."""
        if account.get("auth_method") not in MAIL_METHODS or not message.get("source_locator"):
            raise BridgeError("not_found", "Enveliq can no longer find this email in the mailbox.")
        validity, uid = parse_locator(message["source_locator"])
        with self.bridge.session(self.target(account)) as s:
            if s.select_inbox(readonly=False) != validity:
                raise BridgeError("not_found", "The mailbox was reset on the server. Sync again.")
            s.mark_unseen(uid)

    def apply_outcome(self, account: dict[str, Any], message: dict[str, Any], outcome: str) -> None:
        """Do the matching thing in the real mailbox before the local record is
        removed, so a reviewed email does not come back on the next sync."""
        if account.get("auth_method") not in MAIL_METHODS or not message.get("source_locator"):
            return
        if outcome == "expired":
            return
        validity, uid = parse_locator(message["source_locator"])
        with self.bridge.session(self.target(account)) as s:
            if s.select_inbox(readonly=False) != validity:
                raise BridgeError("not_found", "The mailbox was reset on the server. Sync again.")
            if outcome == "reviewed":
                s.mark_seen(uid)
            elif outcome == "archived":
                s.mark_seen(uid)
                s.move(uid, s.folder_for("archive"))
            elif outcome == "binned":
                s.move(uid, s.folder_for("trash"))
            elif outcome == "junked":
                from .junk import junk_folder          # the mailbox's own Junk or Spam folder; the mail service learns from it too
                s.move(uid, junk_folder(s, self.target(account).kind))
