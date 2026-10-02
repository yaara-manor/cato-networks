from dataclasses import dataclass, field
from typing import Any
from uuid import UUID, uuid4

import psycopg

from actions import ActionDispatcher, ActionResult, DispatchContext
from agents.models import SupportActionKind
from core.clock import SimulationClock
from guardrails import ActionType
from services import CustomerService, TicketService
from services.approval_service import ApprovalService
from storage import Approval, StateStore

PRIYA = "priya@bluebirdretail.com"  # verified member of ACC-1002, not admin
ADMIN = "it-admin@bluebirdretail.com"  # registered admin of ACC-1002
CREDIT = {"amount": "500", "currency": "USD", "incident_id": "INC-9", "period": "2026-09"}
MFA = {"user_email": "bob@bluebirdretail.com"}
_PAYLOADS = {ActionType.CREDIT: CREDIT, ActionType.MFA_RESET: MFA}
_CLEANUP_SQL = (
    "delete from simulated_actions where conversation_id = any(%(ids)s)",
    "delete from tool_calls where conversation_id = any(%(ids)s)",
    "delete from approvals where conversation_id = any(%(ids)s)",
    "delete from traces where conversation_id = any(%(ids)s)",
    "delete from messages where conversation_id = any(%(ids)s)",
    "delete from conversations where id = any(%(ids)s)",
)


class FlakyDispatcher(ActionDispatcher):
    """Reports FAILED from `dispatch_approved` until `works` is set, then behaves for real."""

    works = False

    def dispatch_approved(self, approval: Approval, context: DispatchContext) -> ActionResult:
        if not self.works:
            return ActionResult.failed(SupportActionKind.CREDIT, "boom")
        return super().dispatch_approved(approval, context)


@dataclass
class Desk:
    """A real ApprovalService over Postgres plus a way to file approvals the way the Workflow does."""

    conn: psycopg.Connection[Any]
    clock: SimulationClock
    store: StateStore
    tickets: TicketService
    customers: CustomerService
    dispatcher: ActionDispatcher
    service: ApprovalService
    conversations: list[UUID] = field(default_factory=list)
    tickets_before: int = 0

    @classmethod
    def create(cls, conn: psycopg.Connection[Any], dispatcher: ActionDispatcher | None = None) -> "Desk":
        clock = SimulationClock()
        store, tickets, customers = StateStore(conn), TicketService(conn, clock), CustomerService(conn, clock)
        dispatcher = dispatcher or ActionDispatcher(store, tickets, clock)
        row = conn.execute("select coalesce(max(substring(ticket_id from 5)::int), 0) from tickets").fetchone()
        service = ApprovalService(store, dispatcher, tickets, customers, clock)
        return cls(conn, clock, store, tickets, customers, dispatcher, service, tickets_before=row[0] if row else 0)

    def propose(
        self,
        email: str = PRIYA,
        action_type: ActionType = ActionType.CREDIT,
        payload: dict[str, str] | None = None,
    ) -> Approval:
        """Conversation + customer message + open ticket + PENDING approval, ticket marked pending_approval."""
        identity = self.customers.authenticate_caller(email)
        assert identity.account is not None
        conversation = self.store.create_conversation(
            identity.account.account_id, email, identity.account.tier, self.clock.now()
        )
        self.conversations.append(conversation.id)
        message_id = uuid4()
        self.store.append_customer_message(conversation.id, message_id, "please help", self.clock.now())
        ticket = self.tickets.create_ticket(
            identity.account.account_id, "Test", email, identity.account.company, identity.account.tier,
            "P3", "VPN", "subject", "body",
        )  # fmt: skip
        approval = self.store.create_approval(
            conversation.id,
            message_id,
            action_type,
            {"ticket_id": ticket.ticket_id} | (payload or _PAYLOADS[action_type]),
            f"{message_id}:0",
            self.clock.now(),
        )
        context = DispatchContext(
            identity=identity,
            priority="P3",
            sev1_corroborated=False,
            already_paged=False,
            conversation_id=conversation.id,
            message_id=message_id,
        )
        self.dispatcher.mark_pending(approval, context)
        return approval

    def ticket_status(self, approval: Approval) -> str:
        ticket = self.tickets.get_ticket(approval.payload["ticket_id"])
        assert ticket is not None
        return ticket.status

    def cleanup(self) -> None:
        for statement in _CLEANUP_SQL:
            self.conn.execute(statement, {"ids": self.conversations})
        self.conn.execute(
            "delete from tickets where substring(ticket_id from 5)::int > %s", (self.tickets_before,)
        )
