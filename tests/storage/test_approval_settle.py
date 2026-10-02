from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import psycopg
import pytest

from guardrails.models import ActionType
from storage import (
    Approval,
    ApprovalResolution,
    ApprovalStateError,
    ApprovalStatus,
    ConversationStage,
    MessageSender,
    StateStore,
)

NOW = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)
NewConversation = Callable[[], UUID]
CREDIT = {"amount": "500", "currency": "USD", "ticket_id": "T-1"}
APPROVE = ApprovalResolution(status=ApprovalStatus.APPROVED)


def _propose(store: StateStore, cid: UUID, key: str = "k") -> UUID:
    message_id = uuid4()
    store.append_customer_message(cid, message_id, "credit please", NOW)
    return store.create_approval(cid, message_id, ActionType.CREDIT, CREDIT, key, NOW).id


def _resolved(store: StateStore, cid: UUID, key: str = "k", at: datetime = NOW) -> UUID:
    approval_id = _propose(store, cid, key)
    store.resolve_approval(approval_id, APPROVE, at)
    return approval_id


def test_settle_writes_event_turn_once(
    store: StateStore, new_conversation: NewConversation, conn: psycopg.Connection[Any]
) -> None:
    cid = new_conversation()
    approval_id = _resolved(store, cid)
    before = store.get_conversation(cid)
    assert before is not None

    first = store.settle_approval(approval_id, "approved", NOW)
    again = store.settle_approval(approval_id, "approved", NOW + timedelta(hours=1))

    after = store.get_conversation(cid)
    assert after is not None
    assert (first.sender, first.turn, first.result) == (MessageSender.AGENT, before.last_turn + 1, None)
    assert again == first
    assert (after.last_turn, after.stage, after.state) == (first.turn, before.stage, before.state)
    assert conn.execute("select count(*) from messages where id = %s", (first.id,)).fetchone() == (1,)
    settled = store.get_approval(approval_id)
    assert settled is not None and settled.settled_at == NOW


def test_settle_rejects_pending_and_unknown(store: StateStore, new_conversation: NewConversation) -> None:
    pending = _propose(store, new_conversation())
    for approval_id in (pending, uuid4()):
        with pytest.raises(ApprovalStateError):
            store.settle_approval(approval_id, "x", NOW)


def test_event_turn_does_not_become_open_turn_reply(store: StateStore, new_conversation: NewConversation) -> None:
    """Why settle needs the turn lock: an event bumping last_turn under an open turn skips its IDLE flip."""
    cid = new_conversation()
    approval_id = _resolved(store, cid)
    open_message = uuid4()
    open_turn = store.append_customer_message(cid, open_message, "still chatting", NOW).turn
    event = store.settle_approval(approval_id, "approved", NOW)
    assert event.turn == open_turn + 1
    store.complete_turn(cid, open_turn, MessageSender.AGENT, "real answer", (), (), uuid4(), NOW)
    conversation = store.get_conversation(cid)
    assert conversation is not None and conversation.stage is ConversationStage.INGESTION_GUARD


def test_list_unsettled_is_resolved_unsettled_oldest_first_and_limited(
    store: StateStore, new_conversation: NewConversation
) -> None:
    cid = new_conversation()
    newer = _resolved(store, cid, "a", NOW + timedelta(minutes=5))
    older = _resolved(store, cid, "b", NOW)
    settled = _resolved(store, cid, "c", NOW)
    store.settle_approval(settled, "done", NOW)
    _propose(store, cid, "d")  # pending: not listed

    mine = {newer, older}
    listed = [a.id for a in store.list_unsettled_approvals(1000) if a.conversation_id == cid]
    assert listed == [older, newer] and set(listed) == mine
    assert len(store.list_unsettled_approvals(1)) == 1


def test_customer_reason_roundtrips_and_effective_payload(
    store: StateStore, new_conversation: NewConversation, restart: Callable[[], psycopg.Connection[Any]]
) -> None:
    cid = new_conversation()
    approval_id = _propose(store, cid)
    edit = ApprovalResolution(status=ApprovalStatus.EDITED, edited_payload=CREDIT | {"amount": "300"})
    store.resolve_approval(approval_id, edit, NOW, customer_reason="partial credit")
    with restart() as other:
        approval: Approval | None = StateStore(other).get_approval(approval_id)
    assert approval is not None
    assert approval.customer_reason == "partial credit"
    assert approval.effective_payload["amount"] == "300" and approval.payload["amount"] == "500"
    plain = _resolved(store, cid, "z")
    plain_row = store.get_approval(plain)
    assert plain_row is not None and plain_row.effective_payload == CREDIT
