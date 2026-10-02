from typing import Any
from uuid import uuid4

import psycopg
import pytest

from agents import SupportAction, SupportActionKind
from orchestration.recorder import TurnRecorder
from storage import MessageSender
from tests.orchestration.conftest import PRIYA, Harness, Scripted

PAGE = SupportAction(kind=SupportActionKind.PAGE_ON_CALL, payload={"summary": "country down"}, reason="sev1")
TICKET = SupportAction(
    kind=SupportActionKind.CREATE_TICKET,
    payload={"subject": "Crash ticket", "body": "b", "product_area": "VPN"},
    reason="track",
)


class Crash(BaseException):
    """Process death: not an `Exception`, so the workflow's failure boundary does not catch it."""


def test_crash_after_dispatch_then_retry_yields_one_ticket_one_page_one_reply(
    harness: Harness, scripted: Scripted, conn: psycopg.Connection[Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    scripted.decision = scripted.decision.model_copy(update={"priority": "P1"})
    scripted.sev1, scripted.actions = True, (TICKET, PAGE)
    conversation_id, message_id = harness.new_conversation(PRIYA), uuid4()
    workflow = harness.workflow(scripted, None)
    real = TurnRecorder.complete_turn
    crashes = [True]

    def crash_once(self: TurnRecorder, *args: Any, **kwargs: Any) -> None:
        if crashes.pop() if crashes else False:
            raise Crash
        real(self, *args, **kwargs)

    monkeypatch.setattr(TurnRecorder, "complete_turn", crash_once)
    with pytest.raises(Crash):
        workflow.run_turn(conversation_id, "country down", message_id)
    retried = workflow.run_turn(conversation_id, "country down", message_id)

    assert [r.status.value for r in retried.action_results] == ["DONE", "DONE"]
    assert conn.execute("select count(*) from tickets where subject = 'Crash ticket'").fetchone() == (1,)
    rows = conn.execute(
        "select count(*) from simulated_actions where conversation_id = %s and status = 'DONE'", (conversation_id,)
    ).fetchone()
    assert rows == (2,)
    replies = conn.execute(
        "select count(*) from messages where conversation_id = %s and sender = %s",
        (conversation_id, MessageSender.AGENT.value),
    ).fetchone()
    assert replies == (1,)
