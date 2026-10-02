from typing import assert_never
from uuid import UUID

import streamlit as st

from guardrails import MarkerKind
from ui.chat_view import ApprovalBanner, ApprovalBannerState, ChatView, CitationBadge, MessageRole, MessageView
from ui.session import load_policy, load_trace
from ui.trace_panel import render_trace_panel

ESCALATION_NOTICE = "A support engineer will follow up."


@st.dialog("Policy")
def _policy_dialog(policy_id: str) -> None:
    policy = load_policy(policy_id)
    if policy:
        st.markdown(policy.body)
    else:
        st.text("Policy not found.")


def _render_badge(badge: CitationBadge, key: str) -> None:
    if badge.url:
        st.link_button(badge.label, badge.url)
    elif badge.kind is MarkerKind.POLICY and st.button(badge.label, key=key):
        _policy_dialog(badge.ref)


def render_message(message: MessageView, index: int) -> None:
    """Customer text is plain `st.text`; agent text is markdown (HTML is never enabled)."""
    with st.chat_message("user" if message.role is MessageRole.CUSTOMER else "assistant"):
        if message.role is MessageRole.CUSTOMER:
            st.text(message.text)
            return
        st.markdown(message.text)
        for chip in message.evidence:
            st.badge(
                chip.text,
                color="orange" if chip.is_anomaly else "gray",
                help=f"{chip.tool_name} at {chip.timestamp:%Y-%m-%d %H:%M}",
            )
        for position, badge in enumerate(message.citations):
            _render_badge(badge, f"cite-{index}-{position}")


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
