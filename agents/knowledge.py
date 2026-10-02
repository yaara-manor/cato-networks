from pydantic_ai import Agent, RunContext
from pydantic_ai.models import Model

from agents.base import SupportDeps, build_agent, load_prompt
from agents.messages import tool_returns
from agents.models import AgentRole, AgentRun, KnowledgeBundle, KnowledgeFindings, KnowledgeInput
from agents.runner import run_role
from retrieval.models import KBSearchResult, PolicyDocument


def search_knowledge_base(ctx: RunContext[SupportDeps], query: str) -> KBSearchResult:
    """Search the product knowledge base. Returns passages with ids, or a refusal/unavailable status."""
    return ctx.deps.retrieval.search_kb(query)


def get_policy(ctx: RunContext[SupportDeps], policy_id: str) -> PolicyDocument | None:
    """Full text of one support policy, e.g. POL-CREDIT. None when the id is unknown."""
    return ctx.deps.retrieval.get_policy(policy_id)


def build_knowledge_agent(model: Model | None = None) -> Agent[SupportDeps, KnowledgeFindings]:
    agent = build_agent(load_prompt("knowledge"), KnowledgeFindings, model)
    agent.tool(search_knowledge_base)
    agent.tool(get_policy)
    return agent


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
    bundle = KnowledgeBundle.from_tool_results(
        outcome.output or KnowledgeFindings(),
        tool_returns(messages, "search_knowledge_base"),
        [p for p in tool_returns(messages, "get_policy") if p is not None],
    )
    return AgentRun(output=bundle, trace=outcome.trace)
