from typing import Any

import psycopg
import pytest

from agents import Intent, TriageDecision, TriageResult
from core.clock import SimulationClock
from orchestration.routing import compose_reply, next_stage_after_triage
from services import CustomerService
from storage import ConversationStage
from tests.orchestration.conftest import PRIYA


@pytest.mark.parametrize(
    ("intent", "scoping", "expected"),
    [
        (Intent.TELEMETRY_DIAGNOSIS, None, ConversationStage.DIAGNOSTICS),
        (Intent.KB_INQUIRY, None, ConversationStage.KNOWLEDGE_RETRIEVAL),
        (Intent.POLICY_REQUEST, None, ConversationStage.KNOWLEDGE_RETRIEVAL),
        (Intent.ADVERSARIAL, None, ConversationStage.RESOLUTION),
        (Intent.TELEMETRY_DIAGNOSIS, "Which site?", ConversationStage.DIAGNOSTICS),
        (Intent.KB_INQUIRY, "Which site?", ConversationStage.RESOLUTION),
    ],
)
def test_next_stage_after_triage(
    conn: psycopg.Connection[Any], intent: Intent, scoping: str | None, expected: ConversationStage
) -> None:
    identity = CustomerService(conn, SimulationClock.frozen()).authenticate_caller(PRIYA)
    decision = TriageDecision(intent=intent, priority="P3", symptom_summary="x", scoping_question=scoping)
    assert next_stage_after_triage(TriageResult(decision=decision, identity=identity)) is expected


def test_compose_reply_orders_notices_message_confirmations_denials() -> None:
    assert compose_reply(("notice",), "answer", ("done",), ("denied",)) == "notice\n\nanswer\n\ndone\n\ndenied"
    assert compose_reply((), "answer", (), ()) == "answer"
