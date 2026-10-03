from datetime import timedelta
from typing import Any
from uuid import uuid4

from agents.models import AgentRole, TraceStatus
from retrieval.models import KBSearchStatus
from storage import ApprovalResolution, ApprovalStatus, StateStore
from tests.ui.conftest import NOW, MakeTrace, SeedCase, build_case, make_ticket
from tools.models import TelemetryStatus
from ui.reviewer_panels import SlaState

PSK = "Fg7!qwe-DC-2026-tunnel"


def test_happy_path_fills_every_panel(store: StateStore, seed_case: SeedCase) -> None:
    tickets = [
        make_ticket(f"T-{i}", s)
        for i, s in enumerate(["open", "pending_customer", "pending_approval", "closed"])
    ]
    view = build_case(store, seed_case(), tickets, NOW + timedelta(minutes=50))

    ctx = view.context
    assert (ctx.company, ctx.tier, ctx.triaged) == ("Bluebird Retail", "Standard", True)
    assert [(s.label, s.remaining, s.state) for s in ctx.sla] == [
        ("First response", timedelta(minutes=10), SlaState.AT_RISK),
        ("Resolution", timedelta(hours=7, minutes=10), SlaState.OK),
    ]
    assert ctx.repeat_contact is not None
    assert ctx.repeat_contact.reason == "same site within 7 days"
    assert (ctx.repeat_contact.matching_ticket_ids, ctx.repeat_contact.prior_closed_ids) == (
        ("T-1",),
        ("T-0",),
    )
    assert [t.ticket_id for t in ctx.open_tickets] == ["T-0", "T-1", "T-2"]

    ev = view.evidence
    assert [(e.raw_value, e.is_anomaly) for e in ev.evidence] == [("7.5", True)]
    assert [(u.tool_name, u.status) for u in ev.unavailable_tools] == [
        ("get_bgp_status", TelemetryStatus.UNAVAILABLE)
    ]
    assert [(c.site_id, [x.link for x in c.links]) for c in ev.link_charts] == [("S-1", ["wan1"])]
    assert [c.tool_name for c in ev.raw_calls] == ["get_link_quality", "search_knowledge_base"]
    assert ev.kb_status is KBSearchStatus.CONFIDENT
    assert [(p.citation_tag, p.rrf_score, p.rerank_score, p.cited) for p in ev.kb_passages] == [
        ("[kb:article-p1#h-p1]", 0.03, 0.9, True),
        ("[kb:article-p2#h-p2]", 0.02, 0.1, False),
    ]


def test_partial_failure_yields_explicit_no_data_states(store: StateStore, seed_degraded: SeedCase) -> None:
    view = build_case(store, seed_degraded(), [make_ticket("T-4", "closed")])

    assert (view.context.triaged, view.context.sla, view.context.repeat_contact) == (False, (), None)
    assert view.context.open_tickets == ()
    assert (view.evidence.evidence, view.evidence.kb_passages, view.evidence.kb_status) == ((), (), None)
    assert view.evidence.link_charts == ()  # UNAVAILABLE result carries no data
    assert [c.tool_name for c in view.evidence.raw_calls] == ["get_link_quality"]
    assert view.approvals == ()


def test_schema_drift_falls_back_to_no_data(
    store: StateStore, seed_case: SeedCase, make_trace: MakeTrace
) -> None:
    cid = seed_case()
    for role in (AgentRole.TRIAGE, AgentRole.DIAGNOSTICS, AgentRole.KNOWLEDGE):
        store.record_trace(make_trace(cid, role=role, output={"renamed": "field"}), [])

    view = build_case(store, cid)

    assert (view.context.triaged, view.context.sla) == (False, ())
    assert (view.evidence.evidence, view.evidence.kb_status) == ((), None)


def test_newest_error_trace_defers_to_older_ok_trace(
    store: StateStore, seed_case: SeedCase, make_trace: MakeTrace
) -> None:
    cid = seed_case()
    store.record_trace(make_trace(cid, role=AgentRole.TRIAGE, status=TraceStatus.ERROR, error="boom"), [])
    store.record_trace(make_trace(cid, role=AgentRole.DIAGNOSTICS, output=None), [])

    view = build_case(store, cid)

    assert view.context.triaged
    assert [e.raw_value for e in view.evidence.evidence] == ["7.5"]


def test_approval_card_tracks_resolution(store: StateStore, seed_case: SeedCase) -> None:
    cid = seed_case()

    (card,) = build_case(store, cid).approvals
    assert (card.can_resolve, card.action_label, card.proposing_turn) == (True, "Credit", 1)
    assert [e.raw_value for e in card.evidence_refs] == ["7.5"]

    store.resolve_approval(card.approval.id, ApprovalResolution(status=ApprovalStatus.APPROVED), NOW)

    (resolved,) = build_case(store, cid).approvals
    assert (resolved.can_resolve, resolved.approval.status) == (False, ApprovalStatus.APPROVED)


def test_secret_never_appears_in_case_view(
    store: StateStore, seed_case: SeedCase, make_trace: MakeTrace
) -> None:
    cid = seed_case()
    leaky: dict[str, Any] = {
        "decision": {"intent": "POLICY_REQUEST", "priority": "P2", "symptom_summary": f"PSK is {PSK}"}
    }
    store.record_trace(
        make_trace(cid, role=AgentRole.TRIAGE, output=leaky, input={"text": f"PSK is {PSK}"}),
        [],
    )
    store.append_customer_message(cid, uuid4(), "again", NOW)

    assert PSK not in build_case(store, cid).model_dump_json()
