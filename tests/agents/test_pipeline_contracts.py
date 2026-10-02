import json

import agents
from agents import (
    DiagnosticsInput,
    Intent,
    KnowledgeInput,
    ResolutionInput,
    TriageDecision,
    TriageInput,
    run_diagnostics,
    run_knowledge,
    run_resolution,
    run_triage,
)
from core.config import REPO_ROOT
from guardrails import check_citations, check_outgoing_message
from tests.agents.conftest import MakeDeps, scripted_model

SITE = "S-1007-01"  # ACC-1007, sysadmin@atlas-eng.com


def _question() -> str:
    with (REPO_ROOT / "data/eval/questions.jsonl").open() as f:
        return next(r["question"] for r in map(json.loads, f) if r["question_id"] == "Q10")


def test_every_public_name_is_exported() -> None:
    assert all(hasattr(agents, name) for name in agents.__all__)


def test_four_role_chain_feeds_each_output_to_the_next_input(make_deps: MakeDeps) -> None:
    deps, message = make_deps(), _question()
    decision = TriageDecision(intent=Intent.TELEMETRY_DIAGNOSIS, priority="P2", symptom_summary="s")
    triage = run_triage(
        TriageInput(message=message, identity=deps.identity),
        deps,
        scripted_model([], decision.model_dump()),
    ).output
    diagnostics = run_diagnostics(
        DiagnosticsInput(triage=triage, message=message),
        deps,
        scripted_model([("get_site_status", {"site_id": SITE})], {"root_cause_hypothesis": "h"}),
    ).output
    knowledge = run_knowledge(
        KnowledgeInput(triage=triage, diagnostics=diagnostics, message=message),
        deps,
        scripted_model([("search_knowledge_base", {"query": message})], {}),
    ).output
    data = ResolutionInput(triage=triage, diagnostics=diagnostics, knowledge=knowledge, message=message)
    passage = knowledge.retrieved_passages[0]
    reply = (
        f"{diagnostics.evidence_items[0].format_citation()} "
        f"See [kb:{passage.slug}#{passage.heading_anchor}]."
    )
    plan = run_resolution(data, deps, scripted_model([], {"customer_message": reply})).output
    assert plan.customer_message == reply and not plan.escalate_to_human
    assert check_citations(plan.customer_message, data.grounding_context()).is_grounded
    assert not check_outgoing_message(plan.customer_message, deps.guard_history, deps.approved_actions)
