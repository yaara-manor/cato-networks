from collections.abc import Iterator
import hashlib
import re
from re import Pattern
from typing import NamedTuple

from guardrails.models import RedactionFinding, RedactionResult, SecretKind
from guardrails.normalize import normalize


class _Hit(NamedTuple):
    start: int
    end: int
    kind: SecretKind


class _Rule(NamedTuple):
    kind: SecretKind
    pattern: Pattern[str]


_PLACEHOLDER: Pattern[str] = re.compile(r"\[REDACTED:[A-Z_]+\]")
_KIND_RANK: dict[SecretKind, int] = {kind: rank for rank, kind in enumerate(SecretKind)}

_KEY_NAME: str = (
    r"(?i)\b(?:[a-z0-9]+[_-])*(?:password|passwd|pwd|psk|pre[_-]?shared[_-]?key|secret"
    r"|token|api[_-]?key|apikey|shared[_-]?key)[\"']?\s*[:=]\s*"
)

_PATTERN_RULES: tuple[_Rule, ...] = (
    _Rule(
        SecretKind.PRIVATE_KEY,
        re.compile(
            r"(?P<secret>-----BEGIN (?:[A-Z0-9 ]+ )?PRIVATE KEY-----[\s\S]*?"
            r"(?:-----END (?:[A-Z0-9 ]+ )?PRIVATE KEY-----|\Z))"
        ),
    ),
    _Rule(SecretKind.BEARER_TOKEN, re.compile(r"(?i)\bbearer\s+(?P<secret>[A-Za-z0-9._~+/=-]{16,})")),
    _Rule(
        SecretKind.BEARER_TOKEN,
        re.compile(r"(?i)\bauthorization\s*:\s*(?:(?:basic|bearer|token)\s+)?(?P<secret>[^\s,;\"']+)"),
    ),
    _Rule(
        SecretKind.JWT,
        re.compile(r"\b(?P<secret>eyJ[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]*)"),
    ),
    _Rule(
        SecretKind.VENDOR_KEY,
        re.compile(
            r"\b(?P<secret>AKIA[0-9A-Z]{16}|sk-[A-Za-z0-9_-]{20,}|ghp_[A-Za-z0-9]{30,}"
            r"|xox[bp]-[A-Za-z0-9-]{10,})(?![A-Za-z0-9_-])"
        ),
    ),
    _Rule(SecretKind.KEY_VALUE, re.compile(_KEY_NAME + r"\"(?P<secret>[^\"]+)\"")),
    _Rule(SecretKind.KEY_VALUE, re.compile(_KEY_NAME + r"'(?P<secret>[^']+)'")),
    _Rule(SecretKind.KEY_VALUE, re.compile(_KEY_NAME + r"(?P<secret>[^\s,;&}\"']+)")),
    _Rule(
        SecretKind.KEY_VALUE,
        re.compile(r"(?i)\b[a-z][a-z0-9+.-]*://[^\s/:@]+:(?P<secret>[^\s/@]+)@"),
    ),
    _Rule(
        SecretKind.KEY_VALUE,
        re.compile(r"(?i)\bcurl\b[^\n]*?\s(?:-u|--user)\s+[\"']?[^\s:\"']+:(?P<secret>[^\s\"']+)"),
    ),
)


def secret_hash(value: str) -> str:
    return hashlib.sha256(normalize(value).text.encode()).hexdigest()


def _pattern_hits(text: str) -> Iterator[_Hit]:
    for rule in _PATTERN_RULES:
        for m in rule.pattern.finditer(text):
            yield _Hit(*m.span("secret"), rule.kind)


def _merge(hits: list[_Hit]) -> list[_Hit]:
    merged: list[_Hit] = []
    for hit in sorted(hits):
        if merged and hit.start < merged[-1].end:
            last = merged[-1]
            kind = min(last.kind, hit.kind, key=_KIND_RANK.__getitem__)
            merged[-1] = _Hit(last.start, max(last.end, hit.end), kind)
        else:
            merged.append(hit)
    return merged


def redact(text: str) -> RedactionResult:
    norm = normalize(text)
    placeholders = [m.span() for m in _PLACEHOLDER.finditer(norm.text)]
    hits = [
        hit
        for hit in _pattern_hits(norm.text)
        if not any(hit.start < end and start < hit.end for start, end in placeholders)
    ]
    findings: list[RedactionFinding] = []
    parts: list[str] = []
    cursor = 0
    for hit in _merge(hits):
        start, end = norm.original_span(hit.start, hit.end)
        parts.extend((text[cursor:start], f"[REDACTED:{hit.kind}]"))
        findings.append(RedactionFinding(kind=hit.kind, start=start, end=end, sha256=secret_hash(text[start:end])))
        cursor = end
    parts.append(text[cursor:])
    return RedactionResult(text="".join(parts), findings=tuple(findings))
