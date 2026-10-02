from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from agents.models import (
    DiagnosticEvidence,
    DiagnosticsFindings,
    Intent,
    KnowledgeBundle,
    KnowledgeFindings,
    ResolutionInput,
    SupportAction,
    SupportActionKind,
    TriageDecision,
    TriageResult,
    UnavailableTool,
)
from guardrails import ActionType, GateOutcome, GroundingContext, check_action
from retrieval.models import KBSearchResult, KBSearchStatus
from retrieval.service import RetrievalService
from services.models import CallerIdentity
from tests.agents.conftest import MakeDeps
from tools.models import TelemetryEvidence, TelemetryStatus

_DECISION = TriageDecision(intent=Intent.KB_INQUIRY, priority="P3", symptom_summary="s")


def _triage(identity: CallerIdentity, **decision: str | None) -> TriageResult:
    return TriageResult(
        decision=_DECISION.model_copy(update=decision), identity=identity
    )


def _bundle(
    status: KBSearchStatus, result: KBSearchResult, retrieval: RetrievalService
) -> KnowledgeBundle:
    confident = status == KBSearchStatus.CONFIDENT
    return KnowledgeBundle(
        findings=KnowledgeFindings(),
        retrieved_passages=tuple(result.passages) if confident else (),
        referenced_policies=(policy,) if confident and (policy := retrieval.get_policy("POL-SLA")) else (),
        confidence_status=status,
    )


def test_grounding_context_per_knowledge_status(
    make_deps: MakeDeps, q10_result: KBSearchResult, retrieval: RetrievalService
) -> None:
    triage = _triage(make_deps().identity)
    evidence = DiagnosticEvidence(findings=DiagnosticsFindings(), inspected_tools=("get_bgp_status",))

    def context(knowledge: KnowledgeBundle | None) -> GroundingContext:
        return ResolutionInput(
            triage=triage, diagnostics=evidence, knowledge=knowledge, message="m"
        ).grounding_context()

    confident = context(_bundle(KBSearchStatus.CONFIDENT, q10_result, retrieval))
    assert confident.kb_refs == {(p.slug, p.heading_anchor) for p in q10_result.passages}
    assert confident.policy_ids == {"POL-SLA"}
    assert confident.telemetry_tools == {"get_bgp_status"}
    assert not confident.is_refusal

    for status in (KBSearchStatus.LOW_CONFIDENCE_REFUSAL, KBSearchStatus.UNAVAILABLE):
        refusal = context(_bundle(status, q10_result, retrieval))
        assert refusal.is_refusal
        assert not refusal.kb_refs and not refusal.policy_ids

    none = context(None)
    assert not none.is_refusal
    assert not none.kb_refs and not none.policy_ids


def test_grounding_context_excludes_unavailable_telemetry_tools(make_deps: MakeDeps) -> None:
    evidence = DiagnosticEvidence(
        findings=DiagnosticsFindings(),
        inspected_tools=("get_bgp_status", "get_events"),
        unavailable_tools=(UnavailableTool(tool_name="get_events", status=TelemetryStatus.UNAVAILABLE),),
    )
    context = ResolutionInput(
        triage=_triage(make_deps().identity), diagnostics=evidence, message="m"
    ).grounding_context()
    assert context.telemetry_tools == {"get_bgp_status"}


@pytest.mark.parametrize(
    ("kind", "action_type"),
    [
        (SupportActionKind.CREDIT, ActionType.CREDIT),
        (SupportActionKind.MFA_RESET, ActionType.MFA_RESET),
        (SupportActionKind.VERDICT_OVERRIDE, ActionType.VERDICT_OVERRIDE),
        (SupportActionKind.CLOSE_TICKET, ActionType.CLOSE_TICKET),
        (SupportActionKind.PAGE_ON_CALL, None),  # gated only once plan 22/04 adds the ActionType
        (SupportActionKind.CREATE_TICKET, None),
        (SupportActionKind.UPDATE_TICKET, None),
    ],
)
def test_to_proposed_action_mapping(kind: SupportActionKind, action_type: ActionType | None) -> None:
    proposed = SupportAction(kind=kind, payload={"k": "v"}, reason="r").to_proposed_action("ACC-1007")
    if action_type is None:
        assert proposed is None
    else:
        assert proposed is not None
        assert (proposed.action_type, proposed.target_account_id, proposed.payload) == (
            action_type,
            "ACC-1007",
            {"k": "v"},
        )


def test_credit_proposal_requires_approval_for_verified_admin(make_deps: MakeDeps) -> None:
    identity = make_deps().identity
    assert identity.account is not None and identity.is_registered_admin
    proposed = SupportAction(kind=SupportActionKind.CREDIT, reason="r").to_proposed_action(
        identity.account.account_id
    )
    assert proposed is not None
    assert check_action(proposed, identity).outcome == GateOutcome.REQUIRE_APPROVAL


def test_contracts_are_frozen(make_deps: MakeDeps) -> None:
    triage = _triage(make_deps().identity)
    with pytest.raises(ValidationError):
        triage.sla = None


def test_unrecognized_caller_allows_missing_sla_and_repeat_contact(make_deps: MakeDeps) -> None:
    identity = make_deps("nobody@example.com").identity
    assert identity.account is None
    triage = _triage(identity)
    assert triage.sla is None and triage.repeat_contact is None


def test_identity_scoping_question_wins(make_deps: MakeDeps) -> None:
    identity = make_deps().identity.model_copy(update={"scoping_question": "Which country?"})
    assert _triage(identity, scoping_question="Which site?").scoping_question == "Which country?"
    plain = _triage(make_deps().identity, scoping_question="Which site?")
    assert plain.scoping_question == "Which site?"


def test_has_anomaly_reflects_evidence_items() -> None:
    item = TelemetryEvidence(
        tool_name="get_bgp_status",
        metric_key="routes_count",
        raw_value="1024/1024",
        timestamp=datetime(2026, 8, 28, tzinfo=UTC),
        is_anomaly=True,
    )
    clean = DiagnosticEvidence(findings=DiagnosticsFindings())
    flagged = clean.model_copy(update={"evidence_items": (item,)})
    assert (clean.has_anomaly, flagged.has_anomaly) == (False, True)
