from dataclasses import dataclass, replace
from uuid import UUID

from agents import (
    ConversationTurn,
    DiagnosticEvidence,
    DiagnosticsInput,
    KnowledgeBundle,
    KnowledgeInput,
    ResolutionInput,
    ResolutionPlan,
    SupportAction,
    SupportDeps,
    TriageInput,
    TriageResult,
    TurnSender,
)
from core.clock import SimulationClock
from guardrails import ProposedAction, check_claims, detect, redact
from orchestration.canned import CLARIFICATION_ESCALATION, INJECTION_REFUSAL
from orchestration.gate import gate_actions
from orchestration.models import AgentPorts, TurnResult
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

MAX_DIAG_KB_ROUNDS = 2
_TURN_SENDERS = {MessageSender.CUSTOMER: TurnSender.CUSTOMER, MessageSender.AGENT: TurnSender.AGENT}


@dataclass(frozen=True)
class _Turn:
    recorder: TurnRecorder
    message: str  # redacted
    history: tuple[ConversationTurn, ...]
    deps: SupportDeps


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

    def run_turn(self, conversation_id: UUID, message: str, message_id: UUID) -> TurnResult:
        """`message_id` is the idempotency key: an answered id returns the stored reply."""
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
            recorder.complete_turn(INJECTION_REFUSAL)
            return TurnResult(reply=INJECTION_REFUSAL, path=recorder.path)
        turn = _Turn(
            recorder,
            redacted.text,
            _history(snapshot, stored.turn),
            replace(self.base_deps, guard_history=history),
        )
        return self._answer(turn, snapshot, OrchestratorState.from_snapshot(snapshot.conversation.state))

    def _replay(self, snapshot: ConversationSnapshot, reply: StoredMessage, message_id: UUID) -> TurnResult:
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
        plan = self._resolve(turn, triage, diagnostics, knowledge)
        turn.recorder.enter(ConversationStage.ACTION_EVALUATION)
        gated = gate_actions(
            plan.actions,
            triage.identity,
            triage.decision.priority,
            diagnostics.sev1_corroborated if diagnostics else False,
            state.oncall_paged,
        )
        for index, action in gated.pending:
            turn.recorder.create_approval(index, action)
        if gated.oncall_paged:
            state = state.with_oncall_paged()
        reply = compose_reply((), plan.customer_message, gated.denial_reasons)
        return self._finish(
            turn,
            state,
            reply,
            evidence=diagnostics.evidence_items if diagnostics else (),
            pending=tuple(action for _, action in gated.pending),
            executable=gated.executable,
            escalation_offered=plan.escalate_to_human,
        )

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
    ) -> ResolutionPlan:
        turn.recorder.enter(ConversationStage.RESOLUTION)
        data = ResolutionInput(
            triage=triage,
            diagnostics=diagnostics,
            knowledge=knowledge,
            history=turn.history,
            message=turn.message,
        )
        run = self.ports.resolution(data, turn.deps)
        turn.recorder.record_run(AgentRole.RESOLUTION, data, run)
        return run.output

    def _finish(
        self,
        turn: _Turn,
        state: OrchestratorState,
        reply: str,
        evidence: tuple[TelemetryEvidence, ...] = (),
        pending: tuple[ProposedAction, ...] = (),
        executable: tuple[SupportAction, ...] = (),
        escalation_offered: bool = False,
    ) -> TurnResult:
        """State is saved before the reply: a crash in between never loses an on-call page."""
        turn.recorder.save_state(state.to_snapshot())
        turn.recorder.complete_turn(reply, evidence)
        return TurnResult(
            reply=reply,
            path=turn.recorder.path,
            pending_actions=pending,
            executable_actions=executable,
            escalation_offered=escalation_offered,
        )
