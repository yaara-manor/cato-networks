from typing import Any
from uuid import uuid4

import psycopg
import pytest

from actions import ActionStatus
from agents import SupportAction, SupportActionKind
from orchestration import TurnResult
from orchestration.canned import NEEDS_TICKET_FIRST
from orchestration.state import OrchestratorState
from services import TicketService
from storage import StateStore
from tests.orchestration.conftest import PRIYA, Harness, Scripted

KIND = SupportActionKind
TICKET = SupportAction(
    kind=KIND.CREATE_TICKET,
    payload={"subject": "Site down", "body": "tunnel down", "product_area": "VPN"},
    reason="track",
)
CREDIT = SupportAction(
    kind=KIND.CREDIT,
    payload={"ticket_id": "TCK-hallucinated", "amount": "50", "incident_id": "INC-1", "period": "2026-09"},
    reason="outage",
)


def _state(conn: psycopg.Connection[Any], conversation_id: Any) -> OrchestratorState:
    snapshot = StateStore(conn).rehydrate(conversation_id)
    assert snapshot is not None
    return OrchestratorState.from_snapshot(snapshot.conversation.state)


def _ticket_status(conn: psycopg.Connection[Any], ticket_id: str) -> str:
    row = conn.execute("select status from tickets where ticket_id = %s", (ticket_id,)).fetchone()
    assert row is not None
    return str(row[0])


def test_ticket_confirmation_follows_agent_text_and_state_keeps_ticket(
    harness: Harness, scripted: Scripted, conn: psycopg.Connection[Any]
) -> None:
    scripted.actions = (TICKET,)
    conversation_id = harness.new_conversation(PRIYA)
    result = harness.workflow(scripted, None).run_turn(conversation_id, "site down", uuid4())
    ticket_id = _state(conn, conversation_id).active_ticket_id
    assert ticket_id is not None
    assert result.reply == f"Here is your answer.\n\nI opened ticket {ticket_id} for you."
    assert [r.reference for r in result.action_results] == [ticket_id]


def test_credit_binds_to_state_ticket_and_marks_it_pending(
    harness: Harness, scripted: Scripted, conn: psycopg.Connection[Any]
) -> None:
    conversation_id = harness.new_conversation(PRIYA)
    workflow = harness.workflow(scripted, None)
    scripted.actions = (TICKET,)
    workflow.run_turn(conversation_id, "site down", uuid4())
    ticket_id = _state(conn, conversation_id).active_ticket_id
    assert ticket_id is not None

    scripted.actions = (CREDIT,)  # the model wrote a wrong ticket id
    result = workflow.run_turn(conversation_id, "credit please", uuid4())

    assert scripted.inputs["resolution"][-1][0].known_ticket_id == ticket_id
    (approval,) = StateStore(conn).list_approvals(conversation_id)
    assert approval.payload["ticket_id"] == ticket_id
    assert [a.payload["ticket_id"] for a in result.pending_actions] == [ticket_id]
    assert _ticket_status(conn, ticket_id) == "pending_approval"
    credit_rows = [a for a in StateStore(conn).list_simulated_actions(conversation_id) if a.kind == "CREDIT"]
    assert credit_rows == []


def test_create_and_credit_in_one_plan_bind_to_the_new_ticket(
    harness: Harness, scripted: Scripted, conn: psycopg.Connection[Any]
) -> None:
    scripted.actions = (TICKET, CREDIT)
    conversation_id = harness.new_conversation(PRIYA)
    harness.workflow(scripted, None).run_turn(conversation_id, "site down, credit", uuid4())
    ticket_id = _state(conn, conversation_id).active_ticket_id
    (approval,) = StateStore(conn).list_approvals(conversation_id)
    assert ticket_id is not None and approval.payload["ticket_id"] == ticket_id
    assert _ticket_status(conn, ticket_id) == "pending_approval"


def test_credit_without_ticket_creates_no_approval(
    harness: Harness, scripted: Scripted, conn: psycopg.Connection[Any]
) -> None:
    scripted.actions = (CREDIT,)
    conversation_id = harness.new_conversation(PRIYA)
    result = harness.workflow(scripted, None).run_turn(conversation_id, "credit please", uuid4())
    assert StateStore(conn).list_approvals(conversation_id) == []
    assert result.pending_actions == () and result.reply.endswith(NEEDS_TICKET_FIRST)


def test_handler_failure_never_reads_as_success(
    harness: Harness, scripted: Scripted, conn: psycopg.Connection[Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(*args: object, **kwargs: object) -> None:
        raise RuntimeError("db exploded")

    monkeypatch.setattr(TicketService, "create_ticket", boom)
    scripted.actions = (TICKET,)
    conversation_id = harness.new_conversation(PRIYA)
    result = harness.workflow(scripted, None).run_turn(conversation_id, "site down", uuid4())
    assert [r.status for r in result.action_results] == [ActionStatus.FAILED]
    assert "could not complete the create ticket request" in result.reply
    assert result.escalation_offered
    assert "db exploded" not in result.reply
    assert _state(conn, conversation_id).active_ticket_id is None


def test_duplicate_message_id_replays_results_without_second_ticket(
    harness: Harness, scripted: Scripted, conn: psycopg.Connection[Any]
) -> None:
    scripted.actions = (TICKET,)
    conversation_id = harness.new_conversation(PRIYA)
    message_id = uuid4()
    workflow = harness.workflow(scripted, None)
    first = workflow.run_turn(conversation_id, "site down", message_id)
    again = workflow.run_turn(conversation_id, "site down", message_id)
    assert again.action_results == first.action_results and again.reply == first.reply
    assert conn.execute("select count(*) from tickets where subject = 'Site down'").fetchone() == (1,)


def test_active_ticket_survives_restart(harness: Harness, scripted: Scripted, conn: psycopg.Connection[Any]) -> None:
    scripted.actions = (TICKET,)
    conversation_id = harness.new_conversation(PRIYA)
    harness.workflow(scripted, None).run_turn(conversation_id, "site down", uuid4())
    ticket_id = _state(conn, conversation_id).active_ticket_id
    scripted.actions = ()
    with harness.connect() as fresh:
        harness.workflow(scripted, fresh).run_turn(conversation_id, "any news?", uuid4())
    assert scripted.inputs["resolution"][-1][0].known_ticket_id == ticket_id


def test_action_results_round_trip_and_legacy_envelope_validates(
    harness: Harness, scripted: Scripted
) -> None:
    scripted.actions = (TICKET,)
    result = harness.workflow(scripted, None).run_turn(harness.new_conversation(PRIYA), "site down", uuid4())
    assert TurnResult.model_validate(result.model_dump(mode="json")) == result
    legacy = TurnResult.model_validate({"reply": "x", "path": [], "executable_actions": [{"kind": "CREATE_TICKET"}]})
    assert legacy.action_results == ()
