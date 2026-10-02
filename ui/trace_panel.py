import json
from decimal import Decimal
from typing import Any, Self

import streamlit as st
from pydantic import BaseModel, ConfigDict

from agents import TraceStatus
from storage import AgentRole, ReplayStep, ReplayTurn, TraceReplay

_NONE = "none"


class _View(BaseModel):
    model_config = ConfigDict(frozen=True)


def _dump(data: dict[str, Any] | None) -> str | None:
    return None if data is None else json.dumps(data, indent=2, default=str)


class TraceToolCall(_View):
    """Name, status and latency only: arguments and results never leave the store."""

    tool_name: str
    status: str
    latency_ms: int


class TraceStep(_View):
    agent_role: AgentRole
    status: TraceStatus
    latency_ms: int
    prompt_tokens: int
    completion_tokens: int
    cost_usd: Decimal | None
    tool_calls: tuple[TraceToolCall, ...]
    input_json: str  # redacted at write; shown only when the renderer is asked to
    output_json: str | None

    @classmethod
    def from_replay_step(cls, step: ReplayStep) -> Self:
        trace = step.trace
        return cls(
            agent_role=trace.agent_role,
            status=trace.status,
            latency_ms=trace.latency_ms,
            prompt_tokens=trace.prompt_tokens,
            completion_tokens=trace.completion_tokens,
            cost_usd=trace.cost_usd,
            tool_calls=tuple(
                TraceToolCall(tool_name=c.tool_name, status=c.status, latency_ms=c.latency_ms) for c in step.tool_calls
            ),
            input_json=_dump(trace.input) or "{}",
            output_json=_dump(trace.output),
        )


class TraceTurn(_View):
    turn: int
    customer_text: str | None
    reply: str | None
    is_open: bool  # no reply yet: crashed or still running
    steps: tuple[TraceStep, ...]

    @classmethod
    def from_replay_turn(cls, turn: ReplayTurn) -> Self:
        return cls(
            turn=turn.turn,
            customer_text=turn.customer_message.content if turn.customer_message else None,
            reply=turn.reply.content if turn.reply else None,
            is_open=turn.reply is None,
            steps=tuple(TraceStep.from_replay_step(s) for s in turn.steps),
        )


class TracePanel(_View):
    turns: tuple[TraceTurn, ...]
    total_latency_ms: int
    total_tokens: int
    total_cost_usd: Decimal

    @classmethod
    def from_replay(cls, replay: TraceReplay) -> Self:
        """Turns and steps only: `replay.approvals` and `model_messages` are never read."""
        turns = tuple(TraceTurn.from_replay_turn(t) for t in replay.turns)
        steps = [s for t in turns for s in t.steps]
        return cls(
            turns=turns,
            total_latency_ms=sum(s.latency_ms for s in steps),
            total_tokens=sum(s.prompt_tokens + s.completion_tokens for s in steps),
            total_cost_usd=sum((s.cost_usd or Decimal(0) for s in steps), Decimal(0)),
        )


def _render_step(step: TraceStep, show_io: bool) -> None:
    cost = f" ${step.cost_usd}" if step.cost_usd is not None else ""
    st.text(
        f"{step.agent_role} [{step.status}] {step.latency_ms} ms, "
        f"{step.prompt_tokens}+{step.completion_tokens} tokens{cost}"
    )
    for call in step.tool_calls:
        st.text(f"  tool {call.tool_name} [{call.status}] {call.latency_ms} ms")
    if show_io:
        st.code(step.input_json, language="json")
        st.code(step.output_json or _NONE, language="json")


def _render_turn(turn: TraceTurn, show_io: bool) -> None:
    with st.expander(f"Turn {turn.turn}" + (" (open)" if turn.is_open else "")):
        st.code(turn.customer_text or _NONE, language=None)
        st.code(turn.reply or _NONE, language=None)
        for step in turn.steps:
            _render_step(step, show_io)


def render_trace_panel(panel: TracePanel, show_io: bool = False) -> None:
    """Text only (`st.text`/`st.code`), never HTML. `show_io` is for the reviewer app, off for customers."""
    st.text(f"{panel.total_latency_ms} ms, {panel.total_tokens} tokens, ${panel.total_cost_usd}")
    for turn in panel.turns:
        _render_turn(turn, show_io)
