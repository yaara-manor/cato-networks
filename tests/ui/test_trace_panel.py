from uuid import uuid4

from streamlit.testing.v1 import AppTest

from agents import AgentTrace, ToolCall
from agents.models import AgentRole
from core.clock import SimulationClock
from guardrails import ActionType, ApprovalStatus
from storage import ApprovalResolution, StateStore, ToolCallRecord, TraceRecord
from tests.orchestration.conftest import PRIYA, Harness, Scripted

STUB = "trace_stub_app.py"
LEAKS = (
    "MODEL-MSG-SENTINEL",
    "TOOL-ARG-SENTINEL",
    "TOOL-RESULT-SENTINEL",
    "REVIEWER-NOTE-SENTINEL",
    "STEP-INPUT-SENTINEL",
)


def test_panel_shows_steps_and_totals_but_no_internals(harness: Harness, scripted: Scripted) -> None:
    clock = SimulationClock()
    conversation_id = harness.new_conversation(PRIYA)
    message_id = uuid4()
    scripted.reply = "All good."
    harness.workflow(scripted, None).run_turn(conversation_id, "site down", message_id)

    store = StateStore(harness.connect())
    call = ToolCall(
        tool_name="get_site_health",
        arguments={"k": "TOOL-ARG-SENTINEL"},
        status="OK",
        result={"k": "TOOL-RESULT-SENTINEL"},
        latency_ms=7,
    )
    agent_trace = AgentTrace(
        agent_role=AgentRole.DIAGNOSTICS,
        tool_calls=[call],
        latency_ms=11,
        prompt_tokens=5,
        completion_tokens=6,
        input={"k": "STEP-INPUT-SENTINEL"},
        model_messages=[{"k": "MODEL-MSG-SENTINEL"}],
    )
    trace = TraceRecord.from_agent_trace(agent_trace, conversation_id, 1, message_id, None, clock.now())
    store.record_trace(trace, [ToolCallRecord.from_tool_call(trace.id, conversation_id, 0, call, clock.now())])
    approval = store.create_approval(conversation_id, message_id, ActionType.CREDIT, {"amount": "1"}, "k", clock.now())
    store.resolve_approval(
        approval.id,
        ApprovalResolution(status=ApprovalStatus.REJECTED, reviewer_notes="REVIEWER-NOTE-SENTINEL"),
        clock.now(),
    )

    app = AppTest.from_file(STUB)
    app.query_params["cid"] = str(conversation_id)
    app.run()

    assert not app.exception
    page = " ".join(el.value for el in app.text) + " ".join(el.value for el in app.code)
    for role in ("TRIAGE", "DIAGNOSTICS", "KNOWLEDGE", "RESOLUTION"):
        assert role in page
    assert "tool get_site_health [OK] 7 ms" in page and "5+6 tokens" in page
    assert "site down" in page and "All good." in page
    assert [e.label for e in app.expander] == ["Turn 1"]
    assert not [leak for leak in LEAKS if leak in repr(app)]
