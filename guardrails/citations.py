import re
from enum import StrEnum
from re import Pattern

from pydantic import BaseModel, ConfigDict

# anchors are [\w-]+ per kbindex.chunk.heading_anchor; tool names match TelemetryEvidence.format_citation
KB_MARKER: Pattern[str] = re.compile(r"\[kb:(?P<ref>[^\]]*)\]")
POLICY_MARKER: Pattern[str] = re.compile(r"\[policy:(?P<ref>[^\]]*)\]")
TELEMETRY_MARKER: Pattern[str] = re.compile(r"\[telemetry:(?P<ref>[^\]]*)\]")
KB_REF: Pattern[str] = re.compile(r"(?P<slug>[a-z0-9-]+)#(?P<anchor>[\w-]+)")
ANY_MARKER: Pattern[str] = re.compile(r"\[(?:kb|policy|telemetry):[^\]]*\]")
_MARKER_PARTS: Pattern[str] = re.compile(r"\[(?P<kind>kb|policy|telemetry):(?P<ref>[^\]]*)\]")
_DOUBLE_SPACE: Pattern[str] = re.compile(r" {2,}")


class MarkerKind(StrEnum):
    KB = "kb"
    POLICY = "policy"
    TELEMETRY = "telemetry"


class CitationMarker(BaseModel):
    model_config = ConfigDict(frozen=True)

    kind: MarkerKind
    ref: str


def extract_markers(message: str) -> tuple[CitationMarker, ...]:
    """Markers in order of first appearance, deduped."""
    found = (CitationMarker(kind=MarkerKind(m["kind"]), ref=m["ref"]) for m in _MARKER_PARTS.finditer(message))
    return tuple(dict.fromkeys(found))


def strip_markers(message: str) -> str:
    return _DOUBLE_SPACE.sub(" ", ANY_MARKER.sub("", message)).strip()
