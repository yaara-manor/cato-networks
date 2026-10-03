from collections.abc import Iterator

import psycopg
import pytest

from core.clock import DEFAULT_ANCHOR, SimulationClock
from core.config import settings
from core.models import Ticket
from services import TicketService


@pytest.fixture
def conn() -> Iterator[psycopg.Connection]:
    with psycopg.connect(settings.database_url) as connection:
        yield connection


@pytest.fixture
def created(conn: psycopg.Connection) -> Iterator[list[str]]:
    ids: list[str] = []
    yield ids
    conn.rollback()
    conn.execute("delete from tickets where ticket_id = any(%s)", (ids,))
    conn.commit()


@pytest.fixture
def tickets(conn: psycopg.Connection) -> TicketService:
    return TicketService(conn, SimulationClock.frozen(DEFAULT_ANCHOR))


@pytest.fixture
def new_ticket(tickets: TicketService, created: list[str]) -> Ticket:
    ticket = tickets.create_ticket(
        customer_id="ACC-1002",
        customer_name="Priya",
        requester_email="priya@bluebirdretail.com",
        company="Bluebird",
        tier="Standard",
        priority="P3",
        product_area="Connectivity",
        subject="s",
        body="b",
    )
    created.append(ticket.ticket_id)
    return ticket


def test_each_field_alone_and_together(tickets: TicketService, new_ticket: Ticket) -> None:
    ticket = new_ticket
    assert tickets.update_ticket(ticket.ticket_id, status="pending_customer").status == "pending_customer"
    assert tickets.update_ticket(ticket.ticket_id, site_id="SITE-1").site_id == "SITE-1"
    assert tickets.update_ticket(ticket.ticket_id, priority="P1").priority == "P1"
    both = tickets.update_ticket(ticket.ticket_id, status="closed", site_id="SITE-2", priority="P4")
    assert (both.status, both.site_id, both.priority) == ("closed", "SITE-2", "P4")
    assert tickets.get_ticket(ticket.ticket_id) == both


def test_nothing_given_or_unknown_id_raises(tickets: TicketService, new_ticket: Ticket) -> None:
    ticket = new_ticket
    with pytest.raises(ValueError):
        tickets.update_ticket(ticket.ticket_id)
    with pytest.raises(ValueError):
        tickets.update_ticket("TCK-0", status="closed")


def test_update_ticket_status_still_works(tickets: TicketService, new_ticket: Ticket) -> None:
    ticket = new_ticket
    assert tickets.update_ticket_status(ticket.ticket_id, "closed").status == "closed"
    with pytest.raises(ValueError):
        tickets.update_ticket_status("TCK-0", "closed")
