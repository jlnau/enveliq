"""One mailbox operation at a time, but a request that arrives meanwhile waits its turn instead of being refused."""
from __future__ import annotations

import threading
import time

import pytest

from backend.mail.errors import BridgeError
from backend.mail.service import AccountLocks


def test_a_request_waits_for_the_mailbox_instead_of_being_refused():
    locks = AccountLocks()
    first = locks.acquire("a")
    threading.Timer(0.3, first.release).start()
    started = time.time()
    second = locks.acquire("a", wait=5)
    assert 0.2 < time.time() - started < 3
    second.release()


def test_it_only_gives_up_after_waiting_and_says_so_calmly():
    locks = AccountLocks()
    held = locks.acquire("a")
    with pytest.raises(BridgeError) as err:
        locks.acquire("a", wait=0.2)
    assert err.value.code == "busy" and "Nothing is lost" in err.value.message and "Try again" in err.value.message
    held.release()


def test_each_mailbox_has_its_own_turn():
    locks = AccountLocks()
    one = locks.acquire("a")
    two = locks.acquire("b", wait=0)
    one.release(); two.release()


def test_the_normal_wait_is_long_enough_to_cover_a_sync():
    assert AccountLocks.WAIT >= 20
