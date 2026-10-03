from collections.abc import Sequence
from typing import Self

from pydantic import BaseModel, ConfigDict

from agents.models import UnsettledApprovalView
from guardrails import ApprovalStatus, ApprovedGrant
from storage import Approval

_GRANTING = {ApprovalStatus.APPROVED, ApprovalStatus.EDITED}


class ApprovalContext(BaseModel):
    """What one conversation's approvals license and owe, derived from a single read."""

    model_config = ConfigDict(frozen=True)

    grants: tuple[ApprovedGrant, ...] = ()
    unsettled: tuple[UnsettledApprovalView, ...] = ()

    @classmethod
    def from_approvals(cls, approvals: Sequence[Approval]) -> Self:
        """A grant exists only once settled (executed and customer notified): never quote an unexecuted amount."""
        return cls(
            grants=tuple(
                ApprovedGrant(action_type=a.action_type, approval_id=a.id, payload=a.effective_payload)
                for a in approvals
                if a.settled_at is not None and a.status in _GRANTING
            ),
            unsettled=tuple(
                UnsettledApprovalView(action_type=a.action_type, status=a.status, requested_at=a.requested_at)
                for a in approvals
                if a.settled_at is None
            ),
        )
