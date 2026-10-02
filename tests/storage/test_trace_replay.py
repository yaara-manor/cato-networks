from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import psycopg
from pydantic_ai import Agent
from pydantic_ai.messages import ModelMessagesTypeAdapter
from pydantic_ai.models.test import TestModel

from agents.models import ToolCall, TraceStatus
from guardrails.models import ActionType
from guardrails.redactor import redact
from retrieval.models import KBSearchResult, KBSearchStatus, RetrievedPassage
from storage import AgentRole, MessageSender, StateStore, ToolCallRecord, TraceRecord
from tools import TelemetryService

NOW = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)
Restart = Callable[[], psycopg.Connection[Any]]
NewConversation = Callable[[], UUID]
MakeTrace = Callable[..., TraceRecord]


def _call(trace: TraceRecord, name: str, result: dict[str, Any]) -> ToolCallRecord:
    call = ToolCall(
        tool_name=name,
        arguments={"site_id": "S-1007-01"},
        status="OK",
        result=result,
        latency_ms=4,
    )
    return ToolCallRecord.from_tool_call(trace.id, trace.conversation_id, 0, call, NOW)


def _kb_envelope() -> KBSearchResult:
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
            rrf_score=0.1,
            rerank_score=score,
        )
        for i, score in ((1, 0.9), (2, 0.4))
    ]
    return KBSearchResult(
        status=KBSearchStatus.CONFIDENT,
        query="bgp",
        candidates=passages,
        snapshot_date=NOW,
    )


def test_scripted_turn_replays_from_rows_alone(
    store: StateStore,
    new_conversation: NewConversation,
    make_trace: MakeTrace,
    restart: Restart,
) -> None:
    cid = new_conversation()
    customer_id, reply_id = uuid4(), uuid4()
    store.append_customer_message(cid, customer_id, redact("BGP down at S-1007-01").text, NOW)
    messages = TestModel(custom_output_text="ok")
    run = Agent(messages).run_sync("hello")
    history = ModelMessagesTypeAdapter.dump_python(run.all_messages(), mode="json")

    bgp = TelemetryService().get_bgp_status("S-1007-01").model_dump(mode="json")
    triage = make_trace(cid, role=AgentRole.TRIAGE, model_messages=history, prompt_tokens=7)
    diagnostics = make_trace(cid, role=AgentRole.DIAGNOSTICS, latency_ms=11, cost_usd=Decimal("0.01"))
    knowledge = make_trace(cid, role=AgentRole.KNOWLEDGE, latency_ms=13)
    first_resolution = make_trace(cid, role=AgentRole.RESOLUTION, status=TraceStatus.RETRIED)
    retry = make_trace(
        cid,
        role=AgentRole.RESOLUTION,
        parent_trace_id=first_resolution.id,
        cost_usd=Decimal("0.02"),
    )
    store.record_trace(triage, [])
    store.record_trace(diagnostics, [_call(diagnostics, "get_bgp_status", bgp)])
    store.record_trace(
        knowledge,
        [_call(knowledge, "kb_search", _kb_envelope().model_dump(mode="json"))],
    )
    store.record_trace(first_resolution, [])
    store.record_trace(retry, [])
    approval = store.create_approval(
        cid, customer_id, ActionType.CREDIT, {"amount": "50"}, f"{customer_id}:0", NOW
    )
    store.complete_turn(
        cid,
        1,
        MessageSender.AGENT,
        "fixed",
        (),
        (),
        reply_id,
        NOW + timedelta(minutes=1),
    )
    del store, triage

    with restart() as fresh:
        replay = StateStore(fresh).replay_trace(cid)
    assert replay is not None
    [turn] = replay.turns
    assert turn.customer_message is not None and turn.customer_message.id == customer_id
    assert turn.reply is not None and turn.reply.id == reply_id
    assert [s.trace.seq for s in turn.steps] == [1, 2, 3, 4, 5]
    assert [s.trace.agent_role for s in turn.steps][:3] == [
        AgentRole.TRIAGE,
        AgentRole.DIAGNOSTICS,
        AgentRole.KNOWLEDGE,
    ]
    assert turn.steps[4].trace.parent_trace_id == turn.steps[3].trace.id
    assert [len(s.tool_calls) for s in turn.steps] == [0, 1, 1, 0, 0]
    assert turn.steps[1].tool_calls[0].result["evidence"] == bgp["evidence"]
    assert [c["rerank_score"] for c in turn.steps[2].tool_calls[0].result["candidates"]] == [0.9, 0.4]
    assert sum(s.trace.latency_ms for s in turn.steps) == 5 + 11 + 13 + 5 + 5
    assert sum(s.trace.prompt_tokens for s in turn.steps) == 7 + 10 * 4
    assert sum((s.trace.cost_usd or Decimal(0)) for s in turn.steps) == Decimal("0.03")
    assert [(a.id, a.message_id) for a in replay.approvals] == [(approval.id, customer_id)]
    stored_history = turn.steps[0].trace.model_messages
    assert stored_history is not None
    assert ModelMessagesTypeAdapter.validate_python(stored_history) == run.all_messages()


def test_unknown_and_customer_only_conversations(
    store: StateStore, new_conversation: NewConversation
) -> None:
    assert store.replay_trace(uuid4()) is None
    cid = new_conversation()
    store.append_customer_message(cid, uuid4(), "hi", NOW)
    replay = store.replay_trace(cid)
    assert replay is not None
    [turn] = replay.turns
    assert (turn.steps, turn.reply) == ((), None)


def test_every_row_appears_exactly_once(
    store: StateStore, new_conversation: NewConversation, make_trace: MakeTrace
) -> None:
    cid = new_conversation()
    for turn in (1, 2, 3):
        store.append_customer_message(cid, uuid4(), f"q{turn}", NOW + timedelta(minutes=turn))
        trace = make_trace(cid, turn=turn)
        store.record_trace(trace, [_call(trace, "t", {}), _call(trace, "u", {})])
        store.complete_turn(
            cid,
            turn,
            MessageSender.AGENT,
            "a",
            (),
            (),
            uuid4(),
            NOW + timedelta(minutes=turn, seconds=1),
        )
    replay = store.replay_trace(cid)
    assert replay is not None
    replayed_messages = [m.id for t in replay.turns for m in (t.customer_message, t.reply) if m is not None]
    replayed_calls = [c.id for t in replay.turns for s in t.steps for c in s.tool_calls]
    assert sorted(replayed_messages) == sorted(m.id for m in store.list_messages(cid))
    assert sorted(replayed_calls) == sorted(c.id for c in store.list_tool_calls(cid))
    assert len(replayed_calls) == 6
