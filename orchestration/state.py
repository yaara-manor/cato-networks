import logging
from collections.abc import Callable
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, ValidationError

from orchestration.degradation import DegradationNotice, DegradedSource
from storage import StateSnapshot

logger = logging.getLogger(__name__)

STATE_VERSION = 2
# MIGRATIONS[v] is a pure step turning a version-v payload into version v+1.
# v1 -> v2 only added `active_ticket_id` (defaults); the step exists so an old worker refuses v2 snapshots.
MIGRATIONS: dict[int, Callable[[dict[str, Any]], dict[str, Any]]] = {1: lambda data: data}
MAX_CLARIFICATION_TURNS = 3


class StateVersionError(Exception):
    """Stored snapshot is newer than this code; refuse rather than overwrite it."""


class OrchestratorState(BaseModel):
    """Workflow-owned carry-over, stored as `StateSnapshot.data`."""

    model_config = ConfigDict(frozen=True)

    clarification_turns: int = 0  # consecutive turns that ended in a scoping question
    oncall_paged: bool = False
    active_ticket_id: str | None = None  # ticket opened in this conversation; credit/MFA approvals bind to it
    notice_shown: frozenset[DegradedSource] = frozenset()  # sources whose outage was already disclosed

    @classmethod
    def from_snapshot(cls, snapshot: StateSnapshot) -> Self:
        """Empty or corrupt data rebuilds to safe defaults; older versions migrate; newer ones raise."""
        if snapshot.version > STATE_VERSION:
            raise StateVersionError(f"state version {snapshot.version} > supported {STATE_VERSION}")
        if not snapshot.data:
            return cls()
        data = snapshot.data
        try:
            for version in range(snapshot.version, STATE_VERSION):
                data = MIGRATIONS[version](data)
            return cls.model_validate(data)
        except (ValidationError, KeyError, TypeError, ValueError):
            logger.warning("state snapshot v%s unreadable, rebuilt empty", snapshot.version)
            return cls()

    def to_snapshot(self) -> StateSnapshot:
        return StateSnapshot(version=STATE_VERSION, data=self.model_dump(mode="json"))

    def clarification_exhausted(self) -> bool:
        return self.clarification_turns >= MAX_CLARIFICATION_TURNS

    def after_scoping_question(self) -> Self:
        return self.model_copy(update={"clarification_turns": self.clarification_turns + 1})

    def after_scoping_resolved(self) -> Self:
        return self.model_copy(update={"clarification_turns": 0})

    def with_oncall_paged(self) -> Self:
        return self.model_copy(update={"oncall_paged": True})

    def with_active_ticket(self, ticket_id: str | None) -> Self:
        return self.model_copy(update={"active_ticket_id": ticket_id})

    def unseen(self, notices: tuple[DegradationNotice, ...]) -> tuple[DegradationNotice, ...]:
        return tuple(n for n in notices if n.source not in self.notice_shown)

    def with_degraded(self, notices: tuple[DegradationNotice, ...]) -> Self:
        """Disclosed = degraded this turn: a healthy source drops out, so a later outage is disclosed again."""
        return self.model_copy(update={"notice_shown": frozenset(n.source for n in notices)})
