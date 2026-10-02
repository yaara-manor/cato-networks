from collections.abc import Iterable
from dataclasses import replace

from pydantic_ai import Agent, ModelRetry, RunContext
from pydantic_ai.models import Model

from agents.base import SupportDeps, build_agent, conversation_prompt, load_prompt
from agents.models import AgentRun, ResolutionInput, ResolutionPlan
from agents.runner import run_role
from guardrails import check_citations, check_outgoing_message

HOLDING_MESSAGE = (
    "Thanks for your patience. I am passing your request to a support engineer "
    "who will follow up with you directly."
)
ESCALATION_REASON = "model failure or output validation retries exhausted"


def _retry(kinds: Iterable[str]) -> ModelRetry:
    """Fixed text from violation kind names only: never customer text or matched secrets."""
    return ModelRetry(f"customer_message violates guardrails ({', '.join(sorted(set(kinds)))}). Rewrite it.")


def validate_citations(ctx: RunContext[SupportDeps], plan: ResolutionPlan) -> ResolutionPlan:
    if ctx.deps.grounding is None:
        raise RuntimeError("SupportDeps.grounding must be set before running Resolution")
    report = check_citations(plan.customer_message, ctx.deps.grounding)
    if not report.is_grounded:
        raise _retry(v.kind for v in report.violations)
    return plan


def validate_outgoing(ctx: RunContext[SupportDeps], plan: ResolutionPlan) -> ResolutionPlan:
    violations = check_outgoing_message(
        plan.customer_message, ctx.deps.guard_history, ctx.deps.approved_actions
    )
    if violations:
        raise _retry(v.kind for v in violations)
    return plan


def build_resolution_agent(model: Model | None = None) -> Agent[SupportDeps, ResolutionPlan]:
    agent = build_agent(load_prompt("resolution"), ResolutionPlan, model)
    agent.output_validator(validate_citations)
    agent.output_validator(validate_outgoing)
    return agent


def _prompt(data: ResolutionInput) -> str:
    sections = [f"Triage: {data.triage.decision.model_dump_json()}"]
    if data.triage.sla:
        sections.append(f"SLA: {data.triage.sla.model_dump_json()}")
    if data.triage.scoping_question:
        sections.append(f"Scoping question to ask: {data.triage.scoping_question}")
    if data.diagnostics:
        sections.append(f"Diagnostics: {data.diagnostics.model_dump_json()}")
    if data.knowledge:
        sections.append(f"Knowledge: {data.knowledge.model_dump_json(exclude={'candidates'})}")
    sections.append(conversation_prompt(data.message, data.history))
    return "\n\n".join(sections)


def _holding_plan() -> ResolutionPlan:
    return ResolutionPlan(
        customer_message=HOLDING_MESSAGE, escalate_to_human=True, escalation_reason=ESCALATION_REASON
    )


def run_resolution(
    data: ResolutionInput, deps: SupportDeps, model: Model | None = None
) -> AgentRun[ResolutionPlan]:
    grounded = replace(deps, grounding=data.grounding_context())
    outcome = run_role(build_resolution_agent(model), _prompt(data), grounded, "resolution")
    plan = outcome.output or _holding_plan()
    if deps.identity.account is None:
        plan = plan.model_copy(update={"actions": ()})
    return AgentRun(output=plan, trace=outcome.trace)
