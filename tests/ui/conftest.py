# ruff: noqa: F811  (storage fixtures are re-imported, then requested by name)
from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from pydantic import BaseModel

from agents.models import (
    AgentRole,
    DiagnosticEvidence,
    DiagnosticsFindings,
    Intent,
    KnowledgeBundle,
    KnowledgeFindings,
    ToolCall,
    TraceStatus,
    TriageDecision,
    TriageResult,
    UnavailableTool,
)
from core.models import CustomerAccount, Ticket
from guardrails.models import ActionType
from retrieval.models import KBSearchResult, KBSearchStatus, RetrievedPassage
from services.models import CallerIdentity, RepeatContactResult, SLADeadlines
from storage import StateStore, ToolCallRecord, TraceRecord
from tests.storage.conftest import (  # noqa: F401  (fixtures reused by this package)
    conn,
    created_ids,
    make_trace,
    new_conversation,
    store,
)
from tools.models import (
    LinkMetricsSummary,
    LinkQualityPayload,
    TelemetryEvidence,
    TelemetryStatus,
    TelemetryToolResult,
)
from ui.reviewer_view import CaseView

NOW = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)
ACCOUNT = CustomerAccount(
    account_id="ACC-1002",
    company="Bluebird Retail",
    tier="Premium",
    email_domain="bluebirdretail.com",
    registered_admin_contact="admin@bluebirdretail.com",
)
CREDIT = {"amount": "50", "reason": "SLA breach"}

MakeTrace = Callable[..., TraceRecord]
SeedCase = Callable[[], UUID]


def make_ticket(ticket_id: str, status: str) -> Ticket:
    return Ticket.model_validate(
        {
            "ticket_id": ticket_id,
            "created_at": NOW,
            "channel": "email",
            "customer_id": "ACC-1002",
            "customer_name": "Priya",
            "requester_email": "priya@bluebirdretail.com",
            "company": "Bluebird Retail",
            "tier": "Premium",
            "site_id": None,
            "product_area": "Sockets",
            "priority": "P2",
            "subject": f"subject {ticket_id}",
            "body": "body",
            "status": status,
        }
    )


def build_case(store: StateStore, cid: UUID, tickets: Sequence[Ticket] = (), now: datetime = NOW) -> CaseView:
    snapshot = store.rehydrate(cid)
    replay = store.replay_trace(cid)
    assert snapshot is not None and replay is not None
    return CaseView.from_rows(snapshot, replay, ACCOUNT, tickets, now)


def _identity() -> CallerIdentity:
    return CallerIdentity(
        account=ACCOUNT,
        caller_email="priya@bluebirdretail.com",
        effective_tier="Premium",
        is_verified_account_member=True,
        is_registered_admin=False,
        claimed_tier_rejected=False,
        needs_country_clarification=False,
    )


def _passage(passage_id: str, rrf: float, rerank: float) -> RetrievedPassage:
    return RetrievedPassage(
        passage_id=passage_id,
        slug=f"article-{passage_id}",
        title=f"Article {passage_id}",
        public_url="https://example.com",
        site_updated_at=None,
        heading="h",
        heading_anchor=f"h-{passage_id}",
        body="body",
        lex_rank=1,
        vec_rank=None,
        rrf_score=rrf,
        rerank_score=rerank,
    )


def _output(model: BaseModel) -> dict[str, Any]:
    return model.model_dump(mode="json")


def _call(name: str, result: BaseModel) -> ToolCall:
    return ToolCall(tool_name=name, arguments={}, status="OK", result=_output(result), latency_ms=1)


def _record(store: StateStore, trace: TraceRecord, calls: Sequence[ToolCall] = ()) -> None:
    records = [
        ToolCallRecord.from_tool_call(trace.id, trace.conversation_id, i, c, NOW) for i, c in enumerate(calls)
    ]
    store.record_trace(trace, records)


@pytest.fixture
def seed_case(store: StateStore, new_conversation: Callable[[], UUID], make_trace: MakeTrace) -> SeedCase:
    """SC-03 shaped open turn: credit proposal pending, repeat contact, anomalous telemetry, KB scores."""

    def seed() -> UUID:
        cid = new_conversation()
        message_id = uuid4()
        store.append_customer_message(cid, message_id, "credit please", NOW)
        store.create_approval(cid, message_id, ActionType.CREDIT, CREDIT, "k", NOW)
        triage = TriageResult(
            decision=TriageDecision(intent=Intent.POLICY_REQUEST, priority="P2", symptom_summary="outage"),
            identity=_identity(),
            sla=SLADeadlines(
                priority="P2",
                tier="Premium",
                timezone_name="UTC",
                product_area=None,
                started_at=NOW,
                first_response_due=NOW + timedelta(hours=1),
                resolution_due=NOW + timedelta(hours=8),
                update_cadence="1h",
                is_24x7=True,
                resolution_paused=False,
            ),
            repeat_contact=RepeatContactResult(
                is_repeat_contact=True,
                matching_tickets=[make_ticket("T-1", "open")],
                prior_closed_tickets=[make_ticket("T-0", "closed")],
                reason="same site within 7 days",
            ),
        )
        evidence = DiagnosticEvidence(
            findings=DiagnosticsFindings(),
            evidence_items=(
                TelemetryEvidence(
                    tool_name="get_link_quality",
                    metric_key="avg_packet_loss_pct",
                    raw_value="7.5",
                    timestamp=NOW,
                    is_anomaly=True,
                ),
            ),
            unavailable_tools=(
                UnavailableTool(tool_name="get_bgp_status", status=TelemetryStatus.UNAVAILABLE),
            ),
        )
        link = LinkMetricsSummary(
            link="wan1",
            sample_count=10,
            window_start=NOW - timedelta(hours=1),
            window_end=NOW,
            avg_packet_loss_pct=7.5,
            max_packet_loss_pct=9.0,
            latest_packet_loss_pct=8.0,
            avg_latency_ms=40.0,
            max_latency_ms=80.0,
            avg_jitter_ms=5.0,
            max_jitter_ms=9.0,
            avg_upstream_mbps=10.0,
            avg_downstream_mbps=20.0,
            down_intervals=1,
        )
        link_result = TelemetryToolResult[LinkQualityPayload](
            tool_name="get_link_quality",
            status=TelemetryStatus.OK,
            data=LinkQualityPayload(site_id="S-1", window="24h", links=[link]),
        )
        kb_search = KBSearchResult(
            status=KBSearchStatus.CONFIDENT,
            query="loss",
            passages=[_passage("p1", 0.03, 0.9)],
            candidates=[_passage("p1", 0.03, 0.9), _passage("p2", 0.02, 0.1)],
            snapshot_date=None,
        )
        bundle = KnowledgeBundle(
            findings=KnowledgeFindings(),
            retrieved_passages=(_passage("p1", 0.03, 0.9),),
            candidates=(_passage("p1", 0.03, 0.9), _passage("p2", 0.02, 0.1)),
            confidence_status=KBSearchStatus.CONFIDENT,
        )
        _record(store, make_trace(cid, role=AgentRole.TRIAGE, output=_output(triage)))
        _record(
            store,
            make_trace(cid, role=AgentRole.DIAGNOSTICS, output=_output(evidence)),
            [_call("get_link_quality", link_result)],
        )
        _record(
            store,
            make_trace(cid, role=AgentRole.KNOWLEDGE, output=_output(bundle)),
            [_call("search_knowledge_base", kb_search)],
        )
        return cid

    return seed


@pytest.fixture
def seed_degraded(store: StateStore, new_conversation: Callable[[], UUID], make_trace: MakeTrace) -> SeedCase:
    """Partial failure: no usable triage/diagnostics/knowledge output, telemetry UNAVAILABLE."""

    def seed() -> UUID:
        cid = new_conversation()
        store.append_customer_message(cid, uuid4(), "help", NOW)
        _record(store, make_trace(cid, role=AgentRole.TRIAGE, status=TraceStatus.ERROR, error="boom"))
        unavailable = TelemetryToolResult[LinkQualityPayload](
            tool_name="get_link_quality", status=TelemetryStatus.UNAVAILABLE, error="down"
        )
        _record(
            store,
            make_trace(cid, role=AgentRole.DIAGNOSTICS),
            [_call("get_link_quality", unavailable)],
        )
        return cid

    return seed
