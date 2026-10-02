from datetime import datetime
from uuid import UUID

import psycopg
import streamlit as st

from storage import ApprovalStateError, BoardRow
from ui import reviewer_session
from ui.reviewer_view import ApprovalCard, DecisionForm, DecisionFormError, DecisionKind
from ui.reviewer_widgets import render_approval_card, render_context, render_evidence
from ui.session import load_trace
from ui.trace_panel import render_trace_panel

_STATE = st.session_state
NOT_FOUND = "Conversation not found."


def _age(row: BoardRow, now: datetime) -> str:
    return "-" if row.oldest_pending_at is None else str(now - row.oldest_pending_at).split(".")[0]


def _select(conversation_id: UUID) -> None:
    st.query_params["conversation_id"] = str(conversation_id)
    st.rerun()  # the board is a fragment; the case panels live in the full script


def _render_pending_tab(rows: list[BoardRow], now: datetime) -> None:
    for row in (r for r in rows if r.pending_count):
        label = f"{row.account_id or 'unknown'} | {row.customer_tier} | {row.pending_count} pending | {_age(row, now)}"
        if st.button(label, key=f"pick-{row.conversation_id}"):
            _select(row.conversation_id)


def _render_escalated_tab(rows: list[BoardRow]) -> None:
    for row in (r for r in rows if r.oncall_paged or r.escalation_offered):
        flags = (("on-call paged", row.oncall_paged), ("escalation offered", row.escalation_offered))
        st.text(f"{row.account_id or 'unknown'} | {row.customer_tier} | {row.conversation_id}")
        for name, on in flags:
            if on:
                st.badge(name)


@st.fragment(run_every=3)
def render_board() -> None:
    try:
        rows = reviewer_session.load_board()
    except psycopg.OperationalError:
        st.warning("Database unreachable, retrying.")
        return
    now = reviewer_session.build_reviewer_runtime().clock.now()
    pending_tab, escalated_tab = st.tabs(["Pending", "Escalated"])
    with pending_tab:
        _render_pending_tab(rows, now)
    with escalated_tab:
        _render_escalated_tab(rows)


def _decide(card: ApprovalCard, kind: DecisionKind, edited: dict[str, str] | None) -> None:
    key = str(card.approval.id)
    form = DecisionForm(
        approval_id=card.approval.id,
        kind=kind,
        note=_STATE[f"note-{key}"],
        customer_reason=_STATE[f"reason-{key}"],
        original_payload=card.approval.payload,
        edited_payload=edited,
    )
    try:
        reviewer_session.decide(form.to_decision())
    except (DecisionFormError, ApprovalStateError) as error:
        _STATE.setdefault("errors", {})[card.approval.id] = str(error)
    st.rerun()  # redraw every card from the DB, never optimistic UI


def render_approvals(cards: tuple[ApprovalCard, ...]) -> None:
    st.subheader("Pending approvals")
    errors: dict[UUID, str] = _STATE.get("errors", {})
    for card in cards:
        if error := errors.pop(card.approval.id, None):
            st.error(error)
        render_approval_card(card, _decide)
    if not cards:
        st.text("No approvals.")


def render_live_trace(conversation_id: UUID) -> None:
    @st.fragment(run_every=2)  # ponytail: polls even when IDLE (cheap read); stage-aware stop if load grows
    def poll() -> None:
        panel = load_trace(conversation_id)
        if panel is not None:
            render_trace_panel(panel, show_io=True)

    poll()


def _query_conversation() -> UUID | None:
    try:
        return UUID(st.query_params.get("conversation_id", ""))
    except ValueError:
        return None


def main() -> None:
    reviewer_session.build_reviewer_runtime()
    st.title("Reviewer board")
    with st.sidebar:
        render_board()
    conversation_id = _query_conversation()
    if conversation_id is None:
        st.text("Select a conversation.")
        return
    case = reviewer_session.load_case(conversation_id)
    if case is None:
        st.warning(NOT_FOUND)
        return
    render_context(case.context)
    render_approvals(case.approvals)
    evidence_tab, trace_tab = st.tabs(["Evidence", "Live trace"])
    with evidence_tab:
        render_evidence(case.evidence)
    with trace_tab:
        render_live_trace(conversation_id)


main()
