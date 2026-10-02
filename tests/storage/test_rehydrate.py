from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import psycopg

from agents.models import TraceStatus
from guardrails.models import (
    ActionType,
    InjectionCategory,
    InjectionVerdict,
    RedactionFinding,
    RedactionResult,
    SecretKind,
    SessionGuardHistory,
)
from storage import (
    AgentRole,
    ApprovalResolution,
    ApprovalStatus,
    ConversationStage,
    MessageSender,
    StateStore,
    TraceRecord,
)

NOW = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)
Restart = Callable[[], psycopg.Connection[Any]]
NewConversation = Callable[[], UUID]
MakeTrace = Callable[..., TraceRecord]


def _turn(store: StateStore, cid: UUID, text: str, minute: int) -> UUID:
    message_id = uuid4()
    store.append_customer_message(cid, message_id, text, NOW + timedelta(minutes=minute))
    return message_id


def _reply(store: StateStore, cid: UUID, turn: int, minute: int) -> None:
    store.complete_turn(
        cid,
        turn,
        MessageSender.AGENT,
        "reply",
        [{"tag": "[kb:a#b]"}],
        (),
        uuid4(),
        NOW + timedelta(minutes=minute),
    )


def test_mid_conversation_restart_restores_everything(
    store: StateStore,
    new_conversation: NewConversation,
    restart: Restart,
    make_trace: MakeTrace,
) -> None:
    cid = new_conversation()
    _turn(store, cid, "hello", 0)
    _reply(store, cid, 1, 1)
    verdict = InjectionVerdict(
        blocked=True,
        categories=frozenset({InjectionCategory.ROLE_OVERRIDE}),
        rule_ids=("r1",),
    )
    finding = RedactionFinding(kind=SecretKind.JWT, start=0, end=1, sha256="deadbeef")
    history = (
        SessionGuardHistory()
        .with_injection(verdict)
        .with_redaction(RedactionResult(text="x", findings=(finding,)))
    )
    store.save_guard_history(cid, history, NOW)
    store.record_trace(make_trace(cid), [])
    store.set_stage(cid, ConversationStage.RESOLUTION, NOW)
    before = store.rehydrate(cid)
    del store
    with restart() as fresh:
        after = StateStore(fresh).rehydrate(cid)
    assert after is not None and before is not None
    assert after.messages == before.messages
    assert [m.sender for m in after.messages] == [
        MessageSender.CUSTOMER,
        MessageSender.AGENT,
    ]
    assert after.messages[1].citations == ({"tag": "[kb:a#b]"},)
    assert after.conversation.stage is ConversationStage.RESOLUTION
    assert after.conversation.guard_history.agent_context_note() == history.agent_context_note()
    assert "deadbeef" in after.conversation.guard_history.secret_hashes
    assert after.open_turn_traces == ()


def test_crash_mid_turn_exposes_open_turn_traces(
    store: StateStore,
    new_conversation: NewConversation,
    restart: Restart,
    make_trace: MakeTrace,
) -> None:
    cid = new_conversation()
    _turn(store, cid, "help", 0)
    store.record_trace(
        make_trace(cid, role=AgentRole.TRIAGE, status=TraceStatus.OK, output={"scope": "ok"}),
        [],
    )
    store.set_stage(cid, ConversationStage.DIAGNOSTICS, NOW)
    with restart() as fresh:
        resumed = StateStore(fresh)
        snapshot = resumed.rehydrate(cid)
        assert snapshot is not None
        assert snapshot.conversation.stage is ConversationStage.DIAGNOSTICS
        assert [t.agent_role for t in snapshot.open_turn_traces] == [AgentRole.TRIAGE]
        _reply(resumed, cid, 1, 1)
        done = resumed.rehydrate(cid)
    assert done is not None
    assert done.open_turn_traces == ()
    assert done.conversation.stage is ConversationStage.IDLE


def test_orphaned_older_turn_is_ignored(
    store: StateStore, new_conversation: NewConversation, make_trace: MakeTrace
) -> None:
    cid = new_conversation()
    _turn(store, cid, "never answered", 0)
    store.record_trace(make_trace(cid, turn=1), [])
    _turn(store, cid, "second", 1)
    _reply(store, cid, 2, 2)
    snapshot = store.rehydrate(cid)
    assert snapshot is not None
    assert snapshot.open_turn_traces == ()


def test_pending_approvals_after_restart(
    store: StateStore, new_conversation: NewConversation, restart: Restart
) -> None:
    cid = new_conversation()
    message_id = _turn(store, cid, "credit", 0)
    pending = store.create_approval(cid, message_id, ActionType.CREDIT, {"a": "1"}, "k1", NOW)
    done = store.create_approval(cid, message_id, ActionType.MFA_RESET, {"a": "1"}, "k2", NOW)
    store.resolve_approval(done.id, ApprovalResolution(status=ApprovalStatus.REJECTED), NOW)
    with restart() as fresh:
        snapshot = StateStore(fresh).rehydrate(cid)
    assert snapshot is not None
    assert [a.id for a in snapshot.pending_approvals] == [pending.id]


def test_unknown_and_empty_conversations(store: StateStore, new_conversation: NewConversation) -> None:
    assert store.rehydrate(uuid4()) is None
    snapshot = store.rehydrate(new_conversation())
    assert snapshot is not None
    assert (
        snapshot.messages,
        snapshot.open_turn_traces,
        snapshot.pending_approvals,
    ) == ((), (), ())
