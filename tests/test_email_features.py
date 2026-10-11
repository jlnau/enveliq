"""Optional features: switches (admin and per person), New email, address book, Sent (14 days, read-only), attachments."""
from __future__ import annotations

import base64
import os
import shutil
import time
from email import policy
from email.utils import format_datetime
from datetime import datetime, timedelta, timezone

from test_bridge import MAILBOX, env, html_mail, mails, synced  # noqa: F401  (the shared Bridge fixture)

PREFS = {"keep_reviewed": True, "keep_archived": True, "keep_days": 7, "instructions": ""}


def sent_mail(subject, to, days_ago, uid_id, body="Sent text.\n", extra=""):
    when = format_datetime(datetime.now(timezone.utc) - timedelta(days=days_ago))
    head = f"From: {MAILBOX}\r\nTo: {to}\r\nSubject: {subject}\r\nDate: {when}\r\nMessage-ID: <{uid_id}@example.invalid>\r\n{extra}"
    return (head + "\r\n" + body.replace("\n", "\r\n")).encode()


def flags(client):
    return client.get("/api/v1/me/features").json()


# ---------- switches ----------

def test_everything_is_on_by_default_and_each_switch_is_independent(env):
    _, client, _, _ = env
    f = flags(client)
    assert all(f["admin"].values()) and all(f["effective"].values()) and f["user"]["address_book_auto"] is True
    r = client.put("/api/v1/admin/features", json={"sent": False})
    assert r.status_code == 200 and r.json()["flags"]["sent"] is False and r.json()["flags"]["compose"] is True
    assert flags(client)["effective"]["sent"] is False
    r = client.put("/api/v1/me/features", json={"address_book": False, "address_book_auto": False})
    assert r.json()["effective"]["address_book"] is False and r.json()["user"]["address_book_auto"] is False
    assert client.put("/api/v1/me/features", json={"bogus": True}).status_code == 422


def test_a_person_cannot_turn_on_what_the_administrator_turned_off(env):
    _, client, _, _ = env
    client.put("/api/v1/admin/features", json={"compose": False})
    r = client.put("/api/v1/me/features", json={"compose": True})
    assert r.json()["user"]["compose"] is True and r.json()["effective"]["compose"] is False


def test_saving_other_preferences_keeps_the_feature_choices(env):
    _, client, _, _ = env
    client.put("/api/v1/me/features", json={"sent": False})
    client.put("/api/v1/me/preferences", json=PREFS)
    assert flags(client)["user"]["sent"] is False


# ---------- new email ----------

def test_new_email_is_sent_with_cc_bcc_and_an_attachment(env):
    _, client, bridge, _ = env
    aid, _ = synced(client, bridge)
    data = base64.b64encode(b"hello file").decode()
    r = client.post(f"/api/v1/accounts/{aid}/send", json={
        "to": ["Dana Example <dana@example.invalid>"], "cc": ["eve@example.invalid"], "bcc": ["frank@example.invalid"],
        "subject": "Plans", "body": "See attached.", "files": [{"name": "plan.txt", "type": "text/plain", "data": data}]})
    assert r.status_code == 200 and r.json()["sent"] is True, r.text
    assert len(bridge.sent) == 1
    sent = bridge.sent[0]
    raw = sent["data"] if isinstance(sent, dict) else sent
    assert "Bcc" not in (raw.decode("utf-8", "replace") if isinstance(raw, bytes) else str(raw)).split("\r\n\r\n")[0]


def test_new_email_is_checked_before_it_leaves(env):
    _, client, bridge, _ = env
    aid, _ = synced(client, bridge)
    url = f"/api/v1/accounts/{aid}/send"
    assert client.post(url, json={"to": [], "body": "x"}).status_code in (400, 422)
    assert client.post(url, json={"to": ["not an address"], "body": "x"}).status_code in (400, 422)
    assert client.post(url, json={"to": ["a@example.invalid\r\nBcc: x@example.invalid"], "body": "x"}).status_code in (400, 422)
    assert client.post(url, json={"to": ["a@example.invalid"], "from_address": "stranger@example.invalid", "body": "x"}).status_code in (400, 422)
    assert client.post(url, json={"to": ["a@example.invalid"], "subject": "x\r\nBcc: y@example.invalid"}).status_code == 422
    assert not bridge.sent


def test_new_email_can_be_held_and_cancelled_with_everything_handed_back(env):
    _, client, bridge, _ = env
    aid, _ = synced(client, bridge)
    client.put("/api/v1/me/preferences", json={**PREFS, "undo_send_seconds": 30})
    r = client.post(f"/api/v1/accounts/{aid}/send", json={"to": ["dana@example.invalid"], "cc": ["eve@example.invalid"], "subject": "Hold me", "body": "Draft body",
                                                          "files": [{"name": "plan.pdf", "type": "application/pdf", "data": "aGVsbG8="}]})
    assert r.json()["queued"] is True and not bridge.sent
    listed = client.get("/api/v1/me/outbox").json()["items"]
    assert listed[0]["kind"] == "new" and listed[0]["subject"] == "Hold me"
    back = client.delete(f"/api/v1/me/outbox/{r.json()['id']}").json()
    assert back["body"] == "Draft body" and back["draft"]["subject"] == "Hold me" and back["draft"]["cc"] == ["eve@example.invalid"]
    assert back["files"] == [{"name": "plan.pdf", "type": "application/pdf", "data": "aGVsbG8="}]
    assert not bridge.sent


def test_new_email_is_refused_when_switched_off(env):
    _, client, bridge, _ = env
    aid, _ = synced(client, bridge)
    client.put("/api/v1/admin/features", json={"compose": False})
    r = client.post(f"/api/v1/accounts/{aid}/send", json={"to": ["a@example.invalid"], "body": "x"})
    assert r.status_code == 403 and not bridge.sent


def test_new_email_shares_the_send_limit_with_replies(env):
    _, client, bridge, _ = env
    aid, _ = synced(client, bridge)
    codes = [client.post(f"/api/v1/accounts/{aid}/send", json={"to": ["a@example.invalid"], "body": "x"}).status_code for _ in range(22)]
    assert codes.count(200) == 20 and 429 in codes


def test_large_body_is_allowed_only_for_send(env):
    _, client, bridge, _ = env
    aid, _ = synced(client, bridge)
    big = base64.b64encode(b"x" * (2 * 1024 * 1024)).decode()
    r = client.post(f"/api/v1/accounts/{aid}/send", json={"to": ["a@example.invalid"], "body": "x", "files": [{"name": "big.bin", "data": big}]})
    assert r.status_code == 200, r.text
    r = client.put("/api/v1/me/preferences", content=b'{"x":"' + b"a" * (2 * 1024 * 1024) + b'"}', headers={"content-type": "application/json"})
    assert r.status_code == 413


# ---------- address book ----------

def test_senders_are_remembered_when_mail_is_read(env):
    _, client, bridge, _ = env
    synced(client, bridge)
    book = client.get("/api/v1/me/contacts").json()
    addrs = {p["address"] for p in book["items"]}
    assert "alice@example.invalid" in addrs and "bob@example.invalid" in addrs
    assert MAILBOX not in addrs


def test_remembering_can_be_switched_off_and_the_book_stays_empty(env):
    _, client, bridge, _ = env
    client.put("/api/v1/me/features", json={"address_book_auto": False})
    synced(client, bridge)
    assert client.get("/api/v1/me/contacts").json()["total"] == 0


def test_people_written_to_are_remembered_and_found_by_typing(env):
    _, client, bridge, _ = env
    aid, _ = synced(client, bridge)
    client.post(f"/api/v1/accounts/{aid}/send", json={"to": ["Dana Example <dana@example.invalid>"], "body": "hi"})
    hits = client.get("/api/v1/me/contacts", params={"q": "dan"}).json()["items"]
    assert hits and hits[0]["address"] == "dana@example.invalid" and hits[0]["name"] == "Dana Example"
    assert client.get("/api/v1/me/contacts", params={"q": "zzz"}).json()["items"] == []


def test_import_reports_what_was_added_skipped_and_invalid_and_can_be_cleared(env):
    _, client, _, _ = env
    people = [{"name": "Gina", "address": "gina@example.invalid"}, {"name": "Gina again", "address": "GINA@example.invalid"},
              {"name": "Bad", "address": "nope"}, {"name": "Hal", "address": "hal@example.invalid"}]
    r = client.post("/api/v1/me/contacts/import", json={"people": people}).json()
    assert r == {"added": 2, "skipped": 1, "invalid": 1}
    assert client.get("/api/v1/me/contacts/export").json()["total"] == 2
    assert client.post("/api/v1/me/contacts/remove", json={"address": "hal@example.invalid"}).status_code == 200
    assert client.post("/api/v1/me/contacts/remove", json={"address": "hal@example.invalid"}).status_code == 404
    assert client.delete("/api/v1/me/contacts").status_code == 204
    assert client.get("/api/v1/me/contacts").json()["total"] == 0


def test_address_book_is_off_when_switched_off_but_can_still_be_deleted(env):
    _, client, _, _ = env
    client.post("/api/v1/me/contacts/import", json={"people": [{"name": "Gina", "address": "gina@example.invalid"}]})
    client.put("/api/v1/admin/features", json={"address_book": False})
    assert client.get("/api/v1/me/contacts").status_code == 403
    assert client.post("/api/v1/me/contacts/import", json={"people": []}).status_code == 403
    assert client.delete("/api/v1/me/contacts").status_code == 204
    client.put("/api/v1/admin/features", json={"address_book": True})
    assert client.get("/api/v1/me/contacts").json()["total"] == 0


def test_each_person_has_their_own_address_book_and_switches(env):
    appm, client, _, _ = env
    from helpers import create_user, sign_in
    create_user(client, "second")
    other = sign_in(appm, "second")
    client.post("/api/v1/me/contacts/import", json={"people": [{"name": "Gina", "address": "gina@example.invalid"}]})
    assert other.get("/api/v1/me/contacts").json()["total"] == 0
    other.post("/api/v1/me/contacts/import", json={"people": [{"name": "Hal", "address": "hal@example.invalid"}]})
    assert [p["address"] for p in client.get("/api/v1/me/contacts").json()["items"]] == ["gina@example.invalid"]
    assert other.post("/api/v1/me/contacts/remove", json={"address": "gina@example.invalid"}).status_code == 404
    other.put("/api/v1/me/features", json={"sent": False})
    assert flags(client)["effective"]["sent"] is True and flags(other)["effective"]["sent"] is False
    assert other.put("/api/v1/admin/features", json={"sent": False}).status_code == 403
    assert other.get("/api/v1/admin/features").status_code == 403


# ---------- sent ----------

def add_sent(bridge):
    bridge.folders.append(("\\HasNoChildren \\Sent", "Sent"))
    bridge.add(501, sent_mail("Recent one", "dana@example.invalid", 1, "s1"), folder="Sent")
    bridge.add(502, sent_mail("Two weeks ago", "eve@example.invalid", 13, "s2"), folder="Sent")
    bridge.add(503, sent_mail("Too old", "frank@example.invalid", 20, "s3"), folder="Sent")


def test_sent_shows_only_the_last_14_days_newest_first(env):
    _, client, bridge, _ = env
    aid, _ = synced(client, bridge)
    add_sent(bridge)
    r = client.get(f"/api/v1/accounts/{aid}/sent")
    assert r.status_code == 200, r.text
    body = r.json()
    assert [i["subject"] for i in body["items"]] == ["Recent one", "Two weeks ago"] and body["days"] == 14
    assert r.headers["cache-control"] == "no-store"


def test_a_sent_email_can_be_opened_read_only_and_nothing_is_stored(env):
    _, client, bridge, _ = env
    aid, _ = synced(client, bridge)
    add_sent(bridge)
    first = client.get(f"/api/v1/accounts/{aid}/sent").json()
    item = first["items"][0]
    r = client.get(f"/api/v1/accounts/{aid}/sent/{first['validity']}/{item['uid']}/original")
    assert r.status_code == 200 and "Sent text." in r.json()["text"]
    assert client.get(f"/api/v1/accounts/{aid}/sent/999999/{item['uid']}/original").status_code == 404
    assert all(m.get("source_locator", "").startswith("INBOX") for m in client.get(f"/api/v1/accounts/{aid}/messages").json() if m.get("source_locator"))
    assert client.delete(f"/api/v1/accounts/{aid}/sent").status_code in (404, 405)


def test_sent_is_refused_when_switched_off_by_the_person(env):
    _, client, bridge, _ = env
    aid, _ = synced(client, bridge)
    add_sent(bridge)
    client.put("/api/v1/me/features", json={"sent": False})
    assert client.get(f"/api/v1/accounts/{aid}/sent").status_code == 403


def test_an_empty_sent_folder_is_an_empty_list(env):
    _, client, bridge, _ = env
    aid, _ = synced(client, bridge)
    r = client.get(f"/api/v1/accounts/{aid}/sent")
    assert r.status_code == 200 and r.json()["items"] == []


# ---------- attachments ----------

def test_attachment_is_fetched_on_request_and_never_inline(env):
    _, client, bridge, _ = env
    bridge.add(9, html_mail())
    aid, m = synced(client, bridge)
    mid = m["Rich message"]["id"]
    view = client.get(f"/api/v1/accounts/{aid}/messages/{mid}/original").json()
    assert view["attachments"][0]["filename"] == "report.pdf" and view["attachments"][0]["previewable"] is False
    r = client.get(f"/api/v1/accounts/{aid}/messages/{mid}/attachments/0")
    assert r.status_code == 200 and r.content == b"Hello"
    assert r.headers["content-type"] == "application/octet-stream" and "attachment" in r.headers["content-disposition"]
    assert r.headers["x-content-type-options"] == "nosniff" and r.headers["cache-control"] == "no-store"
    assert client.get(f"/api/v1/accounts/{aid}/messages/{mid}/attachments/7").status_code == 404


def png_mail():
    png = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"0" * 20).decode()
    return (b"From: Carol <carol@example.invalid>\r\nTo: me@example.invalid\r\nSubject: Picture\r\nMessage-ID: <p5@example.invalid>\r\nMIME-Version: 1.0\r\n"
            b'Content-Type: multipart/mixed; boundary="B"\r\n\r\n--B\r\nContent-Type: text/plain\r\n\r\nSee the photo.\r\n'
            b'--B\r\nContent-Type: image/png; name="a.png"\r\nContent-Disposition: attachment; filename="a.png"\r\nContent-Transfer-Encoding: base64\r\n\r\n'
            + png.encode() + b"\r\n--B\r\nContent-Type: image/svg+xml; name=\"s.svg\"\r\nContent-Disposition: attachment; filename=\"s.svg\"\r\n\r\n<svg onload=alert(1)/>\r\n--B--\r\n")


def test_images_preview_but_svg_and_others_only_download(env):
    _, client, bridge, _ = env
    bridge.add(10, png_mail())
    aid, m = synced(client, bridge)
    mid = m["Picture"]["id"]
    parts = client.get(f"/api/v1/accounts/{aid}/messages/{mid}/original").json()["attachments"]
    assert [p["previewable"] for p in parts] == [True, False]
    ok = client.get(f"/api/v1/accounts/{aid}/messages/{mid}/attachments/0", params={"preview": "true"})
    assert ok.headers["content-type"] == "image/png" and ok.headers["x-content-type-options"] == "nosniff"
    svg = client.get(f"/api/v1/accounts/{aid}/messages/{mid}/attachments/1", params={"preview": "true"})
    assert svg.headers["content-type"] == "application/octet-stream" and "attachment" in svg.headers["content-disposition"]


def doc_mail():
    pdf = base64.b64encode(open(os.path.join(os.path.dirname(__file__), "sample.pdf"), "rb").read()).decode()
    return (b"From: Carol <carol@example.invalid>\r\nTo: me@example.invalid\r\nSubject: Papers\r\nMessage-ID: <d6@example.invalid>\r\nMIME-Version: 1.0\r\n"
            b'Content-Type: multipart/mixed; boundary="B"\r\n\r\n--B\r\nContent-Type: text/plain\r\n\r\nPapers attached.\r\n'
            b'--B\r\nContent-Type: application/pdf; name="trip.pdf"\r\nContent-Disposition: attachment; filename="trip.pdf"\r\nContent-Transfer-Encoding: base64\r\n\r\n' + pdf.encode()
            + b'\r\n--B\r\nContent-Type: text/csv; name="a.csv"\r\nContent-Disposition: attachment; filename="a.csv"\r\n\r\nname,qty\r\nTea,2\r\n'
            b'--B\r\nContent-Type: application/vnd.openxmlformats-officedocument.wordprocessingml.document; name="c.docx"\r\nContent-Disposition: attachment; filename="c.docx"\r\n\r\nPK\r\n'
            b'--B\r\nContent-Type: text/html; name="x.html"\r\nContent-Disposition: attachment; filename="x.html"\r\n\r\n<script>alert(1)</script>\r\n--B--\r\n')


def test_pdf_and_text_attachments_can_be_viewed_in_the_page(env):
    _, client, bridge, _ = env
    bridge.add(11, doc_mail())
    aid, m = synced(client, bridge)
    mid = m["Papers"]["id"]
    parts = client.get(f"/api/v1/accounts/{aid}/messages/{mid}/original").json()["attachments"]
    assert [p["viewable"] for p in parts] == [True, True, False, False]
    base = f"/api/v1/accounts/{aid}/messages/{mid}/attachments"
    r = client.get(f"{base}/1/view")
    assert r.headers["cache-control"] == "no-store" and r.json() == {"kind": "csv", "rows": [["name", "qty"], ["Tea", "2"]], "truncated": False}
    assert client.get(f"{base}/2/view").json()["kind"] == "none"
    assert client.get(f"{base}/3/view").json()["kind"] == "none"
    assert client.get(f"{base}/9/view").status_code == 404
    pdf = client.get(f"{base}/0/view").json()
    if shutil.which("pdftocairo"):
        assert pdf["kind"] == "pdf" and pdf["total"] == 2 and len(pdf["pages"]) == 2
        assert base64.b64decode(pdf["pages"][0]).startswith(b"\x89PNG")
    else:
        assert pdf["kind"] == "none"
    client.put("/api/v1/me/features", json={"media": False})
    assert client.get(f"{base}/1/view").status_code == 403


def test_the_renderer_refuses_bad_and_oversized_files(env):
    from backend.mail import render
    assert render.view(b"%PDF-1.4 not really", "x.pdf", "application/pdf")["kind"] == "none"
    assert render.view(b"x" * (render.MAX_PDF_BYTES + 1), "x.pdf", "application/pdf")["kind"] == "none"
    assert render.view(b"MZ\x90", "x.pdf", "application/pdf")["kind"] == "none"          # not a PDF at all
    assert render.view(b"<b>hi</b>", "x.html", "text/html")["kind"] == "none"
    big = render.view(b"a\x00b" + b"line\n" * 100000, "x.txt", "text/plain")
    assert big["kind"] == "text" and big["truncated"] and "\x00" not in big["text"]
    wide = render.view(b"\n".join(b",".join([b"c"] * 40) for _ in range(300)), "x.csv", "text/csv")
    assert len(wide["rows"]) == 200 and len(wide["rows"][0]) == 20 and wide["truncated"]


def test_attachments_are_refused_when_pictures_are_switched_off(env):
    _, client, bridge, _ = env
    bridge.add(9, html_mail())
    aid, m = synced(client, bridge)
    client.put("/api/v1/me/features", json={"media": False})
    assert client.get(f"/api/v1/accounts/{aid}/messages/{m['Rich message']['id']}/attachments/0").status_code == 403


def test_remote_pictures_are_counted_not_loaded(env):
    _, client, bridge, _ = env
    bridge.add(9, html_mail())
    aid, m = synced(client, bridge)
    view = client.get(f"/api/v1/accounts/{aid}/messages/{m['Rich message']['id']}/original").json()
    assert view["remote_images"] == 1


def test_the_running_version_is_told_to_signed_in_people(env):
    from backend.version import VERSION
    _, client, _, _ = env
    assert client.get("/api/v1/system").json()["version"] == VERSION
