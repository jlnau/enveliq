"""Formatted (HTML) email: sent as plain text plus formatted text, pictures inside the message, and nothing unsafe getting through."""
from __future__ import annotations

import base64
import email
from email import policy

import pytest

from fake_bridge import raw_email_with
from helpers import create_user, sign_in
from test_bridge import MAILBOX, WORK, add_account, env, synced  # noqa: F401  (the shared Bridge fixture)
from test_reply_all_forward import synced_with_cc  # noqa: F401

from backend.mail import outhtml

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 40
PREFS = {"keep_reviewed": True, "keep_archived": True, "keep_days": 7, "instructions": ""}


def parsed(bridge, index=-1):
    return email.message_from_bytes(bridge.sent[index]["data"], policy=policy.default)


def image(cid="img1", data=PNG, kind="image/png"):
    return {"cid": cid, "type": kind, "data": base64.b64encode(data).decode()}


# ---------- the rebuild ----------

def test_only_plain_formatting_survives_the_rebuild():
    out = outhtml.clean_html(
        '<p style="color:red;position:fixed;background:url(x)" onclick="x()">Hi <b>there</b><script>alert(1)</script>'
        '<a href="javascript:x()">bad</a> <a href="https://example.com/a">ok</a><img src="http://tracker.invalid/p.gif"><img src="cid:a">'
        '<iframe src="https://example.invalid"></iframe></p><ul><li>one</ul><form><input></form>', {"a": "real@enveliq.invalid"})
    assert "script" not in out and "onclick" not in out and "javascript" not in out and "tracker" not in out and "iframe" not in out and "<form" not in out
    assert "position" not in out and "url(" not in out and 'style="color:red"' in out
    assert '<a href="https://example.com/a" rel="noopener noreferrer">ok</a>' in out and 'src="cid:real@enveliq.invalid"' in out
    assert out.count("<img") == 1 and "<ul><li>one</li></ul>" in out                       # an unclosed list is closed


def test_a_picture_must_be_a_real_picture_of_an_allowed_kind():
    assert outhtml.check_images([image()])[0][1] == "image/png"
    for bad in (image(data=b"<svg onload=x>"), image(kind="image/svg+xml"), image(cid="a b"), {"cid": "x", "type": "image/png", "data": "!!!"}):
        with pytest.raises(outhtml.OutHtmlError):
            outhtml.check_images([bad])
    with pytest.raises(outhtml.OutHtmlError):
        outhtml.check_images([image("a"), image("a")])                                   # one name for two pictures
    with pytest.raises(outhtml.OutHtmlError):
        outhtml.check_images([image(data=PNG + b"0" * (outhtml.MAX_IMAGE_BYTES + 1))])


# ---------- sending ----------

def test_a_new_email_goes_as_plain_text_plus_formatted_text_with_its_picture(env):
    _, client, bridge, _ = env
    aid, _ = synced(client, bridge)
    r = client.post(f"/api/v1/accounts/{aid}/send", json={
        "to": ["dana@example.invalid"], "subject": "Look", "body": "Hello Dana, see this:",
        "html": '<p>Hello <b>Dana</b>, see this:</p><img src="cid:img1" alt="a picture"><script>x()</script>', "images": [image()]})
    assert r.status_code == 200 and r.json()["sent"] is True, r.text
    msg = parsed(bridge)
    assert msg.get_content_type() == "multipart/alternative"
    assert msg.get_body(preferencelist=("plain",)).get_content().strip() == "Hello Dana, see this:"
    html = msg.get_body(preferencelist=("html",))
    page = html.get_content() if html.get_content_type() == "text/html" else next(p for p in html.walk() if p.get_content_type() == "text/html").get_content()
    assert "<b>Dana</b>" in page and "script" not in page and "cid:" in page
    pictures = [p for p in msg.walk() if p.get_content_type() == "image/png"]
    assert len(pictures) == 1 and pictures[0]["Content-ID"].strip("<>") in page and pictures[0].get_content() == PNG


def test_an_email_without_formatting_still_goes_as_plain_text(env):
    _, client, bridge, _ = env
    aid, _ = synced(client, bridge)
    assert client.post(f"/api/v1/accounts/{aid}/send", json={"to": ["dana@example.invalid"], "subject": "Plain", "body": "Just words."}).status_code == 200
    assert parsed(bridge).get_content_type() == "text/plain"


def test_a_bad_picture_stops_the_send_and_nothing_goes(env):
    _, client, bridge, _ = env
    aid, _ = synced(client, bridge)
    r = client.post(f"/api/v1/accounts/{aid}/send", json={"to": ["dana@example.invalid"], "subject": "x", "body": "hi",
                                                           "html": '<img src="cid:img1">', "images": [image(data=b"<svg onload=x>")]})
    assert r.status_code >= 400 and bridge.sent == []


def test_a_formatted_reply_quotes_the_original_in_both_versions(env):
    _, client, bridge, _ = env
    aid, m = synced_with_cc(client, bridge)
    r = client.post(f"/api/v1/accounts/{aid}/messages/{m['Plan for May']['id']}/reply", json={"body": "Agreed.", "html": "<p><i>Agreed.</i></p>"})
    assert r.status_code == 200, r.text
    msg = parsed(bridge)
    plain = msg.get_body(preferencelist=("plain",)).get_content()
    page = msg.get_body(preferencelist=("html",)).get_content()
    assert plain.startswith("Agreed.") and "wrote:" in plain and "> " in plain
    assert "<i>Agreed.</i>" in page and "<blockquote" in page and "wrote:" in page


def test_a_formatted_forward_carries_the_original_and_its_file(env):
    _, client, bridge, _ = env
    aid, m = synced_with_cc(client, bridge)
    r = client.post(f"/api/v1/accounts/{aid}/messages/{m['Plan for May']['id']}/forward", json={"to": ["mum@example.invalid"], "body": "See below.",
                                                                                                    "html": "<p>See <u>below</u>.</p>"})
    assert r.status_code == 200, r.text
    msg = parsed(bridge)
    assert "Forwarded message" in msg.get_body(preferencelist=("plain",)).get_content()
    assert "<u>below</u>" in msg.get_body(preferencelist=("html",)).get_content()
    assert [p.get_filename() for p in msg.iter_attachments()] == ["plan.pdf"]


def test_undo_gives_back_the_formatted_text_and_pictures(env):
    _, client, bridge, _ = env
    aid, _ = synced(client, bridge)
    assert client.put("/api/v1/me/preferences", json={**PREFS, "undo_send_seconds": 20}).status_code == 200
    r = client.post(f"/api/v1/accounts/{aid}/send", json={"to": ["dana@example.invalid"], "subject": "Hold", "body": "Words",
                                                           "html": '<p><b>Words</b></p><img src="cid:img1">', "images": [image()]})
    assert r.status_code == 200 and r.json()["queued"] is True and bridge.sent == []
    back = client.delete(f"/api/v1/me/outbox/{r.json()['id']}").json()
    assert back["html"] == '<p><b>Words</b></p><img src="cid:img1">' and back["images"][0]["cid"] == "img1" and back["body"] == "Words"


def test_drafts_and_waiting_emails_keep_the_formatted_text(env):
    _, client, bridge, _ = env
    aid, _ = synced(client, bridge)
    d = client.post("/api/v1/me/drafts", json={"kind": "new", "account_id": aid, "to": ["dana@example.invalid"], "subject": "D", "body": "Words",
                                                "html": "<p><b>Words</b></p>"})
    assert d.status_code in (200, 201) and d.json()["html"] == "<p><b>Words</b></p>"
    assert client.get("/api/v1/me/drafts").json()["items"][0]["html"] == "<p><b>Words</b></p>"
    s = client.post("/api/v1/me/scheduled", json={"kind": "new", "account_id": aid, "to": ["dana@example.invalid"], "subject": "S", "body": "Words",
                                                   "html": "<p><b>Words</b></p>", "send_at": __import__("time").time() + 3600})
    assert s.status_code == 201, s.text
    back = client.delete(f"/api/v1/me/scheduled/{s.json()['id']}").json()
    assert back["html"] == "<p><b>Words</b></p>"
