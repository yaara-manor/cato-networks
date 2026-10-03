from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

import psycopg
import pytest

from actions import ActionDispatcher
from agents import (
    AgentRun,
    AgentTrace,
    DiagnosticEvidence,
    DiagnosticsFindings,
    DiagnosticsInput,
    Intent,
    KnowledgeBundle,
    KnowledgeFindings,
    KnowledgeInput,
    ResolutionInput,
    ResolutionPlan,
    SupportAction,
    SupportDeps,
    TriageDecision,
    TriageInput,
    TriageResult,
    UnavailableTool,
)
from core.clock import SimulationClock
from core.config import settings
from guardrails import ActionType, SessionGuardHistory
from orchestration import AgentPorts, Workflow
from retrieval.models import KBSearchStatus
from retrieval.service import RetrievalService
from services import CustomerService, TicketService
from storage import AgentRole, StateStore
from tools.telemetry import TelemetryService

PRIYA = "priya@bluebirdretail.com"  # verified member of ACC-1002, not admin
STRANGER = "mark@example.com"  # unknown caller

_CLEANUP_SQL = (
    "delete from simulated_actions where conversation_id = any(%(ids)s)",
    "delete from tool_calls where conversation_id = any(%(ids)s)",
    "delete from approvals where conversation_id = any(%(ids)s)",
    "delete from traces where conversation_id = any(%(ids)s)",
    "delete from messages where conversation_id = any(%(ids)s)",
    "delete from conversations where id = any(%(ids)s)",
)


def _trace(role: AgentRole) -> AgentTrace:
    return AgentTrace(agent_role=role, tool_calls=[], latency_ms=1, prompt_tokens=1, completion_tokens=1)


@dataclass
class Scripted:
    """Scripted agent callables; tweak the fields per test, read `calls` / `inputs` afterwards."""

    decision: TriageDecision = field(
        default_factory=lambda: TriageDecision(
            intent=Intent.TELEMETRY_DIAGNOSIS, priority="P3", symptom_summary="site down"
        )
    )
    scoping_question: str | None = None
    needs_more_telemetry: bool = False
    sev1: bool = False
    actions: tuple[SupportAction, ...] = ()
    escalate: bool = False
    unavailable: tuple[UnavailableTool, ...] = ()
    kb_status: KBSearchStatus = KBSearchStatus.CONFIDENT
    fail_in: str | None = None  # role whose callable raises
    calls: list[str] = field(default_factory=list)
    inputs: dict[str, list[Any]] = field(default_factory=dict)

    def _seen(self, role: str, data: Any) -> None:
        self.calls.append(role)
        if self.fail_in == role:
            raise RuntimeError(f"{role} boom")
        self.inputs.setdefault(role, []).append(data)

    def triage(self, data: TriageInput, deps: SupportDeps) -> AgentRun[TriageResult]:
        self._seen("triage", data)
        decision = self.decision.model_copy(update={"scoping_question": self.scoping_question})
        result = TriageResult(decision=decision, identity=data.identity)
        return AgentRun(output=result, trace=_trace(AgentRole.TRIAGE))

    def diagnostics(self, data: DiagnosticsInput, deps: SupportDeps) -> AgentRun[DiagnosticEvidence]:
        self._seen("diagnostics", data)
        evidence = DiagnosticEvidence(
            findings=DiagnosticsFindings(), unavailable_tools=self.unavailable, sev1_corroborated=self.sev1
        )
        return AgentRun(output=evidence, trace=_trace(AgentRole.DIAGNOSTICS))

    def knowledge(self, data: KnowledgeInput, deps: SupportDeps) -> AgentRun[KnowledgeBundle]:
        self._seen("knowledge", data)
        bundle = KnowledgeBundle(
            findings=KnowledgeFindings(needs_more_telemetry=self.needs_more_telemetry),
            confidence_status=self.kb_status,
            needs_more_telemetry=self.needs_more_telemetry,
        )
        return AgentRun(output=bundle, trace=_trace(AgentRole.KNOWLEDGE))

    def resolution(self, data: ResolutionInput, deps: SupportDeps) -> AgentRun[ResolutionPlan]:
        self._seen("resolution", (data, deps))
        plan = ResolutionPlan(
            customer_message=self.scoping_question or "Here is your answer.",
            actions=self.actions,
            escalate_to_human=self.escalate,
        )
        return AgentRun(output=plan, trace=_trace(AgentRole.RESOLUTION))

    @property
    def ports(self) -> AgentPorts:
        return AgentPorts(self.triage, self.diagnostics, self.knowledge, self.resolution)


@dataclass(frozen=True)
class Harness:
    connect: Callable[[], psycopg.Connection[Any]]
    new_conversation: Callable[[str], UUID]
    workflow: Callable[[Scripted, psycopg.Connection[Any] | None], Workflow]


@pytest.fixture
def scripted() -> Scripted:
    return Scripted()


@pytest.fixture
def conn() -> Iterator[psycopg.Connection[Any]]:
    with psycopg.connect(settings.database_url, autocommit=True) as connection:
        yield connection


@pytest.fixture
def harness(conn: psycopg.Connection[Any]) -> Iterator[Harness]:
    created: list[UUID] = []
    clock = SimulationClock()
    baseline = conn.execute("select coalesce(max(substring(ticket_id from 5)::int), 0) from tickets").fetchone()

    def new_conversation(email: str) -> UUID:
        conversation = StateStore(conn).create_conversation(None, email, "Unknown", clock.now())
        created.append(conversation.id)
        return conversation.id

    def workflow(script: Scripted, connection: psycopg.Connection[Any] | None = None) -> Workflow:
        connection = connection or conn
        customers = CustomerService(connection, clock)
        deps = SupportDeps(
            clock=clock,
            customers=customers,
            tickets=TicketService(connection, clock),
            telemetry=TelemetryService(clock=clock),
            retrieval=RetrievalService(connection),
            identity=customers.authenticate_caller(STRANGER),
            guard_history=SessionGuardHistory(),
            approved_actions=frozenset[ActionType](),
        )
        store = StateStore(connection)
        return Workflow(script.ports, store, clock, deps, ActionDispatcher(store, deps.tickets, clock))

    yield Harness(lambda: psycopg.connect(settings.database_url, autocommit=True), new_conversation, workflow)
    for statement in _CLEANUP_SQL:
        conn.execute(statement, {"ids": created})
    conn.execute("delete from tickets where substring(ticket_id from 5)::int > %s", (baseline[0] if baseline else 0,))
