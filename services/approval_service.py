import logging
from uuid import UUID, uuid5

from actions import ActionDispatcher, ActionStatus, DispatchContext
from agents.models import AgentRole, AgentTrace, TraceStatus
from core.clock import SimulationClock
from guardrails import (
    ApprovalStatus,
    GateOutcome,
    ProposedAction,
    check_action,
    check_outgoing_message,
)
from services.approval_models import DecisionResult, ReviewerDecision, SettleOutcome
from services.approval_notice import ApprovalNotice
from services.customer_service import CustomerService
from services.models import CallerIdentity
from services.ticket_service import TicketService
from storage import (
    Approval,
    ApprovalStateError,
    Conversation,
    StateStore,
    TraceRecord,
    TurnLockTimeout,
)

logger = logging.getLogger(__name__)
_EXECUTES = {ApprovalStatus.APPROVED, ApprovalStatus.EDITED}


class ApprovalService:
    """Reviewer decisions: durable resolve, then idempotent settle (execute, clear ticket, notify).

    Sync, one connection per concurrent caller. No SQL here; policy stays in `check_action`.
    """

    def __init__(
        self,
        store: StateStore,
        dispatcher: ActionDispatcher,
        tickets: TicketService,
        customers: CustomerService,
        clock: SimulationClock,
    ) -> None:
        self._store = store
        self._dispatcher = dispatcher
        self._tickets = tickets
        self._customers = customers
        self._clock = clock

    def list_pending(self, conversation_id: UUID | None = None) -> list[Approval]:
        return self._store.list_pending_approvals(conversation_id)

    def get_approval(self, approval_id: UUID) -> Approval | None:
        return self._store.get_approval(approval_id)

    def decide(self, decision: ReviewerDecision) -> DecisionResult:
        approval = self.resolve(decision)
        return DecisionResult(approval=approval, settle=self.settle(approval.id))

    def resolve(self, decision: ReviewerDecision) -> Approval:
        """Fail-fast checks, then the CAS; does not settle."""
        approval = self._require(decision.approval_id)
        conversation = self._conversation(approval)
        identity = self._identity(conversation)
        resolution = decision.resolution
        if resolution.status is ApprovalStatus.EDITED:
            self._check_edit(approval, identity, resolution.edited_payload or {})
        if decision.customer_reason is not None:
            violations = check_outgoing_message(decision.customer_reason, conversation.guard_history, ())
            if violations:
                raise ApprovalStateError("customer_reason fails the outgoing guards")
        return self._store.resolve_approval(
            approval.id, resolution, self._clock.now(), customer_reason=decision.customer_reason
        )

    def settle(self, approval_id: UUID) -> SettleOutcome:
        approval = self._require(approval_id)
        if approval.status is ApprovalStatus.PENDING:
            raise ApprovalStateError(f"approval {approval_id} is still pending")
        if approval.settled_at is not None:
            return SettleOutcome.ALREADY_SETTLED
        if approval.status in _EXECUTES and not self._dispatch(approval):
            return SettleOutcome.EXECUTION_FAILED
        self._clear_ticket(approval)
        notice = ApprovalNotice.from_approval(approval)
        try:
            with self._store.turn_lock(approval.conversation_id):
                self._store.settle_approval(approval.id, notice.text, self._clock.now())
        except TurnLockTimeout:
            return SettleOutcome.BUSY
        return SettleOutcome.SETTLED

    def settle_unsettled(self, limit: int = 50) -> tuple[SettleOutcome, ...]:
        outcomes: list[SettleOutcome] = []
        for approval in self._store.list_unsettled_approvals(limit):
            try:
                outcomes.append(self.settle(approval.id))
            except Exception as error:  # noqa: BLE001  one bad row must not stop the sweep
                logger.error("settle failed: %s", type(error).__name__)
        return tuple(outcomes)

    def _require(self, approval_id: UUID) -> Approval:
        approval = self._store.get_approval(approval_id)
        if approval is None:
            raise ApprovalStateError(f"approval {approval_id} is unknown")
        return approval

    def _conversation(self, approval: Approval) -> Conversation:
        conversation = self._store.get_conversation(approval.conversation_id)
        assert conversation is not None  # FK guarantees it
        return conversation

    def _identity(self, conversation: Conversation) -> CallerIdentity:
        return self._customers.authenticate_caller(conversation.contact_email, conversation.account_id)

    @staticmethod
    def _check_edit(approval: Approval, identity: CallerIdentity, edited: dict[str, str]) -> None:
        if edited.keys() != approval.payload.keys():
            raise ApprovalStateError("an edit must keep the original payload keys, ticket_id included")
        account_id = identity.account.account_id if identity.account else ""
        proposed = ProposedAction(action_type=approval.action_type, target_account_id=account_id, payload=edited)
        if check_action(proposed, identity).outcome is not GateOutcome.REQUIRE_APPROVAL:
            raise ApprovalStateError("the edited action no longer requires approval; the gate would not allow it")

    def _dispatch(self, approval: Approval) -> bool:
        conversation = self._conversation(approval)
        context = DispatchContext(
            identity=self._identity(conversation),
            priority="P4",  # neutral: CREDIT / MFA_RESET are not priority-gated
            sev1_corroborated=False,
            already_paged=False,
            conversation_id=approval.conversation_id,
            message_id=approval.message_id,
        )
        result = self._dispatcher.dispatch_approved(approval, context)
        if result.status is not ActionStatus.DONE:
            logger.warning("approval dispatch not done: %s", result.status)
        return result.status is ActionStatus.DONE

    def _clear_ticket(self, approval: Approval) -> None:
        """pending_approval -> open for every outcome; a failure is traced, never blocks the notice."""
        ticket_id = approval.effective_payload.get("ticket_id")
        try:
            ticket = self._tickets.get_ticket(ticket_id) if ticket_id else None
            if ticket is not None and ticket.status == "pending_approval":
                self._tickets.update_ticket(ticket.ticket_id, status="open")
        except Exception as error:  # noqa: BLE001  the notice still goes out
            logger.error("ticket clear failed: %s", type(error).__name__)
            self._trace_ticket_failure(approval, type(error).__name__)

    def _trace_ticket_failure(self, approval: Approval, error_class: str) -> None:
        turn = next(m.turn for m in self._store.list_messages(approval.conversation_id) if m.id == approval.message_id)
        trace = AgentTrace(
            agent_role=AgentRole.ORCHESTRATOR,
            tool_calls=[],
            latency_ms=0,
            prompt_tokens=0,
            completion_tokens=0,
            status=TraceStatus.ERROR,
            error=error_class,
        )
        record = TraceRecord.from_agent_trace(
            trace,
            approval.conversation_id,
            turn,
            approval.message_id,
            None,
            self._clock.now(),
            uuid5(approval.id, "ticket-clear"),
        )
        self._store.record_trace(record, [])
