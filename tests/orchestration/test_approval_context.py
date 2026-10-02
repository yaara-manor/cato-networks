from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import psycopg

from agents import SupportAction, SupportActionKind
from agents.base import load_prompt
from guardrails import ApprovalStatus
from orchestration import Workflow
from orchestration.canned import AGENT_FAILURE_PAUSE
from storage import ApprovalResolution, ConversationStage, MessageSender, StateStore
from tests.orchestration.conftest import PRIYA, Harness, Scripted

KIND = SupportActionKind
TICKET = SupportAction(
    kind=KIND.CREATE_TICKET,
    payload={"subject": "Site down", "body": "tunnel down", "product_area": "VPN"},
    reason="track",
)
CREDIT = SupportAction(
    kind=KIND.CREDIT,
    payload={"ticket_id": "x", "amount": "500", "incident_id": "INC-1", "period": "2026-09"},
    reason="outage",
)
NOW = datetime(2026, 10, 2, 9, 0, tzinfo=UTC)
PROMISE_500 = "We will issue a $500 service credit."


def _propose_credit(harness: Harness, scripted: Scripted, conn: psycopg.Connection[Any]) -> tuple[UUID, Workflow, UUID]:
    conversation_id = harness.new_conversation(PRIYA)
    workflow = harness.workflow(scripted, None)
    scripted.actions = (TICKET, CREDIT)
    workflow.run_turn(conversation_id, "site down, credit please", uuid4())
    scripted.actions = ()
    (approval,) = StateStore(conn).list_approvals(conversation_id)
    return conversation_id, workflow, approval.id


def _settle(conn: psycopg.Connection[Any], approval_id: UUID, resolution: ApprovalResolution) -> None:
    store = StateStore(conn)
    store.resolve_approval(approval_id, resolution, NOW)
    store.settle_approval(approval_id, "Your request was reviewed.", NOW)


def _last_resolution_input(scripted: Scripted) -> Any:
    return scripted.inputs["resolution"][-1][0]


def test_pending_status_question_gives_resolution_a_payloadless_view(
    harness: Harness, scripted: Scripted, conn: psycopg.Connection[Any]
) -> None:
    conversation_id, workflow, _ = _propose_credit(harness, scripted, conn)
    workflow.run_turn(conversation_id, "status of my credit?", uuid4())
    data = _last_resolution_input(scripted)
    assert [(v.action_type.value, v.status) for v in data.unsettled_approvals] == [("CREDIT", ApprovalStatus.PENDING)]
    assert "500" not in data.unsettled_approvals[0].model_dump_json()


def test_customer_turn_is_not_blocked_by_pending_approval(
    harness: Harness, scripted: Scripted, conn: psycopg.Connection[Any]
) -> None:
    conversation_id, workflow, approval_id = _propose_credit(harness, scripted, conn)
    result = workflow.run_turn(conversation_id, "another question", uuid4())
    store = StateStore(conn)
    snapshot = store.rehydrate(conversation_id)
    assert result.reply == scripted.reply
    assert snapshot is not None and snapshot.conversation.stage is ConversationStage.IDLE
    approval = store.get_approval(approval_id)
    assert approval is not None and approval.status is ApprovalStatus.PENDING


def test_grant_exists_only_after_settle_and_binds_the_amount(
    harness: Harness, scripted: Scripted, conn: psycopg.Connection[Any]
) -> None:
    conversation_id, workflow, approval_id = _propose_credit(harness, scripted, conn)
    store = StateStore(conn)
    store.resolve_approval(approval_id, ApprovalResolution(status=ApprovalStatus.APPROVED), NOW)
    scripted.reply = PROMISE_500

    unsettled = workflow.run_turn(conversation_id, "so?", uuid4())  # approved but not yet executed/announced
    assert unsettled.reply == AGENT_FAILURE_PAUSE
    assert [v.status for v in _last_resolution_input(scripted).unsettled_approvals] == [ApprovalStatus.APPROVED]
    assert store.list_messages(conversation_id)[-1].sender is MessageSender.SYSTEM

    store.settle_approval(approval_id, "Your credit request was approved.", NOW)
    assert workflow.run_turn(conversation_id, "so?", uuid4()).reply == PROMISE_500
    assert _last_resolution_input(scripted).unsettled_approvals == ()

    scripted.reply = "We will issue a $5,000 service credit."
    assert workflow.run_turn(conversation_id, "more?", uuid4()).reply == AGENT_FAILURE_PAUSE


def test_edited_grant_carries_the_edited_amount(
    harness: Harness, scripted: Scripted, conn: psycopg.Connection[Any]
) -> None:
    conversation_id, workflow, approval_id = _propose_credit(harness, scripted, conn)
    edited = ApprovalResolution(
        status=ApprovalStatus.EDITED, edited_payload=CREDIT.payload | {"amount": "300", "ticket_id": "x"}
    )
    _settle(conn, approval_id, edited)
    scripted.reply = "We will issue a $300 service credit."
    assert workflow.run_turn(conversation_id, "so?", uuid4()).reply == scripted.reply
    scripted.reply = PROMISE_500
    assert workflow.run_turn(conversation_id, "so?", uuid4()).reply == AGENT_FAILURE_PAUSE


def test_replayed_turn_keeps_its_original_envelope_after_approval(
    harness: Harness, scripted: Scripted, conn: psycopg.Connection[Any]
) -> None:
    conversation_id = harness.new_conversation(PRIYA)
    workflow = harness.workflow(scripted, None)
    scripted.actions = (TICKET, CREDIT)
    message_id = uuid4()
    first = workflow.run_turn(conversation_id, "credit please", message_id)
    (approval,) = StateStore(conn).list_approvals(conversation_id)
    _settle(conn, approval.id, ApprovalResolution(status=ApprovalStatus.APPROVED))
    assert workflow.run_turn(conversation_id, "credit please", message_id).pending_actions == first.pending_actions
    assert first.pending_actions


def test_verdict_override_is_denied_without_an_approval_row(
    harness: Harness, scripted: Scripted, conn: psycopg.Connection[Any]
) -> None:
    conversation_id = harness.new_conversation(PRIYA)
    scripted.actions = (SupportAction(kind=KIND.VERDICT_OVERRIDE, payload={"domain": "evil.example"}, reason="x"),)
    result = harness.workflow(scripted, None).run_turn(conversation_id, "whitelist it", uuid4())
    assert "POL-SEC" in result.reply or "Security Ops" in result.reply
    assert StateStore(conn).list_approvals(conversation_id) == []


def test_resolution_prompt_names_the_unsettled_approvals_field() -> None:
    assert "unsettled_approvals" in load_prompt("resolution")
