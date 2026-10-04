from pydantic_ai import Agent, RunContext
from pydantic_ai.models import Model

from agents.base import SupportDeps, build_agent, conversation_prompt, identity_block, load_prompt
from agents.models import AgentRole, AgentRun, Intent, TriageDecision, TriageInput, TriageResult
from agents.runner import run_role
from core.models import Ticket
from guardrails import quarantine, redact
from services.models import CallerIdentity, RepeatContactResult, SLADeadlines


def sanitize_ticket_text(text: str) -> str:
    return quarantine(redact(text).text)


def get_ticket_history(ctx: RunContext[SupportDeps], site_id: str | None = None) -> list[Ticket]:
    """Prior tickets of the caller's account, optionally for one site. Text is redacted and quarantined."""
    account = ctx.deps.identity.account
    if account is None:
        return []
    return [
        ticket.model_copy(
            update={
                "subject": sanitize_ticket_text(ticket.subject),
                "body": sanitize_ticket_text(ticket.body),
            }
        )
        for ticket in ctx.deps.tickets.get_ticket_history(account.account_id, site_id)
    ]


def build_triage_agent(model: Model | None = None) -> Agent[SupportDeps, TriageDecision]:
    agent = build_agent(load_prompt("triage"), TriageDecision, model)
    agent.tool(get_ticket_history)
    agent.instructions(identity_block)
    return agent


def _fallback_decision(message: str) -> TriageDecision:
    return TriageDecision(intent=Intent.KB_INQUIRY, priority="P3", symptom_summary=redact(message).text)


def _sla(decision: TriageDecision, identity: CallerIdentity, deps: SupportDeps) -> SLADeadlines | None:
    if identity.account is None or identity.needs_country_clarification:
        return None
    return deps.customers.calculate_sla_deadlines(
        identity.effective_tier, decision.priority, identity.account.country, decision.product_area
    )


def _repeat_contact(
    decision: TriageDecision, identity: CallerIdentity, deps: SupportDeps
) -> RepeatContactResult | None:
    if identity.account is None:
        return None
    return deps.tickets.detect_repeat_contact(
        identity.account.account_id, decision.site_id, decision.product_area, decision.symptom_summary
    )


def run_triage(data: TriageInput, deps: SupportDeps, model: Model | None = None) -> AgentRun[TriageResult]:
    outcome = run_role(
        build_triage_agent(model), conversation_prompt(data.message, data.history), deps, AgentRole.TRIAGE
    )
    decision = outcome.output or _fallback_decision(data.message)
    result = TriageResult(
        decision=decision,
        identity=data.identity,
        sla=_sla(decision, data.identity, deps),
        repeat_contact=_repeat_contact(decision, data.identity, deps),
    )
    return AgentRun(output=result, trace=outcome.trace)
