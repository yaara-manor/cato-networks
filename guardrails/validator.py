import re
from re import Pattern

from guardrails.models import (
    CitationReport,
    CitationViolation,
    CitationViolationKind,
    ClaimKind,
    EntitlementVerdict,
    FalseClaim,
    GroundingContext,
)
from guardrails.normalize import normalize
from services.models import CallerIdentity

# ponytail: every matched tier word means "Premium"; Standard-side claims ("we're on basic") are not extracted.
_TIER_CLAIM: Pattern[str] = re.compile(
    r"(?i)\bwe(?: are|['’]re)\s+(?:an?\s+)?(?:premium|vip|enterprise|platinum|gold)\b"
)
_ROLES = "ceo|cto|ciso|vp|director|admin|administrator|security lead|owner"
_AUTHORITY_CLAIMS: tuple[Pattern[str], ...] = (
    re.compile(rf"(?i)\bi(?: am|['’]m)\s+(?:(?:the|our|an?)\s+)?(?:{_ROLES})\b"),
    re.compile(rf"(?i)\bassistant to (?:our|the)\s+(?:{_ROLES})\b"),
    re.compile(r"(?i)\bapproved on our side\b"),
    re.compile(r"(?i)\bi(?: am|['’]m)\s+authori[sz](?:ing|ed)\b"),
)
_ACCOUNT_ID: Pattern[str] = re.compile(r"(?i)\bACC-\d+\b")


def check_claims(text: str, identity: CallerIdentity) -> EntitlementVerdict:
    body = " ".join(normalize(text).text.split())
    claims: list[FalseClaim] = []
    if _TIER_CLAIM.search(body) and identity.effective_tier != "Premium":
        claims.append(FalseClaim(kind=ClaimKind.TIER, claimed="Premium", actual=identity.effective_tier))
    if not identity.is_registered_admin:
        for pattern in _AUTHORITY_CLAIMS:
            claims.extend(
                FalseClaim(
                    kind=ClaimKind.AUTHORITY,
                    claimed=" ".join(match.group().lower().split()),
                    actual="not a registered admin contact",
                )
                for match in pattern.finditer(body)
            )
    actual_id = identity.account.account_id if identity.account else None
    for match in _ACCOUNT_ID.finditer(body):
        claimed = match.group().upper()
        if claimed != actual_id:
            claims.append(FalseClaim(kind=ClaimKind.ACCOUNT, claimed=claimed, actual=actual_id or "unverified"))
    return EntitlementVerdict(false_claims=tuple(dict.fromkeys(claims)))


# anchors are [\w-]+ per kbindex.chunk.heading_anchor; tool names match TelemetryEvidence.format_citation
_KB_MARKER: Pattern[str] = re.compile(r"\[kb:(?P<slug>[a-z0-9-]+)#(?P<anchor>[\w-]+)\]")
_POLICY_MARKER: Pattern[str] = re.compile(r"\[policy:(?P<id>POL-[A-Z0-9]+)\]")
_TELEMETRY_MARKER: Pattern[str] = re.compile(r"\[telemetry:(?P<tool>[a-z_]+)\]")
_ANY_MARKER: Pattern[str] = re.compile(r"\[(?:kb|policy|telemetry):[^\]]*\]")
_CLAIM_SIGNALS: tuple[Pattern[str], ...] = (
    re.compile(r"(?<![\w.])\d[\d,]*(?:\.\d+)?\s?(?:ms|sec|s|bytes|B|KB|MB|GB|kbps|Mbps|Gbps|dBm|%)(?!\w)"),
    re.compile(r"(?i)\b(?:UDP|TCP)\s+\d+\b|\bport\s+\d+\b"),
    re.compile(r"\b[A-Z]+(?:_[A-Z]+)+\b"),
    re.compile(r"`[^`\n]+`"),
)
_PARAGRAPH_BREAK: Pattern[str] = re.compile(r"\n\s*\n")
_SENTENCE_BREAK: Pattern[str] = re.compile(r"(?<=[.!?])\s+")


def _sentences(block: str) -> list[str]:
    return [sentence for sentence in _SENTENCE_BREAK.split(block) if sentence.strip()]


def _has_claim_signal(sentence: str) -> bool:
    bare = _ANY_MARKER.sub("", sentence)
    return any(signal.search(bare) for signal in _CLAIM_SIGNALS)


def check_citations(message: str, context: GroundingContext) -> CitationReport:
    violations: list[CitationViolation] = []
    for kind, pattern, known in (
        (CitationViolationKind.UNKNOWN_KB, _KB_MARKER, context.kb_refs),
        (CitationViolationKind.UNKNOWN_POLICY, _POLICY_MARKER, context.policy_ids),
        (CitationViolationKind.UNKNOWN_TELEMETRY, _TELEMETRY_MARKER, context.telemetry_tools),
    ):
        violations.extend(
            CitationViolation(kind=kind, detail=match.group())
            for match in pattern.finditer(message)
            if match.group(*match.groupdict()) not in known  # one named group -> str, two -> (slug, anchor)
        )
    claims: list[str] = []
    for paragraph in _PARAGRAPH_BREAK.split(message):
        cited = _ANY_MARKER.search(paragraph) is not None
        for sentence in _sentences(paragraph):
            if _has_claim_signal(sentence):
                claims.append(sentence)
                if not cited:
                    violations.append(CitationViolation(kind=CitationViolationKind.UNCITED_CLAIM, detail=sentence))
    offenders = [match.group() for match in _KB_MARKER.finditer(message)] + claims
    if context.is_refusal and offenders:
        violations.append(CitationViolation(kind=CitationViolationKind.REFUSAL_BREACH, detail=offenders[0]))
    return CitationReport(violations=tuple(violations))
