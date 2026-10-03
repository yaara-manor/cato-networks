from collections.abc import Iterable, Sequence
from dataclasses import replace

from pydantic_ai import Agent, ModelRetry, RunContext
from pydantic_ai.messages import ModelMessage, ModelRequest, RetryPromptPart
from pydantic_ai.models import Model

from agents.base import SupportDeps, build_agent, conversation_prompt, load_prompt
from agents.models import AgentRole, AgentRun, ResolutionInput, ResolutionPlan
from agents.runner import run_role
from guardrails import check_citations, check_outgoing_message, uncited_playbooks

HOLDING_MESSAGE = (
    "Thanks for your patience. I am passing your request to a support engineer "
    "who will follow up with you directly."
)
ESCALATION_REASON = "model failure or output validation retries exhausted"
NUDGE_PREFIX = "Retrieved playbook(s) not cited:"
NUDGE_PREFIX = "Retrieved playbook(s) not cited:"


def _retry(kinds: Iterable[str]) -> ModelRetry:
    """Fixed text from violation kind names only: never customer text or matched secrets."""
    return ModelRetry(f"customer_message violates guardrails ({', '.join(sorted(set(kinds)))}). Rewrite it.")


def _validate_citations(ctx: RunContext[SupportDeps], plan: ResolutionPlan) -> ResolutionPlan:
    if ctx.deps.grounding is None:
        raise RuntimeError("SupportDeps.grounding must be set before running Resolution")
    report = check_citations(plan.customer_message, ctx.deps.grounding)
    if not report.is_grounded:
        raise _retry(v.kind for v in report.violations)
    return plan


def _validate_outgoing(ctx: RunContext[SupportDeps], plan: ResolutionPlan) -> ResolutionPlan:
    violations = check_outgoing_message(
        plan.customer_message, ctx.deps.guard_history, ctx.deps.approved_grants
    )
    if violations:
        raise _retry(v.kind for v in violations)
    return plan


def _already_nudged(messages: Sequence[ModelMessage]) -> bool:
    return any(
        isinstance(part, RetryPromptPart) and isinstance(part.content, str) and part.content.startswith(NUDGE_PREFIX)
        for message in messages
        if isinstance(message, ModelRequest)
        for part in message.parts
    )


def _nudge_uncited_playbooks(ctx: RunContext[SupportDeps], plan: ResolutionPlan) -> ResolutionPlan:
    """One reminder, only once the reply is otherwise clean; the reply after it is accepted as written."""
    if ctx.deps.grounding is None or _already_nudged(ctx.messages):
        return plan
    if missing := uncited_playbooks(plan.customer_message, ctx.deps.grounding):
        raise ModelRetry(
            f"{NUDGE_PREFIX} {', '.join(missing)}. If one applies, cite it with a "
            "[kb:<slug>#<anchor>] marker from the knowledge passages at the point it applies; otherwise "
            "resend the message unchanged."
        )
    return plan


def build_resolution_agent(model: Model | None = None) -> Agent[SupportDeps, ResolutionPlan]:
    # three output retries: a guard violation, the playbook reminder, and a guard violation in the redraft
    agent = build_agent(load_prompt("resolution"), ResolutionPlan, model, output_retries=3)
    agent.output_validator(_validate_citations)
    agent.output_validator(_validate_outgoing)
    agent.output_validator(_nudge_uncited_playbooks)
    return agent


def _prompt(data: ResolutionInput) -> str:
    sections = [f"Triage: {data.triage.decision.model_dump_json()}"]
    sections.append(f"Known ticket: {data.known_ticket_id or 'none'}")
    if data.unsettled_approvals:
        listed = "; ".join(f"{a.action_type} status={a.status}" for a in data.unsettled_approvals)
        sections.append(f"Unsettled approvals: {listed}")
    if data.triage.sla:
        sections.append(f"SLA: {data.triage.sla.model_dump_json()}")
    if data.triage.scoping_question:
        sections.append(f"Scoping question to ask: {data.triage.scoping_question}")
    if data.diagnostics:
        sections.append(f"Diagnostics: {data.diagnostics.model_dump_json()}")
    if data.knowledge:
        sections.append(f"Knowledge: {data.knowledge.model_dump_json(exclude={'candidates'})}")
    if data.policies:
        listed = "\n\n".join(f"[policy:{p.policy_id}] {p.title}\n{p.body}" for p in data.policies)
        sections.append(f"Support policies (cite only one that governs what you state):\n{listed}")
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
    outcome = run_role(build_resolution_agent(model), _prompt(data), grounded, AgentRole.RESOLUTION)
    plan = outcome.output or _holding_plan()
    if deps.identity.account is None:
        plan = plan.model_copy(update={"actions": ()})
    return AgentRun(output=plan, trace=outcome.trace)
