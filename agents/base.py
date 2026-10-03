from collections.abc import Sequence
from dataclasses import dataclass
from functools import cache
from typing import TYPE_CHECKING

from pydantic_ai import Agent, RunContext
from pydantic_ai.models import Model

from agents.models import ConversationTurn
from core.clock import SimulationClock
from core.config import settings
from guardrails import ApprovedGrant, GroundingContext, SessionGuardHistory
from services import CustomerService, TicketService
from services.models import CallerIdentity
from tools.telemetry import TelemetryService

if TYPE_CHECKING:
    # Type-only: importing retrieval.service loads the embedding stack (~3s); production warms it at boot.
    from retrieval.service import RetrievalService


@dataclass(frozen=True)
class SupportDeps:
    clock: SimulationClock
    customers: CustomerService
    tickets: TicketService
    telemetry: TelemetryService
    retrieval: "RetrievalService"
    identity: CallerIdentity
    guard_history: SessionGuardHistory
    approved_grants: tuple[ApprovedGrant, ...] = ()
    grounding: GroundingContext | None = None


@cache
def load_prompt(name: str) -> str:
    text = (settings.repo_root / "prompts" / f"{name}.md").read_text(encoding="utf-8")
    if not text.strip():
        raise ValueError(f"Prompt '{name}' is blank")
    return text


def _guard_note(ctx: RunContext[SupportDeps]) -> str | None:
    return ctx.deps.guard_history.agent_context_note()


def build_agent[O](
    role_prompt: str, output_type: type[O], model: Model | None = None, output_retries: int = 1
) -> Agent[SupportDeps, O]:
    return Agent(
        model or settings.llm_model,
        deps_type=SupportDeps,
        output_type=output_type,
        instructions=[role_prompt, _guard_note],
        retries={"output": output_retries},
    )


def conversation_prompt(message: str, history: Sequence[ConversationTurn]) -> str:
    if not history:
        return message
    turns = "\n".join(f"{turn.sender}: {turn.content}" for turn in history)
    return f"Conversation so far:\n{turns}\n\nNew message:\n{message}"
