from collections import defaultdict
from collections.abc import Sequence
from typing import Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from storage.models import (
    Approval,
    MessageSender,
    StoredMessage,
    ToolCallRecord,
    TraceRecord,
)


class _ReplayModel(BaseModel):
    model_config = ConfigDict(frozen=True)


class ReplayStep(_ReplayModel):
    trace: TraceRecord
    tool_calls: tuple[ToolCallRecord, ...]


class ReplayTurn(_ReplayModel):
    turn: int
    customer_message: StoredMessage | None
    steps: tuple[ReplayStep, ...]
    reply: StoredMessage | None


class TraceReplay(_ReplayModel):
    """Whole conversation graph rebuilt from rows alone; steps are flat in seq order."""

    conversation_id: UUID
    turns: tuple[ReplayTurn, ...]
    approvals: tuple[Approval, ...]

    @classmethod
    def from_rows(
        cls,
        conversation_id: UUID,
        messages: Sequence[StoredMessage],
        traces: Sequence[TraceRecord],
        tool_calls: Sequence[ToolCallRecord],
        approvals: Sequence[Approval],
    ) -> Self:
        calls_by_trace: defaultdict[UUID, list[ToolCallRecord]] = defaultdict(list)
        for call in tool_calls:
            calls_by_trace[call.trace_id].append(call)
        turn_numbers = sorted({m.turn for m in messages} | {t.turn for t in traces})
        turns = tuple(
            ReplayTurn(
                turn=number,
                customer_message=next(
                    (m for m in messages if m.turn == number and m.sender is MessageSender.CUSTOMER),
                    None,
                ),
                steps=tuple(
                    ReplayStep(trace=t, tool_calls=tuple(calls_by_trace[t.id]))
                    for t in traces
                    if t.turn == number
                ),
                reply=next(
                    (m for m in messages if m.turn == number and m.sender is not MessageSender.CUSTOMER),
                    None,
                ),
            )
            for number in turn_numbers
        )
        return cls(conversation_id=conversation_id, turns=turns, approvals=tuple(approvals))
