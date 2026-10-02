from collections.abc import Sequence
from datetime import timedelta
from enum import StrEnum
from typing import Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, ValidationError

from agents.models import (
    AgentRole,
    DiagnosticEvidence,
    KnowledgeBundle,
    TraceStatus,
    TriageResult,
    UnavailableTool,
)
from core.models import AccountTier, CustomerAccount, Ticket
from retrieval.models import KBSearchStatus, RetrievedPassage
from services.models import RepeatContactResult, SLADeadlines
from storage import (
    ConversationSnapshot,
    ToolCallRecord,
    TraceReplay,
)
from tools.models import (
    LinkMetricsSummary,
    LinkQualityPayload,
    TelemetryEvidence,
    TelemetryToolResult,
)

_AT_RISK_FRACTION = 0.25
_LINK_QUALITY_TOOL = "get_link_quality"


class View(BaseModel):
    model_config = ConfigDict(frozen=True)


def latest_ok_output[T: BaseModel](
    replay: TraceReplay, role: AgentRole, model_type: type[T], turn: int | None = None
) -> T | None:
    """Newest OK trace of `role` validated as `model_type`; schema drift or no trace -> None."""
    traces = (
        step.trace
        for t in reversed(replay.turns)
        if turn is None or t.turn == turn
        for step in reversed(t.steps)
    )
    output = next(
        (t.output for t in traces if t.agent_role is role and t.status is TraceStatus.OK and t.output),
        None,
    )
    if output is None:
        return None
    try:
        return model_type.model_validate(output)
    except ValidationError:
        return None


# -- context panel -------------------------------------------------------


class SlaState(StrEnum):
    OK = "OK"
    AT_RISK = "AT_RISK"
    BREACHED = "BREACHED"
    PAUSED = "PAUSED"


class SlaCountdown(View):
    label: str
    due_at: AwareDatetime
    remaining: timedelta
    state: SlaState

    @classmethod
    def from_deadline(
        cls, label: str, started_at: AwareDatetime, due_at: AwareDatetime, now: AwareDatetime, paused: bool
    ) -> Self:
        remaining = due_at - now
        if paused:
            state = SlaState.PAUSED
        elif remaining < timedelta(0):
            state = SlaState.BREACHED
        elif remaining <= (due_at - started_at) * _AT_RISK_FRACTION:
            state = SlaState.AT_RISK
        else:
            state = SlaState.OK
        return cls(label=label, due_at=due_at, remaining=remaining, state=state)

    @classmethod
    def from_deadlines(cls, sla: SLADeadlines, now: AwareDatetime) -> tuple[Self, ...]:
        return (
            cls.from_deadline("First response", sla.started_at, sla.first_response_due, now, False),
            cls.from_deadline("Resolution", sla.started_at, sla.resolution_due, now, sla.resolution_paused),
        )


class RepeatAlert(View):
    reason: str | None
    matching_ticket_ids: tuple[str, ...]
    prior_closed_ids: tuple[str, ...]

    @classmethod
    def from_result(cls, result: RepeatContactResult) -> Self | None:
        if not result.is_repeat_contact:
            return None
        return cls(
            reason=result.reason,
            matching_ticket_ids=tuple(t.ticket_id for t in result.matching_tickets),
            prior_closed_ids=tuple(t.ticket_id for t in result.prior_closed_tickets),
        )


class TicketRow(View):
    ticket_id: str
    subject: str
    status: str
    priority: str

    @classmethod
    def from_ticket(cls, ticket: Ticket) -> Self:
        return cls(
            ticket_id=ticket.ticket_id, subject=ticket.subject, status=ticket.status, priority=ticket.priority
        )


class ContextPanel(View):
    account_id: str | None
    company: str | None
    tier: AccountTier
    contact_email: str | None
    triaged: bool  # False: SLA and repeat-contact are unknown, not "all clear"
    sla: tuple[SlaCountdown, ...]
    repeat_contact: RepeatAlert | None
    open_tickets: tuple[TicketRow, ...]

    @classmethod
    def from_rows(
        cls,
        snapshot: ConversationSnapshot,
        replay: TraceReplay,
        account: CustomerAccount | None,
        tickets: Sequence[Ticket],
        now: AwareDatetime,
    ) -> Self:
        conversation = snapshot.conversation
        triage = latest_ok_output(replay, AgentRole.TRIAGE, TriageResult)
        sla = triage.sla if triage else None
        repeat = triage.repeat_contact if triage else None
        return cls(
            account_id=conversation.account_id,
            company=account.company if account else None,
            tier=conversation.customer_tier,
            contact_email=conversation.contact_email,
            triaged=triage is not None,
            sla=SlaCountdown.from_deadlines(sla, now) if sla else (),
            repeat_contact=RepeatAlert.from_result(repeat) if repeat else None,
            open_tickets=tuple(TicketRow.from_ticket(t) for t in tickets if t.status != "closed"),
        )


# -- evidence panel ------------------------------------------------------


class LinkChart(View):
    site_id: str
    window: str
    links: tuple[LinkMetricsSummary, ...]

    @classmethod
    def from_call(cls, call: ToolCallRecord) -> Self | None:
        if call.tool_name != _LINK_QUALITY_TOOL:
            return None
        try:
            result = TelemetryToolResult[LinkQualityPayload].model_validate(call.result)
        except ValidationError:
            return None
        if result.data is None:
            return None
        return cls(site_id=result.data.site_id, window=result.data.window, links=tuple(result.data.links))


class PassageScore(View):
    citation_tag: str
    title: str
    rrf_score: float
    rerank_score: float
    lex_rank: int | None
    vec_rank: int | None
    cited: bool  # False: retrieved as a candidate only

    @classmethod
    def from_passage(cls, passage: RetrievedPassage, cited: bool) -> Self:
        return cls(
            citation_tag=passage.citation_tag(),
            title=passage.title,
            rrf_score=passage.rrf_score,
            rerank_score=passage.rerank_score,
            lex_rank=passage.lex_rank,
            vec_rank=passage.vec_rank,
            cited=cited,
        )

    @classmethod
    def from_bundle(cls, bundle: KnowledgeBundle) -> tuple[Self, ...]:
        cited_ids = {p.passage_id for p in bundle.retrieved_passages}
        candidates = (p for p in bundle.candidates if p.passage_id not in cited_ids)
        return tuple(cls.from_passage(p, True) for p in bundle.retrieved_passages) + tuple(
            cls.from_passage(p, False) for p in candidates
        )


class EvidencePanel(View):
    evidence: tuple[TelemetryEvidence, ...]
    unavailable_tools: tuple[UnavailableTool, ...]
    link_charts: tuple[LinkChart, ...]
    raw_calls: tuple[ToolCallRecord, ...]
    kb_passages: tuple[PassageScore, ...]
    kb_status: KBSearchStatus | None  # None: no knowledge stage ran

    @classmethod
    def from_rows(cls, replay: TraceReplay) -> Self:
        """Panels read the newest trace of each role; raw calls come from the newest turn."""
        diagnostics = latest_ok_output(replay, AgentRole.DIAGNOSTICS, DiagnosticEvidence)
        knowledge = latest_ok_output(replay, AgentRole.KNOWLEDGE, KnowledgeBundle)
        calls = tuple(c for t in replay.turns[-1:] for s in t.steps for c in s.tool_calls)
        return cls(
            evidence=diagnostics.evidence_items if diagnostics else (),
            unavailable_tools=diagnostics.unavailable_tools if diagnostics else (),
            link_charts=tuple(chart for c in calls if (chart := LinkChart.from_call(c))),
            raw_calls=calls,
            kb_passages=PassageScore.from_bundle(knowledge) if knowledge else (),
            kb_status=knowledge.confidence_status if knowledge else None,
        )
