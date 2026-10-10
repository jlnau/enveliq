"""The unsubscribe link is stored at sync time and listed with the message."""
from __future__ import annotations

import pytest

from fake_bridge import FakeBridge, raw_email
from test_bridge import synced

ME = "me@example.invalid"


def test_sync_stores_the_header_link_and_lists_it(env_unsub):
    _, client, bridge, _ = env_unsub
    _, by_subject = synced(client, bridge)
    news = by_subject["Weekly news"]
    assert news["unsubscribe"]["url"] == "https://news.example.invalid/u/42" and news["unsubscribe"]["host"] == "news.example.invalid"
    assert by_subject["Quarterly update"].get("unsubscribe") is None
    assert by_subject["Invoice question"].get("unsubscribe") is None       # its link points inside a home network: dropped


@pytest.fixture
def env_unsub(tmp_path):
    from helpers import load_app, setup_admin
    bridge = FakeBridge(tmp_path)
    bridge.add(1, raw_email("Quarterly update", "Alice <alice@example.invalid>", ME, message_id="<a1@example.invalid>"))
    bridge.add(2, raw_email("Weekly news", "News <news@example.invalid>", ME, message_id="<n2@example.invalid>",
                            extra="List-Unsubscribe: <https://news.example.invalid/u/42>\r\nList-Unsubscribe-Post: List-Unsubscribe=One-Click\r\n"))
    bridge.add(3, raw_email("Invoice question", "Bob <bob@example.invalid>", ME, message_id="<b3@example.invalid>",
                            extra="List-Unsubscribe: <http://192.168.1.1/reboot>\r\n"))
    data = tmp_path / "data"
    data.mkdir()
    appm = load_app(data, ENVELIQ_BRIDGE_CA_FILE=str(bridge.cert_path))
    client, _ = setup_admin(appm)
    yield appm, client, bridge, tmp_path
    bridge.close()
