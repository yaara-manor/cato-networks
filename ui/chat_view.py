from collections.abc import Sequence
from datetime import datetime
from enum import StrEnum
from typing import Self, assert_never

from pydantic import BaseModel, ConfigDict

from guardrails import ActionType, ApprovalStatus, MarkerKind, strip_markers
from orchestration import Citation, TurnResult
from storage import Approval, ConversationSnapshot, MessageSender, StoredMessage
from tools.models import TelemetryEvidence


class _View(BaseModel):
    model_config = ConfigDict(frozen=True)


class MessageRole(StrEnum):
    CUSTOMER = "customer"
    SUPPORT = "support"


class CitationBadge(_View):
    kind: MarkerKind  # KB or POLICY
    label: str
    url: str | None  # KB only
    ref: str  # slug#anchor or policy id

    @classmethod
    def from_row(cls, row: dict[str, str]) -> Self:
        citation = Citation.model_validate(row)
        return cls(kind=citation.kind, label=citation.title, url=citation.url or None, ref=citation.ref)


class EvidenceChip(_View):
    tool_name: str
    text: str
    timestamp: datetime
    is_anomaly: bool

    @classmethod
    def from_evidence(cls, evidence: TelemetryEvidence) -> Self:
        return cls(
            tool_name=evidence.tool_name,
            text=f"{evidence.metric_key} {evidence.raw_value}",
            timestamp=evidence.timestamp,
            is_anomaly=evidence.is_anomaly,
        )


class MessageView(_View):
    role: MessageRole
    text: str
    citations: tuple[CitationBadge, ...]
    evidence: tuple[EvidenceChip, ...]
    created_at: datetime

    @classmethod
    def from_message(cls, message: StoredMessage) -> Self:
        if message.sender is MessageSender.CUSTOMER:
            return cls(
                role=MessageRole.CUSTOMER,
                text=message.content,
                citations=(),
                evidence=(),
                created_at=message.created_at,
            )
        first: dict[tuple[str, str, str], TelemetryEvidence] = {}
        for e in message.telemetry_evidence:
            first.setdefault((e.tool_name, e.metric_key, e.raw_value), e)
        return cls(
            role=MessageRole.SUPPORT,
            text=strip_markers(message.content),
            citations=tuple(CitationBadge.from_row(row) for row in message.citations),
            evidence=tuple(EvidenceChip.from_evidence(e) for e in first.values()),
            created_at=message.created_at,
        )


class ApprovalBannerState(StrEnum):
    PENDING = "pending"
    FINALIZING = "finalizing"
    APPROVED = "approved"
    REJECTED = "rejected"


def _action_title(action_type: ActionType) -> str:
    match action_type:
        case ActionType.CREDIT:
            return "Service credit"
        case ActionType.MFA_RESET:
            return "MFA reset"
        case ActionType.VERDICT_OVERRIDE:
            return "Policy exception"
        case ActionType.CLOSE_TICKET:
            return "Close ticket"
        case ActionType.PAGE_ON_CALL:
            return "Page on-call engineer"
        case _:
            assert_never(action_type)


def _banner_state(approval: Approval) -> ApprovalBannerState:
    match approval.status:
        case ApprovalStatus.PENDING:
            return ApprovalBannerState.PENDING
        case ApprovalStatus.APPROVED | ApprovalStatus.EDITED:
            return ApprovalBannerState.APPROVED if approval.settled_at else ApprovalBannerState.FINALIZING
        case ApprovalStatus.REJECTED:
            return ApprovalBannerState.REJECTED
        case _:
            assert_never(approval.status)


class ApprovalBanner(_View):
    """Status and action title only: payload, notes and reasons are never read."""

    state: ApprovalBannerState
    title: str

    @classmethod
    def from_approval(cls, approval: Approval) -> Self:
        return cls(state=_banner_state(approval), title=_action_title(approval.action_type))


def _escalation_offered(messages: Sequence[StoredMessage]) -> bool:
    latest = next((m for m in reversed(messages) if m.sender is not MessageSender.CUSTOMER), None)
    return bool(latest and latest.result and TurnResult.model_validate(latest.result).escalation_offered)


class ChatView(_View):
    messages: tuple[MessageView, ...]
    banners: tuple[ApprovalBanner, ...]
    escalation_offered: bool

    @classmethod
    def from_snapshot(cls, snapshot: ConversationSnapshot, approvals: Sequence[Approval]) -> Self:
        return cls(
            messages=tuple(MessageView.from_message(m) for m in snapshot.messages),
            banners=tuple(ApprovalBanner.from_approval(a) for a in approvals),
            escalation_offered=_escalation_offered(snapshot.messages),
        )
