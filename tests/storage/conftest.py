from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import psycopg
import pytest

from agents.models import TraceStatus
from core.config import settings
from storage import AgentRole, StateStore, TraceRecord

NOW = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)

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
def created_ids(conn: psycopg.Connection[Any]) -> Iterator[list[UUID]]:
    """Conversation ids to delete after the test; tests creating via the store append here."""
    created: list[UUID] = []
    yield created
    for sql in _CLEANUP_SQL:
        conn.execute(sql, {"ids": created})


@pytest.fixture
def store(conn: psycopg.Connection[Any]) -> StateStore:
    return StateStore(conn)


@pytest.fixture
def new_conversation(conn: psycopg.Connection[Any], created_ids: list[UUID]) -> NewConversation:
    def create() -> UUID:
        conversation_id = uuid4()
        now = datetime.now(UTC)
        conn.execute(
            "insert into conversations (id, customer_tier, stage, created_at, updated_at)"
            " values (%(id)s, 'Standard', 'IDLE', %(now)s, %(now)s)",
            {"id": conversation_id, "now": now},
        )
        created_ids.append(conversation_id)
        return conversation_id

    return create


MakeTrace = Callable[..., TraceRecord]


@pytest.fixture
def make_trace() -> MakeTrace:
    def build(
        conversation_id: UUID,
        turn: int = 1,
        role: AgentRole = AgentRole.TRIAGE,
        **overrides: Any,
    ) -> TraceRecord:
        fields: dict[str, Any] = {
            "id": uuid4(),
            "conversation_id": conversation_id,
            "message_id": None,
            "turn": turn,
            "seq": None,
            "agent_role": role,
            "parent_trace_id": None,
            "input": {},
            "output": None,
            "model_messages": None,
            "status": TraceStatus.OK,
            "error": None,
            "latency_ms": 5,
            "prompt_tokens": 10,
            "completion_tokens": 2,
            "cost_usd": None,
            "started_at": NOW,
            "created_at": NOW,
        }
        return TraceRecord(**(fields | overrides))

    return build
