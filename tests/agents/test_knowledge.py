import json
from typing import Any

import psycopg

from agents.base import load_prompt
from agents.knowledge import run_knowledge
from agents.models import Intent, KnowledgeInput, TriageDecision, TriageResult
from core.config import REPO_ROOT, settings
from retrieval.models import KBSearchStatus
from retrieval.service import RetrievalService
from tests.agents.conftest import MakeDeps, scripted_model

HEADINGS = ("Role", "Inputs you receive", "Tools and when to use them", "Rules", "Output fields", "Examples")


def _jsonl_question(path: str, key: str, value: str | None = None) -> str:
    with (REPO_ROOT / path).open() as f:
        rows = [json.loads(line) for line in f]
    return next(r["question"] for r in rows if value is None or r[key] == value)


def _input(make_deps: MakeDeps, message: str) -> KnowledgeInput:
    decision = TriageDecision(intent=Intent.KB_INQUIRY, priority="P3", symptom_summary="s")
    return KnowledgeInput(
        triage=TriageResult(decision=decision, identity=make_deps().identity), message=message
    )


def _search(query: str) -> tuple[str, dict[str, Any]]:
    return ("search_knowledge_base", {"query": query})


def test_confident_search_surfaces_passages_snapshot_and_telemetry_flag(make_deps: MakeDeps) -> None:
    question = _jsonl_question("data/eval/questions.jsonl", "question_id", "Q10")
    model = scripted_model([_search(question)], {"needs_more_telemetry": True})
    run = run_knowledge(_input(make_deps, question), make_deps(), model)
    bundle = run.output
    assert bundle.confidence_status == KBSearchStatus.CONFIDENT
    assert bundle.retrieved_passages and bundle.snapshot_date is not None
    assert bundle.queries == (question,) and bundle.needs_more_telemetry


def test_off_domain_question_is_refused_with_candidates(make_deps: MakeDeps) -> None:
    question = _jsonl_question("data/eval/out_of_coverage.jsonl", "question_id")
    run = run_knowledge(_input(make_deps, question), make_deps(), scripted_model([_search(question)], {}))
    assert run.output.confidence_status == KBSearchStatus.LOW_CONFIDENCE_REFUSAL
    assert run.output.retrieved_passages == () and run.output.candidates != ()


def test_unavailable_search_still_serves_policy(make_deps: MakeDeps) -> None:
    with psycopg.connect(settings.database_url) as conn:
        service = RetrievalService(conn)
        conn.close()
        deps = make_deps(retrieval=service)
        model = scripted_model(
            [_search("ipsec tunnel down"), ("get_policy", {"policy_id": "POL-CREDIT"})], {}
        )
        bundle = run_knowledge(_input(make_deps, "m"), deps, model).output
    assert bundle.confidence_status == KBSearchStatus.UNAVAILABLE
    assert [p.policy_id for p in bundle.referenced_policies] == ["POL-CREDIT"]
    assert bundle.is_refusal


def test_unknown_policy_absent_and_duplicate_searches_deduped(make_deps: MakeDeps) -> None:
    question = _jsonl_question("data/eval/questions.jsonl", "question_id", "Q10")
    model = scripted_model(
        [_search(question), _search(question), ("get_policy", {"policy_id": "POL-NOPE"})], {}
    )
    bundle = run_knowledge(_input(make_deps, question), make_deps(), model).output
    ids = [p.passage_id for p in bundle.retrieved_passages]
    assert bundle.referenced_policies == ()
    assert ids and len(ids) == len(set(ids))
    assert len(bundle.queries) == 2


def test_model_failure_keeps_results_with_empty_findings(make_deps: MakeDeps) -> None:
    model = scripted_model([("get_policy", {"policy_id": "POL-SLA"})], {"uncovered_topics": 5})
    run = run_knowledge(_input(make_deps, "m"), make_deps(), model)
    assert [p.policy_id for p in run.output.referenced_policies] == ["POL-SLA"]
    assert run.output.findings.uncovered_topics == () and run.trace.error


def test_prompt_has_headings_and_no_leaks() -> None:
    prompt = load_prompt("knowledge")
    assert all(f"## {heading}" in prompt for heading in HEADINGS)
    assert "SC-" not in prompt and "expected" not in prompt.lower()
