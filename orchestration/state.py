from typing import Self

from pydantic import BaseModel, ConfigDict, ValidationError

from storage import StateSnapshot

SCHEMA_VERSION = 1
MAX_CLARIFICATION_TURNS = 3


class OrchestratorState(BaseModel):
    """Workflow-owned carry-over, stored as `StateSnapshot.data`."""

    model_config = ConfigDict(frozen=True)

    clarification_turns: int = 0  # consecutive turns that ended in a scoping question
    oncall_paged: bool = False

    @classmethod
    def from_snapshot(cls, snapshot: StateSnapshot) -> Self:
        """Fail safe: unknown version or malformed data starts from empty."""
        if snapshot.version != SCHEMA_VERSION:
            return cls()
        try:
            return cls.model_validate(snapshot.data)
        except ValidationError:
            return cls()

    def to_snapshot(self) -> StateSnapshot:
        return StateSnapshot(version=SCHEMA_VERSION, data=self.model_dump(mode="json"))

    def clarification_exhausted(self) -> bool:
        return self.clarification_turns >= MAX_CLARIFICATION_TURNS

    def after_scoping_question(self) -> Self:
        return self.model_copy(update={"clarification_turns": self.clarification_turns + 1})

    def after_scoping_resolved(self) -> Self:
        return self.model_copy(update={"clarification_turns": 0})

    def with_oncall_paged(self) -> Self:
        return self.model_copy(update={"oncall_paged": True})
