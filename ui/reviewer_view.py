from collections.abc import Sequence
from typing import Self
from uuid import UUID

from pydantic import AwareDatetime

from agents.models import AgentRole, DiagnosticEvidence
from core.models import CustomerAccount, Ticket
from storage import Approval, ApprovalStatus, ConversationSnapshot, TraceReplay
from tools.models import TelemetryEvidence
from ui.reviewer_panels import ContextPanel, EvidencePanel, View, latest_ok_output


class ApprovalCard(View):
    approval: Approval
    action_label: str
    proposing_turn: int | None
    evidence_refs: tuple[TelemetryEvidence, ...]  # evidence gathered in the proposing turn
    can_resolve: bool

    @classmethod
    def from_approval(cls, approval: Approval, replay: TraceReplay) -> Self:
        turn = next(
            (
                t.turn
                for t in replay.turns
                if t.customer_message and t.customer_message.id == approval.message_id
            ),
            None,
        )
        diagnostics = (
            latest_ok_output(replay, AgentRole.DIAGNOSTICS, DiagnosticEvidence, turn)
            if turn is not None
            else None
        )
        return cls(
            approval=approval,
            action_label=approval.action_type.value.replace("_", " ").title(),
            proposing_turn=turn,
            evidence_refs=diagnostics.evidence_items if diagnostics else (),
            can_resolve=approval.status is ApprovalStatus.PENDING,
        )


class CaseView(View):
    conversation_id: UUID
    context: ContextPanel
    evidence: EvidencePanel
    approvals: tuple[ApprovalCard, ...]

    @classmethod
    def from_rows(
        cls,
        snapshot: ConversationSnapshot,
        replay: TraceReplay,
        account: CustomerAccount | None,
        tickets: Sequence[Ticket],
        now: AwareDatetime,
    ) -> Self:
        return cls(
            conversation_id=snapshot.conversation.id,
            context=ContextPanel.from_rows(snapshot, replay, account, tickets, now),
            evidence=EvidencePanel.from_rows(replay),
            approvals=tuple(ApprovalCard.from_approval(a, replay) for a in replay.approvals),
        )
