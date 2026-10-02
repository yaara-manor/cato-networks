from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import psycopg

from guardrails.models import ActionType
from storage import (
    ApprovalResolution,
    ApprovalStatus,
    ConversationStage,
    MessageSender,
    StateSnapshot,
    StateStore,
)

NOW = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)
NewConversation = Callable[[], UUID]
CREDIT = {"amount": "50", "reason": "SLA breach"}


def _propose(store: StateStore, cid: UUID, key: str, at: datetime) -> UUID:
    message_id = uuid4()
    store.append_customer_message(cid, message_id, "credit please", at)
    return store.create_approval(cid, message_id, ActionType.CREDIT, CREDIT, key, at).id


def _reply(store: StateStore, cid: UUID, result: dict[str, Any] | None) -> None:
    turn = store.append_customer_message(cid, uuid4(), "q", NOW).turn
    store.complete_turn(cid, turn, MessageSender.AGENT, "a", (), (), uuid4(), NOW, result=result)


def _rows(store: StateStore, cids: list[UUID], limit: int = 1000) -> dict[UUID, Any]:
    return {r.conversation_id: r for r in store.list_board_rows(limit) if r.conversation_id in cids}


def test_board_orders_pending_first_and_counts_only_pending(
    store: StateStore, new_conversation: NewConversation
) -> None:
    older, newer, resolved_only, plain = (new_conversation() for _ in range(4))
    _propose(store, older, "a", NOW)
    _propose(store, older, "b", NOW + timedelta(minutes=5))
    _propose(store, newer, "a", NOW + timedelta(minutes=1))
    done = _propose(store, resolved_only, "a", NOW)
    store.resolve_approval(done, ApprovalResolution(status=ApprovalStatus.APPROVED), NOW)
    store.set_stage(plain, ConversationStage.TRIAGE, NOW + timedelta(days=30))
    mine = [older, newer, resolved_only, plain]

    ordered = [r for r in store.list_board_rows(1000) if r.conversation_id in mine]

    assert [r.conversation_id for r in ordered] == [older, newer, plain, resolved_only]
    rows = {r.conversation_id: r for r in ordered}
    assert [rows[c].pending_count for c in mine] == [2, 1, 0, 0]
    assert rows[older].oldest_pending_at == NOW
    assert rows[resolved_only].oldest_pending_at is None
    assert len(store.list_board_rows(2)) == 2


def test_oncall_paged_reads_state_and_tolerates_missing_data(
    store: StateStore, new_conversation: NewConversation, conn: psycopg.Connection[Any]
) -> None:
    paged, unpaged, no_data = (new_conversation() for _ in range(3))
    store.save_state(paged, StateSnapshot(data={"oncall_paged": True}), NOW)
    store.save_state(unpaged, StateSnapshot(data={"oncall_paged": False}), NOW)
    conn.execute("update conversations set state = '{\"version\": 1}' where id = %s", (no_data,))

    rows = _rows(store, [paged, unpaged, no_data])

    assert [rows[c].oncall_paged for c in (paged, unpaged, no_data)] == [True, False, False]


def test_escalation_offered_follows_newest_non_null_result(
    store: StateStore, new_conversation: NewConversation, conn: psycopg.Connection[Any]
) -> None:
    offered, cleared, event_after, malformed, none = (new_conversation() for _ in range(5))
    _reply(store, offered, {"escalation_offered": True})
    _reply(store, cleared, {"escalation_offered": True})
    _reply(store, cleared, {"escalation_offered": False})
    _reply(store, event_after, {"escalation_offered": True})
    _reply(store, event_after, None)
    _reply(store, malformed, {"escalation_offered": "maybe"})
    conn.execute(
        "update messages set result = '[1]'::jsonb where conversation_id = %s and result is not null",
        (malformed,),
    )

    rows = _rows(store, [offered, cleared, event_after, malformed, none])

    assert [rows[c].escalation_offered for c in (offered, cleared, event_after, malformed, none)] == [
        True,
        False,
        True,
        False,
        False,
    ]
