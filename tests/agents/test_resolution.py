from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from pydantic_ai.messages import ModelMessage, ModelRequest, ModelResponse, ToolCallPart, UserPromptPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from agents.models import (
    AgentRole,
    DiagnosticEvidence,
    DiagnosticsFindings,
    Intent,
    KnowledgeBundle,
    KnowledgeFindings,
    ResolutionInput,
    TriageDecision,
    TriageResult,
    UnavailableTool,
    UnsettledApprovalView,
)
from agents.resolution import HOLDING_MESSAGE, run_resolution
from guardrails import (
    ActionType,
    ApprovalStatus,
    ApprovedGrant,
    SessionGuardHistory,
    check_citations,
    check_outgoing_message,
    secret_hash,
)
from retrieval.models import KBSearchResult, KBSearchStatus
from tests.agents.conftest import MakeDeps, scripted_model
from tools.models import TelemetryStatus

CREDIT_SENTENCE = "We will apply a $3,600 credit to your account."
CLAIM = "The tunnel dropped after 1350 bytes."


def _plans(*messages: str) -> tuple[FunctionModel, list[int]]:
    """Answers attempt N with `messages[N]`; the counter records how many attempts ran."""
    attempts: list[int] = []

    def respond(_: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        message = messages[min(len(attempts), len(messages) - 1)]
        attempts.append(1)
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {"customer_message": message})])

    return FunctionModel(respond, model_name="scripted"), attempts


def _input(
    make_deps: MakeDeps,
    knowledge: KnowledgeBundle | None = None,
    diagnostics: DiagnosticEvidence | None = None,
) -> ResolutionInput:
    decision = TriageDecision(intent=Intent.KB_INQUIRY, priority="P3", symptom_summary="s")
    triage = TriageResult(decision=decision, identity=make_deps().identity)
    return ResolutionInput(triage=triage, diagnostics=diagnostics, knowledge=knowledge, message="help")


def _knowledge(q10_result: KBSearchResult) -> KnowledgeBundle:
    return KnowledgeBundle.from_tool_results(KnowledgeFindings(), [q10_result])


def _refusal(status: KBSearchStatus) -> KnowledgeBundle:
    return KnowledgeBundle.from_tool_results(
        KnowledgeFindings(), [KBSearchResult(status=status, query="q", snapshot_date=None)]
    )


def _kb_marker(knowledge: KnowledgeBundle) -> str:
    passage = knowledge.retrieved_passages[0]
    return f"[kb:{passage.slug}#{passage.heading_anchor}]"


def test_uncited_claim_then_cited_rewrite_retries_once(
    make_deps: MakeDeps, q10_result: KBSearchResult
) -> None:
    knowledge = _knowledge(q10_result)
    cited = f"{CLAIM} {_kb_marker(knowledge)}"
    model, attempts = _plans(CLAIM, cited)
    data = _input(make_deps, knowledge)
    run = run_resolution(data, make_deps(), model)
    assert len(attempts) == 2
    assert run.output.customer_message == cited and not run.output.escalate_to_human
    assert check_citations(cited, data.grounding_context()).is_grounded


def test_fabricated_kb_citation_is_retried(make_deps: MakeDeps, q10_result: KBSearchResult) -> None:
    model, attempts = _plans("See [kb:no-such-article#nowhere].", "Please share the error text.")
    run = run_resolution(_input(make_deps, _knowledge(q10_result)), make_deps(), model)
    assert len(attempts) == 2 and not run.output.escalate_to_human


def test_credit_amount_twice_falls_back_to_holding_plan(make_deps: MakeDeps) -> None:
    model, attempts = _plans(CREDIT_SENTENCE)
    run = run_resolution(_input(make_deps), make_deps(), model)
    assert len(attempts) == 2
    assert run.output.customer_message == HOLDING_MESSAGE
    assert run.output.escalate_to_human and run.output.actions == ()
    assert run.output.escalation_reason


def test_credit_amount_passes_when_credit_is_approved(make_deps: MakeDeps) -> None:
    model, attempts = _plans(CREDIT_SENTENCE)
    grant = ApprovedGrant(action_type=ActionType.CREDIT, approval_id=uuid4(), payload={"amount": "3600"})
    deps = make_deps(approved_grants=(grant,))
    run = run_resolution(_input(make_deps), deps, model)
    assert len(attempts) == 1 and run.output.customer_message == CREDIT_SENTENCE


def test_refusal_grounding_rejects_kb_marker(make_deps: MakeDeps) -> None:
    model, attempts = _plans("It is documented [kb:any#thing].", "That is not in the knowledge base.")
    knowledge = _refusal(KBSearchStatus.LOW_CONFIDENCE_REFUSAL)
    run = run_resolution(_input(make_deps, knowledge), make_deps(), model)
    assert len(attempts) == 2 and not run.output.escalate_to_human


def test_failed_telemetry_tool_cannot_be_cited(make_deps: MakeDeps) -> None:
    diagnostics = DiagnosticEvidence(
        findings=DiagnosticsFindings(),
        inspected_tools=("get_events",),
        unavailable_tools=(UnavailableTool(tool_name="get_events", status=TelemetryStatus.UNAVAILABLE),),
    )
    model, attempts = _plans("Events show a drop [telemetry:get_events].", "Event data is unavailable.")
    run_resolution(_input(make_deps, diagnostics=diagnostics), make_deps(), model)
    assert len(attempts) == 2


def test_echoed_redacted_secret_is_retried(make_deps: MakeDeps) -> None:
    history = SessionGuardHistory(secret_hashes=frozenset({secret_hash("hunter2-psk-value")}))
    model, attempts = _plans("Your key is hunter2-psk-value.", "Please rotate the key you shared.")
    run_resolution(_input(make_deps), make_deps(guard_history=history), model)
    assert len(attempts) == 2


def test_model_failure_returns_holding_plan_with_trace(make_deps: MakeDeps) -> None:
    run = run_resolution(_input(make_deps), make_deps(), scripted_model([], None))
    assert run.output.customer_message == HOLDING_MESSAGE and run.output.escalate_to_human
    assert run.trace.agent_role is AgentRole.RESOLUTION and run.trace.error


def test_unknown_caller_actions_are_dropped(make_deps: MakeDeps) -> None:
    plan: dict[str, Any] = {
        "customer_message": "Please share your registered email.",
        "actions": [{"kind": "CLOSE_TICKET", "reason": "r"}],
    }
    identity = make_deps().identity.model_copy(update={"account": None})
    run = run_resolution(_input(make_deps), make_deps(identity=identity), scripted_model([], plan))
    assert run.output.actions == ()


def test_holding_message_passes_both_guards(make_deps: MakeDeps) -> None:
    context = _input(make_deps, _refusal(KBSearchStatus.UNAVAILABLE)).grounding_context()
    assert check_citations(HOLDING_MESSAGE, context).is_grounded
    assert not check_outgoing_message(HOLDING_MESSAGE, SessionGuardHistory(), ())


def test_prompt_renders_known_ticket(make_deps: MakeDeps) -> None:
    prompts: list[str] = []

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        request = messages[0]
        assert isinstance(request, ModelRequest)
        prompts.extend(str(p.content) for p in request.parts if isinstance(p, UserPromptPart))
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {"customer_message": "ok"})])

    model = FunctionModel(respond, model_name="scripted")
    data = _input(make_deps)
    run_resolution(data.model_copy(update={"known_ticket_id": "TCK-42"}), make_deps(), model)
    run_resolution(data, make_deps(), model)
    assert "Known ticket: TCK-42" in prompts[0]
    assert "Known ticket: none" in prompts[1]


def test_prompt_renders_unsettled_approvals_without_amounts(make_deps: MakeDeps) -> None:
    prompts: list[str] = []

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        request = messages[0]
        assert isinstance(request, ModelRequest)
        prompts.extend(str(p.content) for p in request.parts if isinstance(p, UserPromptPart))
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {"customer_message": "ok"})])

    unsettled = (
        UnsettledApprovalView(
            action_type=ActionType.CREDIT, status=ApprovalStatus.PENDING, requested_at=datetime.now(UTC)
        ),
    )
    data = _input(make_deps).model_copy(update={"unsettled_approvals": unsettled})
    run_resolution(data, make_deps(), FunctionModel(respond, model_name="scripted"))
    assert "Unsettled approvals: CREDIT status=PENDING" in prompts[0]
