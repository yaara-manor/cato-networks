from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import psycopg
from psycopg import sql

from agents.models import ToolCall
from guardrails.models import SessionGuardHistory
from guardrails.redactor import redact
from storage import (
    AgentRole,
    MessageSender,
    SimulatedActionStatus,
    StateStore,
    ToolCallRecord,
    TraceRecord,
)

NOW = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)
PSK = "Fg7!qwe-DC-2026-tunnel"
_TABLES = {
    "conversations": "id",
    "messages": "conversation_id",
    "traces": "conversation_id",
}


def test_raw_secret_never_reaches_any_row(
    store: StateStore,
    new_conversation: Callable[[], UUID],
    make_trace: Callable[..., TraceRecord],
    conn: psycopg.Connection[Any],
) -> None:
    cid = new_conversation()
    redaction = redact(f"PSK on our side is {PSK}. Can you confirm?")
    assert PSK not in redaction.text
    store.append_customer_message(cid, uuid4(), redaction.text, NOW)
    store.save_guard_history(cid, SessionGuardHistory().with_redaction(redaction), NOW)
    store.record_trace(
        make_trace(cid, role=AgentRole.INGESTION_GUARD, input={"text": redaction.text}),
        [],
    )
    store.complete_turn(cid, 1, MessageSender.AGENT, "rotate the key", (), (), uuid4(), NOW)

    dump = " ".join(
        row[0]
        for table, key in _TABLES.items()
        for row in conn.execute(
            sql.SQL("select t::text from {} t where t.{} = %s").format(
                sql.Identifier(table), sql.Identifier(key)
            ),
            (cid,),
        )
    )
    assert PSK not in dump
    assert "[REDACTED" in dump
    assert redaction.findings[0].sha256 in dump


def test_secret_in_trace_output_and_tool_calls_is_redacted(
    store: StateStore,
    new_conversation: Callable[[], UUID],
    make_trace: Callable[..., TraceRecord],
    conn: psycopg.Connection[Any],
) -> None:
    cid = new_conversation()
    trace = make_trace(
        cid,
        output={"reply": f"PSK is {PSK}"},
        model_messages=[{"content": f"PSK is {PSK}"}],
    )
    call = ToolCallRecord.from_tool_call(
        trace.id,
        cid,
        0,
        ToolCall(
            tool_name="t",
            arguments={"q": f"PSK is {PSK}"},
            status="OK",
            result={"text": f"PSK is {PSK}"},
            latency_ms=1,
        ),
        NOW,
    )
    store.record_trace(trace, [call])

    dump = " ".join(
        row[0]
        for table in ("traces", "tool_calls")
        for row in conn.execute(
            sql.SQL("select t::text from {} t where t.conversation_id = %s").format(sql.Identifier(table)),
            (cid,),
        )
    )
    assert PSK not in dump
    assert "[REDACTED" in dump


def test_secret_in_action_payload_and_result_is_redacted(
    store: StateStore,
    new_conversation: Callable[[], UUID],
    conn: psycopg.Connection[Any],
) -> None:
    cid = new_conversation()
    claimed = store.claim_action(cid, None, None, "CREATE_TICKET", "k", {"body": f"PSK is {PSK}"}, NOW)
    store.finish_action(claimed.action.id, SimulatedActionStatus.DONE, {"note": f"PSK is {PSK}"}, NOW)

    dump = " ".join(
        row[0] for row in conn.execute("select t::text from simulated_actions t where conversation_id = %s", (cid,))
    )
    assert PSK not in dump
    assert "[REDACTED" in dump
