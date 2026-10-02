from collections.abc import Iterator
import re
from re import Pattern
from typing import NamedTuple

from guardrails.models import (
    ActionType,
    CitationReport,
    CitationViolation,
    CitationViolationKind,
    ClaimKind,
    EntitlementVerdict,
    FalseClaim,
    GateDecision,
    GateOutcome,
    GroundingContext,
    OutputViolation,
    OutputViolationKind,
    ProposedAction,
    SessionGuardHistory,
)
from guardrails.normalize import normalize
from guardrails.redactor import redact, secret_hash
from core.models import TicketPriority
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
_KB_MARKER: Pattern[str] = re.compile(r"\[kb:(?P<ref>[^\]]*)\]")
_POLICY_MARKER: Pattern[str] = re.compile(r"\[policy:(?P<ref>[^\]]*)\]")
_TELEMETRY_MARKER: Pattern[str] = re.compile(r"\[telemetry:(?P<ref>[^\]]*)\]")
_KB_REF: Pattern[str] = re.compile(r"(?P<slug>[a-z0-9-]+)#(?P<anchor>[\w-]+)")
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


def _kb_key(ref: str) -> tuple[str, str] | None:
    parsed = _KB_REF.fullmatch(ref)
    return (parsed["slug"], parsed["anchor"]) if parsed else None


def check_citations(message: str, context: GroundingContext) -> CitationReport:
    violations: list[CitationViolation] = []
    for kind, pattern, known, key in (
        (CitationViolationKind.UNKNOWN_KB, _KB_MARKER, context.kb_refs, lambda m: _kb_key(m["ref"])),
        (CitationViolationKind.UNKNOWN_POLICY, _POLICY_MARKER, context.policy_ids, lambda m: m["ref"]),
        (CitationViolationKind.UNKNOWN_TELEMETRY, _TELEMETRY_MARKER, context.telemetry_tools, lambda m: m["ref"]),
    ):
        violations.extend(
            CitationViolation(kind=kind, detail=match.group())
            for match in pattern.finditer(message)
            if key(match) not in known
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


def check_action(
    action: ProposedAction,
    identity: CallerIdentity,
    *,
    priority: TicketPriority | None = None,
    sev1_corroborated: bool = False,
    already_paged: bool = False,
) -> GateDecision:
    if identity.account is None or action.target_account_id != identity.account.account_id:
        return GateDecision(
            outcome=GateOutcome.DENY,
            policy_id="POL-IDV",
            reason="Action target is not the authenticated caller's account.",
        )
    match action.action_type:
        case ActionType.VERDICT_OVERRIDE:
            return GateDecision(
                outcome=GateOutcome.DENY,
                policy_id="POL-SEC",
                reason="Malware/C2 verdict overrides are not a support decision; escalate to Security Ops with the event IDs.",
            )
        case ActionType.MFA_RESET if not identity.is_registered_admin:
            return GateDecision(
                outcome=GateOutcome.DENY, policy_id="POL-IDV", reason="MFA reset requires the registered admin contact."
            )
        case ActionType.MFA_RESET:
            return GateDecision(
                outcome=GateOutcome.REQUIRE_APPROVAL, policy_id="POL-IDV", reason="MFA reset requires human approval."
            )
        case ActionType.CREDIT if not identity.is_verified_account_member:
            return GateDecision(
                outcome=GateOutcome.DENY,
                policy_id="POL-CREDIT",
                reason="Credits can only be requested by verified account members.",
            )
        case ActionType.CREDIT:
            return GateDecision(
                outcome=GateOutcome.REQUIRE_APPROVAL, policy_id="POL-CREDIT", reason="Credits require human approval."
            )
        case ActionType.CLOSE_TICKET:
            return GateDecision(
                outcome=GateOutcome.ALLOW, policy_id=None, reason="Closing a ticket needs no approval."
            )
        case ActionType.PAGE_ON_CALL if priority == "P1" and sev1_corroborated and not already_paged:
            return GateDecision(
                outcome=GateOutcome.ALLOW, policy_id="POL-SEV1", reason="Sev-1 corroborated by telemetry."
            )
        case ActionType.PAGE_ON_CALL:
            return GateDecision(
                outcome=GateOutcome.DENY,
                policy_id="POL-SEV1",
                reason="Paging on-call requires P1 priority, telemetry corroboration, and no earlier page.",
            )


class _OutputRule(NamedTuple):
    kind: OutputViolationKind
    patterns: tuple[Pattern[str], ...]  # all must match within one sentence
    approved_by: ActionType | None  # None: always a violation


_OUTPUT_RULES: tuple[_OutputRule, ...] = (
    _OutputRule(
        OutputViolationKind.CREDIT_AMOUNT_PROMISE,
        (
            re.compile(
                r"(?i)[$€£]\s?\d[\d,]*(?:\.\d+)?|\b\d[\d,]*(?:\.\d+)?\s?(?:USD|EUR)\b|\b(?:USD|EUR)\s?\d[\d,]*"
            ),
            re.compile(r"(?i)\b(?:credits?|refunds?|compensation)\b"),
        ),
        ActionType.CREDIT,
    ),
    _OutputRule(
        OutputViolationKind.MFA_RESET_CLAIM,
        (re.compile(r"(?i)\b(?:have|has|i['’]ve)\s+(?:already\s+)?reset\s+(?:your|the|his|her|their)\s+mfa\b"),),
        ActionType.MFA_RESET,
    ),
    _OutputRule(
        OutputViolationKind.VERDICT_OVERRIDE_CLAIM,
        (
            re.compile(r"(?i)\b(?:whitelisted|allowlisted|unblocked|overrode|overridden)\b"),
            re.compile(r"(?i)\b(?:domain|verdict|c2|malware)\b"),
        ),
        None,
    ),
)
_EDGE_PUNCTUATION = ".,;:()\"'"
# ponytail: echo check hashes word phrases up to 8 words; longer secrets (PEM) rely on the redact() pass. Upgrade path: store the word count with each hash.
_MAX_SECRET_WORDS: int = 8


def _phrases(segment: str) -> Iterator[str]:
    words = normalize(segment).text.split()
    for start in range(len(words)):
        for end in range(start + 1, min(start + _MAX_SECRET_WORDS, len(words)) + 1):
            yield " ".join(words[start:end])


def check_outgoing_message(
    message: str, history: SessionGuardHistory, approved: frozenset[ActionType]
) -> list[OutputViolation]:
    body = _ANY_MARKER.sub(" ", message)
    violations = [
        OutputViolation(kind=rule.kind, detail=sentence)
        for sentence in _sentences(body)
        for rule in _OUTPUT_RULES
        if rule.approved_by not in approved and all(pattern.search(sentence) for pattern in rule.patterns)
    ]
    # details are fixed descriptions: a SECRET_ECHO must never carry the secret it reports
    findings = redact(body).findings
    phrases = (phrase for segment in _ANY_MARKER.split(message) for phrase in _phrases(segment))
    repeats_secret = any(finding.sha256 in history.secret_hashes for finding in findings) or (
        bool(history.secret_hashes)
        and any(
            secret_hash(candidate) in history.secret_hashes
            for phrase in phrases
            for candidate in (phrase, phrase.strip(_EDGE_PUNCTUATION))
        )
    )
    if repeats_secret:
        violations.append(
            OutputViolation(
                kind=OutputViolationKind.SECRET_ECHO, detail="message repeats a previously redacted secret"
            )
        )
    violations.extend(
        OutputViolation(
            kind=OutputViolationKind.SECRET_ECHO, detail=f"message contains an unredacted {finding.kind} secret"
        )
        for finding in findings
        if finding.sha256 not in history.secret_hashes
    )
    return violations
