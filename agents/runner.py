import time
from dataclasses import dataclass

from pydantic_ai import Agent, capture_run_messages
from pydantic_ai.exceptions import UnexpectedModelBehavior
from pydantic_ai.messages import ModelMessage
from pydantic_ai.usage import RunUsage

from agents.base import SupportDeps
from agents.models import AgentRole, AgentTrace


@dataclass(frozen=True)
class RoleOutcome[O]:
    """`output` is None when the model failed; callers map that to their role fallback."""

    output: O | None
    messages: tuple[ModelMessage, ...]
    trace: AgentTrace


def run_role[O](agent: Agent[SupportDeps, O], prompt: str, deps: SupportDeps, role: AgentRole) -> RoleOutcome[O]:
    """Run one agent turn. Only `UnexpectedModelBehavior` is absorbed; transport errors propagate."""
    usage = RunUsage()
    output: O | None = None
    error: str | None = None
    started = time.perf_counter()
    with capture_run_messages() as messages:
        try:
            output = agent.run_sync(prompt, deps=deps, usage=usage).output
        except UnexpectedModelBehavior as exc:
            error = str(exc)
    latency_ms = int((time.perf_counter() - started) * 1000)
    return RoleOutcome(
        output=output,
        messages=tuple(messages),
        trace=AgentTrace.from_run(role, messages, usage, latency_ms, error),
    )
