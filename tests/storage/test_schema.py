from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import psycopg
import pytest

from db.init.seed import apply_schema
from tests.storage.conftest import NewConversation

RUNTIME_TABLES = {"conversations", "messages", "traces", "tool_calls", "approvals"}


def test_runtime_tables_exist_and_apply_schema_is_idempotent(conn: psycopg.Connection[Any]) -> None:
    apply_schema(conn)
    apply_schema(conn)
    rows = conn.execute(
        "select table_name from information_schema.tables where table_schema = 'public'"
    ).fetchall()
    assert RUNTIME_TABLES <= {row[0] for row in rows}


def _insert_trace(conn: psycopg.Connection[Any], conversation_id: object, seq: int) -> None:
    conn.execute(
        "insert into traces (id, conversation_id, turn, seq, agent_role, input, status,"
        " latency_ms, prompt_tokens, completion_tokens, started_at, created_at)"
        " values (%(id)s, %(c)s, 1, %(seq)s, 'TRIAGE', '{}', 'OK', 0, 0, 0, %(now)s, %(now)s)",
        {"id": uuid4(), "c": conversation_id, "seq": seq, "now": datetime.now(UTC)},
    )


def test_unique_and_fk_constraints(
    conn: psycopg.Connection[Any], new_conversation: NewConversation
) -> None:
    conversation_id = new_conversation()
    _insert_trace(conn, conversation_id, 1)
    with pytest.raises(psycopg.errors.UniqueViolation):
        _insert_trace(conn, conversation_id, 1)

    conn.execute(
        "insert into messages (id, conversation_id, turn, sender, content, created_at)"
        " values (%(id)s, %(c)s, 1, 'CUSTOMER', 'hi', %(now)s)",
        {"id": uuid4(), "c": conversation_id, "now": datetime.now(UTC)},
    )
    with pytest.raises(psycopg.errors.RestrictViolation):
        conn.execute("delete from conversations where id = %(c)s", {"c": conversation_id})
