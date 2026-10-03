import importlib

import pytest

from guardrails import ActionType, ApprovalStatus
from services.approval_models import ReviewerDecision, SettleOutcome
from storage import Approval, ApprovalResolution, ApprovalStateError, MessageSender
from tests.approval_desk import ADMIN, MFA, PRIYA, Desk, FlakyDispatcher

APPROVE = ApprovalResolution(status=ApprovalStatus.APPROVED)
REJECT = ApprovalResolution(status=ApprovalStatus.REJECTED, reviewer_notes="INTERNAL-NOTE")


def _edit(approval: Approval, **changes: str) -> ApprovalResolution:
    return ApprovalResolution(status=ApprovalStatus.EDITED, edited_payload=approval.payload | changes)


def _events(desk: Desk, approval: Approval) -> list[str]:
    return [
        m.content for m in desk.store.list_messages(approval.conversation_id) if m.sender is MessageSender.AGENT
    ]


def _effects(desk: Desk, approval: Approval) -> list[str]:
    return [a.kind for a in desk.store.list_simulated_actions(approval.conversation_id) if a.kind == "CREDIT"]


def test_approved_credit_executes_clears_ticket_and_notifies_once(desk: Desk) -> None:
    approval = desk.propose()
    assert desk.ticket_status(approval) == "pending_approval"
    result = desk.service.decide(ReviewerDecision(approval_id=approval.id, resolution=APPROVE))
    assert result.settle is SettleOutcome.SETTLED and result.approval.status is ApprovalStatus.APPROVED
    assert desk.ticket_status(approval) == "open"
    assert _effects(desk, approval) == ["CREDIT"]
    (event,) = _events(desk, approval)
    assert "approved" in event and "500 USD" in event
    assert desk.service.settle(approval.id) is SettleOutcome.ALREADY_SETTLED
    assert len(_events(desk, approval)) == 1 and len(_effects(desk, approval)) == 1


def test_edited_credit_executes_and_announces_the_edited_amount(desk: Desk) -> None:
    approval = desk.propose()
    desk.service.decide(ReviewerDecision(approval_id=approval.id, resolution=_edit(approval, amount="300")))
    (row,) = [a for a in desk.store.list_simulated_actions(approval.conversation_id) if a.kind == "CREDIT"]
    assert row.payload["amount"] == "300"
    (event,) = _events(desk, approval)
    assert "300 USD" in event and "500" not in event


def test_rejected_dispatches_nothing_and_keeps_reviewer_notes_internal(desk: Desk) -> None:
    approval = desk.propose()
    decision = ReviewerDecision(approval_id=approval.id, resolution=REJECT, customer_reason="Outside SLA window")
    result = desk.service.decide(decision)
    assert result.settle is SettleOutcome.SETTLED
    assert _effects(desk, approval) == [] and desk.ticket_status(approval) == "open"
    (event,) = _events(desk, approval)
    assert "Reason: Outside SLA window" in event and "INTERNAL-NOTE" not in event


def test_mfa_reset_lifecycle(desk: Desk) -> None:
    approval = desk.propose(ADMIN, ActionType.MFA_RESET)
    result = desk.service.decide(ReviewerDecision(approval_id=approval.id, resolution=APPROVE))
    assert result.settle is SettleOutcome.SETTLED
    (event,) = _events(desk, approval)
    assert MFA["user_email"] in event


def test_second_decision_loses_and_writes_no_second_message(desk: Desk) -> None:
    approval = desk.propose()
    desk.service.decide(ReviewerDecision(approval_id=approval.id, resolution=APPROVE))
    with pytest.raises(ApprovalStateError):
        desk.service.decide(ReviewerDecision(approval_id=approval.id, resolution=REJECT))
    assert len(_events(desk, approval)) == 1


def test_settle_rejects_pending_and_unknown(desk: Desk) -> None:
    approval = desk.propose()
    with pytest.raises(ApprovalStateError):
        desk.service.settle(approval.id)
    assert [a.id for a in desk.service.list_pending(approval.conversation_id)] == [approval.id]
    assert desk.service.get_approval(approval.id) == approval


@pytest.mark.parametrize("outcome", ["APPROVED", "EDITED", "REJECTED"])
def test_ticket_that_moved_on_is_left_alone(desk: Desk, outcome: str) -> None:
    approval = desk.propose()
    desk.tickets.update_ticket(approval.payload["ticket_id"], status="pending_customer")
    resolution = {"APPROVED": APPROVE, "EDITED": _edit(approval, amount="20"), "REJECTED": REJECT}[outcome]
    desk.service.decide(ReviewerDecision(approval_id=approval.id, resolution=resolution))
    assert desk.ticket_status(approval) == "pending_customer"


def test_ticket_clear_failure_is_traced_and_notice_still_sent(
    desk: Desk, monkeypatch: pytest.MonkeyPatch
) -> None:
    approval = desk.propose()

    def boom(*args: object, **kwargs: object) -> None:
        raise RuntimeError("secret detail")

    monkeypatch.setattr(desk.tickets, "update_ticket", boom)
    result = desk.service.decide(ReviewerDecision(approval_id=approval.id, resolution=APPROVE))
    assert result.settle is SettleOutcome.SETTLED and len(_events(desk, approval)) == 1
    (trace,) = [t for t in desk.store.list_traces(approval.conversation_id) if t.error]
    assert trace.error == "RuntimeError" and trace.agent_role.value == "ORCHESTRATOR"


def test_edit_dropping_or_changing_ticket_id_is_rejected_before_the_cas(desk: Desk) -> None:
    approval = desk.propose()
    dropped = {k: v for k, v in approval.payload.items() if k != "ticket_id"}
    for payload in (dropped, approval.payload | {"ticket_id": "TCK-other"}):
        resolution = ApprovalResolution(status=ApprovalStatus.EDITED, edited_payload=payload)
        with pytest.raises(ApprovalStateError):
            desk.service.resolve(ReviewerDecision(approval_id=approval.id, resolution=resolution))
    assert desk.store.get_approval(approval.id) == approval


def test_edit_that_the_gate_would_deny_is_rejected(desk: Desk) -> None:
    approval = desk.propose(PRIYA, ActionType.MFA_RESET)  # PRIYA is not the registered admin: gate says DENY
    resolution = _edit(approval, user_email="carol@bluebirdretail.com")
    with pytest.raises(ApprovalStateError):
        desk.service.resolve(ReviewerDecision(approval_id=approval.id, resolution=resolution))
    assert desk.store.get_approval(approval.id) == approval


def test_unsafe_customer_reason_is_rejected_before_the_cas(desk: Desk) -> None:
    approval = desk.propose()
    decision = ReviewerDecision(
        approval_id=approval.id, resolution=REJECT, customer_reason="We will issue a $900 service credit."
    )
    with pytest.raises(ApprovalStateError):
        desk.service.resolve(decision)
    assert desk.store.get_approval(approval.id) == approval


def test_failed_dispatch_sends_no_notice_and_the_sweep_retries(desk: Desk) -> None:
    flaky = FlakyDispatcher(desk.store, desk.tickets, desk.clock)
    service = Desk.create(desk.conn, flaky).service
    approval = desk.propose()
    result = service.decide(ReviewerDecision(approval_id=approval.id, resolution=APPROVE))
    assert result.settle is SettleOutcome.EXECUTION_FAILED
    assert _events(desk, approval) == []
    assert approval.id in {a.id for a in desk.store.list_unsettled_approvals(1000)}
    assert desk.ticket_status(approval) == "pending_approval"

    assert SettleOutcome.EXECUTION_FAILED in service.settle_unsettled(1000)
    flaky.works = True
    assert SettleOutcome.SETTLED in service.settle_unsettled(1000)
    assert len(_events(desk, approval)) == 1
    assert approval.id not in {a.id for a in desk.store.list_unsettled_approvals(1000)}


def test_module_import_order_has_no_cycle() -> None:
    importlib.import_module("services")
    importlib.import_module("services.approval_service")
