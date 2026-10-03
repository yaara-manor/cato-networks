from dataclasses import replace
from typing import Any
from uuid import UUID, uuid4

import psycopg
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from agents import (
    AgentRun,
    DiagnosticEvidence,
    DiagnosticsFindings,
    KnowledgeBundle,
    KnowledgeFindings,
    ResolutionInput,
    ResolutionPlan,
    SupportDeps,
    UnavailableTool,
    run_resolution,
)
from orchestration import AgentPorts
from orchestration.canned import AGENT_FAILURE_PAUSE
from orchestration.degradation import (
    DegradationNotice,
    DegradedSource,
    derive_degradations,
)
from retrieval.models import KBSearchStatus
from storage import ConversationStage, MessageSender, StateStore
from tests.orchestration.conftest import PRIYA, Harness, Scripted
from tools.models import TelemetryStatus

DOWN = (UnavailableTool(tool_name="get_ipsec_status", status=TelemetryStatus.UNAVAILABLE),)
NOT_FOUND = (UnavailableTool(tool_name="get_site", status=TelemetryStatus.NOT_FOUND),)
TELEMETRY_TEXT = DegradationNotice.from_telemetry(("x",)).customer_text
RETRIEVAL_TEXT = DegradationNotice.from_retrieval().customer_text


def _state(harness: Harness, conversation_id: UUID) -> dict[str, Any]:
    with harness.connect() as fresh:
        snapshot = StateStore(fresh).rehydrate(conversation_id)
    assert snapshot is not None
    return snapshot.conversation.state.data


def test_derive_degradations_filters_and_orders() -> None:
    evidence = DiagnosticEvidence(findings=DiagnosticsFindings(), unavailable_tools=DOWN + NOT_FOUND)
    bundle = KnowledgeBundle(findings=KnowledgeFindings(), confidence_status=KBSearchStatus.UNAVAILABLE)
    notices = derive_degradations(evidence, bundle)
    assert [n.source for n in notices] == [DegradedSource.TELEMETRY, DegradedSource.RETRIEVAL]
    assert notices[0].detail == "get_ipsec_status"
    assert derive_degradations(None, None) == ()


def test_telemetry_down_discloses_once_without_escalation(harness: Harness, scripted: Scripted) -> None:
    scripted.unavailable = DOWN
    conversation_id = harness.new_conversation(PRIYA)
    workflow = harness.workflow(scripted, None)
    first = workflow.run_turn(conversation_id, "site down", uuid4())
    assert first.reply.startswith(TELEMETRY_TEXT) and not first.escalation_offered
    assert "knowledge" in scripted.calls
    second = workflow.run_turn(conversation_id, "still down", uuid4())
    assert TELEMETRY_TEXT not in second.reply and second.degradations


def test_non_outage_statuses_produce_no_notice(harness: Harness, scripted: Scripted) -> None:
    scripted.unavailable = NOT_FOUND
    result = harness.workflow(scripted, None).run_turn(harness.new_conversation(PRIYA), "site x", uuid4())
    assert result.degradations == () and TELEMETRY_TEXT not in result.reply


def test_retrieval_down_offers_escalation(harness: Harness, scripted: Scripted) -> None:
    scripted.kb_status = KBSearchStatus.UNAVAILABLE
    result = harness.workflow(scripted, None).run_turn(harness.new_conversation(PRIYA), "help", uuid4())
    assert result.reply.startswith(RETRIEVAL_TEXT) and result.escalation_offered


def test_both_down_telemetry_first(harness: Harness, scripted: Scripted) -> None:
    scripted.unavailable = DOWN
    scripted.kb_status = KBSearchStatus.UNAVAILABLE
    reply = harness.workflow(scripted, None).run_turn(harness.new_conversation(PRIYA), "help", uuid4()).reply
    assert reply.index(TELEMETRY_TEXT) < reply.index(RETRIEVAL_TEXT)


def test_low_confidence_refusal_is_not_an_outage(harness: Harness, scripted: Scripted) -> None:
    scripted.kb_status = KBSearchStatus.LOW_CONFIDENCE_REFUSAL
    result = harness.workflow(scripted, None).run_turn(harness.new_conversation(PRIYA), "help", uuid4())
    assert result.degradations == () and not result.escalation_offered


def test_recovery_clears_flag_and_next_outage_is_disclosed_again(
    harness: Harness, scripted: Scripted
) -> None:
    conversation_id = harness.new_conversation(PRIYA)
    scripted.kb_status = KBSearchStatus.UNAVAILABLE
    harness.workflow(scripted, None).run_turn(conversation_id, "help", uuid4())
    assert _state(harness, conversation_id)["notice_shown"] == ["RETRIEVAL"]
    scripted.kb_status = KBSearchStatus.CONFIDENT
    with harness.connect() as fresh:  # restart between turns
        healthy = harness.workflow(scripted, fresh).run_turn(conversation_id, "again", uuid4())
    assert healthy.degradations == () and not healthy.escalation_offered
    assert _state(harness, conversation_id)["notice_shown"] == []
    scripted.kb_status = KBSearchStatus.UNAVAILABLE
    again = harness.workflow(scripted, None).run_turn(conversation_id, "help", uuid4())
    assert again.reply.startswith(RETRIEVAL_TEXT)


def test_outage_persisting_across_restart_is_not_repeated(harness: Harness, scripted: Scripted) -> None:
    conversation_id = harness.new_conversation(PRIYA)
    scripted.kb_status = KBSearchStatus.UNAVAILABLE
    harness.workflow(scripted, None).run_turn(conversation_id, "help", uuid4())
    with harness.connect() as fresh:
        second = harness.workflow(scripted, fresh).run_turn(conversation_id, "help", uuid4())
    assert RETRIEVAL_TEXT not in second.reply and second.escalation_offered


def test_fabricated_number_with_telemetry_down_gets_handoff(harness: Harness, scripted: Scripted) -> None:
    """The real `run_resolution` validators run through the workflow."""
    scripted.unavailable = DOWN

    def respond(_: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        text = "Tunnel shows 1024/1024 [telemetry:get_ipsec_status]."
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {"customer_message": text})])

    def resolve(data: ResolutionInput, deps: SupportDeps) -> AgentRun[ResolutionPlan]:
        return run_resolution(data, deps, FunctionModel(respond, model_name="scripted"))

    ports = AgentPorts(scripted.triage, scripted.diagnostics, scripted.knowledge, resolve)
    workflow = replace(harness.workflow(scripted, None), ports=ports)
    result = workflow.run_turn(harness.new_conversation(PRIYA), "tunnel?", uuid4())
    assert "1024" not in result.reply and result.escalation_offered
    assert result.reply.startswith(TELEMETRY_TEXT)


def test_agent_exception_pauses_turn_and_next_turn_works(
    harness: Harness, scripted: Scripted, conn: psycopg.Connection[Any]
) -> None:
    conversation_id = harness.new_conversation(PRIYA)
    workflow = harness.workflow(scripted, None)
    scripted.kb_status = KBSearchStatus.UNAVAILABLE
    workflow.run_turn(conversation_id, "help", uuid4())
    before = _state(harness, conversation_id)
    scripted.fail_in = "diagnostics"
    failed = workflow.run_turn(conversation_id, "site down", uuid4())
    assert failed.reply == AGENT_FAILURE_PAUSE and failed.path[-1] is ConversationStage.IDLE
    snapshot = StateStore(conn).rehydrate(conversation_id)
    assert snapshot is not None
    assert snapshot.conversation.stage is ConversationStage.IDLE
    assert snapshot.messages[-1].sender is MessageSender.SYSTEM
    assert any(m.content == "site down" for m in snapshot.messages)
    assert _state(harness, conversation_id) == before
    errors = conn.execute(
        "select error from traces where conversation_id = %s and status = 'ERROR'", (conversation_id,)
    ).fetchall()
    assert errors == [("RuntimeError",)]
    scripted.fail_in = None
    assert workflow.run_turn(conversation_id, "site down", uuid4()).reply != AGENT_FAILURE_PAUSE
