import threading
import time
from collections.abc import Callable, Iterator
from contextlib import closing
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import psycopg
import pytest

from actions import ActionDispatcher, ActionResult, DispatchContext
from agents import AgentRun, SupportAction, SupportActionKind, SupportDeps, TriageInput, TriageResult
from agents.models import SupportActionKind as Kind
from core.config import settings
from guardrails import ApprovalStatus
from orchestration.canned import AGENT_FAILURE_PAUSE
from services.approval_models import ReviewerDecision, SettleOutcome
from storage import Approval, ApprovalResolution, ApprovalStateError, ConversationStage, MessageSender, StateStore
from tests.approval_desk import Desk
from tests.orchestration.conftest import PRIYA, Harness, Scripted

TICKET = SupportAction(
    kind=Kind.CREATE_TICKET,
    payload={"subject": "Site down", "body": "tunnel down", "product_area": "VPN"},
    reason="track",
)
CREDIT = SupportAction(
    kind=Kind.CREDIT,
    payload={"ticket_id": "x", "amount": "500", "incident_id": "INC-1", "period": "2026-09"},
    reason="outage",
)
APPROVE = ApprovalResolution(status=ApprovalStatus.APPROVED)
PROMISE_500 = "We will issue a $500 service credit."
PROMISE_5000 = "We will issue a $5,000 service credit."


@dataclass
class Gated(Scripted):
    """Blocks in triage until `release` is set; `entered` marks that the turn is open."""

    entered: threading.Event = field(default_factory=threading.Event)
    release: threading.Event = field(default_factory=threading.Event)

    def triage(self, data: TriageInput, deps: SupportDeps) -> AgentRun[TriageResult]:
        self.entered.set()
        assert self.release.wait(10)
        return super().triage(data, deps)


class _OnceFailingDispatcher(ActionDispatcher):
    """Reports FAILED until `works`; replays real results afterwards."""

    works = False

    def dispatch_approved(self, approval: Approval, context: DispatchContext) -> ActionResult:
        if not self.works:
            return ActionResult.failed(SupportActionKind.CREDIT, "boom")
        return super().dispatch_approved(approval, context)


@pytest.fixture
def desk(conn: psycopg.Connection[Any]) -> Desk:
    return Desk.create(conn)  # harness owns row cleanup


@pytest.fixture
def fresh_connection() -> Iterator[Callable[[], psycopg.Connection[Any]]]:
    opened: list[psycopg.Connection[Any]] = []

    def connect() -> psycopg.Connection[Any]:
        opened.append(psycopg.connect(settings.database_url, autocommit=True))
        return opened[-1]

    yield connect
    for connection in opened:
        connection.close()


def _propose(harness: Harness, scripted: Scripted, conn: psycopg.Connection[Any]) -> tuple[UUID, Approval]:
    conversation_id = harness.new_conversation(PRIYA)
    scripted.actions = (TICKET, CREDIT)
    harness.workflow(scripted, None).run_turn(conversation_id, "credit please", uuid4())
    scripted.actions = ()
    (approval,) = StateStore(conn).list_approvals(conversation_id)
    return conversation_id, approval


def _events(conn: psycopg.Connection[Any], conversation_id: UUID) -> list[str]:
    store = StateStore(conn)
    return [m.content for m in store.list_messages(conversation_id) if m.turn > 1 and m.sender is MessageSender.AGENT]


def _credit_rows(conn: psycopg.Connection[Any], conversation_id: UUID) -> int:
    return len([a for a in StateStore(conn).list_simulated_actions(conversation_id) if a.kind == "CREDIT"])


def test_resume_after_restart_settles_only_the_right_conversation(
    harness: Harness,
    scripted: Scripted,
    conn: psycopg.Connection[Any],
    desk: Desk,
    fresh_connection: Callable[[], psycopg.Connection[Any]],
) -> None:
    cid, approval = _propose(harness, scripted, conn)
    other_cid, _ = _propose(harness, scripted, conn)
    desk.service.resolve(ReviewerDecision(approval_id=approval.id, resolution=APPROVE))  # crash before settle

    restarted = fresh_connection()  # nothing survives but Postgres
    outcomes = Desk.create(restarted).service.settle_unsettled()
    assert outcomes == (SettleOutcome.SETTLED,)
    assert len(_events(restarted, cid)) == 1 and _events(restarted, other_cid) == []
    assert _credit_rows(restarted, cid) == 1

    scripted.reply = PROMISE_500
    workflow = harness.workflow(scripted, restarted)
    assert workflow.run_turn(cid, "so is it done?", uuid4()).reply == PROMISE_500
    history = [turn.content for turn in scripted.inputs["resolution"][-1][0].history]
    assert any("approved" in line for line in history)
    scripted.reply = PROMISE_5000
    assert workflow.run_turn(cid, "and more?", uuid4()).reply == AGENT_FAILURE_PAUSE


def test_crash_after_dispatch_before_settle_commit_yields_one_effect_one_notice(
    harness: Harness, scripted: Scripted, conn: psycopg.Connection[Any], desk: Desk, monkeypatch: pytest.MonkeyPatch
) -> None:
    cid, approval = _propose(harness, scripted, conn)
    real_settle = desk.store.settle_approval
    calls: list[int] = []

    def crash_once(approval_id: UUID, content: str, at: datetime) -> Any:
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("process died")
        return real_settle(approval_id, content, at)

    monkeypatch.setattr(desk.store, "settle_approval", crash_once)
    with pytest.raises(RuntimeError):
        desk.service.decide(ReviewerDecision(approval_id=approval.id, resolution=APPROVE))
    assert _events(conn, cid) == [] and _credit_rows(conn, cid) == 1

    assert desk.service.settle_unsettled() == (SettleOutcome.SETTLED,)
    assert len(_events(conn, cid)) == 1 and _credit_rows(conn, cid) == 1


def test_settle_waits_for_an_open_turn_and_lands_in_a_later_turn(
    harness: Harness, scripted: Scripted, conn: psycopg.Connection[Any], fresh_connection: Callable[[], Any]
) -> None:
    cid, approval = _propose(harness, scripted, conn)
    StateStore(conn).resolve_approval(approval.id, APPROVE, datetime.now(UTC))
    gated = Gated(reply="Real answer.")
    turn_workflow = harness.workflow(gated, fresh_connection())
    turn = threading.Thread(target=lambda: turn_workflow.run_turn(cid, "still chatting", uuid4()))
    turn.start()
    assert gated.entered.wait(10)

    outcome: list[SettleOutcome] = []
    settling = Desk.create(fresh_connection()).service
    settler = threading.Thread(target=lambda: outcome.append(settling.settle(approval.id)))
    settler.start()
    time.sleep(0.5)
    assert outcome == [] and _events(conn, cid) == []  # blocked on the turn lock
    gated.release.set()
    turn.join(15)
    settler.join(15)

    store = StateStore(conn)
    messages = [m for m in store.list_messages(cid) if m.turn > 1]
    assert [m.content for m in messages][0:2] == ["still chatting", "Real answer."]
    assert messages[1].turn == messages[0].turn and messages[2].turn == messages[0].turn + 1
    assert outcome == [SettleOutcome.SETTLED]
    snapshot = store.rehydrate(cid)
    assert snapshot is not None and snapshot.conversation.stage is ConversationStage.IDLE


def test_turn_lock_timeout_is_busy_then_the_sweep_settles(
    harness: Harness,
    scripted: Scripted,
    conn: psycopg.Connection[Any],
    desk: Desk,
    fresh_connection: Callable[[], psycopg.Connection[Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cid, approval = _propose(harness, scripted, conn)
    monkeypatch.setattr(settings, "turn_lock_timeout_s", 0.2)
    with closing(fresh_connection()) as holder, StateStore(holder).turn_lock(cid):
        result = desk.service.decide(ReviewerDecision(approval_id=approval.id, resolution=APPROVE))
    assert result.settle is SettleOutcome.BUSY and _events(conn, cid) == []
    assert result.approval.status is ApprovalStatus.APPROVED
    assert desk.service.settle_unsettled() == (SettleOutcome.SETTLED,)
    assert len(_events(conn, cid)) == 1


def test_failed_dispatch_sends_no_notice_and_every_sweep_retries(
    harness: Harness, scripted: Scripted, conn: psycopg.Connection[Any]
) -> None:
    cid, approval = _propose(harness, scripted, conn)
    probe = Desk.create(conn)
    flaky = _OnceFailingDispatcher(probe.store, probe.tickets, probe.clock)
    service = Desk.create(conn, flaky).service
    assert service.resolve(ReviewerDecision(approval_id=approval.id, resolution=APPROVE)).id == approval.id
    for _ in range(2):
        assert service.settle_unsettled() == (SettleOutcome.EXECUTION_FAILED,)
        assert _events(conn, cid) == []
    flaky.works = True
    assert service.settle_unsettled() == (SettleOutcome.SETTLED,)
    assert len(_events(conn, cid)) == 1 and _credit_rows(conn, cid) == 1


def test_edit_binds_the_edited_amount_for_later_replies(
    harness: Harness, scripted: Scripted, conn: psycopg.Connection[Any], desk: Desk
) -> None:
    cid, approval = _propose(harness, scripted, conn)
    edit = ApprovalResolution(status=ApprovalStatus.EDITED, edited_payload=approval.payload | {"amount": "300"})
    result = desk.service.decide(ReviewerDecision(approval_id=approval.id, resolution=edit))
    assert result.settle is SettleOutcome.SETTLED and "300 USD" in _events(conn, cid)[0]
    workflow = harness.workflow(scripted, None)
    scripted.reply = "We will issue a $300 service credit."
    assert workflow.run_turn(cid, "so?", uuid4()).reply == scripted.reply
    scripted.reply = PROMISE_500
    assert workflow.run_turn(cid, "really?", uuid4()).reply == AGENT_FAILURE_PAUSE


def test_second_reviewer_loses_and_the_result_carries_the_outcome(
    harness: Harness, scripted: Scripted, conn: psycopg.Connection[Any], desk: Desk
) -> None:
    cid, approval = _propose(harness, scripted, conn)
    decision = ReviewerDecision(approval_id=approval.id, resolution=APPROVE)
    first = desk.service.decide(decision)
    assert (first.approval.status, first.settle) == (ApprovalStatus.APPROVED, SettleOutcome.SETTLED)
    with pytest.raises(ApprovalStateError, match="already resolved"):
        desk.service.decide(decision)
    assert len(_events(conn, cid)) == 1
