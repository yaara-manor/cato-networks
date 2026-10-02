from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict

from agents import DiagnosticEvidence, KnowledgeBundle
from retrieval.models import KBSearchStatus
from tools.models import TelemetryStatus


class DegradedSource(StrEnum):
    TELEMETRY = "TELEMETRY"
    RETRIEVAL = "RETRIEVAL"


class DegradationNotice(BaseModel):
    """Customer-facing disclosure that a source was down; `detail` names tools only, no customer data."""

    model_config = ConfigDict(frozen=True)

    source: DegradedSource
    detail: str
    customer_text: str

    @classmethod
    def from_telemetry(cls, unavailable: tuple[str, ...]) -> Self:
        return cls(
            source=DegradedSource.TELEMETRY,
            detail=", ".join(unavailable),
            customer_text=(
                "Note: live telemetry is temporarily unavailable, so I can't confirm the current "
                "state of your network. I won't guess at live values."
            ),
        )

    @classmethod
    def from_retrieval(cls) -> Self:
        return cls(
            source=DegradedSource.RETRIEVAL,
            detail="knowledge base",
            customer_text=(
                "Note: the knowledge base is temporarily unavailable, so I can't give documented "
                "guidance right now. I can pass this to a support engineer if you'd like."
            ),
        )


def derive_degradations(
    evidence: DiagnosticEvidence | None, bundle: KnowledgeBundle | None
) -> tuple[DegradationNotice, ...]:
    """Pure, evaluated fresh each turn. Telemetry first, then retrieval; only outages count."""
    unavailable = evidence.unavailable_tools if evidence else ()
    down = tuple(t.tool_name for t in unavailable if t.status is TelemetryStatus.UNAVAILABLE)
    notices = (DegradationNotice.from_telemetry(down),) if down else ()
    if bundle and bundle.confidence_status is KBSearchStatus.UNAVAILABLE:
        notices += (DegradationNotice.from_retrieval(),)
    return notices
