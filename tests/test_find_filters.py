"""Stage 4: search filters, recent searches and saved searches."""
from __future__ import annotations

import pytest

from fake_bridge import raw_email_with
from helpers import create_user, sign_in
from test_find import env, mail, run_search      # noqa: F401  (the shared fixture)
from test_summaries import account


def search(client, wait=10, **spec):
    spec.setdefault("query", "")
    return run_search_spec(client, spec, wait)


def run_search_spec(client, spec, wait=10):
    import time
    r = client.post("/api/v1/find/searches", json=spec)
    assert r.status_code == 201, r.text
    job = r.json()["id"]
    end = time.time() + wait
    while time.time() < end:
        if client.get(f"/api/v1/find/searches/{job}").json()["done"]:
            break
        time.sleep(0.05)
    return client.get(f"/api/v1/find/searches/{job}/results").json()


def subjects(page):
    return sorted(r["subject"] for r in page["rows"])


@pytest.fixture
def filled(env):
    appm, client, bridge, model = env
    bridge.honour_dates = True            # this fake mail service answers SINCE and BEFORE from the Date lines
    bridge.add(705, mail("Invoice 4471", "Please pay.", 10, sender="Belinda <belinda@example.invalid>"), "Archive")
    bridge.add(706, mail("Invoice query", "A question about it.", 40, sender="Belinda <belinda@example.invalid>"), "Receipts")
    bridge.add(707, raw_email_with("Report with file", "Cara <cara@example.invalid>", "me@example.invalid", message_id="<f1@example.invalid>",
                                   file=("report.pdf", b"%PDF-1.4 test")), "Archive")
    for uid in (701, 702, 704, 706, 707):
        bridge.messages[uid]["flags"].add("\\Seen")
    bridge.messages[702]["flags"].add("\\Flagged")
    if not any(n == "Receipts" for _f, n in bridge.folders):
        bridge.folders.append(("\\HasNoChildren", "Receipts"))
    aid = account(client, bridge)
    return appm, client, bridge, aid


def test_from_alone_needs_no_words(filled):
    _, client, _, _ = filled
    page = search(client, sender="belinda@")
    assert subjects(page) == ["Invoice 4471", "Invoice query"]


def test_to_dates_unread_and_starred_each_narrow_the_list(filled):
    _, client, _, _ = filled
    assert "Invoice 4471" in subjects(search(client, to="me@example.invalid"))
    assert subjects(search(client, to="nobody@example.invalid")) == []
    assert subjects(search(client, sender="belinda@", since="2000-01-01", until="2000-01-02")) == []
    assert subjects(search(client, sender="belinda@", until="2999-01-01")) == ["Invoice 4471", "Invoice query"]
    assert subjects(search(client, sender="belinda@", unread=True)) == ["Invoice 4471"]          # 706 was read
    assert subjects(search(client, starred=True)) == ["Old project"]


def test_since_is_a_real_date_filter_and_until_is_included(filled):
    _, client, _, _ = filled
    from datetime import date, timedelta
    ten = (date.today() - timedelta(days=10)).isoformat()
    assert subjects(search(client, sender="belinda@", since=ten)) == ["Invoice 4471"]                 # 40 days old is out
    assert subjects(search(client, sender="belinda@", until=ten)) == ["Invoice 4471", "Invoice query"]   # the last day counts


def test_has_files_keeps_only_mail_that_carries_a_file(filled):
    _, client, _, _ = filled
    assert subjects(search(client, files=True)) == ["Report with file"]
    assert subjects(search(client, query="report", files=True)) == ["Report with file"]
    assert subjects(search(client, query="invoice", files=True)) == []


def test_words_and_filters_combine_and_a_folder_can_be_chosen(filled):
    _, client, _, aid = filled
    assert subjects(search(client, query="invoice", sender="belinda@")) == ["Invoice 4471", "Invoice query"]
    assert subjects(search(client, query="invoice", account_id=aid, folder="Receipts")) == ["Invoice query"]
    gone = search(client, query="invoice", account_id=aid, folder="Nowhere")
    assert gone["total"] == 0 and "not in this mailbox" in " ".join(m["message"] for m in gone["mailboxes"])


def test_another_persons_mailbox_cannot_be_chosen(filled):
    appm, client, _, aid = filled
    create_user(client, "second")
    other = sign_in(appm, "second")
    assert other.post("/api/v1/find/searches", json={"query": "invoice", "account_id": aid}).status_code == 404


@pytest.mark.parametrize("spec", [
    {"query": ""}, {"query": "a"}, {"query": "invoice", "since": "yesterday"}, {"query": "invoice", "since": "2026-02-31"},
    {"query": "", "since": "2026-05-02", "until": "2026-05-01"},
])
def test_bad_searches_get_a_plain_answer(filled, spec):
    _, client, _, _ = filled
    assert client.post("/api/v1/find/searches", json=spec).status_code == 400


def test_recent_searches_are_kept_newest_first_without_repeats_and_can_be_cleared(filled):
    _, client, _, _ = filled
    for q in ("invoice", "canvas", "invoice"):
        search(client, query=q)
    recent = client.get("/api/v1/find/history").json()["recent"]
    assert [r["query"] for r in recent] == ["invoice", "canvas"]
    assert client.delete("/api/v1/find/history/recent").status_code == 204
    assert client.get("/api/v1/find/history").json()["recent"] == []


def test_only_the_last_eight_recent_searches_are_kept(filled):
    appm, client, _, _ = filled
    for i in range(12):
        appm.searchbook.remember("someone", {"query": f"word{i}x"})
    recent = appm.searchbook.listing("someone")["recent"]
    assert len(recent) == 8 and recent[0]["query"] == "word11x"


def test_saved_searches_can_be_added_replaced_listed_and_removed(filled):
    appm, client, _, _ = filled
    spec = {"query": "invoice", "sender": "belinda@", "files": True, "unread": True, "since": "2026-01-01"}
    r = client.post("/api/v1/find/saved", json={"name": "Belinda invoices", **spec})
    assert r.status_code == 201
    saved = r.json()
    assert saved["name"] == "Belinda invoices" and saved["files"] is True and saved["since"] == "2026-01-01" and saved["id"].startswith("s")
    assert client.post("/api/v1/find/saved", json={"name": "belinda INVOICES", "query": "other"}).status_code == 201          # same name replaces
    listing = client.get("/api/v1/find/history").json()["saved"]
    assert len(listing) == 1 and listing[0]["query"] == "other"
    assert client.post("/api/v1/find/saved", json={"name": "  ", "query": "x"}).status_code == 400
    assert client.delete(f"/api/v1/find/saved/{saved['id']}").status_code == 204
    assert client.get("/api/v1/find/history").json()["saved"] == []
    assert client.delete(f"/api/v1/find/saved/{saved['id']}").status_code == 404


def test_saved_and_recent_searches_belong_to_one_person(filled):
    appm, client, _, _ = filled
    saved = client.post("/api/v1/find/saved", json={"name": "Mine", "query": "secret thing"}).json()
    search(client, query="private words")
    create_user(client, "second")
    other = sign_in(appm, "second")
    body = other.get("/api/v1/find/history").json()
    assert body["saved"] == [] and body["recent"] == []
    assert other.delete(f"/api/v1/find/saved/{saved['id']}").status_code == 404
    assert len(client.get("/api/v1/find/history").json()["saved"]) == 1


def test_the_search_words_are_not_in_the_audit_log(filled):
    appm, client, _, _ = filled
    search(client, query="needlexyz", sender="privatesender@example.invalid")
    client.post("/api/v1/find/saved", json={"name": "Hidden", "query": "needlexyz"})
    dump = repr(appm.vault.audit_events() if hasattr(appm.vault, "audit_events") else "")
    assert "needlexyz" not in dump and "privatesender" not in dump
