import re
from re import Pattern

from guardrails.models import ClaimKind, EntitlementVerdict, FalseClaim
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
    body = normalize(text).text
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
