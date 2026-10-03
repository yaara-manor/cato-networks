from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

import psycopg

from guardrails.models import ActionType
from storage.models import (
    Approval,
    ApprovalResolution,
    ApprovalStateError,
    ApprovalStatus,
)
from storage.sql import fetch_all, fetch_one, jsonable


def insert_approval(
    conn: psycopg.Connection[Any],
    conversation_id: UUID,
    message_id: UUID,
    action_type: ActionType,
    payload: dict[str, str],
    idempotency_key: str,
    at: datetime,
    approval_id: UUID | None,
) -> Approval:
    """First write per (conversation, idempotency_key) wins; a repeat returns the original row."""
    conn.execute(
        "insert into approvals (id, conversation_id, message_id, action_type, payload, status,"
        " idempotency_key, requested_at) values (%(id)s, %(conversation_id)s, %(message_id)s,"
        " %(action_type)s, %(payload)s, %(status)s, %(key)s, %(at)s)"
        " on conflict (conversation_id, idempotency_key) do nothing",
        {
            "id": approval_id or uuid4(),
            "conversation_id": conversation_id,
            "message_id": message_id,
            "action_type": action_type.value,
            "payload": jsonable(payload),
            "status": ApprovalStatus.PENDING.value,
            "key": idempotency_key,
            "at": at,
        },
    )
    approval = fetch_one(
        conn,
        Approval,
        "select * from approvals where conversation_id = %(id)s and idempotency_key = %(key)s",
        {"id": conversation_id, "key": idempotency_key},
    )
    assert approval is not None
    return approval


def get_approval(conn: psycopg.Connection[Any], approval_id: UUID) -> Approval | None:
    return fetch_one(conn, Approval, "select * from approvals where id = %(id)s", {"id": approval_id})


def list_approvals(
    conn: psycopg.Connection[Any], conversation_id: UUID, pending_only: bool
) -> list[Approval]:
    return fetch_all(
        conn,
        Approval,
        "select * from approvals where conversation_id = %(id)s and (not %(pending)s or status = 'PENDING')"
        " order by requested_at, id",
        {"id": conversation_id, "pending": pending_only},
    )


def list_pending_approvals(conn: psycopg.Connection[Any], conversation_id: UUID | None) -> list[Approval]:
    return fetch_all(
        conn,
        Approval,
        "select * from approvals where status = 'PENDING'"
        " and (%(id)s::uuid is null or conversation_id = %(id)s) order by requested_at, id",
        {"id": conversation_id},
    )


def list_unsettled_approvals(conn: psycopg.Connection[Any], limit: int) -> list[Approval]:
    return fetch_all(
        conn,
        Approval,
        "select * from approvals where status <> 'PENDING' and settled_at is null"
        " order by resolved_at, id limit %(limit)s",
        {"limit": limit},
    )


def mark_settled(conn: psycopg.Connection[Any], approval_id: UUID, at: datetime) -> None:
    conn.execute("update approvals set settled_at = %(at)s where id = %(id)s", {"id": approval_id, "at": at})


def resolve_approval(
    conn: psycopg.Connection[Any],
    approval_id: UUID,
    resolution: ApprovalResolution,
    at: datetime,
    customer_reason: str | None,
) -> Approval:
    """Compare-and-set from PENDING: of two racing reviewers exactly one wins."""
    approval = fetch_one(
        conn,
        Approval,
        "update approvals set status = %(status)s, reviewer_notes = %(notes)s, edited_payload = %(edited)s,"
        " customer_reason = %(reason)s, resolved_at = %(at)s"
        " where id = %(id)s and status = 'PENDING' returning *",
        {
            "id": approval_id,
            "status": resolution.status.value,
            "notes": jsonable(resolution.reviewer_notes),
            "edited": jsonable(resolution.edited_payload),
            "reason": jsonable(customer_reason),
            "at": at,
        },
    )
    if approval is None:
        raise ApprovalStateError(f"approval {approval_id} is unknown or already resolved")
    return approval
