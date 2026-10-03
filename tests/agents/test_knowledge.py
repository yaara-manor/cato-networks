import json
from typing import Any

import psycopg

from agents.knowledge import TOOL_TOPICS, run_knowledge, topic_queries
from agents.models import DiagnosticEvidence, DiagnosticsFindings, Intent, KnowledgeInput, TriageDecision, TriageResult
from core.config import REPO_ROOT, settings
from retrieval.models import KBSearchStatus
from retrieval.service import RetrievalService
from tests.agents.conftest import MakeDeps, scripted_model


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


def test_unavailable_search_reports_unavailable(make_deps: MakeDeps) -> None:
    with psycopg.connect(settings.database_url) as conn:
        service = RetrievalService(conn)
        conn.close()
        deps = make_deps(retrieval=service)
        bundle = run_knowledge(_input(make_deps, "m"), deps, scripted_model([_search("ipsec tunnel down")], {})).output
    assert bundle.confidence_status == KBSearchStatus.UNAVAILABLE
    assert bundle.is_refusal


def test_duplicate_searches_deduped(make_deps: MakeDeps) -> None:
    question = _jsonl_question("data/eval/questions.jsonl", "question_id", "Q10")
    model = scripted_model([_search(question), _search(question)], {})
    bundle = run_knowledge(_input(make_deps, question), make_deps(), model).output
    ids = [p.passage_id for p in bundle.retrieved_passages]
    assert ids and len(ids) == len(set(ids))
    assert len(bundle.queries) == 2


def test_model_failure_keeps_results_with_empty_findings(make_deps: MakeDeps) -> None:
    model = scripted_model([_search("ipsec tunnel down")], {"uncovered_topics": 5})
    run = run_knowledge(_input(make_deps, "m"), make_deps(), model)
    assert run.output.retrieved_passages or run.output.candidates
    assert run.output.findings.uncovered_topics == () and run.trace.error



def test_topic_queries_cover_usable_telemetry_tools_only() -> None:
    evidence = DiagnosticEvidence(
        findings=DiagnosticsFindings(),
        inspected_tools=("get_bgp_status", "list_sites", "get_events"),
        unavailable_tools=(),
    )
    bgp, events = TOOL_TOPICS["get_bgp_status"], TOOL_TOPICS["get_events"]
    assert topic_queries(evidence) == (bgp, f"{bgp} playbook", events, f"{events} playbook")
    assert topic_queries(None) == ()


def test_topic_searches_join_the_bundle_and_the_trace(make_deps: MakeDeps) -> None:
    evidence = DiagnosticEvidence(findings=DiagnosticsFindings(), inspected_tools=("get_bgp_status",))
    data = _input(make_deps, "BGP session flaps").model_copy(update={"diagnostics": evidence})
    run = run_knowledge(data, make_deps(), scripted_model([], {}))
    topic = TOOL_TOPICS["get_bgp_status"]
    assert run.output.queries == (topic, f"{topic} playbook")
    searches = [c for c in run.trace.tool_calls if c.tool_name == "search_knowledge_base"]
    assert [c.arguments for c in searches] == [{"query": query} for query in run.output.queries]
    assert run.output.confidence_status == KBSearchStatus.CONFIDENT


def test_best_articles_get_their_surrounding_sections(make_deps: MakeDeps) -> None:
    question = "Socket does not come back after scheduled upgrade what to do"
    run = run_knowledge(_input(make_deps, question), make_deps(), scripted_model([_search(question)], {}))
    anchors = {(p.slug, p.heading_anchor) for p in run.output.retrieved_passages}
    assert any(slug == "xops-network-playbook-socket-offline-after-upgrade" and a.startswith("step-3") for slug, a in anchors)
    assert run.trace.tool_calls[-1].tool_name == "expand_article_sections"
