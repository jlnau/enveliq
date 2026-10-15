"""Tags (labels): Proton labels, Gmail labels and keyword tags, kept in step with the mailbox."""
from __future__ import annotations

import re
import threading

import pytest

from backend.mail import tags as T
from backend.mail.bridge import Target, _ImapSession
from backend.mail.errors import BridgeError
from backend.mail.service import AccountLocks
from backend.models import RetainedMessageCreate


# ---------- a small in-memory mail server (just the commands tags use) ----------

class MemImap:
    capabilities = ("IMAP4REV1", "UIDPLUS", "MOVE")

    def __init__(self, folders, messages, permanent=None):
        self.folders = folders                       # [(flags, name)]
        self.msgs = messages                         # [{uid, folder, mid, flags:set, labels:set}]
        self.permanent = permanent
        self.cur = "INBOX"
        self.untagged: dict[str, list] = {}
        self.next_uid = 500

    def list(self):
        return "OK", [f'({fl}) "/" "{name}"'.encode() for fl, name in self.folders]

    def select(self, name, readonly=False):
        self.cur = name.strip('"')
        self.untagged = {"UIDVALIDITY": [b"7"]}
        if self.permanent is not None:
            self.untagged["PERMANENTFLAGS"] = [self.permanent.encode()]
        return "OK", [str(len(self._here())).encode()]

    def response(self, key):
        return key, self.untagged.pop(key, [None])

    def create(self, name):
        name = name.strip('"')
        if any(n == name for _f, n in self.folders):
            return "NO", [b"exists"]
        self.folders.append(("\\HasNoChildren", name))
        return "OK", [b"done"]

    def _here(self):
        return [m for m in self.msgs if m["folder"] == self.cur]

    def _pick(self, uidset):
        wanted = {int(x) for x in uidset.split(",") if x.isdigit()}
        return [m for m in self._here() if m["uid"] in wanted]

    def uid(self, cmd, *args):
        cmd = cmd.upper()
        if cmd == "SEARCH":
            rest = " ".join(str(a) for a in args if a is not None)
            hits = self._here()
            found = re.search(r'HEADER Message-ID "([^"]+)"', rest)
            if found:
                hits = [m for m in hits if m["mid"] == found.group(1)]
            return "OK", [" ".join(str(m["uid"]) for m in hits).encode()]
        if cmd == "FETCH":
            out = []
            for m in self._pick(args[0]):
                what = args[1]
                if "X-GM-LABELS" in what:
                    labels = " ".join(self._atom(T.utf7_encode(x)) for x in sorted(m["labels"]))
                    out.append(f'1 (X-GM-LABELS ({labels}) UID {m["uid"]})'.encode())
                elif "FLAGS" in what:
                    out.append(f'1 (FLAGS ({" ".join(sorted(m["flags"]))}) UID {m["uid"]})'.encode())
                else:
                    head = f"Message-ID: {m['mid']}\r\n\r\n".encode()
                    out.append((f'1 (UID {m["uid"]} BODY[HEADER.FIELDS (MESSAGE-ID)] {{{len(head)}}}'.encode(), head))
                    out.append(b")")
            return "OK", out
        if cmd == "STORE":
            uid, op, items = args
            names = [t.strip('"') for t in re.findall(r'"[^"]*"|[^\s()]+', items)]
            for m in self._pick(str(uid)):
                if "X-GM-LABELS" in op:
                    target = m["labels"]
                    names = [T.utf7_decode(n) for n in names]
                else:
                    target = m["flags"]
                (target.update if op.startswith("+") else target.difference_update)(names)
            return "OK", [b"done"]
        if cmd == "COPY":
            uid, folder = args
            for m in self._pick(str(uid)):
                self.msgs.append({"uid": self.next_uid, "folder": folder.strip('"'), "mid": m["mid"], "flags": set(), "labels": set()})
                self.next_uid += 1
            return "OK", [b"done"]
        if cmd == "EXPUNGE":
            self.msgs[:] = [m for m in self.msgs if not (m["uid"] == int(args[0]) and m["folder"] == self.cur and "\\Deleted" in m["flags"])]
            return "OK", [b"done"]
        return "BAD", [b"unknown"]

    @staticmethod
    def _atom(text):
        return f'"{text}"' if re.search(r"[ \"]", text) else text


class StubBridge:
    def __init__(self, imap):
        self.imap = imap

    def open_imap(self, target):
        return self.imap

    def _close_imap(self, imap):
        pass

    def _wrap(self, exc, stage):
        return BridgeError("protocol_error", f"{stage} failed")

    def session(self, target):
        return _ImapSession(self, target)


class StubMail:
    def __init__(self, imap):
        self.locks = AccountLocks()
        self.bridge = StubBridge(imap)

    def target(self, account):
        return Target(host="mail.example.com", imap_port=993, smtp_port=None, username="me@example.com", password="x", kind="imap")


class MemVault:
    def __init__(self):
        self.m: dict[str, dict] = {}

    def add(self, mid, **kw):
        data = RetainedMessageCreate(subject="Hello", summary="x", **kw).model_dump(mode="python")
        self.m[mid] = data
        return mid

    def get_message(self, aid, mid):
        if mid not in self.m:
            raise KeyError(mid)
        return {**self.m[mid], "id": mid}

    def update_message(self, aid, mid, data):
        self.m[mid] = RetainedMessageCreate(**data).model_dump(mode="python")

    def list_messages(self, aid):
        return [{**v, "id": k} for k, v in self.m.items()]


def inbox(uid, mid, labels=(), flags=()):
    return {"uid": uid, "folder": "INBOX", "mid": mid, "flags": set(flags), "labels": set(labels)}


def stored(vault, uid, mid, **kw):
    return vault.add(f"m{uid}", source_locator=f"INBOX|7|{uid}", reply_context={"reply_to": "sender@example.invalid", "message_id": mid}, **kw)


def service(imap, vault, on=True):
    return T.TagService(StubMail(imap), vault, lambda user: on)


PROTON = {"id": "a1", "auth_method": "proton_bridge", "owner_user_id": "u1", "settings": {}}
GMAIL = {"id": "a1", "auth_method": "imap", "owner_user_id": "u1", "settings": {"provider_id": "gmail"}}
OTHER = {"id": "a1", "auth_method": "imap", "owner_user_id": "u1", "settings": {"provider_id": "fastmail"}}
OUTLOOK = {"id": "a1", "auth_method": "imap", "owner_user_id": "u1", "settings": {"provider_id": "outlook", "auth": "microsoft"}}


# ---------- names and small helpers ----------

def test_which_kind_of_mailbox_keeps_tags_how():
    assert T.dialect_of(PROTON) == "proton" and T.dialect_of(GMAIL) == "gmail" and T.dialect_of(OTHER) == "keywords"
    assert T.dialect_of(OUTLOOK) is None and T.dialect_of({"auth_method": "oauth"}) is None


def test_tag_names_are_checked():
    assert T.clean_name("  Home   work ", "proton") == "Home work"
    assert T.clean_name("Käse & Brot", "gmail") == "Käse & Brot"
    for bad in ("", "   ", "x" * 41, "a/b", 'a"b', "a\\b", "Inbox", "TRASH", "%", "*star"):
        with pytest.raises(T.TagError):
            T.clean_name(bad, "proton")
    assert T.clean_name("Urgent-1", "keywords") == "Urgent-1"
    with pytest.raises(T.TagError):
        T.clean_name("two words", "keywords")


def test_folder_names_survive_the_trip_through_imap_utf7():
    for text in ("Work", "Käse", "日本語 tag", "A & B", "ñandú"):
        assert T.utf7_decode(T.utf7_encode(text)) == text
    assert T.utf7_encode("A & B") == "A &- B" and T.utf7_decode("K&AOQ-se") == "Käse"


def test_a_label_list_in_a_reply_is_read_whole():
    line = b'1 (X-GM-LABELS (\\Inbox Work "to do" "say \\"hi\\"") UID 11)'
    assert T._fetch_lists([line], "X-GM-LABELS") == {11: ["\\Inbox", "Work", "to do", 'say "hi"']}
    assert T._fetch_lists([b"2 (FLAGS (\\Seen $label1 Urgent) UID 12)"], "FLAGS") == {12: ["\\Seen", "$label1", "Urgent"]}
    assert T._fetch_lists([b"junk", (b"x", b"y"), None], "FLAGS") == {}


# ---------- Proton: labels are folders called Labels/<name> ----------

def proton_world():
    folders = [("\\HasNoChildren", "INBOX"), ("\\HasNoChildren \\Archive", "Archive"), ("\\Noselect \\HasChildren", "Labels"),
               ("\\HasNoChildren", "Labels/Work"), ("\\HasNoChildren", "Labels/To do")]
    msgs = [inbox(11, "<a@example.invalid>"), inbox(12, "<b@example.invalid>"),
            {"uid": 31, "folder": "Labels/Work", "mid": "<a@example.invalid>", "flags": set(), "labels": set()}]
    imap = MemImap(folders, msgs)
    vault = MemVault()
    stored(vault, 11, "<a@example.invalid>")
    stored(vault, 12, "<b@example.invalid>")
    return imap, vault, service(imap, vault)


def test_proton_lists_its_labels_and_makes_a_new_one():
    imap, vault, svc = proton_world()
    assert svc.overview(PROTON) == {"supported": True, "names": ["To do", "Work"], "can_create": True}
    out = svc.create(PROTON, "Home")
    assert out["name"] == "Home" and out["names"] == ["Home", "To do", "Work"]
    assert ("\\HasNoChildren", "Labels/Home") in imap.folders
    with pytest.raises(T.TagError):
        svc.create(PROTON, "work")                        # the same name in other letters
    with pytest.raises(T.TagError):
        svc.create(PROTON, "a/b")


def test_proton_puts_a_label_on_and_takes_it_off_without_touching_the_inbox_copy():
    imap, vault, svc = proton_world()
    assert svc.set_for_message(PROTON, "m12", "Work", True) == ["Work"]
    assert any(m["folder"] == "Labels/Work" and m["mid"] == "<b@example.invalid>" for m in imap.msgs)
    assert vault.m["m12"]["tags"] == ["Work"]
    assert svc.set_for_message(PROTON, "m12", "to do", True) == ["To do", "Work"]      # the mailbox's own spelling wins
    assert svc.set_for_message(PROTON, "m12", "Work", False) == ["To do"]
    assert not any(m["folder"] == "Labels/Work" and m["mid"] == "<b@example.invalid>" for m in imap.msgs)
    assert any(m["folder"] == "Labels/Work" and m["mid"] == "<a@example.invalid>" for m in imap.msgs)     # another email's label stays
    assert any(m["folder"] == "INBOX" and m["uid"] == 12 for m in imap.msgs)                             # the email itself stays


def test_a_tag_that_is_gone_from_the_mailbox_is_not_put_on():
    imap, vault, svc = proton_world()
    with pytest.raises(T.TagError):
        svc.set_for_message(PROTON, "m12", "Nope", True)


def test_proton_sync_reads_which_labels_each_email_has():
    imap, vault, svc = proton_world()
    with svc.mail.bridge.session(None) as s:
        found = T.tags_of_inbox(s, "proton", 7, {11: "<a@example.invalid>", 12: "<b@example.invalid>"})
    assert found == {11: ["Work"], 12: []}


def test_the_sync_updates_stored_tags_and_leaves_other_emails_alone():
    imap, vault, svc = proton_world()
    vault.add("old", source_locator="INBOX|99|11", reply_context={"reply_to": "sender@example.invalid", "message_id": "<a@example.invalid>"})       # another mailbox generation
    vault.add("done", state="reviewed", source_locator="INBOX|7|11", reply_context={"reply_to": "sender@example.invalid", "message_id": "<a@example.invalid>"})
    with svc.mail.bridge.session(None) as s:
        svc.sync(s, PROTON, 7)
    assert vault.m["m11"]["tags"] == ["Work"] and vault.m["m12"]["tags"] == []
    assert vault.m["old"]["tags"] == [] and vault.m["done"]["tags"] == []


def test_nothing_is_read_when_tags_are_switched_off():
    imap, vault, svc = proton_world()
    off = service(imap, vault, on=False)
    with off.mail.bridge.session(None) as s:
        off.sync(s, PROTON, 7)
    assert vault.m["m11"]["tags"] == []
    before = len(imap.msgs)
    assert before == 3


# ---------- Gmail: labels, read and changed directly ----------

def gmail_world():
    folders = [("\\HasNoChildren", "INBOX"), ("\\HasChildren \\Noselect", "[Gmail]"), ("\\HasNoChildren \\All", "[Gmail]/All Mail"),
               ("\\HasNoChildren \\Sent", "[Gmail]/Sent Mail"), ("\\HasNoChildren \\Trash", "[Gmail]/Trash"),
               ("\\HasNoChildren", "Work"), ("\\HasNoChildren", T.utf7_encode("Käse")), ("\\HasNoChildren", "Parent/Child")]
    msgs = [inbox(11, "<a@example.invalid>", labels={"\\Inbox", "Work", "Käse"}), inbox(12, "<b@example.invalid>", labels={"\\Inbox", "\\Important"})]
    imap = MemImap(folders, msgs)
    vault = MemVault()
    stored(vault, 11, "<a@example.invalid>")
    stored(vault, 12, "<b@example.invalid>")
    return imap, vault, service(imap, vault)


def test_gmail_lists_only_the_persons_own_labels():
    imap, vault, svc = gmail_world()
    assert svc.overview(GMAIL)["names"] == ["Käse", "Parent/Child", "Work"]


def test_gmail_puts_a_label_on_and_off_and_makes_a_new_one():
    imap, vault, svc = gmail_world()
    svc.create(GMAIL, "Home")
    assert ("\\HasNoChildren", T.utf7_encode("Home")) in imap.folders
    assert svc.set_for_message(GMAIL, "m12", "Work", True) == ["Work"]
    assert "Work" in imap.msgs[1]["labels"]
    assert svc.set_for_message(GMAIL, "m12", "Käse", True) == ["Käse", "Work"]
    assert "Käse" in imap.msgs[1]["labels"]
    assert svc.set_for_message(GMAIL, "m12", "Work", False) == ["Käse"]
    assert "Work" not in imap.msgs[1]["labels"] and "\\Important" in imap.msgs[1]["labels"]


def test_gmail_sync_reads_labels_and_ignores_its_own_system_ones():
    imap, vault, svc = gmail_world()
    with svc.mail.bridge.session(None) as s:
        svc.sync(s, GMAIL, 7)
    assert vault.m["m11"]["tags"] == ["Käse", "Work"] and vault.m["m12"]["tags"] == []


def test_the_mailbox_being_reset_stops_a_change():
    imap, vault, svc = gmail_world()
    vault.add("m99", source_locator="INBOX|3|11", reply_context={"reply_to": "sender@example.invalid", "message_id": "<a@example.invalid>"})
    with pytest.raises(BridgeError):
        svc.set_for_message(GMAIL, "m99", "Work", True)


# ---------- other IMAP services: keywords ----------

def keyword_world(permanent):
    imap = MemImap([("\\HasNoChildren", "INBOX")], [inbox(11, "<a@example.invalid>", flags={"\\Seen", "Urgent", "$label1"}), inbox(12, "<b@example.invalid>")], permanent=permanent)
    vault = MemVault()
    stored(vault, 11, "<a@example.invalid>")
    stored(vault, 12, "<b@example.invalid>")
    return imap, vault, service(imap, vault)


def test_keywords_are_listed_and_new_ones_can_be_made_when_the_service_allows():
    imap, vault, svc = keyword_world("(\\Answered \\Flagged \\Deleted \\Seen \\Draft $label1 Urgent \\*)")
    assert svc.overview(OTHER) == {"supported": True, "names": ["Urgent"], "can_create": True}
    assert svc.create(OTHER, "Taxes")["names"] == ["Taxes", "Urgent"]
    assert svc.set_for_message(OTHER, "m12", "Taxes", True) == ["Taxes"]
    assert "Taxes" in imap.msgs[1]["flags"]
    assert svc.set_for_message(OTHER, "m12", "Taxes", False) == []
    assert "Taxes" not in imap.msgs[1]["flags"]


def test_a_service_that_keeps_no_custom_keywords_says_so():
    imap, vault, svc = keyword_world("(\\Answered \\Flagged \\Deleted \\Seen \\Draft)")
    assert svc.overview(OTHER) == {"supported": True, "names": [], "can_create": False}
    with pytest.raises(T.TagError):
        svc.create(OTHER, "Taxes")
    with pytest.raises(T.TagError):
        svc.set_for_message(OTHER, "m12", "Taxes", True)


def test_keyword_sync_reads_only_the_persons_own_keywords():
    imap, vault, svc = keyword_world("(\\Seen Urgent \\*)")
    with svc.mail.bridge.session(None) as s:
        svc.sync(s, OTHER, 7)
    assert vault.m["m11"]["tags"] == ["Urgent"] and vault.m["m12"]["tags"] == []


def test_outlook_and_unknown_mailboxes_are_not_supported():
    imap, vault, svc = keyword_world("(\\*)")
    assert svc.overview(OUTLOOK) == {"supported": False, "names": [], "can_create": False}
    with pytest.raises(T.TagError):
        svc.create(OUTLOOK, "Taxes")


def test_only_emails_in_the_inbox_can_be_tagged():
    imap, vault, svc = gmail_world()
    vault.add("kept", state="reviewed", source_locator="INBOX|7|11", reply_context={"reply_to": "sender@example.invalid", "message_id": "<a@example.invalid>"})
    with pytest.raises(T.TagError):
        svc.set_for_message(GMAIL, "kept", "Work", True)
    with pytest.raises(KeyError):
        svc.set_for_message(GMAIL, "nope", "Work", True)


def test_one_change_at_a_time_per_mailbox():
    imap, vault, svc = gmail_world()
    held = svc.mail.locks.acquire("a1")
    try:
        with pytest.raises(BridgeError):
            svc.overview(GMAIL)
    finally:
        held.release()
    assert svc.overview(GMAIL)["supported"]


# ---------- through the app: the real routes against the fake Bridge ----------

from test_summaries import account, messages, start  # noqa: E402


@pytest.fixture
def env(tmp_path):
    appm, client, bridge = start(tmp_path, None)
    yield appm, client, bridge
    bridge.close()


def listed(client, aid):
    return client.get(f"/api/v1/accounts/{aid}/messages").json()


def synced_one(client, bridge):
    aid = account(client, bridge, ai=False)
    assert client.post(f"/api/v1/accounts/{aid}/sync", json={}).status_code == 200
    return aid


def test_the_tag_routes_end_to_end(env):
    appm, client, bridge = env
    aid = synced_one(client, bridge)
    r = client.get(f"/api/v1/accounts/{aid}/tags")
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store" and r.json() == {"supported": True, "names": [], "can_create": True}
    r = client.post(f"/api/v1/accounts/{aid}/tags", json={"name": "Work"})
    assert r.status_code == 201 and r.json()["names"] == ["Work"]
    assert client.post(f"/api/v1/accounts/{aid}/tags", json={"name": "work"}).status_code == 422
    assert client.post(f"/api/v1/accounts/{aid}/tags", json={"name": "a/b"}).status_code == 422
    assert client.post(f"/api/v1/accounts/{aid}/tags", json={"name": "ok", "extra": 1}).status_code == 422
    mid = next(m["id"] for m in listed(client, aid) if m["subject"] == "Quarterly update")
    r = client.put(f"/api/v1/accounts/{aid}/messages/{mid}/tags", json={"name": "Work", "on": True})
    assert r.status_code == 200 and r.json() == {"tags": ["Work"]}
    assert next(m for m in listed(client, aid) if m["id"] == mid)["tags"] == ["Work"]
    assert any(f == "Labels/Work" for f in {m["folder"] for m in bridge.messages.values()})          # it really happened in the mailbox
    # a later sync reads the label back from the mailbox and keeps it
    assert client.post(f"/api/v1/accounts/{aid}/sync", json={}).status_code == 200
    assert next(m for m in listed(client, aid) if m["id"] == mid)["tags"] == ["Work"]
    r = client.put(f"/api/v1/accounts/{aid}/messages/{mid}/tags", json={"name": "Work", "on": False})
    assert r.status_code == 200 and r.json() == {"tags": []}
    assert not any(m["folder"] == "Labels/Work" for m in bridge.messages.values())
    assert any(m["folder"] == "INBOX" for m in bridge.messages.values())
    assert client.post(f"/api/v1/accounts/{aid}/sync", json={}).status_code == 200
    assert next(m for m in listed(client, aid) if m["id"] == mid)["tags"] == []


def test_the_tag_routes_check_what_they_are_given(env):
    appm, client, bridge = env
    aid = synced_one(client, bridge)
    client.post(f"/api/v1/accounts/{aid}/tags", json={"name": "Work"})
    mid = listed(client, aid)[0]["id"]
    put = lambda body, m=mid: client.put(f"/api/v1/accounts/{aid}/messages/{m}/tags", json=body)       # noqa: E731
    assert put({"name": "Work", "on": "yes"}).status_code == 422
    assert put({"name": "Work"}).status_code == 422
    assert put({"name": "Work", "on": True, "extra": 1}).status_code == 422
    assert put({"name": "Missing", "on": True}).status_code == 422
    assert put({"name": "Work", "on": True}, m="00000000-0000-0000-0000-000000000000").status_code == 404
    assert client.put(f"/api/v1/accounts/{aid}/messages/not-an-id/tags", json={"name": "Work", "on": True}).status_code == 422
    assert client.get("/api/v1/accounts/00000000-0000-0000-0000-000000000000/tags").status_code == 404


def test_tags_can_be_switched_off(env):
    appm, client, bridge = env
    aid = synced_one(client, bridge)
    assert client.put("/api/v1/me/features", json={"tags": False}).status_code == 200
    assert client.get(f"/api/v1/accounts/{aid}/tags").status_code == 403
    assert client.post(f"/api/v1/accounts/{aid}/tags", json={"name": "Work"}).status_code == 403
    assert client.put("/api/v1/me/features", json={"tags": True}).status_code == 200
    assert client.put("/api/v1/admin/features", json={"tags": False}).status_code == 200
    assert client.get(f"/api/v1/accounts/{aid}/tags").status_code == 403


def test_another_person_cannot_use_my_mailbox_tags(env):
    from helpers import create_user, sign_in
    appm, client, bridge = env
    aid = synced_one(client, bridge)
    mid = listed(client, aid)[0]["id"]
    create_user(client, "second")
    other = sign_in(appm, "second")
    assert other.get(f"/api/v1/accounts/{aid}/tags").status_code == 404
    assert other.post(f"/api/v1/accounts/{aid}/tags", json={"name": "Work"}).status_code == 404
    assert other.put(f"/api/v1/accounts/{aid}/messages/{mid}/tags", json={"name": "Work", "on": True}).status_code == 404


def test_it_needs_a_signed_in_person(env):
    from fastapi.testclient import TestClient
    appm, client, bridge = env
    aid = synced_one(client, bridge)
    anon = TestClient(appm.app)
    assert anon.get(f"/api/v1/accounts/{aid}/tags").status_code in (401, 403)
    assert anon.post(f"/api/v1/accounts/{aid}/tags", json={"name": "Work"}).status_code in (401, 403)
    assert anon.put(f"/api/v1/accounts/{aid}/messages/00000000-0000-0000-0000-000000000000/tags", json={"name": "Work", "on": True}).status_code in (401, 403)


def test_the_audit_log_records_that_a_tag_changed_but_never_its_name(env):
    appm, client, bridge = env
    aid = synced_one(client, bridge)
    seen = []
    appm.vault.audit_hooks.append(lambda event: seen.append(dict(event)))
    client.post(f"/api/v1/accounts/{aid}/tags", json={"name": "Secret plans"})
    mid = listed(client, aid)[0]["id"]
    client.put(f"/api/v1/accounts/{aid}/messages/{mid}/tags", json={"name": "Secret plans", "on": True})
    assert {e["event"] for e in seen} >= {"tag_created", "message_tagged"}
    assert "Secret plans" not in repr(seen)
