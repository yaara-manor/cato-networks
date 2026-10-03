from typing import Any
from uuid import uuid4

import psycopg
import pytest
from pydantic_ai.models.test import TestModel

from core.clock import SimulationClock
from orchestration import build_ports, build_services, build_workflow, runtime
from storage import MessageSender, StateStore
from tests.orchestration.conftest import PRIYA, Harness, Scripted


def test_build_services_touches_no_encoder(
    conn: psycopg.Connection[Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom() -> None:
        raise AssertionError("encoder loaded")

    monkeypatch.setattr(runtime, "load_embedder", boom)
    monkeypatch.setattr(runtime, "load_reranker", boom)

    services = build_services(conn, SimulationClock())

    assert services.customers.authenticate_caller(PRIYA).account is not None


def test_workflows_on_different_connections_are_independent(harness: Harness, scripted: Scripted) -> None:
    clock = SimulationClock()
    with harness.connect() as other:
        first = build_workflow(other, clock, scripted.ports)
        second = build_workflow(other, clock, scripted.ports)
        assert first.base_deps.customers is not second.base_deps.customers
    conversation_id = harness.new_conversation(PRIYA)

    result = harness.workflow(scripted, None).run_turn(conversation_id, "Branch site is down", uuid4())

    snapshot = StateStore(harness.connect()).rehydrate(conversation_id)
    assert snapshot is not None
    assert snapshot.messages[-1].content == result.reply
    assert snapshot.messages[-1].sender is MessageSender.AGENT


def test_build_ports_binds_model_without_network() -> None:
    ports = build_ports(TestModel())

    assert all(callable(p) for p in (ports.triage, ports.diagnostics, ports.knowledge, ports.resolution))
