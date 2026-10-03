import logging
from dataclasses import dataclass, replace
from uuid import UUID

from actions import ActionDispatcher, ActionResult, DispatchContext
from agents import (
    ConversationTurn,
    DiagnosticEvidence,
    DiagnosticsInput,
    KnowledgeBundle,
    KnowledgeInput,
    ResolutionInput,
    ResolutionPlan,
    SupportDeps,
    TriageInput,
    TriageResult,
    TurnSender,
    UnsettledApprovalView,
)
from core.clock import SimulationClock
from guardrails import (
    ProposedAction,
    check_citations,
    check_claims,
    check_outgoing_message,
    detect,
    redact,
)
from orchestration.actions_step import (
    confirmations,
    has_failure,
    next_active_ticket,
    stamp_ticket_id,
    was_paged,
)
from orchestration.approvals import ApprovalContext
from orchestration.canned import (
    AGENT_FAILURE_PAUSE,
    CLARIFICATION_ESCALATION,
    INJECTION_REFUSAL,
    NEEDS_TICKET_FIRST,
)
from orchestration.degradation import (
    DegradationNotice,
    DegradedSource,
    derive_degradations,
)
from orchestration.gate import GatedActions, gate_actions
from orchestration.models import AgentPorts, Citation, TurnResult
from orchestration.recorder import TurnRecorder
from orchestration.routing import compose_reply, next_stage_after_triage
from orchestration.state import OrchestratorState
from storage import (
    AgentRole,
    ConversationSnapshot,
    ConversationStage,
    MessageSender,
    StateStore,
    StoredMessage,
)
from tools.models import TelemetryEvidence

logger = logging.getLogger(__name__)
MAX_DIAG_KB_ROUNDS = 2
_TURN_SENDERS = {MessageSender.CUSTOMER: TurnSender.CUSTOMER, MessageSender.AGENT: TurnSender.AGENT}


class OutgoingMessageRejected(Exception):
    """A resolution port returned a customer message that fails the outgoing guards."""


def _require_clean_message(message: str, data: ResolutionInput, deps: SupportDeps) -> None:
    """Workflow-boundary check, so no injected port can bypass the agent's own validators."""
    kinds = {v.kind for v in check_outgoing_message(message, deps.guard_history, deps.approved_grants)}
    kinds |= {v.kind for v in check_citations(message, data.grounding_context()).violations}
    if kinds:
        raise OutgoingMessageRejected(", ".join(sorted(kinds)))


@dataclass(frozen=True)
class _Turn:
    recorder: TurnRecorder
    conversation_id: UUID
    message_id: UUID
    message: str  # redacted
    history: tuple[ConversationTurn, ...]
    deps: SupportDeps
    unsettled: tuple[UnsettledApprovalView, ...]


def _history(snapshot: ConversationSnapshot, turn: int) -> tuple[ConversationTurn, ...]:
    """Earlier turns only; SYSTEM rows (pause notices) are not conversation."""
    return tuple(
        ConversationTurn(sender=_TURN_SENDERS[m.sender], content=m.content)
        for m in snapshot.messages
        if m.turn < turn and m.sender in _TURN_SENDERS
    )


def _stored_reply(snapshot: ConversationSnapshot, turn: int) -> StoredMessage | None:
    return next(
        (m for m in snapshot.messages if m.turn == turn and m.sender is not MessageSender.CUSTOMER), None
    )


@dataclass(frozen=True)
class Workflow:
    """One customer turn through guards, agents and the action gate. Holds no state between turns."""

    ports: AgentPorts
    store: StateStore
    clock: SimulationClock
    base_deps: SupportDeps
    dispatcher: ActionDispatcher

    def run_turn(self, conversation_id: UUID, message: str, message_id: UUID) -> TurnResult:
        """`message_id` is the idempotency key: an answered id returns the stored reply.

        Turns of one conversation serialize across workers; may raise TurnLockTimeout.
        """
        with self.store.turn_lock(conversation_id):
            return self._run_locked(conversation_id, message, message_id)

    def _run_locked(self, conversation_id: UUID, message: str, message_id: UUID) -> TurnResult:
        redacted = redact(message)
        stored = self.store.append_customer_message(
            conversation_id, message_id, redacted.text, self.clock.now()
        )
        snapshot = self.store.rehydrate(conversation_id)
        assert snapshot is not None
        if (reply := _stored_reply(snapshot, stored.turn)) is not None:
            return self._replay(snapshot, reply, message_id)
        recorder = TurnRecorder(self.store, self.clock, conversation_id, stored.turn, message_id)
        verdict = detect(redacted.text)
        history = snapshot.conversation.guard_history.with_redaction(redacted).with_injection(verdict)
        recorder.save_guard_history(history)
        if verdict.blocked:
            refusal = TurnResult(reply=INJECTION_REFUSAL, path=recorder.completed_path)
            recorder.complete_turn(refusal)
            return refusal
        approvals = ApprovalContext.from_approvals(self.store.list_approvals(conversation_id))
        turn = _Turn(
            recorder,
            conversation_id,
            message_id,
            redacted.text,
            _history(snapshot, stored.turn),
            replace(self.base_deps, guard_history=history, approved_grants=approvals.grants),
            approvals.unsettled,
        )
        state = OrchestratorState.from_snapshot(snapshot.conversation.state)  # StateVersionError propagates
        try:
            return self._answer(turn, snapshot, state)
        except Exception as error:  # noqa: BLE001  the one agent-failure boundary; the message is already saved
            return self._pause(recorder, error)

    def _pause(self, recorder: TurnRecorder, error: Exception) -> TurnResult:
        """State is not saved: carry-over flags stay as the last good turn left them."""
        logger.error("agent failure: %s", type(error).__name__, exc_info=error)
        recorder.record_failure(error)
        pause = TurnResult(reply=AGENT_FAILURE_PAUSE, path=recorder.completed_path)
        recorder.complete_turn(pause, sender=MessageSender.SYSTEM)
        return pause

    def _replay(self, snapshot: ConversationSnapshot, reply: StoredMessage, message_id: UUID) -> TurnResult:
        if reply.result is not None:
            return TurnResult.model_validate(reply.result)
        pending = tuple(
            ProposedAction(
                action_type=a.action_type,
                target_account_id=snapshot.conversation.account_id or "",
                payload=a.payload,
            )
            for a in snapshot.pending_approvals
            if a.message_id == message_id
        )
        return TurnResult(reply=reply.content, path=(), pending_actions=pending)

    def _answer(self, turn: _Turn, snapshot: ConversationSnapshot, state: OrchestratorState) -> TurnResult:
        triage, turn = self._triage(turn, snapshot)
        if triage.scoping_question and state.clarification_exhausted():
            return self._finish(turn, state, CLARIFICATION_ESCALATION, escalation_offered=True)
        state = state.after_scoping_question() if triage.scoping_question else state.after_scoping_resolved()
        stage = next_stage_after_triage(triage)
        diagnostics, knowledge = self._evidence(turn, triage, stage)
        plan = self._resolve(turn, triage, diagnostics, knowledge, state)
        turn.recorder.enter(ConversationStage.ACTION_EVALUATION)
        gated = gate_actions(
            plan.actions,
            triage.identity,
            triage.decision.priority,
            diagnostics.sev1_corroborated if diagnostics else False,
            state.oncall_paged,
        )
        results, pending, state = self._execute(turn, triage, diagnostics, gated, state)
        degradations = derive_degradations(diagnostics, knowledge)
        notices = tuple(n.customer_text for n in state.unseen(degradations))
        lines = (*confirmations(results), *((NEEDS_TICKET_FIRST,) if gated.pending and not pending else ()))
        reply = compose_reply(notices, plan.customer_message, lines, gated.denial_reasons)
        retrieval_down = any(n.source is DegradedSource.RETRIEVAL for n in degradations)
        return self._finish(
            turn,
            state.with_degraded(degradations),
            reply,
            evidence=diagnostics.evidence_items if diagnostics else (),
            pending=tuple(action for _, action in pending),
            results=results,
            escalation_offered=plan.escalate_to_human or retrieval_down,
            degradations=degradations,
            knowledge=knowledge,
        )

    def _execute(
        self,
        turn: _Turn,
        triage: TriageResult,
        diagnostics: DiagnosticEvidence | None,
        gated: GatedActions,
        state: OrchestratorState,
    ) -> tuple[tuple[ActionResult, ...], tuple[tuple[int, ProposedAction], ...], OrchestratorState]:
        """Dispatch cleared actions, then bind, record and mark approvals against the (possibly new) ticket."""
        context = DispatchContext(
            identity=triage.identity,
            priority=triage.decision.priority,
            sev1_corroborated=diagnostics.sev1_corroborated if diagnostics else False,
            already_paged=state.oncall_paged,
            conversation_id=turn.conversation_id,
            message_id=turn.message_id,
        )
        results = self.dispatcher.dispatch_turn(gated.executable, context)
        state = state.with_active_ticket(next_active_ticket(results, state.active_ticket_id))
        if was_paged(results):
            state = state.with_oncall_paged()
        pending = stamp_ticket_id(gated.pending, state.active_ticket_id)
        for index, action in pending:
            self.dispatcher.mark_pending(turn.recorder.create_approval(index, action), context)
        return results, pending, state

    def _triage(self, turn: _Turn, snapshot: ConversationSnapshot) -> tuple[TriageResult, _Turn]:
        turn.recorder.enter(ConversationStage.TRIAGE)
        conversation = snapshot.conversation
        identity = self.base_deps.customers.authenticate_caller(
            conversation.contact_email, conversation.account_id
        )
        data = TriageInput(message=turn.message, identity=identity, history=turn.history)
        run = self.ports.triage(data, replace(turn.deps, identity=identity))
        turn.recorder.record_run(AgentRole.TRIAGE, data, run)
        result = run.output
        turn.recorder.save_identity(result.identity, result.decision.site_id)
        history = turn.deps.guard_history.with_entitlement(check_claims(turn.message, result.identity))
        turn.recorder.save_guard_history(history)
        return result, replace(turn, deps=replace(turn.deps, identity=result.identity, guard_history=history))

    def _evidence(
        self, turn: _Turn, triage: TriageResult, stage: ConversationStage
    ) -> tuple[DiagnosticEvidence | None, KnowledgeBundle | None]:
        match stage:
            case ConversationStage.KNOWLEDGE_RETRIEVAL:
                return None, self._retrieve(turn, triage, None)
            case ConversationStage.DIAGNOSTICS:
                diagnostics, knowledge = self._diagnose_then_retrieve(turn, triage)
                for _ in range(MAX_DIAG_KB_ROUNDS - 1):
                    if not knowledge.needs_more_telemetry:
                        break
                    diagnostics, knowledge = self._diagnose_then_retrieve(turn, triage)
                return diagnostics, knowledge
            case _:
                return None, None

    def _diagnose_then_retrieve(
        self, turn: _Turn, triage: TriageResult
    ) -> tuple[DiagnosticEvidence, KnowledgeBundle]:
        diagnostics = self._diagnose(turn, triage)
        return diagnostics, self._retrieve(turn, triage, diagnostics)

    def _diagnose(self, turn: _Turn, triage: TriageResult) -> DiagnosticEvidence:
        turn.recorder.enter(ConversationStage.DIAGNOSTICS)
        data = DiagnosticsInput(triage=triage, message=turn.message, history=turn.history)
        run = self.ports.diagnostics(data, turn.deps)
        turn.recorder.record_run(AgentRole.DIAGNOSTICS, data, run)
        return run.output

    def _retrieve(
        self, turn: _Turn, triage: TriageResult, diagnostics: DiagnosticEvidence | None
    ) -> KnowledgeBundle:
        turn.recorder.enter(ConversationStage.KNOWLEDGE_RETRIEVAL)
        data = KnowledgeInput(triage=triage, diagnostics=diagnostics, message=turn.message)
        run = self.ports.knowledge(data, turn.deps)
        turn.recorder.record_run(AgentRole.KNOWLEDGE, data, run)
        return run.output

    def _resolve(
        self,
        turn: _Turn,
        triage: TriageResult,
        diagnostics: DiagnosticEvidence | None,
        knowledge: KnowledgeBundle | None,
        state: OrchestratorState,
    ) -> ResolutionPlan:
        turn.recorder.enter(ConversationStage.RESOLUTION)
        data = ResolutionInput(
            triage=triage,
            diagnostics=diagnostics,
            knowledge=knowledge,
            history=turn.history,
            message=turn.message,
            known_ticket_id=state.active_ticket_id,
            unsettled_approvals=turn.unsettled,
        )
        run = self.ports.resolution(data, turn.deps)
        turn.recorder.record_run(AgentRole.RESOLUTION, data, run)
        _require_clean_message(run.output.customer_message, data, turn.deps)
        return run.output

    def _finish(
        self,
        turn: _Turn,
        state: OrchestratorState,
        reply: str,
        evidence: tuple[TelemetryEvidence, ...] = (),
        pending: tuple[ProposedAction, ...] = (),
        results: tuple[ActionResult, ...] = (),
        escalation_offered: bool = False,
        degradations: tuple[DegradationNotice, ...] = (),
        knowledge: KnowledgeBundle | None = None,
    ) -> TurnResult:
        """State and reply are one transaction: a retry never reapplies a transition."""
        result = TurnResult(
            reply=reply,
            path=turn.recorder.completed_path,
            pending_actions=pending,
            action_results=results,
            escalation_offered=escalation_offered or has_failure(results),
            degradations=degradations,
            citations=Citation.for_reply(reply, knowledge),
        )
        turn.recorder.complete_turn(result, evidence, state=state.to_snapshot())
        return result
