"""Files added by the person to a reply or a forward (on top of the original's own files for a forward)."""
from __future__ import annotations

import base64

from test_reply_all_forward import BOSS, sent_message, synced_with_cc  # noqa: F401
from test_bridge import env  # noqa: F401  (the shared Bridge fixture)


def file_in(name="notes.txt", data=b"hello there"):
    return {"name": name, "type": "text/plain", "data": base64.b64encode(data).decode()}


def names(msg):
    return [p.get_filename() for p in msg.iter_attachments()]


def test_a_reply_can_carry_a_file(env):
    _, client, bridge, _ = env
    aid, m = synced_with_cc(client, bridge)
    r = client.post(f"/api/v1/accounts/{aid}/messages/{m['Plan for May']['id']}/reply", json={"body": "See attached.", "files": [file_in()]})
    assert r.status_code == 200, r.text
    _, msg = sent_message(bridge)
    assert names(msg) == ["notes.txt"]


def test_a_forward_carries_the_original_files_and_the_new_one(env):
    _, client, bridge, _ = env
    aid, m = synced_with_cc(client, bridge)
    r = client.post(f"/api/v1/accounts/{aid}/messages/{m['Plan for May']['id']}/forward", json={"to": [BOSS], "files": [file_in()]})
    assert r.status_code == 200, r.text
    _, msg = sent_message(bridge)
    assert sorted(names(msg)) == ["notes.txt", "plan.pdf"]


def test_too_many_or_unreadable_files_are_refused_and_nothing_is_sent(env):
    _, client, bridge, _ = env
    aid, m = synced_with_cc(client, bridge)
    base = f"/api/v1/accounts/{aid}/messages/{m['Plan for May']['id']}/reply"
    assert client.post(base, json={"body": "x", "files": [{"name": "a.txt", "type": "text/plain", "data": "not base64!!"}]}).status_code >= 400
    big = file_in("big.bin", b"0" * (6 * 1024 * 1024))
    r = client.post(base, json={"body": "x", "files": [big, {**big, "name": "big2.bin"}]})
    assert r.status_code >= 400
    assert bridge.sent == []
