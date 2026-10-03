import re
from collections.abc import Callable, Iterator
from decimal import Decimal, InvalidOperation
from re import Pattern
from typing import NamedTuple

from core.models import TicketPriority
from guardrails.citations import ANY_MARKER, KB_MARKER, KB_REF, POLICY_MARKER, TELEMETRY_MARKER
from guardrails.models import (
    ActionType,
    ApprovedGrant,
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
    bare = ANY_MARKER.sub("", sentence)
    return any(signal.search(bare) for signal in _CLAIM_SIGNALS)


_BLOCKQUOTE_LINE: Pattern[str] = re.compile(r"^[ \t]*>[ \t]?(.*)$", re.MULTILINE)
_MD_IMAGE: Pattern[str] = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_MD_LINK: Pattern[str] = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_NON_WORD: Pattern[str] = re.compile(r"[\W_]+")
_ELLIPSIS: Pattern[str] = re.compile(r"\.\.\.|…")
_MIN_QUOTE_WORDS = 3


def _normalize(text: str) -> str:
    """Words only, lowercase: markdown, punctuation and spacing differences never break a quote match."""
    return _NON_WORD.sub(" ", _MD_LINK.sub(r"\1", _MD_IMAGE.sub("", text)).lower()).strip()


def _blockquotes(message: str) -> list[str]:
    """Consecutive `>` lines form one block; its text keeps the markers."""
    blocks: list[list[str]] = []
    previous_end = -2
    for line in _BLOCKQUOTE_LINE.finditer(message):
        if line.start() > previous_end + 1:
            blocks.append([])
        blocks[-1].append(line.group(1))
        previous_end = line.end()
    return ["\n".join(lines) for lines in blocks]


def _quote_violations(message: str, context: GroundingContext) -> list[CitationViolation]:
    """A blockquote must cite a knowledge passage and repeat that passage word for word."""
    violations: list[CitationViolation] = []
    for block in _blockquotes(message):
        keys = [key for m in KB_MARKER.finditer(block) if (key := _kb_key(m["ref"])) in context.kb_refs]
        if not keys:
            if not KB_MARKER.search(block):  # an unknown marker is already an UNKNOWN_KB violation
                violations.append(CitationViolation(kind=CitationViolationKind.UNGROUNDED_QUOTE, detail=block))
            continue
        source = _normalize(" ".join(context.kb_texts.get(key, "") for key in keys))
        quoted = KB_MARKER.sub("", block)
        fragments = [_normalize(part) for part in _ELLIPSIS.split(quoted)]
        if any(len(f.split()) >= _MIN_QUOTE_WORDS and f not in source for f in fragments):
            violations.append(CitationViolation(kind=CitationViolationKind.UNGROUNDED_QUOTE, detail=block))
    return violations


def _kb_key(ref: str) -> tuple[str, str] | None:
    parsed = KB_REF.fullmatch(ref)
    return (parsed["slug"], parsed["anchor"]) if parsed else None


def check_citations(message: str, context: GroundingContext) -> CitationReport:
    violations: list[CitationViolation] = []
    for kind, pattern, known, key in (
        (CitationViolationKind.UNKNOWN_KB, KB_MARKER, context.kb_refs, lambda m: _kb_key(m["ref"])),
        (CitationViolationKind.UNKNOWN_POLICY, POLICY_MARKER, context.policy_ids, lambda m: m["ref"]),
        (CitationViolationKind.UNKNOWN_TELEMETRY, TELEMETRY_MARKER, context.telemetry_tools, lambda m: m["ref"]),
    ):
        violations.extend(
            CitationViolation(kind=kind, detail=match.group())
            for match in pattern.finditer(message)
            if key(match) not in known
        )
    claims: list[str] = []
    for paragraph in _PARAGRAPH_BREAK.split(message):
        cited = ANY_MARKER.search(paragraph) is not None
        non_kb_evidence = TELEMETRY_MARKER.search(paragraph) is not None or POLICY_MARKER.search(paragraph) is not None
        for sentence in _sentences(paragraph):
            if _has_claim_signal(sentence):
                if not cited:
                    violations.append(CitationViolation(kind=CitationViolationKind.UNCITED_CLAIM, detail=sentence))
                if not non_kb_evidence:  # a refusal bars knowledge claims only; telemetry and policy stay citable
                    claims.append(sentence)
    violations.extend(_quote_violations(message, context))
    offenders = [match.group() for match in KB_MARKER.finditer(message)] + claims
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


_AMOUNT: Pattern[str] = re.compile(
    r"(?i)(?P<symbol>[$€£])\s?(?P<n1>\d[\d,]*(?:\.\d+)?)"
    r"|\b(?P<n2>\d[\d,]*(?:\.\d+)?)\s?(?P<code2>USD|EUR|GBP)\b"
    r"|\b(?P<code3>USD|EUR|GBP)\s?(?P<n3>\d[\d,]*(?:\.\d+)?)(?!\d)"
)
_SYMBOL_CODE = {"$": "USD", "€": "EUR", "£": "GBP"}
_Grants = tuple[ApprovedGrant, ...]


def _quoted_amounts(sentence: str) -> set[tuple[Decimal, str]]:
    quoted: set[tuple[Decimal, str]] = set()
    for match in _AMOUNT.finditer(sentence):
        number = match["n1"] or match["n2"] or match["n3"]
        code = _SYMBOL_CODE.get(match["symbol"] or "") or (match["code2"] or match["code3"]).upper()
        quoted.add((Decimal(number.replace(",", "")), code))
    return quoted


def _granted_amounts(grants: _Grants) -> set[tuple[Decimal, str]]:
    granted: set[tuple[Decimal, str]] = set()
    for grant in grants:
        if grant.action_type is not ActionType.CREDIT:
            continue
        try:
            amount = Decimal(grant.payload["amount"].replace(",", ""))
            granted.add((amount, grant.payload.get("currency", "USD").upper()))
        except (KeyError, InvalidOperation):
            continue  # a malformed payload grants nothing
    return granted


def _credit_approved(sentence: str, grants: _Grants) -> bool:
    return _quoted_amounts(sentence) <= _granted_amounts(grants)


def _mfa_approved(sentence: str, grants: _Grants) -> bool:
    return any(grant.action_type is ActionType.MFA_RESET for grant in grants)  # ponytail: not payload-bound


def _never_approved(sentence: str, grants: _Grants) -> bool:
    return False


class _OutputRule(NamedTuple):
    kind: OutputViolationKind
    patterns: tuple[Pattern[str], ...]  # all must match within one sentence
    approved: Callable[[str, _Grants], bool]


_OUTPUT_RULES: tuple[_OutputRule, ...] = (
    _OutputRule(
        OutputViolationKind.CREDIT_AMOUNT_PROMISE,
        (_AMOUNT, re.compile(r"(?i)\b(?:credits?|refunds?|compensation)\b")),
        _credit_approved,
    ),
    _OutputRule(
        OutputViolationKind.MFA_RESET_CLAIM,
        (re.compile(r"(?i)\b(?:have|has|i['’]ve)\s+(?:already\s+)?reset\s+(?:your|the|his|her|their)\s+mfa\b"),),
        _mfa_approved,
    ),
    _OutputRule(
        OutputViolationKind.VERDICT_OVERRIDE_CLAIM,
        (
            re.compile(r"(?i)\b(?:whitelisted|allowlisted|unblocked|overrode|overridden)\b"),
            re.compile(r"(?i)\b(?:domain|verdict|c2|malware)\b"),
        ),
        _never_approved,
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
    message: str, history: SessionGuardHistory, grants: _Grants
) -> list[OutputViolation]:
    body = ANY_MARKER.sub(" ", message)
    violations = [
        OutputViolation(kind=rule.kind, detail=sentence)
        for sentence in _sentences(body)
        for rule in _OUTPUT_RULES
        if all(pattern.search(sentence) for pattern in rule.patterns) and not rule.approved(sentence, grants)
    ]
    # details are fixed descriptions: a SECRET_ECHO must never carry the secret it reports
    findings = redact(body).findings
    phrases = (phrase for segment in ANY_MARKER.split(message) for phrase in _phrases(segment))
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
