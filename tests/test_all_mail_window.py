"""All emails IMAP lookup must return every UID in the requested window."""
from backend.mail.bridge import _ImapSession


class FakeImap:
    def uid(self, *args):
        return None


class FakeSession:
    imap = FakeImap()

    def _call(self, action, command, *args):
        assert action == "search"
        assert args[0:3] == ("SEARCH", None, "SINCE")
        return [b"1 2 3 4 5 6"]


def test_recent_uids_without_limit_returns_all():
    assert _ImapSession.recent_uids(FakeSession(), 60, None) == [6, 5, 4, 3, 2, 1]


def test_recent_uids_with_limit_still_caps():
    assert _ImapSession.recent_uids(FakeSession(), 14, 2) == [6, 5]
