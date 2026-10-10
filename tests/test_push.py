"""Browser push (RFC 8291 / 8292) and the Email reminder channel."""
from __future__ import annotations

import email
import json
from email import policy

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, utils

from test_bridge import mails  # noqa: F401
from test_summaries import account, start  # noqa: F401
from test_llm import FakeModel
from backend.mail import extra_channels as X
from backend.mail import marks, outbound
from backend.mail.parse import summarise_headers

b = X.b64d


def test_encryption_matches_the_rfc_8291_example():
    as_priv = ec.derive_private_key(int.from_bytes(b("yfWPiYE-n46HLnH0KqZOF1fJJU3MYrct3AELtAQ-oRw"), "big"), ec.SECP256R1())
    body = X.encrypt(b("V2hlbiBJIGdyb3cgdXAsIEkgd2FudCB0byBiZSBhIHdhdGVybWVsb24"), b("BCVxsr7N_eNgVRqvHtD0zTZsEc6-VV-JvLexhqUzORcxaOzi6-AYWXvTBHm4bjyPjs7Vd8pZGH6SRpkNtoIAiw4"),
                     b("BTBZMqHH6r4Tts7J_aSIgg"), as_private=as_priv, salt=b("DGv6ra1nlYgDCS1FRnbzlw"))
    assert X.b64e(body[:86]) == "DGv6ra1nlYgDCS1FRnbzlwAAEABBBP4z9KsN6nGRTbVYI_c7VJSPQTBtkgcy27mlmlMoZIIgDll6e3vCYLocInmYWAmS6TlzAC8wEqKK6PBru3jl7A8"
    assert X.b64e(body[86:]) == "8pfeW0KbunFT06SuDKoJH9Ql87S1QUrdirN6GcG7sFz1y1sqLgVi1VhjVkHsUoEsbI_0LpXMuGvnzQ"
    ua = ec.derive_private_key(int.from_bytes(b("q1dXpw3UpT5VOmu_cf_v6ih07Aems3njxI-JWgLcM94"), "big"), ec.SECP256R1())
    assert X.decrypt(body, ua, b("BTBZMqHH6r4Tts7J_aSIgg")) == b"When I grow up, I want to be a watermelon"


def test_a_fresh_message_round_trips_and_is_different_each_time():
    ua = ec.generate_private_key(ec.SECP256R1())
    pub = ua.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    auth = b"0123456789abcdef"
    one, two = X.encrypt("Call the school – ünï".encode(), pub, auth), X.encrypt("Call the school – ünï".encode(), pub, auth)
    assert one != two and X.decrypt(one, ua, auth).decode() == "Call the school – ünï"
    with pytest.raises(ValueError):
        X.encrypt(b"x" * 5000, pub, auth)


def test_the_vapid_header_is_a_valid_signed_token():
    key = ec.generate_private_key(ec.SECP256R1())
    header = X.vapid_header(key, "https://push.example/send/abc", "https://enveliq.example", now=1000)
    token, _, k = header[len("vapid t="):].partition(", k=")
    assert k == X.public_key_text(key)
    head, claims, sig = token.split(".")
    assert json.loads(b(claims)) == {"aud": "https://push.example", "exp": 1000 + 43200, "sub": "https://enveliq.example"}
    raw = b(sig)
    key.public_key().verify(utils.encode_dss_signature(int.from_bytes(raw[:32], "big"), int.from_bytes(raw[32:], "big")), f"{head}.{claims}".encode(), ec.ECDSA(hashes.SHA256()))


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("ENVELIQ_NOTIFY_ALLOWED_HOSTS", "127.0.0.1")
    model = FakeModel()
    appm, client, bridge = start(tmp_path, model)
    yield appm, client, bridge
    bridge.close()
    model.close()


class FakePush:
    def __init__(self, monkeypatch, status=201):
        self.calls, self.status = [], status
        monkeypatch.setattr(X.outbound, "check_target", lambda url, allow: ("https", "push.example", 443, "93.184.216.34", "/x", False))

        def request(method, url, **kw):
            self.calls.append({"method": method, "url": url, **kw})
            return self.status, b""
        monkeypatch.setattr(X.outbound, "request", request)


def device(ua):
    pub = ua.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    return {"endpoint": "https://push.example/send/device-one", "p256dh": X.b64e(pub), "auth": X.b64e(b"0123456789abcdef"), "label": "Chrome on Windows"}


def test_a_device_is_added_tested_and_its_address_never_shown_again(env, monkeypatch):
    appm, client, _ = env
    push = FakePush(monkeypatch)
    assert len(b(client.get("/api/v1/me/notifications/browser/key").json()["public_key"])) == 65
    ua = ec.generate_private_key(ec.SECP256R1())
    r = client.post("/api/v1/me/notifications/browser", json=device(ua))
    assert r.status_code == 200, r.text
    ch = next(c for c in r.json()["channels"] if c["id"] == "browser")
    assert ch["enabled"] and ch["configured"] and ch["devices"][0]["label"] == "Chrome on Windows"
    assert "device-one" not in r.text and "device-one" not in client.get("/api/v1/me/notifications").text
    assert not any(appm.vault.plaintext_scan(["push.example/send/device-one"]).values())
    assert client.post("/api/v1/me/notifications/channels/browser/test").json() == {"ok": True}
    call = push.calls[-1]
    assert call["url"] == "https://push.example/send/device-one" and call["headers"]["Content-Encoding"] == "aes128gcm" and call["headers"]["Authorization"].startswith("vapid t=")
    shown = json.loads(X.decrypt(call["body"], ua, b"0123456789abcdef"))
    assert shown["title"] == "Enveliq test" and "reminder will look" in shown["body"]


def test_a_gone_device_is_forgotten_and_the_person_told(env, monkeypatch):
    _, client, _ = env
    push = FakePush(monkeypatch)
    client.post("/api/v1/me/notifications/browser", json=device(ec.generate_private_key(ec.SECP256R1())))
    push.status = 410
    r = client.post("/api/v1/me/notifications/channels/browser/test")
    assert r.status_code == 502 and "no longer" in r.json()["detail"]
    ch = next(c for c in client.get("/api/v1/me/notifications").json()["channels"] if c["id"] == "browser")
    assert ch["devices"] == [] and not ch["enabled"]


def test_bad_devices_are_refused(env, monkeypatch):
    _, client, _ = env
    FakePush(monkeypatch)
    ua = ec.generate_private_key(ec.SECP256R1())
    d = device(ua)
    assert client.post("/api/v1/me/notifications/browser", json={**d, "endpoint": "http://push.example/x"}).status_code == 422
    assert client.post("/api/v1/me/notifications/browser", json={**d, "p256dh": "AAAA"}).status_code == 422
    assert client.put("/api/v1/me/notifications/channels/browser", json={"enabled": True, "values": {}}).status_code == 422     # nothing to switch on yet
    for i in range(5):
        assert client.post("/api/v1/me/notifications/browser", json={**d, "endpoint": f"https://push.example/send/{i}"}).status_code == 200
    assert client.post("/api/v1/me/notifications/browser", json={**d, "endpoint": "https://push.example/send/6"}).status_code == 422


def test_a_private_push_address_is_never_called(env):
    _, client, _ = env
    ua = ec.generate_private_key(ec.SECP256R1())
    r = client.post("/api/v1/me/notifications/browser", json={**device(ua), "endpoint": "https://127.0.0.1/send/x"})
    assert r.status_code == 422


def test_devices_can_be_removed(env, monkeypatch):
    _, client, _ = env
    FakePush(monkeypatch)
    client.post("/api/v1/me/notifications/browser", json=device(ec.generate_private_key(ec.SECP256R1())))
    ch = next(c for c in client.get("/api/v1/me/notifications").json()["channels"] if c["id"] == "browser")
    r = client.delete(f"/api/v1/me/notifications/browser/{ch['devices'][0]['id']}")
    assert next(c for c in r.json()["channels"] if c["id"] == "browser")["devices"] == []


def test_the_service_worker_is_served_from_the_top(env):
    _, client, _ = env
    r = client.get("/sw.js")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/javascript") and r.headers["service-worker-allowed"] == "/"
    assert "showNotification" in r.text


# ---------- Email ----------

def test_email_goes_only_to_the_persons_own_mailbox_and_is_not_made_into_a_task(env):
    appm, client, bridge = env
    aid = account(client, bridge)
    mailbox = client.get("/api/v1/accounts").json()[0]["email_address"]
    assert client.put("/api/v1/me/notifications/channels/email", json={"enabled": True, "values": {"address": "someone.else@example.invalid"}}).status_code == 422
    r = client.put("/api/v1/me/notifications/channels/email", json={"enabled": True, "values": {}})
    assert r.status_code == 200, r.text
    assert next(f for c in r.json()["channels"] if c["id"] == "email" for f in c["fields"])["value"] == mailbox
    assert client.post("/api/v1/me/notifications/channels/email/test").json() == {"ok": True}
    item = bridge.sent[-1]
    msg = email.message_from_bytes(item["data"], policy=policy.default)
    assert item["to"] == [mailbox] and msg["Subject"] == "Enveliq test"
    mark = msg["X-Enveliq-Reminder"]
    assert marks.ours(appm.vault, msg["Message-ID"], mark)
    # a sync skips a message with our own mark, but not one that merely claims to
    raw = f"From: {mailbox}\r\nTo: {mailbox}\r\nSubject: Enveliq test\r\nMessage-ID: {msg['Message-ID']}\r\nX-Enveliq-Reminder: {mark}\r\n\r\n".encode()
    info = summarise_headers(raw, [mailbox])
    assert marks.ours(appm.vault, info["message_id"], info["reminder_mark"])
    forged = summarise_headers(raw.replace(mark.encode(), b"0" * 40), [mailbox])
    assert not marks.ours(appm.vault, forged["message_id"], forged["reminder_mark"])
    assert not marks.ours(appm.vault, "<other@x>", mark)


def test_email_needs_a_mailbox(env):
    _, client, _ = env
    r = client.put("/api/v1/me/notifications/channels/email", json={"enabled": True, "values": {}})
    assert r.status_code == 422 and "mailbox" in r.json()["detail"]
