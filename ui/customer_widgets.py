from typing import assert_never
from uuid import UUID

import streamlit as st

from guardrails import MarkerKind
from ui.chat_view import ApprovalBanner, ApprovalBannerState, ChatView, CitationBadge, MessageRole, MessageView
from ui.citation_render import escape_label
from ui.session import load_policy, load_trace
from ui.trace_panel import TraceTurn, render_trace_panel, step_lines

ESCALATION_NOTICE = "A support engineer will follow up."


@st.dialog("Policy")
def _policy_dialog(policy_id: str) -> None:
    policy = load_policy(policy_id)
    if policy:
        st.markdown(policy.body)
    else:
        st.text("Policy not found.")


def _source_line(position: int, badge: CitationBadge) -> str:
    label = escape_label(badge.section_label)
    return f"[{position}] [{label}]({badge.section_url})" if badge.section_url else f"[{position}] {label}"


def _render_sources(message: MessageView, index: int) -> None:
    if not message.citations:
        return
    st.caption(" · ".join(_source_line(n, badge) for n, badge in enumerate(message.citations, start=1)))
    for position, badge in enumerate(message.citations):
        if badge.kind is MarkerKind.POLICY and st.button(badge.label, key=f"cite-{index}-{position}"):
            _policy_dialog(badge.ref)


def _worked_label(log: TraceTurn) -> str:
    seconds = sum(step.latency_ms for step in log.steps) / 1000
    return f"Worked for {seconds:.0f} s · {len(log.steps)} steps"


def _render_log(message: MessageView, log: TraceTurn | None) -> None:
    """The step lines and telemetry chips of one reply, folded away until asked for."""
    if log is None or not log.steps:
        return
    with st.expander(_worked_label(log), expanded=False):
        for step in log.steps:
            for line in step_lines(step):
                st.text(line)
        for chip in message.evidence:
            st.badge(
                chip.text,
                color="orange" if chip.is_anomaly else "gray",
                help=f"{chip.tool_name} at {chip.timestamp:%Y-%m-%d %H:%M}",
            )


def render_message(message: MessageView, index: int, log: TraceTurn | None = None) -> None:
    """Customer text is plain `st.text`; agent text is markdown (HTML is never enabled)."""
    with st.chat_message("user" if message.role is MessageRole.CUSTOMER else "assistant"):
        if message.role is MessageRole.CUSTOMER:
            st.text(message.text)
            return
        st.markdown(message.text)
        _render_sources(message, index)
        _render_log(message, log)


def _render_banner(banner: ApprovalBanner) -> None:
    match banner.state:
        case ApprovalBannerState.PENDING:
            st.info(f"Awaiting review by our support team: {banner.title}")
        case ApprovalBannerState.FINALIZING:
            st.info(f"Approved, being finalized: {banner.title}")
        case ApprovalBannerState.APPROVED:
            st.success(f"Approved: {banner.title}")
        case ApprovalBannerState.REJECTED:
            st.warning(f"Not approved: {banner.title}")
        case _:
            assert_never(banner.state)


def render_banners(view: ChatView) -> None:
    for banner in view.banners:
        _render_banner(banner)
    if view.escalation_offered:
        st.info(ESCALATION_NOTICE)


def render_trace(conversation_id: UUID) -> None:
    panel = load_trace(conversation_id)
    if panel is not None:
        render_trace_panel(panel)
