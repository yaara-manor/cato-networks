from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

import psycopg
import pytest

from actions import ActionDispatcher, DispatchContext
from agents.models import SupportAction, SupportActionKind
from core.clock import SimulationClock
from core.config import settings
from core.models import TicketPriority
from services import CustomerService, TicketService
from services.models import CallerIdentity
from storage import StateStore

PRIYA = "priya@bluebirdretail.com"  # verified member of ACC-1002
ADMIN = "it-admin@bluebirdretail.com"  # registered admin of ACC-1002
OTHER = "grace.novak@solsticemedia.com"  # member of ACC-1008

_CLEANUP_SQL = (
    "delete from simulated_actions where conversation_id = any(%(ids)s)",
    "delete from approvals where conversation_id = any(%(ids)s)",
    "delete from messages where conversation_id = any(%(ids)s)",
    "delete from conversations where id = any(%(ids)s)",
)
_TICKET_NUMBER = "substring(ticket_id from 5)::int"

MakeContext = Callable[..., DispatchContext]
NextTurn = Callable[[DispatchContext], DispatchContext]


@dataclass(frozen=True)
class Actions:
    conn: psycopg.Connection[Any]
    store: StateStore
    tickets: TicketService
    dispatcher: ActionDispatcher
    customers: CustomerService
    clock: SimulationClock
    make_context: MakeContext
    next_turn: NextTurn


def action(kind: SupportActionKind, **payload: str) -> SupportAction:
    return SupportAction(kind=kind, payload=payload, reason="test")


@pytest.fixture
def actions() -> Iterator[Actions]:
    clock = SimulationClock()
    with psycopg.connect(settings.database_url, autocommit=True) as conn:
        store, tickets, customers = StateStore(conn), TicketService(conn, clock), CustomerService(conn, clock)
        baseline = conn.execute(f"select max({_TICKET_NUMBER}) from tickets").fetchone()
        conversations: list[UUID] = []

        def make_context(
            email: str = PRIYA,
            priority: TicketPriority = "P3",
            sev1_corroborated: bool = False,
            already_paged: bool = False,
            identity: CallerIdentity | None = None,
        ) -> DispatchContext:
            conversation_id, message_id = uuid4(), uuid4()
            store.create_conversation(None, email, "Unknown", clock.now(), conversation_id)
            store.append_customer_message(conversation_id, message_id, "help", clock.now())
            conversations.append(conversation_id)
            return DispatchContext(
                identity=identity or customers.authenticate_caller(email),
                priority=priority,
                sev1_corroborated=sev1_corroborated,
                already_paged=already_paged,
                conversation_id=conversation_id,
                message_id=message_id,
            )

        def next_turn(context: DispatchContext) -> DispatchContext:
            message_id = uuid4()
            store.append_customer_message(context.conversation_id, message_id, "again", clock.now())
            return context.model_copy(update={"message_id": message_id})

        yield Actions(
            conn, store, tickets, ActionDispatcher(store, tickets, clock), customers, clock, make_context, next_turn
        )
        for statement in _CLEANUP_SQL:
            conn.execute(statement, {"ids": conversations})
        conn.execute(f"delete from tickets where {_TICKET_NUMBER} > %s", (baseline[0] if baseline else 0,))
