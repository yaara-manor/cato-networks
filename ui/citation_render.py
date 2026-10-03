import re
from collections.abc import Sequence
from re import Match

from guardrails import MarkerKind
from orchestration import Citation

_MARKER_PARTS = re.compile(r"[ \t]*\[(?P<kind>kb|policy|telemetry):(?P<ref>[^\]]*)\]")
_BLOCKQUOTE_PREFIX = re.compile(r"^[ \t]*>")
_PUNCTUATION = re.compile(r"[^\w\s]")
_WHITESPACE = re.compile(r"\s+")


def site_anchor(heading: str) -> str:
    """The knowledge-base site's own heading id: lowercase, punctuation dropped, spaces become hyphens."""
    return _WHITESPACE.sub("-", _PUNCTUATION.sub("", heading.lower()).strip())


def escape_label(label: str) -> str:
    return label.replace("[", r"\[").replace("]", r"\]")


def source_label(citation: Citation) -> str:
    return f"{citation.title} › {citation.heading}" if citation.heading else citation.title


def source_url(citation: Citation) -> str | None:
    if not citation.url:
        return None
    return f"{citation.url}#{site_anchor(citation.heading)}" if citation.heading else citation.url


def render_reply(content: str, citations: Sequence[Citation]) -> str:
    """Stored reply to display markdown.

    Knowledge and policy markers become numbered links; numbers follow `citations` order, which the "Sources"
    line repeats. A knowledge marker closing a blockquote becomes that quote's source attribution. Telemetry
    markers become a tool tag. Markers that resolve to no stored citation are dropped.
    """
    numbers = {citation.ref: position for position, citation in enumerate(citations, start=1)}
    known = {citation.ref: citation for citation in citations}

    def replace(match: Match[str], quoted: bool) -> str:
        kind, ref = MarkerKind(match["kind"]), match["ref"]
        if kind is MarkerKind.TELEMETRY:
            return f" *({ref})*"
        citation = known.get(ref)
        if citation is None:
            return ""
        url = source_url(citation)
        if quoted and kind is MarkerKind.KB and url:
            return f"  \n> — [{escape_label(source_label(citation))}]({url})"
        return f" [{numbers[ref]}]({url})" if url else f" [{numbers[ref]}]"

    lines = [
        _MARKER_PARTS.sub(lambda m, quoted=bool(_BLOCKQUOTE_PREFIX.match(line)): replace(m, quoted), line)
        for line in content.split("\n")
    ]
    return "\n".join(lines).strip()
