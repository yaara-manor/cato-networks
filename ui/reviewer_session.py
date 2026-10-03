from dataclasses import dataclass
from typing import Any, Self
from uuid import UUID

import psycopg
import streamlit as st

from actions import ActionDispatcher
from core.clock import SimulationClock
from orchestration import build_services
from services.approval_models import DecisionResult, ReviewerDecision
from services.approval_service import ApprovalService
from storage import BoardRow, StateStore
from ui.reviewer_view import CaseView
from ui.session import connection

BOARD_LIMIT = 100


@dataclass(frozen=True)
class ReviewerRuntime:
    """Clock plus an ApprovalService factory over `build_services`: no encoder, retrieval or LLM is touched."""

    clock: SimulationClock

    def approvals(self, connection: psycopg.Connection[Any]) -> ApprovalService:
        services = build_services(connection, self.clock)
        dispatcher = ActionDispatcher(services.store, services.tickets, self.clock)
        return ApprovalService(services.store, dispatcher, services.tickets, services.customers, self.clock)

    @classmethod
    def start(cls, connection: psycopg.Connection[Any]) -> Self:
        """Finishes approvals a crashed process left resolved but unsettled, once."""
        runtime = cls(SimulationClock())
        runtime.approvals(connection).settle_unsettled()
        return runtime


@st.cache_resource
def build_reviewer_runtime() -> ReviewerRuntime:
    with connection() as conn:
        return ReviewerRuntime.start(conn)


def load_board() -> list[BoardRow]:
    with connection() as conn:
        return StateStore(conn).list_board_rows(BOARD_LIMIT)


def load_case(conversation_id: UUID) -> CaseView | None:
    runtime = build_reviewer_runtime()
    with connection() as conn:
        services = build_services(conn, runtime.clock)
        snapshot = services.store.rehydrate(conversation_id)
        replay = services.store.replay_trace(conversation_id)
        if snapshot is None or replay is None:
            return None
        account_id = snapshot.conversation.account_id
        return CaseView.from_rows(
            snapshot,
            replay,
            services.customers.lookup_account(account_id) if account_id else None,
            services.tickets.get_ticket_history(account_id) if account_id else [],
            services.store.list_simulated_actions(conversation_id),
            runtime.clock.now(),
        )


def decide(decision: ReviewerDecision) -> DecisionResult:
    with connection() as conn:
        return build_reviewer_runtime().approvals(conn).decide(decision)
