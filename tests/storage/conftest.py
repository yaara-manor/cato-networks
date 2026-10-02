from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import psycopg
import pytest

from core.config import settings

NewConversation = Callable[[], UUID]

# FK order: children first.
_CLEANUP_SQL = (
    "delete from tool_calls where conversation_id = any(%(ids)s)",
    "delete from approvals where conversation_id = any(%(ids)s)",
    "delete from traces where conversation_id = any(%(ids)s)",
    "delete from messages where conversation_id = any(%(ids)s)",
    "delete from conversations where id = any(%(ids)s)",
)


@pytest.fixture
def conn() -> Iterator[psycopg.Connection[Any]]:
    with psycopg.connect(settings.database_url, autocommit=True) as connection:
        yield connection


@pytest.fixture
def restart() -> Callable[[], psycopg.Connection[Any]]:
    """Brand-new autocommit connection, simulating a process restart."""
    return lambda: psycopg.connect(settings.database_url, autocommit=True)


@pytest.fixture
def new_conversation(conn: psycopg.Connection[Any]) -> Iterator[NewConversation]:
    created: list[UUID] = []

    def create() -> UUID:
        conversation_id = uuid4()
        now = datetime.now(UTC)
        conn.execute(
            "insert into conversations (id, customer_tier, stage, created_at, updated_at)"
            " values (%(id)s, 'Standard', 'IDLE', %(now)s, %(now)s)",
            {"id": conversation_id, "now": now},
        )
        created.append(conversation_id)
        return conversation_id

    yield create
    for sql in _CLEANUP_SQL:
        conn.execute(sql, {"ids": created})
