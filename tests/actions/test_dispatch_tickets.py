from actions import ActionStatus
from agents.models import SupportActionKind as Kind
from storage import SimulatedActionStatus
from tests.actions.conftest import OTHER, Actions, action

CREATE = {"subject": "VPN down", "body": "tunnel flaps", "product_area": "VPN"}


def _create(actions: Actions, email: str = "priya@bluebirdretail.com") -> str:
    context = actions.make_context(email)
    (result,) = actions.dispatcher.dispatch_turn([action(Kind.CREATE_TICKET, **CREATE)], context)
    assert result.reference is not None
    return result.reference


def test_create_ticket_writes_ticket_and_done_row(actions: Actions) -> None:
    context = actions.make_context(priority="P2")
    (result,) = actions.dispatcher.dispatch_turn([action(Kind.CREATE_TICKET, **CREATE)], context)
    assert result.status is ActionStatus.DONE
    assert result.customer_line == f"I opened ticket {result.reference} for you."
    ticket = actions.tickets.get_ticket(result.reference or "")
    assert ticket is not None
    assert (ticket.customer_id, ticket.priority, ticket.status) == ("ACC-1002", "P2", "open")
    (row,) = actions.store.list_simulated_actions(context.conversation_id)
    assert row.status is SimulatedActionStatus.DONE
    assert row.result is not None and row.result["reference"] == result.reference
    assert row.message_id == context.message_id


def test_duplicate_dispatch_replays_without_second_ticket(actions: Actions) -> None:
    context = actions.make_context()
    plan = [action(Kind.CREATE_TICKET, **CREATE)]
    (first,) = actions.dispatcher.dispatch_turn(plan, context)
    (again,) = actions.dispatcher.dispatch_turn(plan, context)
    assert (first.replayed, again.replayed) == (False, True)
    assert again.model_copy(update={"replayed": False}) == first
    assert len(actions.store.list_simulated_actions(context.conversation_id)) == 1
    created = actions.conn.execute("select count(*) from tickets where subject = 'VPN down'").fetchone()
    assert created == (1,)


def test_update_each_field_and_close(actions: Actions) -> None:
    ticket_id = _create(actions)
    context = actions.make_context()
    updates = [
        {"status": "pending_customer"},
        {"site_id": "SITE-9"},
        {"priority": "P1"},
        {"status": "open", "site_id": "SITE-8", "priority": "P4"},
    ]
    results = actions.dispatcher.dispatch_turn(
        [action(Kind.UPDATE_TICKET, ticket_id=ticket_id, **u) for u in updates]
        + [action(Kind.CLOSE_TICKET, ticket_id=ticket_id)],
        context,
    )
    assert [r.status for r in results] == [ActionStatus.DONE] * 5
    ticket = actions.tickets.get_ticket(ticket_id)
    assert ticket is not None
    assert (ticket.status, ticket.site_id, ticket.priority) == ("closed", "SITE-8", "P4")
    assert results[0].customer_line == f"I updated ticket {ticket_id}."
    assert results[-1].customer_line == f"I closed ticket {ticket_id}."


def test_unknown_ticket_fails_with_failed_row(actions: Actions) -> None:
    context = actions.make_context()
    (result,) = actions.dispatcher.dispatch_turn([action(Kind.CLOSE_TICKET, ticket_id="TCK-1")], context)
    assert result.status is ActionStatus.FAILED
    assert result.customer_line is not None and "could not complete" in result.customer_line
    (row,) = actions.store.list_simulated_actions(context.conversation_id)
    assert row.status is SimulatedActionStatus.FAILED


def test_other_accounts_ticket_is_refused_and_untouched(actions: Actions) -> None:
    ticket_id = _create(actions)
    context = actions.make_context(OTHER)
    (result,) = actions.dispatcher.dispatch_turn([action(Kind.UPDATE_TICKET, ticket_id=ticket_id, status="closed")], context)
    assert result.status is ActionStatus.REFUSED
    ticket = actions.tickets.get_ticket(ticket_id)
    assert ticket is not None and ticket.status == "open"


def test_invalid_payload_is_invalid_and_writes_nothing(actions: Actions) -> None:
    context = actions.make_context()
    before = actions.conn.execute("select count(*) from tickets").fetchone()
    (result,) = actions.dispatcher.dispatch_turn([action(Kind.CREATE_TICKET, subject="only")], context)
    assert result.status is ActionStatus.INVALID
    assert actions.conn.execute("select count(*) from tickets").fetchone() == before


def test_unidentified_caller_cannot_open_a_ticket(actions: Actions) -> None:
    context = actions.make_context("mark@example.com")
    (result,) = actions.dispatcher.dispatch_turn([action(Kind.CREATE_TICKET, **CREATE)], context)
    assert result.status is ActionStatus.INVALID


def test_stored_claim_without_result_reports_unknown_outcome(actions: Actions) -> None:
    context = actions.make_context()
    plan = [action(Kind.CREATE_TICKET, **CREATE)]
    actions.store.claim_action(
        context.conversation_id, context.message_id, None, "CREATE_TICKET",
        f"{context.message_id}:CREATE_TICKET:0", CREATE, actions.clock.now(),
    )
    (result,) = actions.dispatcher.dispatch_turn(plan, context)
    assert result.status is ActionStatus.FAILED
    assert "outcome unknown" in result.detail
    assert actions.conn.execute("select count(*) from tickets where subject = 'VPN down'").fetchone() == (0,)
