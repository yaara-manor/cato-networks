from uuid import UUID, uuid5

from pydantic import BaseModel

from agents import AgentRun, AgentTrace, TraceStatus
from core.clock import SimulationClock
from guardrails import ProposedAction, SessionGuardHistory
from orchestration.models import TurnResult
from services.models import CallerIdentity
from storage import (
    AgentRole,
    Approval,
    ConversationStage,
    MessageSender,
    StateSnapshot,
    StateStore,
    ToolCallRecord,
    TraceRecord,
)
from tools.models import TelemetryEvidence


class TurnRecorder:
    """Writes one turn through `StateStore` and remembers the stages it entered."""

    def __init__(
        self, store: StateStore, clock: SimulationClock, conversation_id: UUID, turn: int, message_id: UUID
    ) -> None:
        self._store = store
        self._clock = clock
        self._conversation_id = conversation_id
        self._turn = turn
        self._message_id = message_id
        self._path = [ConversationStage.INGESTION_GUARD]  # set by append_customer_message
        self._traces = 0
        self._last_trace_id: UUID | None = None

    @property
    def path(self) -> tuple[ConversationStage, ...]:
        return tuple(self._path)

    def enter(self, stage: ConversationStage) -> None:
        self._store.set_stage(self._conversation_id, stage, self._clock.now())
        self._path.append(stage)

    def save_guard_history(self, history: SessionGuardHistory) -> None:
        self._store.save_guard_history(self._conversation_id, history, self._clock.now())

    def save_identity(self, identity: CallerIdentity, active_site_id: str | None) -> None:
        account_id = identity.account.account_id if identity.account else None
        self._store.update_identity(
            self._conversation_id,
            account_id,
            identity.caller_email,
            identity.effective_tier,
            active_site_id,
            self._clock.now(),
        )

    def record_run[T: BaseModel](self, role: AgentRole, data: BaseModel, run: AgentRun[T]) -> None:
        """Trace ids derive from the message id, so a resumed turn does not duplicate traces."""
        self._write_trace(
            run.trace.model_copy(
                update={
                    "agent_role": role,
                    "input": data.model_dump(mode="json"),
                    "output": run.output.model_dump(mode="json"),
                }
            )
        )

    def record_failure(self, error: Exception) -> None:
        """Class name only: the message may carry customer data."""
        self._write_trace(
            AgentTrace(
                agent_role=AgentRole.ORCHESTRATOR,
                tool_calls=[],
                latency_ms=0,
                prompt_tokens=0,
                completion_tokens=0,
                status=TraceStatus.ERROR,
                error=type(error).__name__,
            )
        )

    def _write_trace(self, agent_trace: AgentTrace) -> None:
        now = self._clock.now()
        trace_id = uuid5(self._message_id, f"trace:{self._traces}")
        trace = TraceRecord.from_agent_trace(
            agent_trace,
            self._conversation_id,
            self._turn,
            self._message_id,
            self._last_trace_id,
            now,
            trace_id,
        )
        calls = [
            ToolCallRecord.from_tool_call(trace_id, self._conversation_id, seq, call, now)
            for seq, call in enumerate(agent_trace.tool_calls)
        ]
        self._store.record_trace(trace, calls)
        self._traces += 1
        self._last_trace_id = trace_id

    def create_approval(self, action_index: int, action: ProposedAction) -> Approval:
        return self._store.create_approval(
            self._conversation_id,
            self._message_id,
            action.action_type,
            action.payload,
            f"{self._message_id}:{action_index}",
            self._clock.now(),
        )

    @property
    def completed_path(self) -> tuple[ConversationStage, ...]:
        """The path the turn will have once `complete_turn` lands it in IDLE."""
        return (*self._path, ConversationStage.IDLE)

    def complete_turn(
        self,
        result: TurnResult,
        evidence: tuple[TelemetryEvidence, ...] = (),
        sender: MessageSender = MessageSender.AGENT,
        state: StateSnapshot | None = None,
    ) -> None:
        """Reply, `result` envelope and `state` land in one transaction."""
        self._store.complete_turn(
            self._conversation_id,
            self._turn,
            sender,
            result.reply,
            tuple(c.to_row() for c in result.citations),
            evidence,
            uuid5(self._message_id, "reply"),
            self._clock.now(),
            state,
            result.model_dump(mode="json"),
        )
        self._path.append(ConversationStage.IDLE)
