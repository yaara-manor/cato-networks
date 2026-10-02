from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

import psycopg

from storage.jsonb import redacted_json
from storage.models import ActionStateError, ClaimedAction, SimulatedAction, SimulatedActionStatus
from storage.sql import fetch_all, fetch_one, jsonable


def claim_action(
    conn: psycopg.Connection[Any],
    conversation_id: UUID,
    message_id: UUID | None,
    approval_id: UUID | None,
    kind: str,
    idempotency_key: str,
    payload: dict[str, Any],
    at: datetime,
) -> ClaimedAction:
    """The unique key is the lock: of any number of racing claims exactly one is new."""
    inserted = conn.execute(
        "insert into simulated_actions (id, conversation_id, message_id, idempotency_key, kind, approval_id,"
        " payload, status, claimed_at) values (%(id)s, %(conversation_id)s, %(message_id)s, %(key)s, %(kind)s,"
        " %(approval_id)s, %(payload)s, %(status)s, %(at)s) on conflict (idempotency_key) do nothing",
        {
            "id": uuid4(),
            "conversation_id": conversation_id,
            "message_id": message_id,
            "key": idempotency_key,
            "kind": kind,
            "approval_id": approval_id,
            "payload": jsonable(redacted_json(payload)),
            "status": SimulatedActionStatus.CLAIMED.value,
            "at": at,
        },
    ).rowcount
    action = fetch_one(
        conn,
        SimulatedAction,
        "select * from simulated_actions where idempotency_key = %(key)s",
        {"key": idempotency_key},
    )
    assert action is not None
    return ClaimedAction(action=action, is_new=inserted == 1)


def finish_action(
    conn: psycopg.Connection[Any],
    action_id: UUID,
    status: SimulatedActionStatus,
    result: dict[str, Any],
    at: datetime,
) -> SimulatedAction:
    """Compare-and-set from CLAIMED: an action finishes once."""
    action = fetch_one(
        conn,
        SimulatedAction,
        "update simulated_actions set status = %(status)s, result = %(result)s, completed_at = %(at)s"
        " where id = %(id)s and status = 'CLAIMED' returning *",
        {"id": action_id, "status": status.value, "result": jsonable(redacted_json(result)), "at": at},
    )
    if action is None:
        raise ActionStateError(f"action {action_id} is unknown or already finished")
    return action


def list_simulated_actions(conn: psycopg.Connection[Any], conversation_id: UUID) -> list[SimulatedAction]:
    return fetch_all(
        conn,
        SimulatedAction,
        "select * from simulated_actions where conversation_id = %(id)s order by claimed_at, id",
        {"id": conversation_id},
    )
