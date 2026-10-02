from collections.abc import Sequence
from enum import StrEnum
from typing import Self
from uuid import UUID

from pydantic import AwareDatetime

from agents.models import AgentRole, DiagnosticEvidence
from core.models import CustomerAccount, Ticket
from services.approval_models import ReviewerDecision
from storage import Approval, ApprovalResolution, ApprovalStatus, ConversationSnapshot, SimulatedAction, TraceReplay
from tools.models import TelemetryEvidence
from ui.reviewer_panels import ContextPanel, EvidencePanel, View, latest_ok_output


class ApprovalCard(View):
    approval: Approval
    action_label: str
    proposing_turn: int | None
    evidence_refs: tuple[TelemetryEvidence, ...]  # evidence gathered in the proposing turn
    can_resolve: bool
    dispatch: SimulatedAction | None  # the executed (or failed) simulated action, once approved

    @classmethod
    def from_approval(
        cls, approval: Approval, replay: TraceReplay, actions: Sequence[SimulatedAction]
    ) -> Self:
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
            # the dispatcher's key for the approved action; `:pending` marks the ticket and is not the outcome
            dispatch=next((a for a in actions if a.idempotency_key == f"approval:{approval.id}"), None),
        )


class DecisionKind(StrEnum):
    APPROVE = "APPROVE"
    EDIT = "EDIT"
    REJECT = "REJECT"


class DecisionFormError(ValueError):
    """The reviewer's input cannot become a decision; the message is shown verbatim."""


_STATUS = {
    DecisionKind.APPROVE: ApprovalStatus.APPROVED,
    DecisionKind.EDIT: ApprovalStatus.EDITED,
    DecisionKind.REJECT: ApprovalStatus.REJECTED,
}


class DecisionForm(View):
    approval_id: UUID
    kind: DecisionKind
    note: str
    customer_reason: str
    original_payload: dict[str, str]
    edited_payload: dict[str, str] | None = None

    def to_decision(self) -> ReviewerDecision:
        """Checks only what the UI can know; the service re-checks the gate rules at resolve time."""
        note = self.note.strip()
        if self.kind is DecisionKind.REJECT and not note:
            raise DecisionFormError("a rejection needs an internal note")
        edited = self.edited_payload if self.kind is DecisionKind.EDIT else None
        if self.kind is DecisionKind.EDIT and (edited is None or edited.keys() != self.original_payload.keys()):
            raise DecisionFormError("an edit must keep the original payload keys")
        return ReviewerDecision(
            approval_id=self.approval_id,
            resolution=ApprovalResolution(
                status=_STATUS[self.kind], reviewer_notes=note or None, edited_payload=edited
            ),
            customer_reason=self.customer_reason.strip() or None,
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
        actions: Sequence[SimulatedAction],
        now: AwareDatetime,
    ) -> Self:
        return cls(
            conversation_id=snapshot.conversation.id,
            context=ContextPanel.from_rows(snapshot, replay, account, tickets, now),
            evidence=EvidencePanel.from_rows(replay),
            approvals=tuple(ApprovalCard.from_approval(a, replay, actions) for a in replay.approvals),
        )
