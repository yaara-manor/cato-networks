from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any, Self
from uuid import UUID, uuid4

from pydantic import AwareDatetime, BaseModel, ConfigDict, model_validator

from agents.models import AgentRole, AgentTrace, ToolCall, TraceStatus
from core.models import AccountTier
from guardrails.models import ActionType, SessionGuardHistory
from tools.models import TelemetryEvidence


class _StorageModel(BaseModel):
    model_config = ConfigDict(frozen=True)


class ConversationStage(StrEnum):
    INGESTION_GUARD = "INGESTION_GUARD"
    TRIAGE = "TRIAGE"
    SCOPE_CHECK = "SCOPE_CHECK"
    DIAGNOSTICS = "DIAGNOSTICS"
    KNOWLEDGE_RETRIEVAL = "KNOWLEDGE_RETRIEVAL"
    RESOLUTION = "RESOLUTION"
    ACTION_EVALUATION = "ACTION_EVALUATION"
    OUTPUT_GUARD = "OUTPUT_GUARD"
    IDLE = "IDLE"


class MessageSender(StrEnum):
    CUSTOMER = "CUSTOMER"
    AGENT = "AGENT"
    SYSTEM = "SYSTEM"


class ApprovalStatus(StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    EDITED = "EDITED"
    REJECTED = "REJECTED"


class ApprovalStateError(Exception):
    """Resolving an unknown or already-resolved approval."""


class StateSnapshot(_StorageModel):
    """Opaque versioned orchestrator carry-over; storage knows nothing of its content."""

    version: int = 1
    data: dict[str, Any] = {}


class Conversation(_StorageModel):
    id: UUID
    account_id: str | None
    contact_email: str | None
    customer_tier: AccountTier
    active_site_id: str | None
    stage: ConversationStage
    guard_history: SessionGuardHistory
    last_turn: int
    last_seq: int
    state: StateSnapshot
    created_at: AwareDatetime
    updated_at: AwareDatetime


class StoredMessage(_StorageModel):
    id: UUID
    conversation_id: UUID
    turn: int
    sender: MessageSender
    content: str
    citations: tuple[dict[str, str], ...]
    telemetry_evidence: tuple[TelemetryEvidence, ...]
    result: dict[str, Any] | None = None  # replies only: the TurnResult envelope, JSON
    created_at: AwareDatetime


class ToolCallRecord(_StorageModel):
    id: UUID
    trace_id: UUID
    conversation_id: UUID
    seq: int
    tool_name: str
    arguments: dict[str, Any]
    status: str
    result: dict[str, Any]
    latency_ms: int
    created_at: AwareDatetime

    @classmethod
    def from_tool_call(
        cls, trace_id: UUID, conversation_id: UUID, seq: int, call: ToolCall, at: datetime
    ) -> Self:
        return cls(
            id=uuid4(),
            trace_id=trace_id,
            conversation_id=conversation_id,
            seq=seq,
            created_at=at,
            **call.model_dump(),
        )


class TraceRecord(_StorageModel):
    id: UUID
    conversation_id: UUID
    message_id: UUID | None
    turn: int
    seq: int | None  # None until the store assigns it from conversations.last_seq
    agent_role: AgentRole
    parent_trace_id: UUID | None
    input: dict[str, Any]
    output: dict[str, Any] | None
    model_messages: list[dict[str, Any]] | None
    status: TraceStatus
    error: str | None
    latency_ms: int
    prompt_tokens: int
    completion_tokens: int
    cost_usd: Decimal | None
    started_at: AwareDatetime
    created_at: AwareDatetime

    @classmethod
    def from_agent_trace(
        cls,
        agent_trace: AgentTrace,
        conversation_id: UUID,
        turn: int,
        message_id: UUID | None,
        parent_trace_id: UUID | None,
        at: datetime,
        trace_id: UUID | None = None,
    ) -> Self:
        """Pass a stable `trace_id` on retry so the write stays idempotent."""
        return cls(
            id=trace_id or uuid4(),
            conversation_id=conversation_id,
            message_id=message_id,
            turn=turn,
            seq=None,
            agent_role=agent_trace.agent_role,
            parent_trace_id=parent_trace_id,
            input=agent_trace.input,
            output=agent_trace.output,
            model_messages=agent_trace.model_messages,
            status=agent_trace.status,
            error=agent_trace.error,
            latency_ms=agent_trace.latency_ms,
            prompt_tokens=agent_trace.prompt_tokens,
            completion_tokens=agent_trace.completion_tokens,
            cost_usd=agent_trace.cost_usd,
            started_at=at,
            created_at=at,
        )


class Approval(_StorageModel):
    id: UUID
    conversation_id: UUID
    message_id: UUID
    action_type: ActionType
    payload: dict[str, str]
    status: ApprovalStatus
    idempotency_key: str  # f"{message_id}:{action_index}"
    reviewer_notes: str | None
    edited_payload: dict[str, str] | None
    requested_at: AwareDatetime
    resolved_at: AwareDatetime | None


class SimulatedActionStatus(StrEnum):
    CLAIMED = "CLAIMED"
    DONE = "DONE"
    FAILED = "FAILED"
    INVALID = "INVALID"
    REFUSED = "REFUSED"


class SimulatedAction(_StorageModel):
    id: UUID
    conversation_id: UUID
    message_id: UUID | None  # None on the approval path
    idempotency_key: str
    kind: str
    approval_id: UUID | None
    payload: dict[str, Any]
    status: SimulatedActionStatus
    result: dict[str, Any] | None
    claimed_at: AwareDatetime
    completed_at: AwareDatetime | None


class ClaimedAction(_StorageModel):
    action: SimulatedAction
    is_new: bool


class ActionStateError(Exception):
    """Caller bug: finishing an action that is unknown or already finished."""


class ApprovalResolution(_StorageModel):
    status: ApprovalStatus
    reviewer_notes: str | None = None
    edited_payload: dict[str, str] | None = None

    @model_validator(mode="after")
    def _check_consistent(self) -> Self:
        if self.status is ApprovalStatus.PENDING:
            raise ValueError("a resolution cannot be PENDING")
        if (self.edited_payload is not None) != (self.status is ApprovalStatus.EDITED):
            raise ValueError("edited_payload is required if and only if status is EDITED")
        return self


class ConversationSnapshot(_StorageModel):
    """Open turn = highest turn with a CUSTOMER message and no AGENT/SYSTEM message.

    Resume rule: reuse `output` of OK traces per role, redo roles lacking an OK trace.
    """

    conversation: Conversation
    messages: tuple[StoredMessage, ...]
    pending_approvals: tuple[Approval, ...]
    open_turn_traces: tuple[TraceRecord, ...]
