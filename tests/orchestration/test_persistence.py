from typing import Any
from uuid import uuid4

import psycopg

from guardrails import SessionGuardHistory
from storage import ConversationStage as S
from storage import MessageSender, StateStore
from tests.orchestration.conftest import PRIYA, Harness, Scripted

PSK = "pre_shared_key: Zq8vN3xLw0pTt7YbRk2mC9dH"


def test_full_turn_persists_and_survives_restart(harness: Harness, scripted: Scripted) -> None:
    conversation_id = harness.new_conversation(PRIYA)
    result = harness.workflow(scripted, None).run_turn(conversation_id, "Branch site is down", uuid4())

    assert result.path == (
        S.INGESTION_GUARD,
        S.TRIAGE,
        S.DIAGNOSTICS,
        S.KNOWLEDGE_RETRIEVAL,
        S.RESOLUTION,
        S.ACTION_EVALUATION,
        S.IDLE,
    )
    with harness.connect() as fresh:
        store = StateStore(fresh)
        snapshot = store.rehydrate(conversation_id)
        assert snapshot is not None
        assert [m.sender for m in snapshot.messages] == [MessageSender.CUSTOMER, MessageSender.AGENT]
        assert snapshot.messages[1].content == result.reply
        assert snapshot.conversation.stage is S.IDLE
        assert snapshot.conversation.account_id == "ACC-1002"
        traces = store.list_traces(conversation_id)
        assert [t.agent_role.value for t in traces] == ["TRIAGE", "DIAGNOSTICS", "KNOWLEDGE", "RESOLUTION"]
        assert traces[1].parent_trace_id == traces[0].id


def test_retry_with_same_message_id_does_not_rerun_agents(harness: Harness, scripted: Scripted) -> None:
    conversation_id = harness.new_conversation(PRIYA)
    workflow = harness.workflow(scripted, None)
    message_id = uuid4()
    first = workflow.run_turn(conversation_id, "Branch site is down", message_id)
    calls_after_first = list(scripted.calls)

    again = workflow.run_turn(conversation_id, "Branch site is down", message_id)

    assert again.reply == first.reply
    assert scripted.calls == calls_after_first
    snapshot = StateStore(harness.connect()).rehydrate(conversation_id)
    assert snapshot is not None
    assert [m.sender for m in snapshot.messages].count(MessageSender.CUSTOMER) == 1


def test_psk_never_reaches_agents_or_storage(
    harness: Harness, scripted: Scripted, conn: psycopg.Connection[Any]
) -> None:
    conversation_id = harness.new_conversation(PRIYA)
    harness.workflow(scripted, None).run_turn(conversation_id, f"Tunnel flaps. {PSK}", uuid4())

    secret = PSK.split(": ")[1]
    assert all(secret not in repr(data) for seen in scripted.inputs.values() for data in seen)
    for query in (
        "select t::text from messages t where conversation_id = %(id)s",
        "select t::text from traces t where conversation_id = %(id)s",
        "select t::text from tool_calls t where conversation_id = %(id)s",
        "select t::text from conversations t where id = %(id)s",
    ):
        assert all(secret not in row[0] for row in conn.execute(query, {"id": conversation_id}))
    snapshot = StateStore(conn).rehydrate(conversation_id)
    assert snapshot is not None
    assert snapshot.conversation.guard_history != SessionGuardHistory()  # hash kept, not the secret
