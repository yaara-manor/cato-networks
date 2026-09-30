import re
from re import Pattern
from typing import NamedTuple

from guardrails.models import InjectionCategory, InjectionVerdict
from guardrails.normalize import normalize


class _Rule(NamedTuple):
    rule_id: str
    category: InjectionCategory
    pattern: Pattern[str]


_IMPERATIVES: str = (
    "ignore|disregard|close|reset|issue|grant|approve|whitelist|allowlist|override|disable|delete|reveal|refund"
    "|credit|unlock"
)


def _with_imperative(claim: str) -> str:
    return rf"(?:{claim}.{{0,200}}\b(?:{_IMPERATIVES})\b|\b(?:{_IMPERATIVES})\b.{{0,200}}{claim})"


# ponytail: base64/rot13 payload decoding skipped (design §4.2); upgrade path: decode candidate tokens before matching when a scenario needs it.
_RULES: tuple[_Rule, ...] = (
    _Rule(
        "override.ignore_previous",
        InjectionCategory.INSTRUCTION_OVERRIDE,
        re.compile(
            r"\b(?:ignore|disregard|forget)\s+(?:(?:all|any|your|the|my)\s+)*(?:previous|prior|above)\s+"
            r"(?:instructions?|rules?|prompts?)\b"
        ),
    ),
    _Rule("override.new_instructions", InjectionCategory.INSTRUCTION_OVERRIDE, re.compile(r"\bnew instructions\s*:")),
    _Rule("role.you_are_now", InjectionCategory.ROLE_OVERRIDE, re.compile(r"\byou are now\b")),
    _Rule(
        "role.privileged_mode",
        InjectionCategory.ROLE_OVERRIDE,
        re.compile(r"\b(?:maintenance|developer|debug|admin|god|dan) mode\b"),
    ),
    _Rule("role.act_as", InjectionCategory.ROLE_OVERRIDE, re.compile(r"\bact as (?:an? )?(?:admin|system|developer)\b")),
    _Rule("role.pretend", InjectionCategory.ROLE_OVERRIDE, re.compile(r"\bpretend (?:you are|to be)\b")),
    _Rule(
        "exfil.system_prompt",
        InjectionCategory.PROMPT_EXFILTRATION,
        re.compile(
            r"\b(?:reveal|print|show|repeat|reply with|output)\b[^.?!]{0,60}?"
            r"\b(?:system prompt|your instructions|hidden prompt|initial prompt)\b"
        ),
    ),
    _Rule(
        "authority.authorized_test",
        InjectionCategory.FAKE_AUTHORITY,
        re.compile(_with_imperative(r"\bauthori[sz]ed (?:test|request) by (?:cato|anthropic|engineering|security)\b")),
    ),
    _Rule(
        "authority.team_claim",
        InjectionCategory.FAKE_AUTHORITY,
        re.compile(_with_imperative(r"\bthis is (?:cato|the) (?:engineering|security|support) team\b")),
    ),
    _Rule("delim.system_tag", InjectionCategory.DELIMITER_INJECTION, re.compile(r"</?system>")),
    _Rule("delim.chatml", InjectionCategory.DELIMITER_INJECTION, re.compile(r"<\|im_(?:start|end)\|>|<\|endoftext\|>")),
    _Rule("delim.inst", InjectionCategory.DELIMITER_INJECTION, re.compile(r"\[/?inst\]")),
    _Rule("delim.header", InjectionCategory.DELIMITER_INJECTION, re.compile(r"###\s*(?:system|instruction)")),
    _Rule("delim.begin_system_prompt", InjectionCategory.DELIMITER_INJECTION, re.compile(r"\bbegin system prompt\b")),
)


def detect(text: str) -> InjectionVerdict:
    folded = " ".join(normalize(text).text.lower().split())
    hits = [rule for rule in _RULES if rule.pattern.search(folded)]
    return InjectionVerdict(
        blocked=bool(hits),
        categories=frozenset(rule.category for rule in hits),
        rule_ids=tuple(rule.rule_id for rule in hits),
    )


def quarantine(text: str) -> str:
    verdict = detect(text)
    if verdict.blocked:
        return f"[QUARANTINED: prior message matched injection rules {', '.join(verdict.rule_ids)}]"
    return text
