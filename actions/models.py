from enum import StrEnum
from typing import Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from agents.models import SupportAction, SupportActionKind
from core.models import TicketPriority
from services.models import CallerIdentity


class _ActionModel(BaseModel):
    model_config = ConfigDict(frozen=True)


class ActionStatus(StrEnum):
    DONE = "DONE"
    FAILED = "FAILED"
    INVALID = "INVALID"
    REFUSED = "REFUSED"


class DispatchContext(_ActionModel):
    identity: CallerIdentity
    priority: TicketPriority
    sev1_corroborated: bool
    already_paged: bool
    conversation_id: UUID
    message_id: UUID


class DispatchRequest(_ActionModel):
    action: SupportAction
    idempotency_key: str
    context: DispatchContext
    approval_id: UUID | None = None


class ActionResult(_ActionModel):
    """Persisted inside `TurnResult` (`messages.result`): plain enum/str/bool fields only."""

    kind: SupportActionKind
    status: ActionStatus
    replayed: bool = False
    reference: str | None = None
    detail: str  # fixed text: never a raw payload or exception message
    customer_line: str | None = None

    @classmethod
    def done(cls, kind: SupportActionKind, reference: str, customer_line: str | None) -> Self:
        return cls(kind=kind, status=ActionStatus.DONE, reference=reference, detail="done", customer_line=customer_line)

    @classmethod
    def failed(cls, kind: SupportActionKind, detail: str) -> Self:
        return cls._unsuccessful(kind, ActionStatus.FAILED, detail)

    @classmethod
    def invalid(cls, kind: SupportActionKind, detail: str) -> Self:
        return cls._unsuccessful(kind, ActionStatus.INVALID, detail)

    @classmethod
    def refused(cls, kind: SupportActionKind, detail: str, silent: bool = False) -> Self:
        return cls._unsuccessful(kind, ActionStatus.REFUSED, detail, announce=not silent)

    @classmethod
    def _unsuccessful(cls, kind: SupportActionKind, status: ActionStatus, detail: str, announce: bool = True) -> Self:
        line = f"We could not complete the {kind.value.lower().replace('_', ' ')} request; a support engineer will follow up."
        return cls(kind=kind, status=status, detail=detail, customer_line=line if announce else None)

    def as_replay(self) -> Self:
        return self.model_copy(update={"replayed": True})
