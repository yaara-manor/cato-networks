from typing import Any
from uuid import UUID, uuid4

import pytest

from core.clock import SimulationClock
from orchestration.canned import AGENT_FAILURE_PAUSE
from orchestration.state import STATE_VERSION, OrchestratorState, StateVersionError
from storage import MessageSender, StateSnapshot, StateStore, StoredMessage
from tests.orchestration.conftest import PRIYA, Harness, Scripted
from tests.orchestration.test_partial_failure import DOWN, TELEMETRY_TEXT


def _stored(harness: Harness, conversation_id: UUID) -> StateSnapshot:
    with harness.connect() as fresh:
        snapshot = StateStore(fresh).rehydrate(conversation_id)
    assert snapshot is not None
    return snapshot.conversation.state


def test_state_survives_worker_restart(harness: Harness, scripted: Scripted) -> None:
    scripted.unavailable = DOWN
    conversation_id = harness.new_conversation(PRIYA)
    first = harness.workflow(scripted, None).run_turn(conversation_id, "help", uuid4())
    assert first.reply.startswith(TELEMETRY_TEXT)
    before = OrchestratorState.from_snapshot(_stored(harness, conversation_id))
    assert before.notice_shown

    with harness.connect() as fresh:  # new worker, new connection
        second = harness.workflow(scripted, fresh).run_turn(conversation_id, "help", uuid4())
    after = OrchestratorState.from_snapshot(_stored(harness, conversation_id))
    assert TELEMETRY_TEXT not in second.reply
    assert after == before


def test_pre_state_conversation_gets_current_version(harness: Harness, scripted: Scripted) -> None:
    conversation_id = harness.new_conversation(PRIYA)
    assert _stored(harness, conversation_id).data == {}
    harness.workflow(scripted, None).run_turn(conversation_id, "help", uuid4())
    assert _stored(harness, conversation_id).version == STATE_VERSION


def test_newer_snapshot_is_refused_and_untouched(harness: Harness, scripted: Scripted) -> None:
    conversation_id = harness.new_conversation(PRIYA)
    newer = StateSnapshot(version=STATE_VERSION + 98, data={"clarification_turns": 7})
    with harness.connect() as fresh:
        StateStore(fresh).save_state(conversation_id, newer, SimulationClock().now())
    with pytest.raises(StateVersionError):
        harness.workflow(scripted, None).run_turn(conversation_id, "help", uuid4())
    assert _stored(harness, conversation_id) == newer
    assert scripted.calls == []


def test_reply_write_failure_rolls_back_state_and_retry_replays(
    harness: Harness, scripted: Scripted, monkeypatch: pytest.MonkeyPatch
) -> None:
    scripted.unavailable = DOWN  # a successful turn would set notice_shown
    conversation_id = harness.new_conversation(PRIYA)
    workflow = harness.workflow(scripted, None)
    retried = uuid4()
    real_insert = StateStore._insert_message
    failures = [True]

    def fail_once(self: StateStore, *args: Any, **kwargs: Any) -> StoredMessage:
        if failures and args[3] is MessageSender.AGENT:
            failures.pop()
            raise RuntimeError("db down")
        return real_insert(self, *args, **kwargs)

    monkeypatch.setattr(StateStore, "_insert_message", fail_once)
    assert workflow.run_turn(conversation_id, "help", retried).reply == AGENT_FAILURE_PAUSE
    assert not OrchestratorState.from_snapshot(_stored(harness, conversation_id)).notice_shown
    calls = list(scripted.calls)
    assert workflow.run_turn(conversation_id, "help", retried).reply == AGENT_FAILURE_PAUSE
    assert scripted.calls == calls
    assert workflow.run_turn(conversation_id, "help", uuid4()).reply.startswith(TELEMETRY_TEXT)


def test_idempotent_retry_returns_the_full_original_result(harness: Harness, scripted: Scripted) -> None:
    scripted.unavailable = DOWN
    conversation_id = harness.new_conversation(PRIYA)
    workflow = harness.workflow(scripted, None)
    message_id = uuid4()
    first = workflow.run_turn(conversation_id, "help", message_id)
    assert first.degradations
    assert workflow.run_turn(conversation_id, "help", message_id) == first
