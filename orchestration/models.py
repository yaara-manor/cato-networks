from collections.abc import Callable
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict

from agents import (
    AgentRun,
    DiagnosticEvidence,
    DiagnosticsInput,
    KnowledgeBundle,
    KnowledgeInput,
    ResolutionInput,
    ResolutionPlan,
    SupportAction,
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
    executable_actions: tuple[SupportAction, ...] = ()
    escalation_offered: bool = False
    degradations: tuple[DegradationNotice, ...] = ()
