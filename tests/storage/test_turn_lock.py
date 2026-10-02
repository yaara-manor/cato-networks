import threading
import time
from collections.abc import Iterator
from typing import Any
from uuid import UUID, uuid4

import psycopg
import pytest

from core.config import settings
from storage import TurnLockTimeout
from storage.turn_lock import turn_lock

TIMEOUT = 5.0
Pair = tuple[psycopg.Connection[Any], psycopg.Connection[Any]]


@pytest.fixture
def pair() -> Iterator[Pair]:
    with (
        psycopg.connect(settings.database_url, autocommit=True) as a,
        psycopg.connect(settings.database_url, autocommit=True) as b,
    ):
        yield a, b


def _acquire_in_thread(conn: psycopg.Connection[Any], cid: UUID, got: threading.Event) -> threading.Thread:
    def run() -> None:
        with turn_lock(conn, cid, TIMEOUT):
            got.set()

    thread = threading.Thread(target=run)
    thread.start()
    return thread


def test_waiter_blocks_until_release(pair: Pair) -> None:
    a, b = pair
    cid, got = uuid4(), threading.Event()
    with turn_lock(a, cid, TIMEOUT):
        thread = _acquire_in_thread(b, cid, got)
        assert not got.wait(0.3)
    assert got.wait(TIMEOUT)
    thread.join()


def test_other_conversations_independent(pair: Pair) -> None:
    a, b = pair
    with turn_lock(a, uuid4(), TIMEOUT), turn_lock(b, uuid4(), 0.3):
        pass


def test_timeout_then_acquire_after_release(pair: Pair) -> None:
    a, b = pair
    cid = uuid4()
    with turn_lock(a, cid, TIMEOUT):
        start = time.monotonic()
        with pytest.raises(TurnLockTimeout), turn_lock(b, cid, 0.3):
            pass
        assert 0.25 < time.monotonic() - start < 3
    with turn_lock(b, cid, 0.3):
        pass


def test_killed_holder_releases_lock(pair: Pair) -> None:
    a, b = pair
    cid = uuid4()
    pid = a.execute("select pg_backend_pid()").fetchone()
    assert pid is not None
    with (
        psycopg.connect(settings.database_url, autocommit=True) as killer,
        pytest.raises(psycopg.OperationalError),
        turn_lock(a, cid, TIMEOUT),
    ):
        killer.execute("select pg_terminate_backend(%s)", (pid[0],))
        a.execute("select 1")
    with turn_lock(b, cid, TIMEOUT):
        pass


def test_exception_in_block_unlocks(pair: Pair) -> None:
    a, b = pair
    cid = uuid4()
    with pytest.raises(ValueError), turn_lock(a, cid, TIMEOUT):
        raise ValueError("boom")
    with turn_lock(b, cid, 0.3):
        pass


def test_same_connection_is_reentrant(pair: Pair) -> None:
    a, _ = pair
    cid = uuid4()
    with turn_lock(a, cid, 0.3), turn_lock(a, cid, 0.3):
        pass
