from collections import Counter
from collections.abc import Iterable, Sequence
from decimal import Decimal
from enum import StrEnum
from typing import Any, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict
from pydantic_ai.messages import ModelMessage
from pydantic_ai.usage import RunUsage

from agents.messages import tool_call_dicts
from core.models import TicketPriority
from guardrails import ActionType, GroundingContext, ProposedAction
from retrieval.models import KBSearchResult, KBSearchStatus, PolicyDocument, RetrievedPassage
from services.models import CallerIdentity, RepeatContactResult, SLADeadlines
from tools.models import (
    SiteListPayload,
    SiteRecord,
    TelemetryEvidence,
    TelemetryStatus,
    TelemetryToolResult,
)


class TraceStatus(StrEnum):
    OK = "OK"
    ERROR = "ERROR"
    RETRIED = "RETRIED"


class ToolCall(BaseModel):
    model_config = ConfigDict(frozen=True)

    tool_name: str
    arguments: dict[str, Any]
    status: str
    result: dict[str, Any]
    latency_ms: int


class AgentTrace(BaseModel):
    agent_role: str
    tool_calls: list[ToolCall]
    latency_ms: int
    prompt_tokens: int
    completion_tokens: int
    input: dict[str, Any] = {}
    output: dict[str, Any] | None = None
    model_messages: list[dict[str, Any]] | None = None
    status: TraceStatus = TraceStatus.OK
    error: str | None = None
    cost_usd: Decimal | None = None

    @classmethod
    def from_run(
        cls,
        role: str,
        messages: list[ModelMessage],
        usage: RunUsage,
        latency_ms: int,
        error: str | None = None,
    ) -> Self:
        """`cost_usd` is PydanticAI's own genai_prices estimate; None for unknown models."""
        return cls(
            agent_role=role,
            tool_calls=[ToolCall(**call) for call in tool_call_dicts(messages)],
            latency_ms=latency_ms,
            prompt_tokens=usage.input_tokens,
            completion_tokens=usage.output_tokens,
            cost_usd=usage.cost,
            status=TraceStatus.OK if error is None else TraceStatus.ERROR,
            error=error,
        )


class _AgentModel(BaseModel):
    model_config = ConfigDict(frozen=True)


class TurnSender(StrEnum):
    CUSTOMER = "CUSTOMER"
    AGENT = "AGENT"
    REVIEWER = "REVIEWER"


class ConversationTurn(_AgentModel):
    sender: TurnSender
    content: str


class AgentRun[T](_AgentModel):
    output: T
    trace: AgentTrace


# Triage


class Intent(StrEnum):
    TELEMETRY_DIAGNOSIS = "TELEMETRY_DIAGNOSIS"
    KB_INQUIRY = "KB_INQUIRY"
    POLICY_REQUEST = "POLICY_REQUEST"
    ADVERSARIAL = "ADVERSARIAL"


class TriageInput(_AgentModel):
    message: str
    identity: CallerIdentity
    history: tuple[ConversationTurn, ...] = ()


class TriageDecision(_AgentModel):
    intent: Intent
    priority: TicketPriority
    site_id: str | None = None
    product_area: str | None = None
    symptom_summary: str
    scoping_question: str | None = None


class TriageResult(_AgentModel):
    decision: TriageDecision
    identity: CallerIdentity
    sla: SLADeadlines | None = None
    repeat_contact: RepeatContactResult | None = None

    @property
    def scoping_question(self) -> str | None:
        return self.identity.scoping_question or self.decision.scoping_question


# Diagnostics


class DiagnosticsInput(_AgentModel):
    triage: TriageResult
    message: str
    history: tuple[ConversationTurn, ...] = ()


class DiagnosticsFindings(_AgentModel):
    root_cause_hypothesis: str | None = None
    needs_customer_input: str | None = None
    kb_query_hints: tuple[str, ...] = ()


class UnavailableTool(_AgentModel):
    tool_name: str
    status: TelemetryStatus
    error: str | None = None


def _sev1_corroborated(ok_results: Sequence[TelemetryToolResult[Any]]) -> bool:
    """Two+ sites disconnected in one country, or a whole listed account disconnected."""
    payloads = [r.data for r in ok_results]
    sites = {s.site_id: s for p in payloads for s in _sites_of(p)}
    countries = Counter(s.country for s in sites.values() if s.status == "disconnected")
    listed = [p.sites for p in payloads if isinstance(p, SiteListPayload)]
    return any(n >= 2 for n in countries.values()) or any(
        all(s.status == "disconnected" for s in group) for group in listed if group
    )


def _sites_of(payload: object) -> list[SiteRecord]:
    if isinstance(payload, SiteListPayload):
        return payload.sites
    return [payload] if isinstance(payload, SiteRecord) else []


class DiagnosticEvidence(_AgentModel):
    findings: DiagnosticsFindings
    inspected_tools: tuple[str, ...] = ()
    evidence_items: tuple[TelemetryEvidence, ...] = ()
    unavailable_tools: tuple[UnavailableTool, ...] = ()
    sev1_corroborated: bool = False

    @classmethod
    def from_tool_results(
        cls, findings: DiagnosticsFindings, results: Sequence[TelemetryToolResult[Any]]
    ) -> Self:
        ok = [r for r in results if r.status == TelemetryStatus.OK]
        return cls(
            findings=findings,
            inspected_tools=tuple(dict.fromkeys(r.tool_name for r in results)),
            evidence_items=tuple(item for r in ok for item in r.evidence),
            unavailable_tools=tuple(
                UnavailableTool(tool_name=r.tool_name, status=r.status, error=r.error)
                for r in results
                if r.status != TelemetryStatus.OK
            ),
            sev1_corroborated=_sev1_corroborated(ok),
        )

    @property
    def has_anomaly(self) -> bool:
        return any(item.is_anomaly for item in self.evidence_items)

    @property
    def usable_tools(self) -> frozenset[str]:
        failed = {tool.tool_name for tool in self.unavailable_tools}
        return frozenset(self.inspected_tools) - failed


# Knowledge


class KnowledgeInput(_AgentModel):
    triage: TriageResult
    diagnostics: DiagnosticEvidence | None = None
    message: str


class KnowledgeFindings(_AgentModel):
    uncovered_topics: tuple[str, ...] = ()
    needs_more_telemetry: bool = False


def _dedupe_passages(passages: Iterable[RetrievedPassage]) -> tuple[RetrievedPassage, ...]:
    """One copy per passage_id (highest rerank_score), best first."""
    best: dict[str, RetrievedPassage] = {}
    for p in passages:
        if p.passage_id not in best or p.rerank_score > best[p.passage_id].rerank_score:
            best[p.passage_id] = p
    return tuple(sorted(best.values(), key=lambda p: p.rerank_score, reverse=True))


class KnowledgeBundle(_AgentModel):
    findings: KnowledgeFindings
    retrieved_passages: tuple[RetrievedPassage, ...] = ()
    candidates: tuple[RetrievedPassage, ...] = ()
    referenced_policies: tuple[PolicyDocument, ...] = ()
    confidence_status: KBSearchStatus
    snapshot_date: AwareDatetime | None = None
    queries: tuple[str, ...] = ()
    needs_more_telemetry: bool = False

    @classmethod
    def from_tool_results(
        cls,
        findings: KnowledgeFindings,
        searches: Sequence[KBSearchResult],
        policies: Sequence[PolicyDocument],
    ) -> Self:
        statuses = {r.status for r in searches}
        if KBSearchStatus.CONFIDENT in statuses:
            status = KBSearchStatus.CONFIDENT
        elif KBSearchStatus.UNAVAILABLE in statuses:
            status = KBSearchStatus.UNAVAILABLE
        else:
            status = KBSearchStatus.LOW_CONFIDENCE_REFUSAL
        return cls(
            findings=findings,
            retrieved_passages=_dedupe_passages(p for r in searches for p in r.passages),
            candidates=_dedupe_passages(p for r in searches for p in r.candidates),
            referenced_policies=tuple({p.policy_id: p for p in policies}.values()),
            confidence_status=status,
            snapshot_date=next((r.snapshot_date for r in searches if r.snapshot_date), None),
            queries=tuple(r.query for r in searches),
            needs_more_telemetry=findings.needs_more_telemetry,
        )

    @property
    def is_refusal(self) -> bool:
        return self.confidence_status != KBSearchStatus.CONFIDENT


# Resolution


class SupportActionKind(StrEnum):
    CREATE_TICKET = "CREATE_TICKET"
    UPDATE_TICKET = "UPDATE_TICKET"
    PAGE_ON_CALL = "PAGE_ON_CALL"
    CLOSE_TICKET = "CLOSE_TICKET"
    CREDIT = "CREDIT"
    MFA_RESET = "MFA_RESET"
    VERDICT_OVERRIDE = "VERDICT_OVERRIDE"


# Kinds absent here are ungated. PAGE_ON_CALL joins when plan 22/04 adds ActionType.PAGE_ON_CALL.
_GATED_ACTION_TYPES: dict[SupportActionKind, ActionType] = {
    SupportActionKind.CLOSE_TICKET: ActionType.CLOSE_TICKET,
    SupportActionKind.CREDIT: ActionType.CREDIT,
    SupportActionKind.MFA_RESET: ActionType.MFA_RESET,
    SupportActionKind.VERDICT_OVERRIDE: ActionType.VERDICT_OVERRIDE,
}


class SupportAction(_AgentModel):
    kind: SupportActionKind
    payload: dict[str, str] = {}
    reason: str

    def to_proposed_action(self, target_account_id: str) -> ProposedAction | None:
        action_type = _GATED_ACTION_TYPES.get(self.kind)
        if action_type is None:
            return None
        return ProposedAction(
            action_type=action_type, target_account_id=target_account_id, payload=self.payload
        )


class ResolutionPlan(_AgentModel):
    customer_message: str
    actions: tuple[SupportAction, ...] = ()
    escalate_to_human: bool = False
    escalation_reason: str | None = None


class ResolutionInput(_AgentModel):
    triage: TriageResult
    diagnostics: DiagnosticEvidence | None = None
    knowledge: KnowledgeBundle | None = None
    history: tuple[ConversationTurn, ...] = ()
    message: str

    def grounding_context(self) -> GroundingContext:
        """Built from successful tool results only; absent stages contribute nothing."""
        knowledge, diagnostics = self.knowledge, self.diagnostics
        return GroundingContext(
            kb_refs=frozenset(
                (p.slug, p.heading_anchor) for p in (knowledge.retrieved_passages if knowledge else ())
            ),
            policy_ids=frozenset(
                p.policy_id for p in (knowledge.referenced_policies if knowledge else ())
            ),
            telemetry_tools=diagnostics.usable_tools if diagnostics else frozenset(),
            is_refusal=knowledge.is_refusal if knowledge else False,
        )
