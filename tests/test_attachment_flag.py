"""The paperclip: Enveliq keeps only whether an email has attached files, and how many. Never a name, never content."""
from __future__ import annotations

import json

import pytest

from fake_bridge import FakeBridge
from test_bridge import html_mail
from test_llm import FakeModel
from test_summaries import SECRET_WORDS, account, messages, start  # noqa: F401
from backend.mail import parse

PLAIN = (b"From: Dana <dana@example.invalid>\r\nTo: me@example.invalid\r\nSubject: Just words\r\nMessage-ID: <w1@example.invalid>\r\n\r\nHello.\r\n")
INLINE_ONLY = (b"From: Eve <eve@example.invalid>\r\nTo: me@example.invalid\r\nSubject: Picture inside\r\nMessage-ID: <i1@example.invalid>\r\nMIME-Version: 1.0\r\n"
               b'Content-Type: multipart/mixed; boundary="Z"\r\n\r\n--Z\r\nContent-Type: text/plain\r\n\r\nSee below.\r\n'
               b"--Z\r\nContent-Type: image/png\r\nContent-ID: <logo@example.invalid>\r\nContent-Transfer-Encoding: base64\r\n\r\niVBORw0K\r\n--Z--\r\n")


@pytest.fixture
def env(tmp_path):
    model = FakeModel()
    appm, client, bridge = start(tmp_path, model)
    for uid in list(bridge.messages):
        del bridge.messages[uid]
    bridge.add(11, html_mail())
    bridge.add(12, PLAIN)
    bridge.add(13, INLINE_ONLY)
    yield appm, client, bridge, model
    bridge.close()
    model.close()


def test_headers_alone_give_a_first_guess():
    mixed = parse.parse_headers(b"Content-Type: multipart/mixed; boundary=x\r\n\r\n")
    plain = parse.parse_headers(b"Content-Type: text/plain\r\n\r\n")
    none = parse.parse_headers(b"Subject: hi\r\n\r\n")
    pdf = parse.parse_headers(b"Content-Type: application/pdf\r\n\r\n")
    assert parse.likely_has_files(mixed) and parse.likely_has_files(pdf)
    assert not parse.likely_has_files(plain) and not parse.likely_has_files(none)


def test_the_exact_count_ignores_pictures_that_are_part_of_the_text():
    assert parse.render_original(html_mail())["file_count"] == 1
    assert parse.render_original(PLAIN)["file_count"] == 0
    assert parse.render_original(INLINE_ONLY)["file_count"] == 0


def test_a_new_email_gets_a_guess_and_no_count_until_it_is_summarised(env):
    _, client, bridge, _ = env
    aid = account(client, bridge)
    assert client.post(f"/api/v1/accounts/{aid}/sync", json={}).status_code == 200
    m = messages(client, aid)
    assert m["Rich message"]["has_attachments"] is True and m["Rich message"]["attachment_count"] is None
    assert m["Just words"]["has_attachments"] is False
    assert m["Picture inside"]["has_attachments"] is True          # a "mixed" email: the guess can be wrong...


def test_summarising_replaces_the_guess_with_the_exact_count(env):
    _, client, bridge, _ = env
    aid = account(client, bridge)
    client.post(f"/api/v1/accounts/{aid}/sync", json={})
    assert client.post(f"/api/v1/accounts/{aid}/summarise", json={}).status_code == 200
    m = messages(client, aid)
    assert (m["Rich message"]["has_attachments"], m["Rich message"]["attachment_count"]) == (True, 1)
    assert (m["Just words"]["has_attachments"], m["Just words"]["attachment_count"]) == (False, 0)
    assert (m["Picture inside"]["has_attachments"], m["Picture inside"]["attachment_count"]) == (False, 0)      # ...and is put right here


def test_no_file_name_or_content_is_ever_kept(env):
    appm, client, bridge, _ = env
    aid = account(client, bridge)
    client.post(f"/api/v1/accounts/{aid}/sync", json={})
    client.post(f"/api/v1/accounts/{aid}/summarise", json={})
    text = json.dumps(messages(client, aid))
    assert "report.pdf" not in text and "SGVsbG8" not in text
    assert appm.vault.plaintext_scan(["report.pdf", "SGVsbG8="]) == {"report.pdf": False, "SGVsbG8=": False}
