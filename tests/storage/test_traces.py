import threading
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

import psycopg
import pytest

from agents.models import ToolCall, TraceStatus
from core.config import settings
from retrieval.models import KBSearchResult, KBSearchStatus, RetrievedPassage
from storage import AgentRole, StateStore, ToolCallRecord, TraceRecord
from tools import TelemetryService

NOW = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)
NewConversation = Callable[[], UUID]
MakeTrace = Callable[..., TraceRecord]
PSK = "Fg7!qwe-DC-2026-tunnel"


def _call(trace: TraceRecord, name: str, result: dict[str, Any]) -> ToolCallRecord:
    return ToolCallRecord.from_tool_call(
        trace.id,
        trace.conversation_id,
        99,
        ToolCall(tool_name=name, arguments={}, status="OK", result=result, latency_ms=3),
        NOW,
    )


def test_trace_with_tool_calls_roundtrips_full_envelope(
    store: StateStore, new_conversation: NewConversation, make_trace: MakeTrace
) -> None:
    cid = new_conversation()
    bgp = TelemetryService().get_bgp_status("S-1007-01")
    trace = make_trace(cid, role=AgentRole.DIAGNOSTICS)
    store.record_trace(
        trace,
        [
            _call(trace, "get_bgp_status", bgp.model_dump(mode="json")),
            _call(trace, "second", {}),
        ],
    )
    [stored] = store.list_traces(cid)
    calls = store.list_tool_calls(cid)
    assert stored.seq == 1
    assert [(c.seq, c.tool_name) for c in calls] == [
        (0, "get_bgp_status"),
        (1, "second"),
    ]
    assert calls[0].result["evidence"] == bgp.model_dump(mode="json")["evidence"]
    assert calls[0].result["evidence"]
    assert store.list_tool_calls(cid, trace.id) == calls


def test_kb_scores_survive(
    store: StateStore, new_conversation: NewConversation, make_trace: MakeTrace
) -> None:
    cid = new_conversation()
    passages = [
        RetrievedPassage(
            passage_id=f"p{i}",
            slug="s",
            title="t",
            public_url="u",
            site_updated_at=None,
            heading="h",
            heading_anchor="a",
            body="b",
            lex_rank=i,
            vec_rank=i,
            rrf_score=0.1 * i,
            rerank_score=score,
        )
        for i, score in ((1, 0.91), (2, 0.42))
    ]
    envelope = KBSearchResult(
        status=KBSearchStatus.CONFIDENT,
        query="q",
        candidates=passages,
        snapshot_date=NOW,
    )
    trace = make_trace(cid, role=AgentRole.KNOWLEDGE)
    store.record_trace(trace, [_call(trace, "kb_search", envelope.model_dump(mode="json"))])
    [call] = store.list_tool_calls(cid)
    assert [c["rerank_score"] for c in call.result["candidates"]] == [0.91, 0.42]


def test_record_trace_is_idempotent(
    store: StateStore,
    new_conversation: NewConversation,
    make_trace: MakeTrace,
    conn: psycopg.Connection[Any],
) -> None:
    cid = new_conversation()
    trace = make_trace(cid)
    calls = [_call(trace, "t", {})]
    store.record_trace(trace, calls)
    store.record_trace(trace, calls)
    assert len(store.list_traces(cid)) == 1
    assert len(store.list_tool_calls(cid)) == 1
    assert conn.execute("select last_seq from conversations where id = %s", (cid,)).fetchone() == (1,)


def test_failed_tool_call_insert_rolls_back_trace(
    store: StateStore,
    new_conversation: NewConversation,
    make_trace: MakeTrace,
    conn: psycopg.Connection[Any],
) -> None:
    cid = new_conversation()
    trace = make_trace(cid)
    call = _call(trace, "t", {})
    with pytest.raises(psycopg.errors.UniqueViolation):
        store.record_trace(trace, [call, call])  # duplicate tool call primary key
    assert store.list_traces(cid) == []
    assert conn.execute("select last_seq from conversations where id = %s", (cid,)).fetchone() == (0,)


def test_concurrent_writers_get_gapless_seqs(
    store: StateStore, new_conversation: NewConversation, make_trace: MakeTrace
) -> None:
    cid = new_conversation()
    errors: list[BaseException] = []

    def writer() -> None:
        try:
            with psycopg.connect(settings.database_url, autocommit=True) as connection:
                worker = StateStore(connection)
                for _ in range(20):
                    worker.record_trace(make_trace(cid), [])
        except BaseException as exc:  # noqa: BLE001 - surfaced in the assertion below
            errors.append(exc)

    threads = [threading.Thread(target=writer) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert errors == []
    assert [t.seq for t in store.list_traces(cid)] == list(range(1, 41))


def test_retry_child_orders_after_parent_and_cost_roundtrips(
    store: StateStore, new_conversation: NewConversation, make_trace: MakeTrace
) -> None:
    cid = new_conversation()
    parent = make_trace(cid, status=TraceStatus.RETRIED, cost_usd=Decimal("0.0123"))
    child = make_trace(cid, parent_trace_id=parent.id)
    store.record_trace(parent, [])
    store.record_trace(child, [])
    stored_parent, stored_child = store.list_traces(cid)
    assert stored_child.parent_trace_id == stored_parent.id
    assert (stored_parent.cost_usd, stored_child.cost_usd) == (Decimal("0.0123"), None)
    assert store.list_traces(cid, turn=2) == []


def test_trace_input_is_redacted_and_truncated(
    store: StateStore, new_conversation: NewConversation, make_trace: MakeTrace
) -> None:
    cid = new_conversation()
    store.record_trace(make_trace(cid, input={"text": f"our PSK on our side is {PSK} ok"}), [])
    store.record_trace(make_trace(cid, input={"text": "a" * 30_000}), [])
    redacted, truncated = store.list_traces(cid)
    assert PSK not in str(redacted.input)
    assert "[REDACTED" in str(redacted.input)
    assert len(str(truncated.input["truncated"])) == 20_000
