from collections.abc import Iterator
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import contextmanager
from typing import Any
from uuid import UUID

import psycopg
import streamlit as st

from core.clock import SimulationClock
from core.config import settings
from orchestration import AgentPorts, TurnResult, build_services, build_workflow, warm_models
from retrieval.models import PolicyDocument
from retrieval.service import RetrievalService
from storage import ConversationStage, StateStore
from ui.chat_view import ChatView
from ui.trace_panel import TracePanel

LOCK_NOTICE = "Still working on your previous message, retry."
_CLOCK = SimulationClock()  # one per process so simulated time keeps advancing across turns
_TURN_POOL = ThreadPoolExecutor(max_workers=4, thread_name_prefix="customer-turn")
ports_override: AgentPorts | None = None  # tests inject scripted agents; None = real PydanticAI agents


@st.cache_resource
def warm() -> None:
    warm_models()


@contextmanager
def connection() -> Iterator[psycopg.Connection[Any]]:
    """Fresh autocommit connection per call: services bind one connection and 24 forbids sharing."""
    with psycopg.connect(settings.database_url, autocommit=True) as conn:
        yield conn


def start_conversation(email: str) -> UUID:
    with connection() as conn:
        services = build_services(conn, _CLOCK)
        identity = services.customers.authenticate_caller(email)
        account_id = identity.account.account_id if identity.account else None
        conversation = services.store.create_conversation(
            account_id, identity.caller_email, identity.effective_tier, _CLOCK.now()
        )
    return conversation.id


def run_customer_turn(conversation_id: UUID, text: str, message_id: UUID) -> TurnResult:
    with connection() as conn:
        return build_workflow(conn, _CLOCK, ports_override).run_turn(conversation_id, text, message_id)


def start_customer_turn(conversation_id: UUID, text: str, message_id: UUID) -> Future[TurnResult]:
    """Runs off the script thread, so the page can show progress while the turn works."""
    return _TURN_POOL.submit(run_customer_turn, conversation_id, text, message_id)


def load_stage(conversation_id: UUID) -> ConversationStage | None:
    with connection() as conn:
        snapshot = StateStore(conn).rehydrate(conversation_id)
    return None if snapshot is None else snapshot.conversation.stage


def load_view(conversation_id: UUID) -> ChatView | None:
    with connection() as conn:
        store = StateStore(conn)
        snapshot = store.rehydrate(conversation_id)
        if snapshot is None:
            return None
        return ChatView.from_snapshot(snapshot, store.list_approvals(conversation_id))


def load_trace(conversation_id: UUID) -> TracePanel | None:
    with connection() as conn:
        replay = StateStore(conn).replay_trace(conversation_id)
    return None if replay is None else TracePanel.from_replay(replay)


def load_policy(policy_id: str) -> PolicyDocument | None:
    with connection() as conn:
        return RetrievalService(conn).get_policy(policy_id)
