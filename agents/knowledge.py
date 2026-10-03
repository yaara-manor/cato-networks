import time
from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from types import MappingProxyType

from pydantic_core import to_jsonable_python
from pydantic_ai import Agent, RunContext
from pydantic_ai.models import Model

from agents.base import SupportDeps, build_agent, load_prompt
from agents.messages import tool_returns
from agents.models import (
    AgentRole,
    AgentRun,
    DiagnosticEvidence,
    KnowledgeBundle,
    KnowledgeFindings,
    KnowledgeInput,
    ToolCall,
)
from agents.runner import run_role
from retrieval.models import KBSearchResult, KBSearchStatus, RetrievedPassage
from retrieval.service import RetrievalService

SEARCH_TOOL = "search_knowledge_base"
EXPAND_TOOL = "expand_article_sections"
EXPANDED_ARTICLES = 2  # the best-scoring articles get their surrounding sections added

# Short topic queries per telemetry tool: whatever tool ran, its knowledge-base domain is searched too.
# "playbook" reaches the XOps playbooks, which are titled that way. BGP and IPsec also keep a plain query,
# because their reference articles (neighbor settings, recommendations) are not playbooks.
TOOL_QUERIES: Mapping[str, tuple[str, ...]] = MappingProxyType(
    {
        "get_site_status": ("site connectivity status troubleshooting playbook",),
        "get_link_quality": ("link quality packet loss and SLA playbook",),
        "get_events": ("connectivity events and what they mean",),
        "get_bgp_status": (
            "BGP neighbor settings and route limits",
            "BGP neighbor settings and route limits playbook",
        ),
        "get_ipsec_status": (
            "IPsec connection recommendations and troubleshooting",
            "IPsec connection recommendations and troubleshooting playbook",
        ),
        "get_client_diagnostics": ("Cato Client connection troubleshooting",),
    }
)


def search_knowledge_base(ctx: RunContext[SupportDeps], query: str) -> KBSearchResult:
    """Search the product knowledge base. Returns passages with ids, or a refusal/unavailable status."""
    return ctx.deps.retrieval.search_kb(query)


def build_knowledge_agent(model: Model | None = None) -> Agent[SupportDeps, KnowledgeFindings]:
    agent = build_agent(load_prompt("knowledge"), KnowledgeFindings, model)
    agent.tool(search_knowledge_base)
    return agent


def topic_queries(diagnostics: DiagnosticEvidence | None) -> tuple[str, ...]:
    """Queries for the telemetry tools that returned usable data, in a stable order."""
    if diagnostics is None:
        return ()
    return tuple(
        query for tool in sorted(diagnostics.usable_tools) for query in TOOL_QUERIES.get(tool, ())
    )


def _timed_search(retrieval: RetrievalService, query: str) -> tuple[KBSearchResult, int]:
    started = time.perf_counter()
    result = retrieval.search_kb(query)
    return result, int((time.perf_counter() - started) * 1000)


def search_topics(retrieval: RetrievalService, queries: Sequence[str]) -> tuple[tuple[KBSearchResult, int], ...]:
    """All queries concurrently; results in query order."""
    if not queries:
        return ()
    with ThreadPoolExecutor(max_workers=len(queries)) as pool:
        return tuple(pool.map(lambda query: _timed_search(retrieval, query), queries))


def expand_top_articles(retrieval: RetrievalService, searches: Sequence[KBSearchResult]) -> KBSearchResult | None:
    """Sections around the best passage of each of the top articles, so steps that follow a hit are not lost.

    A passage that matched on an overview would otherwise leave out the steps below it.
    """
    passages = [p for search in searches for p in search.passages]
    best: dict[str, RetrievedPassage] = {}
    for passage in sorted(passages, key=lambda p: p.rerank_score, reverse=True):
        best.setdefault(passage.slug, passage)
    have = {p.passage_id for p in passages}
    added: dict[str, RetrievedPassage] = {}
    for passage in list(best.values())[:EXPANDED_ARTICLES]:
        for section in retrieval.adjacent_sections(passage):
            if section.passage_id not in have:
                added.setdefault(section.passage_id, section)
    if not added:
        return None
    sections = list(added.values())
    slugs = ", ".join(dict.fromkeys(p.slug for p in sections))
    snapshot = next((s.snapshot_date for s in searches if s.snapshot_date), None)
    return KBSearchResult(
        status=KBSearchStatus.CONFIDENT,
        query=f"sections around hits: {slugs}",
        passages=sections,
        candidates=sections,
        snapshot_date=snapshot,
    )


def _as_trace_call(tool_name: str, query: str, result: KBSearchResult, latency_ms: int) -> ToolCall:
    return ToolCall(
        tool_name=tool_name,
        arguments={"query": query},
        status=str(result.status),
        result=to_jsonable_python(result),
        latency_ms=latency_ms,
    )


def _prompt(data: KnowledgeInput) -> str:
    decision = data.triage.decision
    lines = [f"Triage: intent {decision.intent}, symptom: {decision.symptom_summary}"]
    if data.diagnostics:
        findings = data.diagnostics.findings
        lines.append(f"Diagnostics hypothesis: {findings.root_cause_hypothesis}")
        lines.append(f"kb_query_hints: {list(findings.kb_query_hints)}")
    lines.append(f"Customer message:\n{data.message}")
    return "\n".join(lines)


def run_knowledge(
    data: KnowledgeInput, deps: SupportDeps, model: Model | None = None
) -> AgentRun[KnowledgeBundle]:
    outcome = run_role(build_knowledge_agent(model), _prompt(data), deps, AgentRole.KNOWLEDGE)
    messages = list(outcome.messages)
    queries = topic_queries(data.diagnostics)
    topic_results = search_topics(deps.retrieval, queries)
    searches = (*tool_returns(messages, SEARCH_TOOL), *(result for result, _ in topic_results))
    started = time.perf_counter()
    expansion = expand_top_articles(deps.retrieval, searches)
    expand_ms = int((time.perf_counter() - started) * 1000)
    bundle = KnowledgeBundle.from_tool_results(outcome.output or KnowledgeFindings(), searches, expansion)
    calls = [
        _as_trace_call(SEARCH_TOOL, q, result, ms) for q, (result, ms) in zip(queries, topic_results, strict=True)
    ]
    if expansion:
        calls.append(_as_trace_call(EXPAND_TOOL, expansion.query, expansion, expand_ms))
    trace = outcome.trace.model_copy(update={"tool_calls": [*outcome.trace.tool_calls, *calls]})
    return AgentRun(output=bundle, trace=trace)
