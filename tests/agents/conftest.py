import json
from collections.abc import Callable, Iterator
from typing import Any

import psycopg
import pytest
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from agents.base import SupportDeps
from core.clock import SimulationClock
from core.config import REPO_ROOT, settings
from guardrails import ActionType, SessionGuardHistory
from retrieval.models import KBSearchResult
from retrieval.service import RetrievalService
from services import CustomerService, TicketService
from tools.telemetry import TelemetryService

MakeDeps = Callable[..., SupportDeps]
ToolScript = list[tuple[str, dict[str, Any]]]


@pytest.fixture(scope="session")
def connection() -> Iterator[psycopg.Connection[Any]]:
    with psycopg.connect(settings.database_url, autocommit=True) as conn:
        yield conn


@pytest.fixture(scope="session")
def retrieval(connection: psycopg.Connection[Any]) -> RetrievalService:
    return RetrievalService(connection)


@pytest.fixture(scope="session")
def q10_result(retrieval: RetrievalService) -> KBSearchResult:
    with (REPO_ROOT / "data/eval/questions.jsonl").open() as f:
        question = next(r["question"] for r in map(json.loads, f) if r["question_id"] == "Q10")
    return retrieval.search_kb(question)


@pytest.fixture
def make_deps(connection: psycopg.Connection[Any], retrieval: RetrievalService) -> MakeDeps:
    clock = SimulationClock.frozen()

    def make(email: str = "sysadmin@atlas-eng.com", **overrides: Any) -> SupportDeps:
        customers = CustomerService(connection, clock)
        fields: dict[str, Any] = {
            "clock": clock,
            "customers": customers,
            "tickets": TicketService(connection, clock),
            "telemetry": TelemetryService(clock=clock),
            "retrieval": retrieval,
            "identity": customers.authenticate_caller(email),
            "guard_history": SessionGuardHistory(),
            "approved_actions": frozenset[ActionType](),
        }
        return SupportDeps(**{**fields, **overrides})

    return make


def scripted_model(
    calls: ToolScript, final: dict[str, Any] | None, model_name: str = "scripted"
) -> FunctionModel:
    """Issues `calls` one by one, then answers with `final` via the output tool.

    `final=None` sends an output-tool call that never validates (exhausts retries).
    """

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        done = sum(
            isinstance(p, ToolReturnPart) and not p.tool_name.startswith("final_result")
            for m in messages
            for p in m.parts
        )
        if done < len(calls):
            name, args = calls[done]
            return ModelResponse(parts=[ToolCallPart(name, args)])
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, final or {"bad": 1})])

    return FunctionModel(respond, model_name=model_name)
