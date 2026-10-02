from uuid import UUID, uuid4

import streamlit as st

from orchestration.state import StateVersionError
from storage import TurnLockTimeout
from ui import session
from ui.customer_widgets import render_banners, render_message, render_trace
from ui.scenarios import load_scenarios

CUSTOM = "Custom"
LOCK_NOTICE = "Still working on your previous message, retry."
VERSION_NOTICE = "Service updating, retry."
_SCENARIOS = {s.scenario_id: s for s in load_scenarios()}
_STATE = st.session_state


def _start(email: str) -> None:
    _STATE.conversation_id = session.start_conversation(email)
    _STATE.pending = _STATE.notice = None
    _STATE.pop("banner_signature", None)
    st.query_params["conversation_id"] = str(_STATE.conversation_id)


def _on_scenario() -> None:
    if (scenario := _SCENARIOS.get(_STATE.scenario)) is not None:
        _STATE.email = scenario.requester_email
        _start(scenario.requester_email)


def _query_conversation() -> UUID | None:
    try:
        candidate = UUID(st.query_params.get("conversation_id", ""))
    except ValueError:
        return None
    return candidate if session.load_view(candidate) is not None else None


def _sidebar() -> None:
    with st.sidebar:
        st.selectbox("Scenario", [CUSTOM, *_SCENARIOS], key="scenario", on_change=_on_scenario)
        st.text_input("Email", key="email")
        if st.button("New conversation"):
            _start(_STATE.email)
        scenario = _SCENARIOS.get(_STATE.scenario)
        if scenario and st.button("Send opening message"):
            _STATE.pending = (uuid4(), scenario.opening_message)


@st.fragment(run_every=5)
def _banners(conversation_id: UUID) -> None:
    view = session.load_view(conversation_id)
    if view is None:
        return
    render_banners(view)
    signature = tuple(b.state for b in view.banners)
    previous = _STATE.get("banner_signature", signature)
    _STATE.banner_signature = signature
    if previous != signature:
        st.rerun()  # an approval moved: reload the transcript so the AGENT notice appears


def _run_pending(conversation_id: UUID) -> None:
    message_id, text = _STATE.pending
    try:
        with st.spinner("Working on it..."):
            session.run_customer_turn(conversation_id, text, message_id)
    except TurnLockTimeout:
        _STATE.notice = LOCK_NOTICE
    except StateVersionError:
        _STATE.notice = VERSION_NOTICE
    else:
        _STATE.pending = _STATE.notice = None
    st.rerun()  # redraw the transcript, or the notice with its retry button


def main() -> None:
    session.warm()
    _STATE.setdefault("scenario", next(iter(_SCENARIOS)))
    if "email" not in _STATE:
        _STATE.email = _SCENARIOS[_STATE.scenario].requester_email
    _STATE.setdefault("pending", None)
    _STATE.setdefault("notice", None)
    _STATE.setdefault("conversation_id", _query_conversation())
    if _STATE.conversation_id is None:
        _start(_STATE.email)
    conversation_id: UUID = _STATE["conversation_id"]

    _sidebar()
    st.title("Cato support")
    chat_tab, trace_tab = st.tabs(["Chat", "Trace"])
    with trace_tab:
        render_trace(conversation_id)
    with chat_tab:
        _banners(conversation_id)
        view = session.load_view(conversation_id)
        assert view is not None
        for index, message in enumerate(view.messages):
            render_message(message, index)
        retry = _STATE.notice is not None and st.button("Retry")
        if _STATE.notice:
            st.warning(_STATE.notice)
    if text := st.chat_input("Describe your issue"):
        _STATE.pending = (uuid4(), text)
        _STATE.notice = None
    if _STATE.pending and (retry or _STATE.notice is None):
        with chat_tab:
            with st.chat_message("user"):
                st.text(_STATE.pending[1])
            _run_pending(conversation_id)


main()
