from typing import Any

import pytest

from actions import ActionStatus, DispatchContext
from agents.models import SupportActionKind as Kind
from guardrails import ActionType
from storage import Approval, ApprovalResolution, ApprovalStatus, SimulatedActionStatus
from tests.actions.conftest import ADMIN, Actions, action

CREDIT = {"ticket_id": "TCK-1", "amount": "50", "currency": "USD", "incident_id": "INC-9", "period": "2026-09"}
MFA = {"ticket_id": "TCK-1", "user_email": "bob@bluebirdretail.com"}
APPROVE = ApprovalResolution(status=ApprovalStatus.APPROVED)


def _approval(
    actions: Actions,
    context: DispatchContext,
    action_type: ActionType = ActionType.CREDIT,
    payload: dict[str, str] | None = None,
    resolution: ApprovalResolution | None = APPROVE,
) -> Approval:
    now = actions.clock.now()
    approval = actions.store.create_approval(
        context.conversation_id, context.message_id, action_type, payload or CREDIT, "k", now
    )
    return actions.store.resolve_approval(approval.id, resolution, now) if resolution else approval


def test_approved_credit_records_event_with_approval_id(actions: Actions) -> None:
    context = actions.make_context()
    approval = _approval(actions, context)
    result = actions.dispatcher.dispatch_approved(approval, context)
    assert result.status is ActionStatus.DONE and result.customer_line is None
    (row,) = actions.store.list_simulated_actions(context.conversation_id)
    assert (row.approval_id, row.message_id, row.idempotency_key) == (approval.id, None, f"approval:{approval.id}")
    assert row.result is not None and row.result["effect"]["amount"] == "50"
    assert actions.dispatcher.dispatch_approved(approval, context).replayed is True


def test_edited_uses_edited_payload_and_keeps_original(actions: Actions) -> None:
    context = actions.make_context()
    edit = ApprovalResolution(status=ApprovalStatus.EDITED, edited_payload=CREDIT | {"amount": "20"})
    approval = _approval(actions, context, resolution=edit)
    actions.dispatcher.dispatch_approved(approval, context)
    (row,) = actions.store.list_simulated_actions(context.conversation_id)
    assert row.result is not None and row.result["effect"]["amount"] == "20"
    assert row.payload["amount"] == "20"
    stored = actions.store.get_approval(approval.id)
    assert stored is not None and stored.payload["amount"] == "50"


def test_edit_that_changes_ticket_is_invalid(actions: Actions) -> None:
    context = actions.make_context()
    dropped = {k: v for k, v in CREDIT.items() if k != "ticket_id"}
    resolution = ApprovalResolution(status=ApprovalStatus.EDITED, edited_payload=dropped)
    approval = _approval(actions, context, resolution=resolution)
    assert actions.dispatcher.dispatch_approved(approval, context).status is ActionStatus.INVALID
    assert actions.store.list_simulated_actions(context.conversation_id) == []


@pytest.mark.parametrize(
    "resolution",
    [None, ApprovalResolution(status=ApprovalStatus.REJECTED)],
    ids=["pending", "rejected"],
)
def test_pending_or_rejected_is_refused_without_row(actions: Actions, resolution: ApprovalResolution | None) -> None:
    context = actions.make_context()
    approval = _approval(actions, context, resolution=resolution)
    assert actions.dispatcher.dispatch_approved(approval, context).status is ActionStatus.REFUSED
    assert actions.store.list_simulated_actions(context.conversation_id) == []


def test_mfa_reset_requires_registered_admin(actions: Actions) -> None:
    member = actions.make_context()
    assert actions.dispatcher.dispatch_approved(
        _approval(actions, member, ActionType.MFA_RESET, MFA), member
    ).status is ActionStatus.REFUSED
    admin = actions.make_context(ADMIN)
    result = actions.dispatcher.dispatch_approved(_approval(actions, admin, ActionType.MFA_RESET, MFA), admin)
    assert result.status is ActionStatus.DONE
    (row,) = actions.store.list_simulated_actions(admin.conversation_id)
    effect: dict[str, Any] = (row.result or {})["effect"]
    assert (effect["is_registered_admin"], effect["requester_email"]) == (True, ADMIN)


def test_verdict_override_is_always_refused(actions: Actions) -> None:
    context = actions.make_context()
    (result,) = actions.dispatcher.dispatch_turn([action(Kind.VERDICT_OVERRIDE)], context)
    assert result.status is ActionStatus.REFUSED


def test_credit_on_turn_path_is_refused(actions: Actions) -> None:
    context = actions.make_context()
    (result,) = actions.dispatcher.dispatch_turn([action(Kind.CREDIT, **CREDIT)], context)
    assert result.status is ActionStatus.REFUSED
    assert actions.store.list_simulated_actions(context.conversation_id) == []


def test_mark_pending_flips_ticket_and_replay_is_noop(actions: Actions) -> None:
    context = actions.make_context()
    (created,) = actions.dispatcher.dispatch_turn(
        [action(Kind.CREATE_TICKET, subject="s", body="b", product_area="Billing")], context
    )
    ticket_id = created.reference or ""
    approval = _approval(actions, context, payload=CREDIT | {"ticket_id": ticket_id}, resolution=None)
    first = actions.dispatcher.mark_pending(approval, context)
    ticket = actions.tickets.get_ticket(ticket_id)
    assert first.status is ActionStatus.DONE and ticket is not None and ticket.status == "pending_approval"
    actions.tickets.update_ticket(ticket_id, status="open")
    assert actions.dispatcher.mark_pending(approval, context).replayed is True
    reopened = actions.tickets.get_ticket(ticket_id)
    assert reopened is not None and reopened.status == "open"
    keys = {r.idempotency_key for r in actions.store.list_simulated_actions(context.conversation_id)}
    assert f"approval:{approval.id}:pending" in keys


def test_handler_failure_is_failed_without_exception_text(
    actions: Actions, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(*args: object, **kwargs: object) -> None:
        raise RuntimeError("secret-token-123")

    monkeypatch.setattr(actions.tickets, "create_ticket", boom)
    context = actions.make_context()
    (result,) = actions.dispatcher.dispatch_turn(
        [action(Kind.CREATE_TICKET, subject="s", body="b", product_area="VPN")], context
    )
    assert result.status is ActionStatus.FAILED
    (row,) = actions.store.list_simulated_actions(context.conversation_id)
    assert row.status is SimulatedActionStatus.FAILED
    assert "secret-token-123" not in str(row.result) and "secret-token-123" not in result.model_dump_json()
