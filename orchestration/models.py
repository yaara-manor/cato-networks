from collections.abc import Callable
from dataclasses import dataclass
from typing import Self

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
from guardrails import KB_REF, MarkerKind, ProposedAction, extract_markers
from orchestration.degradation import DegradationNotice
from storage import ConversationStage


@dataclass(frozen=True)
class AgentPorts:
    """The four `run_<role>` callables, model argument already bound."""

    triage: Callable[[TriageInput, SupportDeps], AgentRun[TriageResult]]
    diagnostics: Callable[[DiagnosticsInput, SupportDeps], AgentRun[DiagnosticEvidence]]
    knowledge: Callable[[KnowledgeInput, SupportDeps], AgentRun[KnowledgeBundle]]
    resolution: Callable[[ResolutionInput, SupportDeps], AgentRun[ResolutionPlan]]


class Citation(BaseModel):
    model_config = ConfigDict(frozen=True)

    kind: MarkerKind  # KB or POLICY
    ref: str
    title: str
    url: str = ""  # policies have no public url

    @classmethod
    def for_reply(cls, reply: str, bundle: KnowledgeBundle | None) -> tuple[Self, ...]:
        """Reply markers resolved against the turn's bundle; unknown and telemetry markers are dropped."""
        if bundle is None:
            return ()
        # ascending rerank: the best passage per (slug, anchor) is written last
        best = {
            (p.slug, p.heading_anchor): p for p in sorted(bundle.retrieved_passages, key=lambda p: p.rerank_score)
        }
        policies = {p.policy_id: p for p in bundle.referenced_policies}
        citations: list[Self] = []
        for marker in extract_markers(reply):
            if marker.kind is MarkerKind.KB and (ref := KB_REF.fullmatch(marker.ref)):
                if passage := best.get((ref["slug"], ref["anchor"])):
                    citations.append(
                        cls(kind=MarkerKind.KB, ref=marker.ref, title=passage.title, url=passage.public_url)
                    )
            elif marker.kind is MarkerKind.POLICY and (policy := policies.get(marker.ref)):
                citations.append(cls(kind=MarkerKind.POLICY, ref=marker.ref, title=policy.title))
        return tuple(citations)

    def to_row(self) -> dict[str, str]:
        return self.model_dump(mode="json")


class TurnResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    reply: str
    path: tuple[ConversationStage, ...]
    pending_actions: tuple[ProposedAction, ...] = ()
    action_results: tuple[ActionResult, ...] = ()
    escalation_offered: bool = False
    degradations: tuple[DegradationNotice, ...] = ()
    citations: tuple[Citation, ...] = ()
