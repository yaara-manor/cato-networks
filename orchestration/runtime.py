from dataclasses import dataclass
from functools import partial
from typing import Any

import psycopg
from pydantic_ai.models import Model

from actions import ActionDispatcher
from agents import SupportDeps, run_diagnostics, run_knowledge, run_resolution, run_triage
from core.clock import SimulationClock
from encoders.embed import load_embedder
from encoders.rerank import load_reranker
from guardrails import ActionType, SessionGuardHistory
from orchestration.models import AgentPorts
from orchestration.workflow import Workflow
from retrieval.service import RetrievalService
from services import CustomerService, TicketService
from storage import StateStore
from tools.telemetry import TelemetryService


@dataclass(frozen=True)
class Services:
    """Connection-bound services; no encoder or LLM is touched building them."""

    store: StateStore
    customers: CustomerService
    tickets: TicketService
    telemetry: TelemetryService


def build_services(connection: psycopg.Connection[Any], clock: SimulationClock) -> Services:
    return Services(
        store=StateStore(connection),
        customers=CustomerService(connection, clock),
        tickets=TicketService(connection, clock),
        telemetry=TelemetryService(clock=clock),
    )


def build_ports(model: Model | None = None) -> AgentPorts:
    """`model=None` lets each agent resolve `settings.llm_model` lazily, on first run."""
    return AgentPorts(
        triage=partial(run_triage, model=model),
        diagnostics=partial(run_diagnostics, model=model),
        knowledge=partial(run_knowledge, model=model),
        resolution=partial(run_resolution, model=model),
    )


def build_workflow(
    connection: psycopg.Connection[Any], clock: SimulationClock, ports: AgentPorts | None = None
) -> Workflow:
    """Fresh services on `connection` per call: nothing is shared between workflows."""
    services = build_services(connection, clock)
    deps = SupportDeps(
        clock=clock,
        customers=services.customers,
        tickets=services.tickets,
        telemetry=services.telemetry,
        retrieval=RetrievalService(connection),
        identity=services.customers.authenticate_caller(None),  # placeholder; triage sets the real one
        guard_history=SessionGuardHistory(),
        approved_actions=frozenset[ActionType](),
    )
    return Workflow(ports or build_ports(), services.store, clock, deps, ActionDispatcher(services.store, services.tickets, clock))


def warm_models() -> None:
    load_embedder()
    load_reranker()
