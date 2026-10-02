from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from actions.models import ActionStatus, DispatchContext
from actions.payloads import (
    ActionPayload,
    CloseTicketPayload,
    CreateTicketPayload,
    CreditPayload,
    MfaResetPayload,
    PageOnCallPayload,
    UpdateTicketPayload,
)
from agents.models import SupportActionKind
from core.models import Ticket
from services import TicketService

PAGE_ACK_MINUTES = 15  # POL-SEV1

TICKET_CREATED_LINE = "I opened ticket {ticket_id} for you."
TICKET_UPDATED_LINE = "I updated ticket {ticket_id}."
TICKET_CLOSED_LINE = "I closed ticket {ticket_id}."
PAGED_LINE = "I paged the on-call engineer (incident {incident_ref}); expect acknowledgement within {minutes} minutes."

REFUSED_KINDS = frozenset({SupportActionKind.VERDICT_OVERRIDE})


class ActionRejected(Exception):
    """A handler's deliberate non-success; `status` is what the dispatcher records."""

    status: ActionStatus = ActionStatus.FAILED


class InvalidActionError(ActionRejected):
    status = ActionStatus.INVALID


class OwnershipError(ActionRejected):
    status = ActionStatus.REFUSED


class ActionOutcome(BaseModel):
    model_config = ConfigDict(frozen=True)

    reference: str
    result: dict[str, Any]
    customer_line: str | None = None


@dataclass(frozen=True)
class HandlerCall:
    context: DispatchContext
    tickets: TicketService
    action_id: UUID


Runner = Callable[[HandlerCall], ActionOutcome]
Handler = Callable[[dict[str, str]], Runner]


def _owned_ticket(call: HandlerCall, ticket_id: str) -> Ticket:
    ticket = call.tickets.get_ticket(ticket_id)
    if ticket is None:
        raise ValueError("unknown ticket")
    account = call.context.identity.account
    if account is None or ticket.customer_id != account.account_id:
        raise OwnershipError("ticket belongs to another account")
    return ticket


def _ticket_outcome(ticket: Ticket, line: str) -> ActionOutcome:
    return ActionOutcome(
        reference=ticket.ticket_id,
        result={"ticket_id": ticket.ticket_id, "status": ticket.status},
        customer_line=line.format(ticket_id=ticket.ticket_id),
    )


def _event_id(prefix: str, call: HandlerCall) -> str:
    return f"{prefix}-{call.action_id.hex[:8].upper()}"


def create_ticket(payload: CreateTicketPayload, call: HandlerCall) -> ActionOutcome:
    identity = call.context.identity
    if identity.account is None or identity.caller_email is None:
        raise InvalidActionError("no identified caller to open a ticket for")
    ticket = call.tickets.create_ticket(
        customer_id=identity.account.account_id,
        customer_name=identity.caller_email,
        requester_email=identity.caller_email,
        company=identity.account.company,
        tier=identity.account.tier,
        priority=payload.priority or call.context.priority,
        product_area=payload.product_area,
        subject=payload.subject,
        body=payload.body,
        site_id=payload.site_id,
    )
    return _ticket_outcome(ticket, TICKET_CREATED_LINE)


def update_ticket(payload: UpdateTicketPayload, call: HandlerCall) -> ActionOutcome:
    _owned_ticket(call, payload.ticket_id)
    ticket = call.tickets.update_ticket(
        payload.ticket_id, status=payload.status, site_id=payload.site_id, priority=payload.priority
    )
    return _ticket_outcome(ticket, TICKET_UPDATED_LINE)


def close_ticket(payload: CloseTicketPayload, call: HandlerCall) -> ActionOutcome:
    _owned_ticket(call, payload.ticket_id)
    return _ticket_outcome(call.tickets.update_ticket(payload.ticket_id, status="closed"), TICKET_CLOSED_LINE)


def page_on_call(payload: PageOnCallPayload, call: HandlerCall) -> ActionOutcome:
    incident_ref = _event_id("INC", call)
    return ActionOutcome(
        reference=incident_ref,
        result={
            "event": "oncall_paged",
            "incident_ref": incident_ref,
            "summary": payload.summary,
            "site_ids": list(payload.sites),
            "priority": call.context.priority,
            "ack_minutes": PAGE_ACK_MINUTES,
        },
        customer_line=PAGED_LINE.format(incident_ref=incident_ref, minutes=PAGE_ACK_MINUTES),
    )


def request_credit(payload: CreditPayload, call: HandlerCall) -> ActionOutcome:
    request_id = _event_id("CRD", call)
    return ActionOutcome(
        reference=request_id,
        result={
            "event": "credit_request_submitted",
            "ticket_id": payload.ticket_id,
            "amount": str(payload.amount),
            "currency": payload.currency,
            "incident_id": payload.incident_id,
            "period": payload.period,
        },
    )


def reset_mfa(payload: MfaResetPayload, call: HandlerCall) -> ActionOutcome:
    request_id = _event_id("MFA", call)
    identity = call.context.identity
    return ActionOutcome(
        reference=request_id,
        result={
            "event": "mfa_reset_triggered",
            "ticket_id": payload.ticket_id,
            "user_email": payload.user_email,
            "requester_email": identity.caller_email,
            "is_registered_admin": identity.is_registered_admin,
        },
    )


def _bind[P: ActionPayload](model: type[P], handler: Callable[[P, HandlerCall], ActionOutcome]) -> Handler:
    """Parse the raw payload now (ValueError if invalid); run the handler later."""
    return lambda raw: partial(handler, model.from_payload(raw))


HANDLERS: dict[SupportActionKind, Handler] = {
    SupportActionKind.CREATE_TICKET: _bind(CreateTicketPayload, create_ticket),
    SupportActionKind.UPDATE_TICKET: _bind(UpdateTicketPayload, update_ticket),
    SupportActionKind.CLOSE_TICKET: _bind(CloseTicketPayload, close_ticket),
    SupportActionKind.PAGE_ON_CALL: _bind(PageOnCallPayload, page_on_call),
    SupportActionKind.CREDIT: _bind(CreditPayload, request_credit),
    SupportActionKind.MFA_RESET: _bind(MfaResetPayload, reset_mfa),
}
