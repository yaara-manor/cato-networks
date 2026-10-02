import threading
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import psycopg
import pytest

from core.config import settings
from guardrails.models import ActionType
from storage import (
    ApprovalResolution,
    ApprovalStateError,
    ApprovalStatus,
    ConversationStage,
    MessageSender,
    StateStore,
)

NOW = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)
Restart = Callable[[], psycopg.Connection[Any]]
NewConversation = Callable[[], UUID]
CREDIT = {"amount": "50", "reason": "SLA breach"}
APPROVE = ApprovalResolution(status=ApprovalStatus.APPROVED)


def _propose(store: StateStore, cid: UUID, key: str = "k", payload: dict[str, str] | None = None) -> UUID:
    message_id = uuid4()
    store.append_customer_message(cid, message_id, "credit please", NOW)
    return store.create_approval(cid, message_id, ActionType.CREDIT, payload or CREDIT, key, NOW).id


def test_pending_visible_after_restart_and_resolved_by_third_connection(
    store: StateStore, new_conversation: NewConversation, restart: Restart
) -> None:
    cid = new_conversation()
    approval_id = _propose(store, cid)
    with restart() as second, restart() as third:
        assert [a.id for a in StateStore(second).list_pending_approvals(cid)] == [approval_id]
        resolved = StateStore(third).resolve_approval(approval_id, APPROVE, NOW)
        assert (resolved.status, resolved.resolved_at) == (ApprovalStatus.APPROVED, NOW)
        assert StateStore(second).list_pending_approvals(cid) == []
        with pytest.raises(ApprovalStateError):
            StateStore(second).resolve_approval(approval_id, APPROVE, NOW)
    with pytest.raises(ApprovalStateError):
        store.resolve_approval(uuid4(), APPROVE, NOW)


def test_create_is_idempotent_first_payload_wins(
    store: StateStore, new_conversation: NewConversation, conn: psycopg.Connection[Any]
) -> None:
    cid = new_conversation()
    message_id = uuid4()
    store.append_customer_message(cid, message_id, "q", NOW)
    first = store.create_approval(cid, message_id, ActionType.CREDIT, CREDIT, "k", NOW)
    again = store.create_approval(cid, message_id, ActionType.CREDIT, {"amount": "999"}, "k", NOW)
    assert again == first
    assert conn.execute("select count(*) from approvals where conversation_id = %s", (cid,)).fetchone() == (
        1,
    )


def test_edited_resolution_keeps_original_payload(
    store: StateStore, new_conversation: NewConversation
) -> None:
    cid = new_conversation()
    approval_id = _propose(store, cid)
    edit = ApprovalResolution(
        status=ApprovalStatus.EDITED,
        reviewer_notes="lower",
        edited_payload={"amount": "20"},
    )
    resolved = store.resolve_approval(approval_id, edit, NOW)
    assert (resolved.payload, resolved.edited_payload, resolved.reviewer_notes) == (
        CREDIT,
        {"amount": "20"},
        "lower",
    )


def test_queue_spans_conversations(store: StateStore, new_conversation: NewConversation) -> None:
    first, second = new_conversation(), new_conversation()
    first_id, second_id = _propose(store, first), _propose(store, second)
    assert {first_id, second_id} <= {a.id for a in store.list_pending_approvals()}
    assert [a.id for a in store.list_pending_approvals(first)] == [first_id]


def test_racing_reviewers_yield_one_winner(store: StateStore, new_conversation: NewConversation) -> None:
    cid = new_conversation()
    approval_id = _propose(store, cid)
    outcomes: list[str] = []

    def reviewer() -> None:
        with psycopg.connect(settings.database_url, autocommit=True) as connection:
            try:
                StateStore(connection).resolve_approval(approval_id, APPROVE, NOW)
                outcomes.append("won")
            except ApprovalStateError:
                outcomes.append("lost")

    threads = [threading.Thread(target=reviewer) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(outcomes) == ["lost", "won"]


def test_every_action_type_roundtrips(store: StateStore, new_conversation: NewConversation) -> None:
    cid = new_conversation()
    message_id = uuid4()
    store.append_customer_message(cid, message_id, "q", NOW)
    for index, action in enumerate(ActionType):
        stored = store.create_approval(cid, message_id, action, CREDIT, f"{message_id}:{index}", NOW)
        assert store.get_approval(stored.id) == stored
        assert stored.action_type is action


def test_pending_approval_does_not_block_conversation(
    store: StateStore, new_conversation: NewConversation
) -> None:
    cid = new_conversation()
    _propose(store, cid)
    store.append_customer_message(cid, uuid4(), "another question", NOW)
    store.complete_turn(cid, 2, MessageSender.AGENT, "answer", (), (), uuid4(), NOW)
    conversation = store.get_conversation(cid)
    assert conversation is not None
    assert conversation.stage is ConversationStage.IDLE
    assert len(store.list_pending_approvals(cid)) == 1
