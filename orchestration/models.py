from collections.abc import Callable
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict

from actions import ActionResult
from agents import (
    AgentRun,
    DiagnosticEvidence,
    DiagnosticsInput,
    KnowledgeBundle,
    KnowledgeInput,
    ResolutionInput,
    ResolutionPlan,
    SupportDeps,
    TriageInput,
    TriageResult,
)
from guardrails import ProposedAction
from orchestration.degradation import DegradationNotice
from storage import ConversationStage


@dataclass(frozen=True)
class AgentPorts:
    """The four `run_<role>` callables, model argument already bound."""

    triage: Callable[[TriageInput, SupportDeps], AgentRun[TriageResult]]
    diagnostics: Callable[[DiagnosticsInput, SupportDeps], AgentRun[DiagnosticEvidence]]
    knowledge: Callable[[KnowledgeInput, SupportDeps], AgentRun[KnowledgeBundle]]
    resolution: Callable[[ResolutionInput, SupportDeps], AgentRun[ResolutionPlan]]


class TurnResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    reply: str
    path: tuple[ConversationStage, ...]
    pending_actions: tuple[ProposedAction, ...] = ()
    action_results: tuple[ActionResult, ...] = ()
    escalation_offered: bool = False
    degradations: tuple[DegradationNotice, ...] = ()
