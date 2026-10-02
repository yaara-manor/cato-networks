from datetime import UTC, datetime
from uuid import uuid4

import pytest

from guardrails import ActionType, ApprovalStatus, ApprovedGrant, SessionGuardHistory, check_outgoing_message, redact
from services.approval_notice import ApprovalNotice
from storage import Approval

NOW = datetime(2026, 10, 2, 9, 0, tzinfo=UTC)
PAYLOADS = {
    ActionType.CREDIT: {"ticket_id": "TCK-77", "amount": "500", "currency": "USD", "incident_id": "INC-SECRET-9"},
    ActionType.MFA_RESET: {"ticket_id": "TCK-77", "user_email": "bob@bluebirdretail.com"},
}
EDITS = {
    ActionType.CREDIT: {"ticket_id": "TCK-77", "amount": "300", "currency": "USD", "incident_id": "INC-SECRET-9"},
    ActionType.MFA_RESET: {"ticket_id": "TCK-77", "user_email": "carol@bluebirdretail.com"},
}
ORIGINAL = {ActionType.CREDIT: "500", ActionType.MFA_RESET: "bob@bluebirdretail.com"}
SHOWN = {ActionType.CREDIT: "300", ActionType.MFA_RESET: "carol@bluebirdretail.com"}
SUPPORTED = [(t, s) for t in PAYLOADS for s in (ApprovalStatus.APPROVED, ApprovalStatus.EDITED, ApprovalStatus.REJECTED)]


def _approval(action_type: ActionType, status: ApprovalStatus, reason: str | None = None) -> Approval:
    return Approval(
        id=uuid4(),
        conversation_id=uuid4(),
        message_id=uuid4(),
        action_type=action_type,
        payload=PAYLOADS[action_type],
        status=status,
        idempotency_key="k",
        reviewer_notes="INTERNAL-NOTE",
        edited_payload=EDITS[action_type] if status is ApprovalStatus.EDITED else None,
        requested_at=NOW,
        resolved_at=NOW,
        customer_reason=reason,
    )


@pytest.mark.parametrize(("action_type", "status"), SUPPORTED)
def test_notice_shows_only_allowlisted_effective_values(action_type: ActionType, status: ApprovalStatus) -> None:
    approval = _approval(action_type, status)
    text = ApprovalNotice.from_approval(approval).text
    assert "INTERNAL-NOTE" not in text and "TCK-77" not in text and "INC-SECRET-9" not in text
    assert redact(text).text == text
    grants = (ApprovedGrant(action_type=action_type, approval_id=approval.id, payload=approval.effective_payload),)
    if status is ApprovalStatus.REJECTED:
        assert not check_outgoing_message(text, SessionGuardHistory(), ())
        return
    assert (SHOWN if status is ApprovalStatus.EDITED else ORIGINAL)[action_type] in text
    assert not check_outgoing_message(text, SessionGuardHistory(), grants)
    if action_type is ActionType.CREDIT:  # pins why grants exist
        assert check_outgoing_message(text, SessionGuardHistory(), ())


def test_rejected_notice_appends_customer_reason_never_reviewer_notes() -> None:
    rejected = _approval(ActionType.CREDIT, ApprovalStatus.REJECTED, "Outside SLA window")
    text = ApprovalNotice.from_approval(rejected).text
    assert "Reason: Outside SLA window" in text and "INTERNAL-NOTE" not in text
    assert text.endswith("request an engineer.")


@pytest.mark.parametrize("action_type", [ActionType.CLOSE_TICKET, ActionType.PAGE_ON_CALL])
def test_unsupported_type_and_pending_raise(action_type: ActionType) -> None:
    with pytest.raises(ValueError):
        ApprovalNotice.from_approval(_approval(ActionType.CREDIT, ApprovalStatus.PENDING))
    unsupported = _approval(ActionType.CREDIT, ApprovalStatus.APPROVED).model_copy(update={"action_type": action_type})
    with pytest.raises(ValueError):
        ApprovalNotice.from_approval(unsupported)
