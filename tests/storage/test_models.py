import json
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from agents.models import AgentTrace, ToolCall
from guardrails.models import (
    InjectionCategory,
    InjectionVerdict,
    RedactionFinding,
    RedactionResult,
    SecretKind,
    SessionGuardHistory,
)
from storage import (
    ApprovalResolution,
    ApprovalStatus,
    ToolCallRecord,
    TraceRecord,
    strip_nul,
    to_jsonb,
)

NOW = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)


def test_guard_history_json_roundtrip_restores_frozenset() -> None:
    verdict = InjectionVerdict(
        blocked=True, categories=frozenset({InjectionCategory.ROLE_OVERRIDE}), rule_ids=("r1",)
    )
    finding = RedactionFinding(kind=SecretKind.JWT, start=0, end=1, sha256="abc")
    history = (
        SessionGuardHistory()
        .with_injection(verdict)
        .with_redaction(RedactionResult(text="x", findings=(finding,)))
    )
    restored = SessionGuardHistory.model_validate(
        json.loads(json.dumps(history.model_dump(mode="json")))
    )
    assert restored == history
    assert isinstance(restored.secret_hashes, frozenset)
    assert restored.agent_context_note() == history.agent_context_note()


@pytest.mark.parametrize(
    ("status", "payload", "valid"),
    [
        (ApprovalStatus.PENDING, None, False),
        (ApprovalStatus.EDITED, None, False),
        (ApprovalStatus.APPROVED, {"amount": "5"}, False),
        (ApprovalStatus.APPROVED, None, True),
        (ApprovalStatus.REJECTED, None, True),
        (ApprovalStatus.EDITED, {"amount": "5"}, True),
    ],
)
def test_approval_resolution_validator(
    status: ApprovalStatus, payload: dict[str, str] | None, valid: bool
) -> None:
    if valid:
        ApprovalResolution(status=status, edited_payload=payload)
    else:
        with pytest.raises(ValidationError):
            ApprovalResolution(status=status, edited_payload=payload)


def test_records_built_from_agent_trace() -> None:
    call = ToolCall(tool_name="t", arguments={"a": 1}, status="OK", result={"r": 2}, latency_ms=7)
    agent_trace = AgentTrace(
        agent_role="TRIAGE", tool_calls=[call], latency_ms=40, prompt_tokens=11, completion_tokens=5
    )
    conversation_id = uuid4()
    trace = TraceRecord.from_agent_trace(agent_trace, conversation_id, 1, None, None, NOW)
    assert trace.agent_role == "TRIAGE"
    assert (trace.prompt_tokens, trace.completion_tokens, trace.latency_ms) == (11, 5, 40)
    assert trace.seq is None
    record = ToolCallRecord.from_tool_call(trace.id, conversation_id, 0, call, NOW)
    assert (record.tool_name, record.arguments, record.result, record.latency_ms) == (
        "t",
        {"a": 1},
        {"r": 2},
        7,
    )


def test_nul_is_stripped_from_text_and_json() -> None:
    assert strip_nul("a\x00b") == "ab"
    payload = {"k\x00": ["x\x00y", {"n": "z\x00"}], "literal": "\\u0000"}
    dumps = to_jsonb(payload).dumps
    assert dumps is not None
    dumped = dumps(payload)
    assert json.loads(dumped) == {"k": ["xy", {"n": "z"}], "literal": "\\u0000"}
