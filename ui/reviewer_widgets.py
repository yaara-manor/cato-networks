import json
from collections.abc import Callable

import streamlit as st

from storage import ApprovalStatus
from ui.reviewer_panels import ContextPanel, EvidencePanel, LinkChart, PassageScore
from ui.reviewer_view import ApprovalCard, DecisionForm, DecisionKind, ModelMessagesView

_NO_DATA = "No data"
_CHART_METRICS = ("avg_packet_loss_pct", "avg_latency_ms", "avg_jitter_ms")
Submit = Callable[[DecisionForm], None]


def render_context(context: ContextPanel) -> None:
    """Customer-influenced text goes through `st.text`/`st.code` only, never markdown or HTML."""
    st.subheader("Context")
    st.text(f"{context.company or 'Unknown account'} ({context.account_id or '-'}) | {context.tier}")
    st.text(f"Contact: {context.contact_email or '-'}")
    if not context.triaged:
        st.text(f"Triage: {_NO_DATA}")
    for countdown in context.sla:
        st.text(f"{countdown.label}: {countdown.state} ({countdown.remaining}, due {countdown.due_at:%Y-%m-%d %H:%M})")
    if context.repeat_contact:
        st.warning(f"Repeat contact: {context.repeat_contact.reason}")
        st.text(f"Matching: {', '.join(context.repeat_contact.matching_ticket_ids) or '-'}")
    for ticket in context.open_tickets:
        st.text(f"{ticket.ticket_id} [{ticket.status}] {ticket.priority} {ticket.subject}")


def _render_link_chart(chart: LinkChart) -> None:
    st.text(f"Links at {chart.site_id} ({chart.window})")
    for metric in _CHART_METRICS:
        st.bar_chart({metric: {link.link: getattr(link, metric) for link in chart.links}})


def _render_passage(passage: PassageScore) -> None:
    mark = "cited" if passage.cited else "candidate"
    scores = f"rrf={passage.rrf_score:.3f} rerank={passage.rerank_score:.3f}"
    st.text(f"{passage.citation_tag} {passage.title} [{mark}] {scores}")


def render_evidence(evidence: EvidencePanel) -> None:
    if not (evidence.evidence or evidence.unavailable_tools or evidence.kb_passages):
        st.text(f"Evidence: {_NO_DATA}")
    for item in evidence.evidence:
        st.text(f"{'ANOMALY ' if item.is_anomaly else ''}{item.tool_name} {item.metric_key} = {item.raw_value}")
    for tool in evidence.unavailable_tools:
        st.warning(f"{tool.tool_name}: {tool.status}")
    for chart in evidence.link_charts:
        _render_link_chart(chart)
    st.text(f"Knowledge base: {evidence.kb_status or _NO_DATA}")
    for passage in evidence.kb_passages:
        _render_passage(passage)
    with st.expander("Raw tool calls"):
        for call in evidence.raw_calls:
            st.text(f"{call.tool_name} [{call.status}]")
            st.code(json.dumps(call.result, indent=2, default=str), language="json")


def _render_payload(payload: dict[str, str]) -> None:
    st.code(json.dumps(payload, indent=2), language="json")


def _render_resolved(card: ApprovalCard) -> None:
    approval = card.approval
    st.text(f"{approval.status} | internal note: {approval.reviewer_notes or '-'}")
    if approval.status is ApprovalStatus.EDITED:
        _render_payload(approval.effective_payload)
    if approval.customer_reason:
        st.text(f"Customer reason: {approval.customer_reason}")
    if card.dispatch:
        st.text(f"Action {card.dispatch.status}")
    if approval.settled_at is None:
        st.info("Decision saved, customer notice pending.")
    else:
        st.text("Settled")


def _render_decision_inputs(card: ApprovalCard, submit: Submit) -> None:
    key = str(card.approval.id)
    note = st.text_input("Internal note (never shown to the customer)", key=f"note-{key}")
    reason = st.text_input("Customer reason (optional, guard-checked)", key=f"reason-{key}")

    def form(kind: DecisionKind, edited: dict[str, str] | None = None) -> DecisionForm:
        return DecisionForm(
            approval_id=card.approval.id,
            kind=kind,
            note=note,
            customer_reason=reason,
            original_payload=card.approval.payload,
            edited_payload=edited,
        )

    approve, reject = st.columns(2)
    if approve.button("Approve", key=f"approve-{key}"):
        submit(form(DecisionKind.APPROVE))
    if reject.button("Reject", key=f"reject-{key}"):
        submit(form(DecisionKind.REJECT))
    with st.expander("Edit"), st.form(f"edit-{key}"):
        edited = {
            name: st.text_input(name, value=value, key=f"edit-{key}-{name}")
            for name, value in card.approval.payload.items()
        }
        if st.form_submit_button("Submit edit"):
            submit(form(DecisionKind.EDIT, edited))


def render_approval_card(card: ApprovalCard, submit: Submit) -> None:
    st.markdown(f"**{card.action_label}** (turn {card.proposing_turn or '?'})")
    _render_payload(card.approval.payload)
    for item in card.evidence_refs:
        st.text(f"{item.metric_key} = {item.raw_value}")
    if card.can_resolve:
        _render_decision_inputs(card, submit)
    else:
        _render_resolved(card)


def render_model_messages(view: ModelMessagesView) -> None:
    for step in view.steps:
        with st.expander(f"Turn {step.turn} {step.agent_role}"):
            if step.messages is None:
                st.text("not recorded")
            else:
                st.code(json.dumps(step.messages, indent=2, default=str), language="json")
