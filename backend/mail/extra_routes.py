"""Optional features: feature switches, New email, the address book, Sent (read-only) and attachment previews."""
from __future__ import annotations

import logging
import threading
import time
from email.utils import parseaddr
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi import Path as PathParam
from pydantic import Field, field_validator

from ..models import StrictModel, header_safe
from ..security import Session
from . import contacts, features
from .errors import BridgeError
from .limits import SlidingWindowLimiter
from .summary_queue import SummaryQueue
from .render import view as render_view
from .parse import PREVIEW_IMAGE_TYPES, attachment_bytes, render_original, sending_identities
from .routes import AccountId, MessageId, fail

log = logging.getLogger("enveliq.queue")

Validity = Annotated[int, PathParam(ge=0, le=2**63 - 1)]
Uid = Annotated[int, PathParam(ge=1, le=2**63 - 1)]
PartIndex = Annotated[int, PathParam(ge=0, le=99)]


class FeaturesBody(StrictModel):
    compose: bool | None = None
    address_book: bool | None = None
    sent: bool | None = None
    media: bool | None = None
    all_mail: bool | None = None
    shipping: bool | None = None
    subscriptions: bool | None = None
    travel: bool | None = None
    waiting: bool | None = None
    messages: bool | None = None
    write_help: bool | None = None
    rss: bool | None = None
    tags: bool | None = None
    find_mail: bool | None = None


class FollowBody(StrictModel):
    force: bool = False


class MyFeaturesBody(FeaturesBody):
    address_book_auto: bool | None = None


class FileIn(StrictModel):
    name: str = Field(min_length=1, max_length=255)
    type: str = Field(default="application/octet-stream", max_length=127)
    data: str = Field(max_length=14_500_000)          # base64; the total is checked again after decoding

    @field_validator("name", "type")
    @classmethod
    def safe(cls, value: str) -> str:
        return header_safe(value)


class NewMailBody(StrictModel):
    to: list[str] = Field(default_factory=list, max_length=50)
    cc: list[str] = Field(default_factory=list, max_length=50)
    bcc: list[str] = Field(default_factory=list, max_length=50)
    subject: str = Field(default="", max_length=900)
    body: str = Field(default="", max_length=100_000)
    from_address: str | None = Field(default=None, max_length=320)
    files: list[FileIn] = Field(default_factory=list, max_length=10)

    @field_validator("subject", "from_address")
    @classmethod
    def one_line(cls, value: str | None) -> str | None:
        return header_safe(value)

    @field_validator("to", "cc", "bcc")
    @classmethod
    def short(cls, values: list[str]) -> list[str]:
        for v in values:
            if len(v) > 320:
                raise ValueError("address too long")
        return values


class Person(StrictModel):
    name: str = Field(default="", max_length=200)
    address: str = Field(max_length=320)


class ImportBody(StrictModel):
    people: list[Person] = Field(max_length=contacts.MAX_PEOPLE)


class RemoveBody(StrictModel):
    address: str = Field(max_length=320)


def build_extra_router(ctx: Any) -> APIRouter:
    router = APIRouter(prefix="/api/v1")
    service = ctx.mail
    vault = ctx.vault
    outbox = ctx.outbox
    session_dep = ctx.full_session
    admin_dep = ctx.admin_session
    view_limit = SlidingWindowLimiter(max_events=60, window=60)
    render_limit = SlidingWindowLimiter(max_events=12, window=60)
    book_limit = SlidingWindowLimiter(max_events=120, window=60)
    follow_limit = SlidingWindowLimiter(max_events=20, window=60)

    def owned(account_id: str, session: Session, action: str) -> dict[str, Any]:
        return ctx.load_account(account_id, session.principal, owner_only=True, action=action)

    def need(session: Session, key: str) -> str:
        user = session.principal.user_id
        if not features.effective(vault, user)[key]:
            raise HTTPException(status_code=403, detail=f"{features.LABELS[key]} is switched off.")
        return user

    def remember_for(account: dict[str, Any], people: list[tuple[str, str]], source: str = "seen") -> None:
        user = account.get("owner_user_id")
        if not user or not people:
            return
        if not features.effective(vault, user)["address_book"] or not features.user_flags(vault, user)["address_book_auto"]:
            return
        contacts.remember(vault, user, people, source, own=sending_identities(account))

    service.on_people = lambda account, people: remember_for(account, people, "seen")

    def drop_listed(wanted: Any) -> None:
        """Forget the quiet entries "All emails" added (nothing else) for people it was just switched off for."""
        for acct in vault.list_accounts():
            if not wanted(acct.get("owner_user_id")):
                continue
            for m in vault.list_messages(acct["id"]):
                if m.get("from_all_mail") and not m.get("found_until"):
                    vault.delete_message(acct["id"], m["id"])

    def drop_found(wanted: Any) -> None:
        """Forget the emails kept from searches (nothing else) for people Find any email was just switched off for."""
        owners: set[str] = set()
        for acct in vault.list_accounts():
            if wanted(acct.get("owner_user_id")):
                owners.add(acct.get("owner_user_id"))
                for m in vault.list_messages(acct["id"]):
                    if m.get("found_until"):
                        vault.delete_message(acct["id"], m["id"])
        finder = getattr(ctx, "find_index", None)              # Fast search goes with the feature
        if finder is not None:
            for owner in owners:
                if owner:
                    finder.delete_user(owner)

    # ---------- switches ----------

    @router.get("/me/features")
    def my_features(response: Response, session: Session = Depends(session_dep)):
        response.headers["Cache-Control"] = "no-store"
        return features.overview(vault, session.principal.user_id)

    @router.put("/me/features")
    def save_my_features(body: MyFeaturesBody, session: Session = Depends(session_dep)):
        features.save_user_flags(vault, ctx.users, session.principal.user_id, body.model_dump())
        if not features.effective(vault, session.principal.user_id)["all_mail"]:
            drop_listed(lambda uid: uid == session.principal.user_id)
        if not features.effective(vault, session.principal.user_id)["find_mail"]:
            drop_found(lambda uid: uid == session.principal.user_id)
        vault.audit({"event": "features_saved_user", "actor_user_id": session.principal.user_id, "at": time.time()})
        return features.overview(vault, session.principal.user_id)

    @router.get("/admin/features")
    def admin_features(response: Response, session: Session = Depends(admin_dep)):
        response.headers["Cache-Control"] = "no-store"
        return {"flags": features.admin_flags(vault), "labels": features.LABELS}

    @router.put("/admin/features")
    def save_admin_features(body: FeaturesBody, session: Session = Depends(admin_dep)):
        flags = features.save_admin_flags(vault, body.model_dump())
        if not flags["all_mail"]:
            drop_listed(lambda uid: True)
        if not flags["find_mail"]:
            drop_found(lambda uid: True)
        vault.audit({"event": "features_saved_admin", "actor_user_id": session.principal.user_id, "flags": flags, "at": time.time()})
        return {"flags": flags, "labels": features.LABELS}

    # ---------- all emails: the last 14 days of the inbox, and Generate summary ----------

    def announce(account: dict[str, Any], items: list[dict[str, Any]]) -> None:
        """Alert only after release makes an email visible, without waiting for other summaries."""
        user = account.get("owner_user_id")
        if not user or not items:
            return
        alerts = getattr(ctx.auto_sync, "mail_alerts", None)
        if alerts is not None:
            try:
                alerts.send(user, items)
            except Exception:
                log.info("new-mail alert failed")

    def run_summary(account_id: str, message_id: str) -> None:
        """Summarise one email and its files. A bad answer or a busy mailbox gets a few more tries; whatever happens, the email is
        shown at the end (with its summary, or marked that it could not be summarised)."""
        account = vault.get_account(account_id)
        service.refresh_ai(vault)
        busy = bad = 0
        try:
            while True:
                try:
                    service.summarise_one(vault, account, message_id, release=False)
                    return
                except BridgeError as err:
                    if err.code == "busy" and busy < 4:
                        busy += 1
                        time.sleep(3)
                    elif err.code in ("ai_bad_reply", "ai_unreachable") and bad < 2 and service.hold_new_mail:
                        bad += 1
                        time.sleep(5 * bad)
                    else:
                        raise
        finally:
            announce(account, service.release(vault, account, [message_id]))

    queue = SummaryQueue(run_summary)
    ctx.summary_queue = queue
    service.on_pending = lambda account, ids: [queue.add(account["owner_user_id"], account["id"], i, auto=True) for i in ids if account.get("owner_user_id")]
    list_limit = SlidingWindowLimiter(max_events=20, window=60)
    queue_limit = SlidingWindowLimiter(max_events=120, window=60)

    @router.post("/accounts/{account_id}/inbox/recent")
    def keep_recent(account_id: AccountId, session: Session = Depends(session_dep)):
        user = need(session, "all_mail")
        account = owned(account_id, session, "list recent mail")
        if not list_limit.allow(f"recent:{user}"):
            raise HTTPException(status_code=429, detail="Too many requests. Wait a minute.")
        try:
            return service.keep_recent(vault, account)
        except BridgeError as err:
            raise fail(err) from None

    @router.post("/accounts/{account_id}/messages/{message_id}/summary", status_code=202)
    def ask_summary(account_id: AccountId, message_id: MessageId, session: Session = Depends(session_dep)):
        user = session.principal.user_id
        owned(account_id, session, "summarise this email")
        try:
            kept = vault.get_message(account_id, message_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="Message not found") from None
        need(session, "find_mail" if kept.get("found_until") else "all_mail")
        if not queue_limit.allow(f"queue:{user}"):
            raise HTTPException(status_code=429, detail="Too many requests. Wait a minute.")
        service.refresh_ai(vault)
        if not service.summariser.enabled:
            raise HTTPException(status_code=409, detail={"code": "ai_not_configured", "message": "No AI model is set up yet. An administrator can add one under Administration, AI model."})
        try:
            queue.add(user, account_id, message_id)
        except BridgeError as err:
            raise fail(err) from None
        vault.audit({"event": "summary_queued", "actor_user_id": user, "account_id": account_id, "message_id": message_id, "at": time.time()})
        return queue.listing(user)

    @router.get("/me/summary-queue")
    def my_summary_queue(response: Response, session: Session = Depends(session_dep)):
        response.headers["Cache-Control"] = "no-store"
        return queue.listing(session.principal.user_id)

    @router.delete("/accounts/{account_id}/messages/{message_id}/summary")
    def cancel_summary(account_id: AccountId, message_id: MessageId, session: Session = Depends(session_dep)):
        owned(account_id, session, "cancel this summary")
        if not queue.cancel(session.principal.user_id, account_id, message_id):
            raise HTTPException(status_code=409, detail="That summary has already started or is not waiting.")
        return queue.listing(session.principal.user_id)

    # ---------- address book ----------

    @router.get("/me/contacts")
    def my_contacts(response: Response, q: str = Query(default="", max_length=100), offset: int = Query(default=0, ge=0, le=100_000),
                    limit: int = Query(default=50, ge=1, le=200), session: Session = Depends(session_dep)):
        user = need(session, "address_book")
        if not book_limit.allow(f"book:{user}"):
            raise HTTPException(status_code=429, detail="Too many requests. Wait a minute.")
        response.headers["Cache-Control"] = "no-store"
        if q.strip():
            return {"items": contacts.search(vault, user, q, min(limit, 10))}
        return contacts.listing(vault, user, offset, limit)

    @router.get("/me/contacts/export")
    def export_contacts(response: Response, session: Session = Depends(session_dep)):
        user = need(session, "address_book")
        response.headers["Cache-Control"] = "no-store"
        return contacts.listing(vault, user, 0, contacts.MAX_PEOPLE)

    @router.post("/me/contacts/import")
    def import_contacts(body: ImportBody, session: Session = Depends(session_dep)):
        user = need(session, "address_book")
        result = contacts.import_people(vault, user, [(p.name, p.address) for p in body.people])
        vault.audit({"event": "contacts_imported", "actor_user_id": user, "added": result["added"], "at": time.time()})
        return result

    @router.post("/me/contacts/remove")
    def remove_contact(body: RemoveBody, session: Session = Depends(session_dep)):
        user = session.principal.user_id          # allowed even when the feature is off: people can always delete their data
        if not contacts.remove(vault, user, body.address):
            raise HTTPException(status_code=404, detail="That person is not in your address book.")
        return {"ok": True}

    @router.delete("/me/contacts", status_code=204)
    def clear_contacts(session: Session = Depends(session_dep)):
        contacts.clear(vault, session.principal.user_id)
        vault.audit({"event": "contacts_cleared", "actor_user_id": session.principal.user_id, "at": time.time()})
        return Response(status_code=204)

    # ---------- new email ----------

    @router.post("/accounts/{account_id}/send")
    def send_new(body: NewMailBody, account_id: AccountId, session: Session = Depends(session_dep)):
        user = need(session, "compose")
        account = owned(account_id, session, "send email")
        if not ctx.send_limit.allow(f"send:{user}") or not ctx.send_total.allow("all"):
            raise HTTPException(status_code=429, detail="Too many emails sent recently. Wait a few minutes.")
        from . import review
        delay = review.user_prefs(vault, user)["undo_send_seconds"]
        try:
            built = service.build_new(account, body.to, body.cc, body.bcc, body.subject, body.body, body.from_address, [f.model_dump() for f in body.files])
            _, chosen, recipients = built
            named = [parseaddr(v) for v in (*body.to, *body.cc, *body.bcc)]
            people = [(n, a) for n, a in named]

            def noted() -> None:
                remember_for(account, people, "sent")

            if delay > 0:
                draft = {"to": body.to, "cc": body.cc, "bcc": body.bcc, "subject": body.subject, "attachments": len(body.files)}
                item = outbox.enqueue(user, account_id, None, built, body.body, delay, draft=draft, on_sent=noted)
                return {"queued": True, "id": item.id, "send_at": item.send_at, "now": time.time(), "from": item.chosen,
                        "to": item.recipients[0] if item.recipients else ""}
            service.bridge.send(service.target(account), built[0], chosen, recipients)
        except BridgeError as err:
            raise fail(err) from None
        noted()
        vault.audit({"event": "email_sent", "actor_user_id": user, "account_id": account_id, "at": time.time()})
        return {"sent": True, "from": chosen}

    # ---------- sent (read-only) ----------

    @router.get("/accounts/{account_id}/sent")
    def sent(account_id: AccountId, response: Response, session: Session = Depends(session_dep)):
        user = need(session, "sent")
        account = owned(account_id, session, "view sent emails")
        if not view_limit.allow(f"sent:{user}"):
            raise HTTPException(status_code=429, detail="Too many requests. Wait a minute.")
        try:
            result = service.sent_list(account, with_ids=True)
        except BridgeError as err:
            raise fail(err) from None
        book = getattr(ctx, "waiting", None)
        ids = [i["mid"] for i in result["items"] if i.get("mid")]
        states = book.states_for(user, account_id, ids) if book is not None and ids and book.enabled(user) else {}
        for i in result["items"]:
            i["follow"] = states.get(i.pop("mid", ""))        # None, "waiting", "replied" or "done"
        response.headers["Cache-Control"] = "no-store"
        return result

    @router.post("/accounts/{account_id}/sent/{validity}/{uid}/follow")
    def sent_follow(body: FollowBody, account_id: AccountId, validity: Validity, uid: Uid, response: Response, session: Session = Depends(session_dep)):
        """Follow this sent email for a reply, whatever its age: it is shown to the AI model once and noted if it waits on an answer."""
        user = need(session, "waiting")
        account = owned(account_id, session, "follow sent emails")
        if not follow_limit.allow(f"follow:{user}"):
            raise HTTPException(status_code=429, detail="Too many requests. Wait a minute.")
        try:
            result = service.follow_sent(vault, account, validity, uid, body.force)
        except BridgeError as err:
            raise fail(err) from None
        response.headers["Cache-Control"] = "no-store"
        return result

    @router.get("/accounts/{account_id}/sent/{validity}/{uid}/original")
    def sent_original(account_id: AccountId, validity: Validity, uid: Uid, response: Response, session: Session = Depends(session_dep)):
        user = need(session, "sent")
        account = owned(account_id, session, "view sent emails")
        if not view_limit.allow(f"sent:{user}"):
            raise HTTPException(status_code=429, detail="Too many requests. Wait a minute.")
        try:
            result = render_original(service.sent_raw(account, validity, uid))
        except BridgeError as err:
            raise fail(err) from None
        response.headers["Cache-Control"] = "no-store"
        return result

    # ---------- attachments: fetched when asked for, handed over, never stored ----------

    def file_response(found: tuple[bytes, str, str] | None, preview: bool) -> Response:
        if found is None:
            raise HTTPException(status_code=404, detail="That attachment was not found.")
        data, name, ctype = found
        headers = {"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"}
        if preview and ctype in PREVIEW_IMAGE_TYPES:
            return Response(content=data, media_type=ctype, headers=headers)
        safe = "".join(c if c.isalnum() or c in " ._-()" else "_" for c in name)[:120] or "attachment"
        headers["Content-Disposition"] = f'attachment; filename="{safe}"'
        return Response(content=data, media_type="application/octet-stream", headers=headers)

    def view_response(found: tuple[bytes, str, str] | None) -> dict[str, Any]:
        if found is None:
            raise HTTPException(status_code=404, detail="That attachment was not found.")
        data, name, ctype = found
        return render_view(data, name, ctype)

    @router.get("/accounts/{account_id}/messages/{message_id}/attachments/{index}/view")
    def inbox_attachment_view(account_id: AccountId, message_id: MessageId, index: PartIndex, response: Response, session: Session = Depends(session_dep)):
        user = need(session, "media")
        account = owned(account_id, session, "view attachments")
        try:
            message = vault.get_message(account_id, message_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="Message not found") from None
        if not render_limit.allow(f"render:{user}"):
            raise HTTPException(status_code=429, detail="Too many requests. Wait a minute.")
        try:
            raw = service.original_raw(account, message)
        except BridgeError as err:
            raise fail(err) from None
        response.headers["Cache-Control"] = "no-store"
        return view_response(attachment_bytes(raw, index))

    @router.get("/accounts/{account_id}/sent/{validity}/{uid}/attachments/{index}/view")
    def sent_attachment_view(account_id: AccountId, validity: Validity, uid: Uid, index: PartIndex, response: Response, session: Session = Depends(session_dep)):
        user = need(session, "media")
        need(session, "sent")
        account = owned(account_id, session, "view attachments")
        if not render_limit.allow(f"render:{user}"):
            raise HTTPException(status_code=429, detail="Too many requests. Wait a minute.")
        try:
            raw = service.sent_raw(account, validity, uid)
        except BridgeError as err:
            raise fail(err) from None
        response.headers["Cache-Control"] = "no-store"
        return view_response(attachment_bytes(raw, index))

    @router.get("/accounts/{account_id}/messages/{message_id}/attachments/{index}")
    def inbox_attachment(account_id: AccountId, message_id: MessageId, index: PartIndex, preview: bool = False, session: Session = Depends(session_dep)):
        user = need(session, "media")
        account = owned(account_id, session, "view attachments")
        try:
            message = vault.get_message(account_id, message_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="Message not found") from None
        if not view_limit.allow(f"view:{user}"):
            raise HTTPException(status_code=429, detail="Too many requests. Wait a minute.")
        try:
            raw = service.original_raw(account, message)
        except BridgeError as err:
            raise fail(err) from None
        return file_response(attachment_bytes(raw, index), preview)

    @router.get("/accounts/{account_id}/sent/{validity}/{uid}/attachments/{index}")
    def sent_attachment(account_id: AccountId, validity: Validity, uid: Uid, index: PartIndex, preview: bool = False, session: Session = Depends(session_dep)):
        user = need(session, "media")
        need(session, "sent")
        account = owned(account_id, session, "view attachments")
        if not view_limit.allow(f"view:{user}"):
            raise HTTPException(status_code=429, detail="Too many requests. Wait a minute.")
        try:
            raw = service.sent_raw(account, validity, uid)
        except BridgeError as err:
            raise fail(err) from None
        return file_response(attachment_bytes(raw, index), preview)

    return router
