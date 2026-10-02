from collections.abc import Callable
from typing import Any

from pydantic_ai import Agent, RunContext
from pydantic_ai.models import Model

from agents.base import SupportDeps, build_agent, conversation_prompt, load_prompt
from agents.messages import tool_returns
from agents.models import AgentRole, AgentRun, DiagnosticEvidence, DiagnosticsFindings, DiagnosticsInput
from agents.runner import run_role
from tools.models import TelemetryStatus, TelemetryToolResult

type Telemetry = TelemetryToolResult[Any]


def _refusal(tool_name: str) -> Telemetry:
    return TelemetryToolResult(
        tool_name=tool_name, status=TelemetryStatus.INVALID_ARGUMENT, error="site not in caller account"
    )


def _caller_account_id(ctx: RunContext[SupportDeps]) -> str | None:
    identity = ctx.deps.identity
    if identity.account is None or not identity.is_verified_account_member:
        return None
    return identity.account.account_id


def _guarded_site(
    ctx: RunContext[SupportDeps], tool_name: str, site_id: str, call: Callable[[], Telemetry]
) -> Telemetry:
    """Ownership guard for every site-scoped tool: the site must be listed under the caller's account."""
    account_id = _caller_account_id(ctx)
    if account_id is None:
        return _refusal(tool_name)
    listed = ctx.deps.telemetry.list_sites(account_id).data
    if listed is None or site_id not in {site.site_id for site in listed.sites}:
        return _refusal(tool_name)
    return call()


def list_sites(ctx: RunContext[SupportDeps]) -> Telemetry:
    """All sites of the caller's account with status and last_seen."""
    account_id = _caller_account_id(ctx)
    return ctx.deps.telemetry.list_sites(account_id) if account_id else _refusal("list_sites")


def get_site_status(ctx: RunContext[SupportDeps], site_id: str) -> Telemetry:
    """Current status of one site."""
    return _guarded_site(ctx, "get_site_status", site_id, lambda: ctx.deps.telemetry.get_site_status(site_id))


def get_link_quality(ctx: RunContext[SupportDeps], site_id: str, window: str = "24h") -> Telemetry:
    """Packet loss, latency, jitter per WAN link. window: '1h', '6h', '12h', '24h', '7d' or 'all'."""
    return _guarded_site(
        ctx, "get_link_quality", site_id, lambda: ctx.deps.telemetry.get_link_quality(site_id, window)
    )


def get_events(
    ctx: RunContext[SupportDeps], site_id: str, event_type: str | None = None, window: str = "24h"
) -> Telemetry:
    """Site events, optionally filtered by event_type. window: '1h', '6h', '12h', '24h', '7d' or 'all'."""
    return _guarded_site(
        ctx, "get_events", site_id, lambda: ctx.deps.telemetry.get_events(site_id, event_type, window)
    )


def get_bgp_status(ctx: RunContext[SupportDeps], site_id: str) -> Telemetry:
    """BGP neighbors of one site: state, routes vs limit, last error, flaps."""
    return _guarded_site(ctx, "get_bgp_status", site_id, lambda: ctx.deps.telemetry.get_bgp_status(site_id))


def get_ipsec_status(ctx: RunContext[SupportDeps], site_id: str) -> Telemetry:
    """IPsec tunnel state, last error and negotiated parameters of one site."""
    return _guarded_site(
        ctx, "get_ipsec_status", site_id, lambda: ctx.deps.telemetry.get_ipsec_status(site_id)
    )


def get_client_diagnostics(ctx: RunContext[SupportDeps], user_email: str) -> Telemetry:
    """Remote-access client diagnostics of one user of the caller's account."""
    account_id = _caller_account_id(ctx)
    if account_id is None:
        return _refusal("get_client_diagnostics")
    result = ctx.deps.telemetry.get_client_diagnostics(user_email)
    # Ownership is only knowable from the payload, so a NOT_FOUND must read like a foreign user
    # (no probing which emails exist); UNAVAILABLE stays visible as a real outage.
    if result.status is TelemetryStatus.NOT_FOUND:
        return _refusal("get_client_diagnostics")
    if result.data is not None and result.data.customer_id != account_id:
        return _refusal("get_client_diagnostics")
    return result


_TOOLS: tuple[Callable[..., Telemetry], ...] = (
    list_sites,
    get_site_status,
    get_link_quality,
    get_events,
    get_bgp_status,
    get_ipsec_status,
    get_client_diagnostics,
)


def build_diagnostics_agent(model: Model | None = None) -> Agent[SupportDeps, DiagnosticsFindings]:
    agent = build_agent(load_prompt("diagnostics"), DiagnosticsFindings, model)
    for tool in _TOOLS:
        agent.tool(tool)
    return agent


def _prompt(data: DiagnosticsInput) -> str:
    decision = data.triage.decision
    return (
        f"Triage: intent {decision.intent}, priority {decision.priority}, site {decision.site_id}, "
        f"product area {decision.product_area}, symptom: {decision.symptom_summary}\n\n"
        f"{conversation_prompt(data.message, data.history)}"
    )


def run_diagnostics(
    data: DiagnosticsInput, deps: SupportDeps, model: Model | None = None
) -> AgentRun[DiagnosticEvidence]:
    outcome = run_role(build_diagnostics_agent(model), _prompt(data), deps, AgentRole.DIAGNOSTICS)
    results = tool_returns(list(outcome.messages), *(tool.__name__ for tool in _TOOLS))
    evidence = DiagnosticEvidence.from_tool_results(outcome.output or DiagnosticsFindings(), results)
    if not evidence.inspected_tools:
        findings = evidence.findings.model_copy(update={"root_cause_hypothesis": None})
        evidence = evidence.model_copy(update={"findings": findings})
    return AgentRun(output=evidence, trace=outcome.trace)
