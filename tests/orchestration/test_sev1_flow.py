from typing import Any
from uuid import UUID, uuid4

import psycopg

from agents import SupportAction, SupportActionKind
from core.clock import SimulationClock
from storage import SimulatedActionStatus, StateSnapshot, StateStore
from tests.orchestration.conftest import PRIYA, Harness, Scripted

PAGE = SupportAction(kind=SupportActionKind.PAGE_ON_CALL, payload={"summary": "country down"}, reason="sev1")


def _p1(scripted: Scripted, sev1: bool = True) -> Scripted:
    scripted.decision = scripted.decision.model_copy(update={"priority": "P1"})
    scripted.sev1, scripted.actions = sev1, (PAGE,)
    return scripted


def _rows(conn: psycopg.Connection[Any], conversation_id: UUID) -> Any:
    return StateStore(conn).list_simulated_actions(conversation_id)


def test_corroborated_p1_pages_and_confirms(harness: Harness, scripted: Scripted, conn: psycopg.Connection[Any]) -> None:
    conversation_id = harness.new_conversation(PRIYA)
    result = harness.workflow(_p1(scripted), None).run_turn(conversation_id, "country down", uuid4())
    (row,) = _rows(conn, conversation_id)
    assert row.status is SimulatedActionStatus.DONE
    incident = row.result["reference"]
    assert result.reply.endswith(
        f"I paged the on-call engineer (incident {incident}); expect acknowledgement within 15 minutes."
    )


def test_uncorroborated_page_is_denied_in_reply_and_writes_nothing(
    harness: Harness, scripted: Scripted, conn: psycopg.Connection[Any]
) -> None:
    conversation_id = harness.new_conversation(PRIYA)
    result = harness.workflow(_p1(scripted, sev1=False), None).run_turn(conversation_id, "one site down", uuid4())
    assert _rows(conn, conversation_id) == [] and "paged" not in result.reply.replace("earlier page", "")
    assert result.action_results == ()


def test_wiped_state_cannot_cause_a_second_page_or_repeat_line(
    harness: Harness, scripted: Scripted, conn: psycopg.Connection[Any]
) -> None:
    conversation_id = harness.new_conversation(PRIYA)
    workflow = harness.workflow(_p1(scripted), None)
    workflow.run_turn(conversation_id, "country down", uuid4())
    StateStore(conn).save_state(conversation_id, StateSnapshot(version=1, data={}), SimulationClock().now())
    again = workflow.run_turn(conversation_id, "still down", uuid4())
    assert [r.status.value for r in again.action_results] == ["REFUSED"]
    assert "paged the on-call" not in again.reply
    assert [r.status for r in _rows(conn, conversation_id)] == [SimulatedActionStatus.DONE]
