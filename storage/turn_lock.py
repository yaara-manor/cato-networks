from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any, LiteralString
from uuid import UUID

import psycopg
from psycopg import errors

_KEY: LiteralString = "hashtextextended('turn:' || %(id)s::text, 0)"
_ACQUIRE: LiteralString = f"select pg_advisory_lock({_KEY})"
_RELEASE: LiteralString = f"select pg_advisory_unlock({_KEY})"


class TurnLockTimeout(Exception):
    """Another worker holds this conversation's turn; retry with the same message_id."""


@contextmanager
def turn_lock(connection: psycopg.Connection[Any], conversation_id: UUID, timeout_s: float) -> Iterator[None]:
    """Session advisory lock per conversation; Postgres drops it if the backend dies.

    Session locks are reentrant per connection: use one connection per concurrent turn.
    ponytail: one connection per in-flight turn, pool when concurrency grows.
    """
    params = {"id": conversation_id}
    timeout = f"{int(timeout_s * 1000)}ms"
    connection.execute("select set_config('lock_timeout', %(timeout)s, false)", {"timeout": timeout})
    try:
        connection.execute(_ACQUIRE, params)
    except errors.LockNotAvailable as exc:
        raise TurnLockTimeout(f"conversation {conversation_id} is busy") from exc
    finally:
        connection.execute("reset lock_timeout")
    try:
        yield
    finally:
        try:
            connection.execute(_RELEASE, params)
        except psycopg.OperationalError:
            pass  # backend gone, lock already released
