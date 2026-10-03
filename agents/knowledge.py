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
from retrieval.models import KBSearchResult
from retrieval.service import RetrievalService

SEARCH_TOOL = "search_knowledge_base"

# One short topic phrase per telemetry tool: whatever tool ran, its knowledge-base domain is searched too.
TOOL_TOPICS: Mapping[str, str] = MappingProxyType(
    {
        "get_site_status": "site connectivity status troubleshooting",
        "get_link_quality": "link quality packet loss and SLA",
        "get_events": "connectivity events and what they mean",
        "get_bgp_status": "BGP neighbor settings and route limits",
        "get_ipsec_status": "IPsec connection recommendations and troubleshooting",
        "get_client_diagnostics": "Cato Client connection troubleshooting",
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
    """Topic phrases of the telemetry tools that returned usable data, in a stable order."""
    if diagnostics is None:
        return ()
    return tuple(TOOL_TOPICS[tool] for tool in sorted(diagnostics.usable_tools) if tool in TOOL_TOPICS)


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


def _as_trace_call(query: str, result: KBSearchResult, latency_ms: int) -> ToolCall:
    return ToolCall(
        tool_name=SEARCH_TOOL,
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
    bundle = KnowledgeBundle.from_tool_results(
        outcome.output or KnowledgeFindings(),
        (*tool_returns(messages, SEARCH_TOOL), *(result for result, _ in topic_results)),
    )
    topic_calls = [_as_trace_call(q, result, ms) for q, (result, ms) in zip(queries, topic_results, strict=True)]
    trace = outcome.trace.model_copy(update={"tool_calls": [*outcome.trace.tool_calls, *topic_calls]})
    return AgentRun(output=bundle, trace=trace)
