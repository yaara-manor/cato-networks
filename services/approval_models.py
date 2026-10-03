from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from storage import Approval, ApprovalResolution


class _ApprovalModel(BaseModel):
    model_config = ConfigDict(frozen=True)


class ReviewerDecision(_ApprovalModel):
    approval_id: UUID
    resolution: ApprovalResolution
    customer_reason: str | None = None  # customer-safe, guard-checked at resolve time


class SettleOutcome(StrEnum):
    SETTLED = "SETTLED"
    ALREADY_SETTLED = "ALREADY_SETTLED"
    EXECUTION_FAILED = "EXECUTION_FAILED"
    BUSY = "BUSY"


class DecisionResult(_ApprovalModel):
    approval: Approval
    settle: SettleOutcome
