import json
from collections.abc import Iterator, Mapping, Sequence
from contextlib import AbstractContextManager, contextmanager
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

import psycopg
from psycopg import sql

from core.config import settings
from core.models import AccountTier
from guardrails.models import ActionType, SessionGuardHistory
from guardrails.redactor import redact
from storage import approval_queries
from storage.models import (
    Approval,
    ApprovalResolution,
    Conversation,
    ConversationSnapshot,
    ConversationStage,
    MessageSender,
    StateSnapshot,
    StoredMessage,
    ToolCallRecord,
    TraceRecord,
)
from storage.replay import TraceReplay
from storage.sql import fetch_all, fetch_one, insert_row, jsonable
from storage.turn_lock import turn_lock
from tools.models import TelemetryEvidence

_TRACE_INPUT_MAX_CHARS = 20_000


def _redacted_input(trace_input: dict[str, Any]) -> dict[str, Any]:
    text = redact(json.dumps(trace_input, ensure_ascii=False)).text
    if len(text) > _TRACE_INPUT_MAX_CHARS:
        return {"truncated": text[:_TRACE_INPUT_MAX_CHARS]}
    try:
        return json.loads(text)
    except ValueError:  # a redaction span cut through JSON syntax
        return {"text": text}


def _open_turn(messages: Sequence[StoredMessage]) -> int | None:
    """Highest customer turn that has no AGENT/SYSTEM reply; older orphans are ignored."""
    customer_turns = [m.turn for m in messages if m.sender is MessageSender.CUSTOMER]
    if not customer_turns:
        return None
    top = max(customer_turns)
    replied = any(m.turn == top and m.sender is not MessageSender.CUSTOMER for m in messages)
    return None if replied else top


class StateStore:
    """Postgres persistence for conversations, messages, traces, tool calls, approvals.

    Every write locks the conversation row, so writers of one conversation serialize.
    """

    def __init__(self, connection: psycopg.Connection[Any]) -> None:
        if not connection.autocommit:
            raise ValueError("StateStore requires an autocommit connection")
        self._conn = connection

    def turn_lock(self, conversation_id: UUID) -> AbstractContextManager[None]:
        return turn_lock(self._conn, conversation_id, settings.turn_lock_timeout_s)

    # -- helpers ---------------------------------------------------------

    def _update_conversation(self, conversation_id: UUID, at: datetime, values: Mapping[str, Any]) -> None:
        query = sql.SQL("update conversations set {}, updated_at = %(updated_at)s where id = %(id)s").format(
            sql.SQL(", ").join(
                sql.SQL("{} = {}").format(sql.Identifier(k), sql.Placeholder(k)) for k in values
            )
        )
        params = {k: jsonable(v) for k, v in values.items()} | {
            "id": conversation_id,
            "updated_at": at,
        }
        if self._conn.execute(query, params).rowcount == 0:
            raise LookupError(f"unknown conversation {conversation_id}")

    def _lock_conversation(self, conversation_id: UUID) -> Conversation:
        conversation = fetch_one(
            self._conn,
            Conversation,
            "select * from conversations where id = %(id)s for update",
            {"id": conversation_id},
        )
        if conversation is None:
            raise LookupError(f"unknown conversation {conversation_id}")
        return conversation

    def _get_message(self, message_id: UUID) -> StoredMessage | None:
        return fetch_one(
            self._conn,
            StoredMessage,
            "select * from messages where id = %(id)s",
            {"id": message_id},
        )

    def _insert_message(
        self,
        conversation_id: UUID,
        message_id: UUID,
        turn: int,
        sender: MessageSender,
        content: str,
        citations: Sequence[dict[str, str]],
        telemetry_evidence: Sequence[TelemetryEvidence],
        at: datetime,
    ) -> StoredMessage:
        insert_row(
            self._conn,
            "messages",
            {
                "id": message_id,
                "conversation_id": conversation_id,
                "turn": turn,
                "sender": sender.value,
                "content": content,
                "citations": list(citations),
                "telemetry_evidence": [e.model_dump(mode="json") for e in telemetry_evidence],
                "created_at": at,
            },
        )
        stored = self._get_message(message_id)
        assert stored is not None
        return stored

    @contextmanager
    def _consistent_read(self) -> Iterator[None]:
        with self._conn.transaction():
            self._conn.execute("set transaction isolation level repeatable read")
            yield

    # -- conversations ---------------------------------------------------

    def create_conversation(
        self,
        account_id: str | None,
        contact_email: str | None,
        customer_tier: AccountTier,
        at: datetime,
        conversation_id: UUID | None = None,
    ) -> Conversation:
        conversation_id = conversation_id or uuid4()
        self._conn.execute(
            "insert into conversations (id, account_id, contact_email, customer_tier, stage, created_at, updated_at)"
            " values (%(id)s, %(account_id)s, %(contact_email)s, %(tier)s, %(stage)s, %(at)s, %(at)s)"
            " on conflict (id) do nothing",
            {
                "id": conversation_id,
                "account_id": account_id,
                "contact_email": contact_email,
                "tier": customer_tier,
                "stage": ConversationStage.IDLE.value,
                "at": at,
            },
        )
        conversation = self.get_conversation(conversation_id)
        assert conversation is not None
        return conversation

    def get_conversation(self, conversation_id: UUID) -> Conversation | None:
        return fetch_one(
            self._conn,
            Conversation,
            "select * from conversations where id = %(id)s",
            {"id": conversation_id},
        )

    def save_state(self, conversation_id: UUID, state: StateSnapshot, at: datetime) -> None:
        self._update_conversation(conversation_id, at, {"state": state.model_dump(mode="json")})

    def set_stage(self, conversation_id: UUID, stage: ConversationStage, at: datetime) -> None:
        self._update_conversation(conversation_id, at, {"stage": stage.value})

    def update_identity(
        self,
        conversation_id: UUID,
        account_id: str | None,
        contact_email: str | None,
        customer_tier: AccountTier,
        active_site_id: str | None,
        at: datetime,
    ) -> None:
        self._update_conversation(
            conversation_id,
            at,
            {
                "account_id": account_id,
                "contact_email": contact_email,
                "customer_tier": customer_tier,
                "active_site_id": active_site_id,
            },
        )

    def save_guard_history(self, conversation_id: UUID, history: SessionGuardHistory, at: datetime) -> None:
        self._update_conversation(conversation_id, at, {"guard_history": history.model_dump(mode="json")})

    # -- messages --------------------------------------------------------

    def append_customer_message(
        self, conversation_id: UUID, message_id: UUID, content: str, at: datetime
    ) -> StoredMessage:
        with self._conn.transaction():
            conversation = self._lock_conversation(conversation_id)
            if (existing := self._get_message(message_id)) is not None:
                return existing
            turn = conversation.last_turn + 1
            self._update_conversation(
                conversation_id,
                at,
                {"last_turn": turn, "stage": ConversationStage.INGESTION_GUARD.value},
            )
            return self._insert_message(
                conversation_id,
                message_id,
                turn,
                MessageSender.CUSTOMER,
                content,
                (),
                (),
                at,
            )

    def complete_turn(
        self,
        conversation_id: UUID,
        turn: int,
        sender: MessageSender,
        content: str,
        citations: Sequence[dict[str, str]],
        telemetry_evidence: Sequence[TelemetryEvidence],
        message_id: UUID,
        at: datetime,
    ) -> StoredMessage:
        if sender is MessageSender.CUSTOMER:
            raise ValueError("complete_turn stores a reply; sender cannot be CUSTOMER")
        with self._conn.transaction():
            conversation = self._lock_conversation(conversation_id)
            if (existing := self._get_message(message_id)) is not None:
                return existing
            if turn == conversation.last_turn:  # a stale retry must not flip a newer turn's stage
                self._update_conversation(conversation_id, at, {"stage": ConversationStage.IDLE.value})
            return self._insert_message(
                conversation_id,
                message_id,
                turn,
                sender,
                content,
                citations,
                telemetry_evidence,
                at,
            )

    def list_messages(self, conversation_id: UUID) -> list[StoredMessage]:
        return fetch_all(
            self._conn,
            StoredMessage,
            "select * from messages where conversation_id = %(id)s order by turn, created_at, id",
            {"id": conversation_id},
        )

    # -- traces and tool calls -------------------------------------------

    def record_trace(self, trace: TraceRecord, tool_calls: Sequence[ToolCallRecord]) -> None:
        with self._conn.transaction():
            conversation = self._lock_conversation(trace.conversation_id)
            if self._conn.execute("select 1 from traces where id = %(id)s", {"id": trace.id}).fetchone():
                return
            seq = conversation.last_seq + 1
            self._conn.execute(
                "update conversations set last_seq = %(seq)s where id = %(id)s",
                {"seq": seq, "id": trace.conversation_id},
            )
            insert_row(
                self._conn,
                "traces",
                trace.model_dump(mode="json") | {"seq": seq, "input": _redacted_input(trace.input)},
            )
            for position, call in enumerate(tool_calls):
                row = call.model_copy(
                    update={
                        "seq": position,
                        "trace_id": trace.id,
                        "conversation_id": trace.conversation_id,
                    }
                )
                insert_row(self._conn, "tool_calls", row.model_dump(mode="json"))

    def list_traces(self, conversation_id: UUID, turn: int | None = None) -> list[TraceRecord]:
        return fetch_all(
            self._conn,
            TraceRecord,
            "select * from traces where conversation_id = %(id)s and (%(turn)s::int is null or turn = %(turn)s)"
            " order by seq",
            {"id": conversation_id, "turn": turn},
        )

    def list_tool_calls(self, conversation_id: UUID, trace_id: UUID | None = None) -> list[ToolCallRecord]:
        return fetch_all(
            self._conn,
            ToolCallRecord,
            "select tc.* from tool_calls tc join traces t on t.id = tc.trace_id"
            " where tc.conversation_id = %(id)s and (%(trace_id)s::uuid is null or tc.trace_id = %(trace_id)s)"
            " order by t.seq, tc.seq",
            {"id": conversation_id, "trace_id": trace_id},
        )

    # -- approvals (SQL in approval_queries) -----------------------------

    def create_approval(
        self,
        conversation_id: UUID,
        message_id: UUID,
        action_type: ActionType,
        payload: dict[str, str],
        idempotency_key: str,
        at: datetime,
        approval_id: UUID | None = None,
    ) -> Approval:
        with self._conn.transaction():
            self._lock_conversation(conversation_id)
            return approval_queries.insert_approval(
                self._conn,
                conversation_id,
                message_id,
                action_type,
                payload,
                idempotency_key,
                at,
                approval_id,
            )

    def get_approval(self, approval_id: UUID) -> Approval | None:
        return approval_queries.get_approval(self._conn, approval_id)

    def list_approvals(self, conversation_id: UUID, pending_only: bool = False) -> list[Approval]:
        return approval_queries.list_approvals(self._conn, conversation_id, pending_only)

    def list_pending_approvals(self, conversation_id: UUID | None = None) -> list[Approval]:
        return approval_queries.list_pending_approvals(self._conn, conversation_id)

    def resolve_approval(self, approval_id: UUID, resolution: ApprovalResolution, at: datetime) -> Approval:
        return approval_queries.resolve_approval(self._conn, approval_id, resolution, at)

    # -- consistent reads ------------------------------------------------

    def rehydrate(self, conversation_id: UUID) -> ConversationSnapshot | None:
        with self._consistent_read():
            conversation = self.get_conversation(conversation_id)
            if conversation is None:
                return None
            messages = self.list_messages(conversation_id)
            open_turn = _open_turn(messages)
            return ConversationSnapshot(
                conversation=conversation,
                messages=tuple(messages),
                pending_approvals=tuple(self.list_approvals(conversation_id, pending_only=True)),
                open_turn_traces=tuple(self.list_traces(conversation_id, open_turn) if open_turn else ()),
            )

    def replay_trace(self, conversation_id: UUID) -> TraceReplay | None:
        with self._consistent_read():
            if self.get_conversation(conversation_id) is None:
                return None
            return TraceReplay.from_rows(
                conversation_id,
                self.list_messages(conversation_id),
                self.list_traces(conversation_id),
                self.list_tool_calls(conversation_id),
                self.list_approvals(conversation_id),
            )
