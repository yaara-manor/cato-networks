import threading
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import psycopg
import pytest

from guardrails.models import ActionType
from storage import ActionStateError, SimulatedActionStatus, StateStore

NOW = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)
Restart = Callable[[], psycopg.Connection[Any]]
NewConversation = Callable[[], UUID]


def _claim(store: StateStore, cid: UUID, key: str = "k", **overrides: Any) -> Any:
    args: dict[str, Any] = {
        "conversation_id": cid,
        "message_id": None,
        "approval_id": None,
        "kind": "CREATE_TICKET",
        "idempotency_key": key,
        "payload": {"subject": "s"},
        "at": NOW,
    }
    return store.claim_action(**(args | overrides))


def test_claim_twice_returns_same_row_and_finish_once(store: StateStore, new_conversation: NewConversation) -> None:
    cid = new_conversation()
    first, again = _claim(store, cid), _claim(store, cid)
    assert (first.is_new, again.is_new) == (True, False)
    assert first.action == again.action
    done = store.finish_action(first.action.id, SimulatedActionStatus.DONE, {"ref": "x"}, NOW)
    assert (done.status, done.result, done.completed_at) == (SimulatedActionStatus.DONE, {"ref": "x"}, NOW)
    with pytest.raises(ActionStateError):
        store.finish_action(first.action.id, SimulatedActionStatus.FAILED, {}, NOW)
    assert _claim(store, cid).action.status is SimulatedActionStatus.DONE


def test_racing_claims_yield_one_new(
    store: StateStore, new_conversation: NewConversation, restart: Restart
) -> None:
    cid = new_conversation()
    outcomes: list[bool] = []

    def race() -> None:
        with restart() as connection:
            outcomes.append(_claim(StateStore(connection), cid).is_new)

    threads = [threading.Thread(target=race) for _ in range(6)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(outcomes) == [False] * 5 + [True]


def test_list_is_ordered_and_survives_restart(
    store: StateStore, new_conversation: NewConversation, restart: Restart
) -> None:
    cid = new_conversation()
    _claim(store, cid, "late", at=NOW + timedelta(minutes=1))
    _claim(store, cid, "early")
    with restart() as second:
        assert [a.idempotency_key for a in StateStore(second).list_simulated_actions(cid)] == ["early", "late"]


def test_approval_path_row_keeps_approval_id(store: StateStore, new_conversation: NewConversation) -> None:
    cid = new_conversation()
    message_id = uuid4()
    store.append_customer_message(cid, message_id, "credit", NOW)
    approval = store.create_approval(cid, message_id, ActionType.CREDIT, {"amount": "5"}, "k", NOW)
    claimed = _claim(store, cid, f"approval:{approval.id}", approval_id=approval.id, kind="CREDIT")
    assert claimed.action.approval_id == approval.id
    assert claimed.action.message_id is None


def test_nul_byte_in_payload_is_stripped(store: StateStore, new_conversation: NewConversation) -> None:
    cid = new_conversation()
    claimed = _claim(store, cid, payload={"subject": "a\x00b"})
    assert claimed.action.payload == {"subject": "ab"}


def test_message_from_another_conversation_is_rejected(
    store: StateStore, new_conversation: NewConversation
) -> None:
    mine, other = new_conversation(), new_conversation()
    message_id = uuid4()
    store.append_customer_message(other, message_id, "hi", NOW)
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        _claim(store, mine, message_id=message_id)
