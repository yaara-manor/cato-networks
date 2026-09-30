# Phase 1.5 (Plan 1 of 2): Guardrails Foundation & Credential Redactor — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create the `guardrails` package skeleton and ship the POL-CRED redactor: `redact(text) -> RedactionResult` with offset-preserving normalization, a four-layer detector (structural → vendor config → contextual → entropy), span merging, and a table-driven functional test suite with a negative corpus over the real seed data.

**Spec:** [`design.md`](design.md) §2, §3 (redaction contracts), §4.1, §5 (`test_redactor.py`). Plan 2 ([`02-detectors-validators-plan.md`](02-detectors-validators-plan.md)) builds injection, validator and session history on top of this package; it only starts after this plan is merged.

**Why two plans:** the redactor is ~40% of the effort and is the only guard with three downstream callers (ingestion, tool output, agent tool) plus a shared primitive (`normalize`) that Plan 2 reuses. Plan 1 ends with a package that has zero unused code: only the models the redactor returns exist after this plan; Plan 2 appends the rest as each guard that returns them lands.

**Architecture:**

```mermaid
flowchart LR
    Text["raw text"] --> Norm["normalize.normalize()\nNFKC + zero-width strip\nNormalizedText(text, offsets)"]
    Norm --> L1["_PATTERN_RULES\n(structural + vendor config)"]
    Norm --> L3["_contextual_hits"]
    Norm --> L4["_entropy_hits"]
    L1 --> Drop["drop hits overlapping\n[REDACTED:*] placeholders"]
    L3 --> Drop
    L4 --> Drop
    Drop --> Merge["_merge()\noverlap → union,\nearliest SecretKind wins"]
    Merge --> Out["RedactionResult\n(text, findings[kind, span, sha256])"]
```

**Tech Stack:** Python 3.12+, Pydantic v2 (frozen `BaseModel`), stdlib only (`re`, `math`, `hashlib`, `unicodedata`, `dataclasses`, `enum.StrEnum`), Pytest (parametrized, table-driven), Ruff, Pyright.

## Design deltas (prototype-verified — each is a bug or dead rule in the design as written)

Prototyped against `data/eval/questions.jsonl`, `data/tickets/tickets.jsonl` and `data/eval/scenarios.jsonl` before writing this plan. The negative corpus is clean with these rules; the positive corpus (TCK-20264230, SC-08) is caught. Task 5 folds these back into `design.md`.

| # | Design says | Plan does | Why |
|---|---|---|---|
| D1 | Normalization "same in redactor and injection" | One shared `guardrails/normalize.py` (new file, ~30 lines) | Two call sites need the same offset-mapped NFKC + zero-width strip; duplicating it is the first thing a maintainability review flags. Plan 2's validator uses it too. |
| D2 | Contextual separator `(is\|:\|=\|was)` then next token | Separator is `\b(is\|was)\b\s*[:=]?` or `[:=]`; value group excludes surrounding quotes and trailing `.,;:)` in the regex itself | As written, `PSK on our side is: Fg7!…` captures the `:` as the secret and leaves the PSK in the clear (SC-08 and TCK-20264230 both fail). |
| D3 | Contextual redacts the next token unconditionally | Contextual value must contain a digit **or** ≥ 3 character classes | `check_outgoing_message` (Plan 2) runs `redact()` on agent output. Without the guard, "the password reset is pending" / "the PSK was re-entered 26 h ago" produce a false `SECRET_ECHO` violation. `Fg7!qwe-DC-2026-tunnel` (4 classes) still passes. |
| D4 | Key list includes `radius_secret`, `scim_token`, `client_secret`; `.env` `*_KEY/_SECRET/_TOKEN/_PASSWORD` under VENDOR_CONFIG | Generic key rule `(?:\w+[_-])*(password\|…)` covers the prefixed names; the `.env` VENDOR_CONFIG rule is `*_KEY=` only | The other three `.env` suffixes are already caught (as `KEY_VALUE`) by the prefix wildcard — a second rule would be dead. Tests still name every key from the design. |
| D5 | Entropy allowlist: repo IDs, URLs, slugs, UUIDs, hex hashes, IPv4/6, MAC, email | Allowlist = lowercase-delimited identifiers (slugs, FQDNs, snake_case), UUID, URL without userinfo, email, IPv6, lowercase path | Repo IDs, IPv4, MAC (< 24 chars) and lowercase hex hashes (< 3 classes) can never pass the gates, so those entries are dead. FQDNs / snake_case / paths do pass the gates (verified) and were missing. Lowercase-only segments keep random mixed-case base64url tokens detectable. |
| D6 | (silent) | `[REDACTED:<KIND>]` placeholders in the input never produce hits | Tool-output sanitization re-runs `redact()` on text that was redacted at ingestion; without this, `password: [REDACTED:KEY_VALUE]` is re-wrapped. |
| D7 | `SecretKind` members only | `StrEnum` values equal their names (`CONTEXTUAL = "CONTEXTUAL"`) | Matches `tools.models.TelemetryStatus`; placeholder is `[REDACTED:CONTEXTUAL]`. |

## Global Constraints

- **No inline imports.** All imports at module top. Sort by module name with `import x` and `from x import y` interleaved (matches `tools/telemetry.py`, `core/clock.py`).
- **Full annotations** on every function, method, module constant and attribute (Pyright standard). Module constants are private (`_UPPER`) and annotated, like `services/customer_service.py`.
- **Pure.** `guardrails/` performs no DB, file, network or clock access. Only tests read `data/`, via `settings.repo_root`.
- **`# ponytail:` comments** mark every deliberate simplification and state the upgrade path, exactly like `kbindex/chunk.py` and `tools/telemetry.py`. No other narrative comments; no docstrings (none in `core/`, `tools/`).
- **No unnecessary files or wrappers.** New modules: `models.py`, `normalize.py`, `redactor.py`, `__init__.py`. No `utils.py`, no `patterns.py`, no rule classes beyond `_Rule`.
- **Table-driven, branch-free core.** Regex layers are data (`_PATTERN_RULES`); the detection loop has no per-rule `if`. Adding a rule is one tuple.
- **Size budget.** `redactor.py` ≤ 220 lines, `models.py` ≤ 60 lines in this plan. If `redactor.py` passes 250 lines, stop and extract the rule table before continuing.
- **Branching.** Commit directly on `p-1-5_guardrails`. No PR unless asked.
- **Verification commands** (run in the dev environment; `ruff` and `pyright` are not in `pyproject.toml`, invoke them directly):
  - `uv run pytest tests/guardrails -q`
  - `ruff check guardrails tests/guardrails`
  - `pyright guardrails tests/guardrails`

## File Map

| File | Action | Responsibility |
|---|---|---|
| `guardrails/__init__.py` | create | Re-exports only, `__all__` sorted. |
| `guardrails/models.py` | create | `_GuardModel` (frozen base), `SecretKind`, `RedactionFinding`, `RedactionResult`. |
| `guardrails/normalize.py` | create | `NormalizedText`, `normalize()`. |
| `guardrails/redactor.py` | create | `redact()`, `secret_hash()`, rule table, contextual + entropy layers, `_merge`. |
| `tests/guardrails/conftest.py` | create | `corpus` fixture: every customer-authored string in the seed data, keyed by stable id. |
| `tests/guardrails/test_normalize.py` | create | Offset mapping. |
| `tests/guardrails/test_redactor.py` | create | Per-layer tables, negative corpus, idempotence, evasion, performance. |

---

### Task 1: Package skeleton, redaction contracts, offset-preserving normalizer

**Files:** create `guardrails/__init__.py`, `guardrails/models.py`, `guardrails/normalize.py`, `tests/guardrails/test_normalize.py`.

**Interfaces:**
- `models.py`
  - `class _GuardModel(BaseModel)`: `model_config = ConfigDict(frozen=True)`. The single place frozenness is declared; every contract in Plans 1–2 subclasses it (no per-class `ConfigDict`).
  - `class SecretKind(StrEnum)`: `PRIVATE_KEY, BEARER_TOKEN, JWT, VENDOR_KEY, KEY_VALUE, VENDOR_CONFIG, CONTEXTUAL, HIGH_ENTROPY`, each value equal to its name. **Declaration order is merge precedence** (structural → vendor → contextual → entropy); a one-line comment says so.
  - `class RedactionFinding(_GuardModel)`: `kind: SecretKind`, `start: int`, `end: int` (span in the **original** text), `sha256: str`. Never the raw value.
  - `class RedactionResult(_GuardModel)`: `text: str`, `findings: tuple[RedactionFinding, ...]`; `@property was_redacted -> bool`.
- `normalize.py`
  - `_ZERO_WIDTH: frozenset[str] = frozenset("​‌‍⁠﻿")`
  - `@dataclass(frozen=True) class NormalizedText`: `text: str`, `offsets: tuple[int, ...]` (normalized index → original index); `def original_span(self, start: int, end: int) -> tuple[int, int]` returning `(offsets[start], offsets[end - 1] + 1)`. Precondition `start < end` (callers never pass empty spans).
  - `def normalize(text: str) -> NormalizedText`: iterate original chars; drop `_ZERO_WIDTH`; apply `unicodedata.normalize("NFKC", ch)` **per character** so every output char has an exact source index (an expanding char such as `ﬁ` maps both output chars to its one source index).
  - `# ponytail: per-character NFKC skips cross-character composition (e + combining accent). Secrets are ASCII-dominant; upgrade path: normalize grapheme clusters.`
- `__init__.py` exports `RedactionFinding`, `RedactionResult`, `SecretKind` (Task 5 adds `redact`, `secret_hash`).

- [ ] **Step 1: Write failing `tests/guardrails/test_normalize.py`**
  Functions (all `-> None`, plain asserts, no fixtures):
  - `test_zero_width_characters_are_removed_and_spans_map_back`: `normalize("pa​ss﻿word")` → `.text == "password"`; `original_span(0, 8) == (0, 10)` (the literal is 10 characters, two of them zero-width).
  - `test_fullwidth_letters_fold_to_ascii`: `normalize("ＰＳＫ").text == "PSK"`, `original_span(0, 3) == (0, 3)`.
  - `test_expanding_character_maps_to_one_source_index`: `normalize("aﬁb").text == "afib"`; `original_span(1, 3) == (1, 2)`.
  - `test_plain_ascii_is_identity`: text unchanged, `offsets == tuple(range(len(text)))`.

- [ ] **Step 2: Run `uv run pytest tests/guardrails/test_normalize.py -q`; confirm `ModuleNotFoundError: guardrails`.**

- [ ] **Step 3: Create `guardrails/models.py`, `guardrails/normalize.py`, `guardrails/__init__.py` as specified above.**

- [ ] **Step 4: Run the test file (green), `ruff check guardrails tests/guardrails`, `pyright guardrails tests/guardrails` (zero errors).**

- [ ] **Step 5: Commit** — `feat(guardrails): add package skeleton, redaction contracts and offset-preserving normalizer`

---

### Task 2: Redactor core + structural layer

**Files:** create `guardrails/redactor.py`, `tests/guardrails/test_redactor.py`; modify `guardrails/__init__.py`.

**Interfaces (all in `redactor.py`):**
- `class _Hit(NamedTuple)`: `start: int`, `end: int`, `kind: SecretKind` (offsets into the **normalized** text).
- `class _Rule(NamedTuple)`: `kind: SecretKind`, `pattern: Pattern[str]`. **Every rule pattern exposes exactly one named group `secret`**; the hit span is `m.span("secret")` (no value-group special-casing anywhere).
- `_PLACEHOLDER: Pattern[str] = re.compile(r"\[REDACTED:[A-Z_]+\]")`
- `def secret_hash(value: str) -> str`: `hashlib.sha256(normalize(value).text.encode()).hexdigest()`. Public: Plan 2's validator uses it for `SECRET_ECHO`, so both sides hash identically.
- `def _pattern_hits(text: str) -> Iterator[_Hit]`: the loop `for rule in _PATTERN_RULES: for m in rule.pattern.finditer(text): yield _Hit(*m.span("secret"), rule.kind)`.
- `def _merge(hits: list[_Hit]) -> list[_Hit]`: sort by `start`; sweep; overlapping hits become one span `(min start, max end)` whose kind is the member with the lowest `list(SecretKind).index` (module constant `_KIND_RANK: dict[SecretKind, int]`). Touching-but-not-overlapping hits stay separate.
- `def redact(text: str) -> RedactionResult`: `norm = normalize(text)` → collect hits from all layers over `norm.text` → drop hits overlapping a `_PLACEHOLDER` span (D6) → `_merge` → map each hit to the original text with `norm.original_span` → `RedactionFinding(kind, start, end, sha256=secret_hash(text[start:end]))` → rebuild `text` from the **original** string replacing each span with `f"[REDACTED:{kind}]"` (so zero-width characters outside secrets are preserved). Returns findings in span order.

**Structural rules (`_PATTERN_RULES`, in this order; `(?i)` etc. are inline flags at the start of each pattern):**

```python
_KEY_NAME = (
    r"(?i)\b(?:[a-z0-9]+[_-])*(?:password|passwd|pwd|psk|pre[_-]?shared[_-]?key|secret"
    r"|token|api[_-]?key|apikey|shared[_-]?key)[\"']?\s*[:=]\s*"
)
```

| Kind | Pattern | Covers |
|---|---|---|
| `PRIVATE_KEY` | `(?P<secret>-----BEGIN (?:[A-Z0-9 ]+ )?PRIVATE KEY-----[\s\S]*?(?:-----END (?:[A-Z0-9 ]+ )?PRIVATE KEY-----\|\Z))` | PEM; an unterminated paste redacts to end of text |
| `BEARER_TOKEN` | `(?i)\bbearer\s+(?P<secret>[A-Za-z0-9._~+/=-]{16,})` | `Bearer <token>` (16+ chars so "bearer of bad news" is safe) |
| `BEARER_TOKEN` | `(?i)\bauthorization\s*:\s*(?:(?:basic\|bearer\|token)\s+)?(?P<secret>[^\s,;"']+)` | `Authorization:` header, any scheme |
| `JWT` | `\b(?P<secret>eyJ[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]*)` | three base64url segments (empty signature allowed) |
| `VENDOR_KEY` | `\b(?P<secret>AKIA[0-9A-Z]{16}\|sk-[A-Za-z0-9_-]{20,}\|ghp_[A-Za-z0-9]{30,}\|xox[bp]-[A-Za-z0-9-]{10,})(?![A-Za-z0-9_-])` | AWS, OpenAI-style, GitHub, Slack |
| `KEY_VALUE` | `_KEY_NAME + r"\"(?P<secret>[^\"]+)\""` | JSON/YAML double-quoted (spaces allowed) |
| `KEY_VALUE` | `_KEY_NAME + r"'(?P<secret>[^']+)'"` | single-quoted |
| `KEY_VALUE` | `_KEY_NAME + r"(?P<secret>[^\s,;&}\"']+)"` | bare `key=value`, `key: value`, query strings |
| `KEY_VALUE` | `(?i)\b[a-z][a-z0-9+.-]*://[^\s/:@]+:(?P<secret>[^\s/@]+)@` | URL userinfo password |
| `KEY_VALUE` | `(?i)\bcurl\b[^\n]*?\s(?:-u\|--user)\s+["']?[^\s:"']+:(?P<secret>[^\s"']+)` | `curl -u user:pass` |

Three quoting variants share `_KEY_NAME` by string concatenation so the key list exists once.

- [ ] **Step 1: Write failing tests in `tests/guardrails/test_redactor.py` (structural layer)**
  - One `@pytest.mark.parametrize("case_id,text,secret,kind", _STRUCTURAL_CASES, ids=…)` test `test_structural_secret_is_redacted` with cases (each `text` is realistic, secret is the exact value to disappear):
    `pem` (multi-line RSA block), `pem_truncated` (BEGIN, no END), `bearer_header` (`curl -H 'Authorization: Bearer abcdefghijklmnop1234'`), `authorization_basic` (`Authorization: Basic dXNlcjpwYXNz`), `jwt` (`eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjMifQ.SflKxwRJSMeKKF2QT4`), `aws_akia` (`AKIAIOSFODNN7EXAMPLE`), `openai_sk`, `github_ghp` (`"ghp_" + "a" * 36`), `slack_xoxb` (`xoxb-1234567890-abcdef`), `kv_equals` (`password=hunter2`), `kv_yaml` (`api_key: abc123XYZ`), `kv_json_spaces` (`{"client_secret": "s3cr3t value!", "x": 1}` → secret `s3cr3t value!`), `radius_secret` (`radius_secret = Tr0ub4dor`), `scim_token_env` (`SCIM_TOKEN=tok-12345`), `psk_key` (`pre_shared_key: abc123`), `url_userinfo` (`https://admin:P4ss@host.example.com/x` → `P4ss`), `curl_user` (`curl -u admin:P4ss https://x` → `P4ss`).
  - Assertions per case: `secret not in result.text`; `len(result.findings) == 1` (proves merging collapses the JWT/Bearer/KV double hits); `result.findings[0].kind == kind`; `text[f.start:f.end] == secret`; `f.sha256 == hashlib.sha256(secret.encode()).hexdigest()`; `f"[REDACTED:{kind}]" in result.text`.
  - `test_finding_never_contains_the_raw_value`: `redact("password=hunter2").model_dump_json()` does not contain `hunter2`.
  - `test_overlapping_hits_merge_with_earliest_kind`: `"Authorization: Bearer abcdefghijklmnop1234"` → one finding, `BEARER_TOKEN`.
  - `test_clean_text_is_returned_unchanged`: `redact("BGP hold time is 30 seconds")` → same text, `findings == ()`, `was_redacted is False`.

- [ ] **Step 2: Run the file; confirm it fails on import of `redact`.**

- [ ] **Step 3: Implement `_Hit`, `_Rule`, `_PLACEHOLDER`, `_KIND_RANK`, `_PATTERN_RULES` (structural rows only), `secret_hash`, `_pattern_hits`, `_merge`, `redact`.** Contextual/entropy layers are absent here by design. Export `redact`, `secret_hash` from `guardrails/__init__.py`.

- [ ] **Step 4: Run tests (green), Ruff, Pyright.**

- [ ] **Step 5: Commit** — `feat(guardrails): add redactor core with structural secret layer`

---

### Task 3: Vendor-config layer + contextual layer

**Files:** modify `guardrails/redactor.py`, `tests/guardrails/test_redactor.py`.

**Vendor-config rows appended to `_PATTERN_RULES` (kind `VENDOR_CONFIG`):**

| Pattern | Covers |
|---|---|
| `(?i)\bset\s+(?:psksecret\|passwd\|password\|secret)\s+(?:ENC\s+)?"?(?P<secret>[^\s"]+)` | FortiGate `set psksecret [ENC] <v>` |
| `(?i)\b(?:pre-shared-key(?:\s+(?:local\|remote))?\|key\|password\|secret)\s+[05-9]\s+(?P<secret>\S+)` | Cisco type-0/5/6/7/8/9 `key`, `password`, `secret`, `pre-shared-key` |
| `(?im)^\s*:\s*PSK\s+"(?P<secret>[^"]+)"` | strongSwan `: PSK "…"` |
| `(?m)^\s*(?:export\s+)?[A-Z][A-Z0-9_]*_KEY\s*=\s*["']?(?P<secret>[^\s"']+)` | `.env` `*_KEY=` (D4) |

`# ponytail:` above the Cisco row: untyped keys (`crypto isakmp key <plain> address …`) are left to the contextual and entropy layers; upgrade path: add an untyped rule when a scenario needs it.

**Contextual layer (module level, not in the table — it is not a single-group pattern on a fixed prefix):**
```python
_CONTEXTUAL: Pattern[str] = re.compile(
    r"(?i)\b(?:psk|pre-shared key|password|passphrase|secret|token|api key|shared key)\b"
    r"(?:\s+[^\s:=]+){0,5}?"
    r"\s*(?:\b(?:is|was)\b\s*[:=]?|[:=])\s*"
    r"[\"'(]?(?P<secret>[^\s\"'()]\S*?)(?=[.,;:)\"']*(?:\s|$))"
)
```
- `def _looks_like_secret(value: str) -> bool`: `any(c.isdigit() for c in value) or _character_classes(value) >= 3` (D3). `_character_classes(value) -> int` counts lowercase / uppercase / digit / other (shared with the entropy layer in Task 4 — define it once here).
- `def _contextual_hits(text: str) -> Iterator[_Hit]`: for each match whose `secret` satisfies `_looks_like_secret`, yield `_Hit(*m.span("secret"), SecretKind.CONTEXTUAL)`.
- `redact` adds `_contextual_hits(masked)` to its hit list.

- [ ] **Step 1: Write failing tests**
  - Extend the parametrized structural-style table into `_VENDOR_CASES`: `forti_enc` (`set psksecret ENC abcdEFG==`), `forti_quoted` (`set psksecret "abcd1234"`), `cisco_key7` (`crypto isakmp key 7 0822455D0A16 address 1.2.3.4`), `cisco_password0` (`username a password 0 hunter2`), `cisco_secret5` (`enable secret 5 $1$abc$xyz`), `cisco_psk_local` (`pre-shared-key local 0 MyKey123`), `strongswan` (`: PSK "abc def"` → `abc def`), `env_key` (`STRIPE_SECRET_KEY=abc`), `env_export_key` (`export DEPLOY_KEY="k3y-value"` → `k3y-value`). Same assertions as Task 2 (kind `VENDOR_CONFIG`).
  - `test_contextual_catches_sc08_psk_in_both_spellings`: the real strings (read from the fixture in Task 5; here inline) `PSK on our side is: Fg7!qwe-DC-2026-tunnel. Can you confirm what you have on your side?` and `PSK on our side is Fg7!qwe-DC-2026-tunnel. Can you confirm…` → PSK absent from output, one finding `CONTEXTUAL`, trailing `.` **not** inside the span, output still contains `Can you confirm what you have on your side?`.
  - `test_contextual_value_shape_guard`: parametrize → **no findings** for `"The password reset is pending."`, `"the token was expired"`, `"PSK was re-entered 26 h ago"`, `"The PSK on the Cato side was re-entered yesterday"`, `"the secret is unknown"`.
  - `test_contextual_is_bounded_to_five_words`: `"password one two three four five six is Zz9!aaaa"` → no findings.
  - `test_key_value_and_contextual_overlap_merge_to_key_value`: `"password=hunter2"` → one finding, `KEY_VALUE`.

- [ ] **Step 2: Run; confirm the new cases fail.**

- [ ] **Step 3: Add the four vendor rows, `_CONTEXTUAL`, `_character_classes`, `_looks_like_secret`, `_contextual_hits`; wire into `redact`.**

- [ ] **Step 4: Run tests, Ruff, Pyright.** If `redactor.py` is above 180 lines here, re-read it for a simplification before Task 4.

- [ ] **Step 5: Commit** — `feat(guardrails): add vendor-config and contextual redaction layers`

---

### Task 4: Entropy fallback + allowlist

**Files:** modify `guardrails/redactor.py`, `tests/guardrails/test_redactor.py`.

**Interfaces:**
- Module-top constants (design §4.1): `_ENTROPY_MIN_LENGTH: int = 24`, `_ENTROPY_MIN_CLASSES: int = 3`, `_ENTROPY_MIN_BITS: float = 3.5`.
- `_TOKEN: Pattern[str] = re.compile(r"[^\s\"'`,;()<>\[\]{}]+")`
- `_ENTROPY_ALLOWLIST: tuple[Pattern[str], ...]` — matched with `fullmatch`:
  1. `[a-z0-9]+(?:[-_.][a-z0-9]+)+` — slugs, FQDNs, snake_case, lowercase UUIDs
  2. `(?i)[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}` — any-case UUID
  3. `(?i)[a-z][a-z0-9+.-]*://[^/@\s]*(?:/\S*)?` — URL **without** userinfo
  4. `[^@\s]+@[^@\s]+\.[^@\s]+` — email
  5. `(?i)(?:[0-9a-f]{0,4}:){2,7}[0-9a-f]{0,4}(?:/\d+)?` — IPv6 / CIDR
  6. `/?(?:[a-z0-9._-]+/)+[a-z0-9._-]*` — lowercase file path
  `# ponytail:` above the tuple: lowercase-only segments on purpose so mixed-case base64url tokens stay detectable; upgrade path: per-source allowlists if an FP corpus grows.
- `def _shannon_entropy(token: str) -> float`: bits per character over character frequencies.
- `def _entropy_hits(text: str) -> Iterator[_Hit]`: for each `_TOKEN` match, `token = m.group().rstrip(".:")`; yield `_Hit(m.start(), m.start() + len(token), SecretKind.HIGH_ENTROPY)` when `len ≥ 24`, `_character_classes ≥ 3`, `entropy ≥ 3.5`, and no allowlist pattern full-matches.

- [ ] **Step 1: Write failing tests**
  - `_ENTROPY_CASES` parametrized: `bare_token` (`here q3Zx9LkP0mNb7VcR2tYwH5jA8sDf end`), `base64` (`dGhpcyBpcyBhIHZlcnkgbG9uZyBzZWNyZXQ=`), `mixed_case_with_separators` (`aB3-x_9KqLmN2-pQ7r_ZzYw1vv`) → one finding `HIGH_ENTROPY` each.
  - `_ALLOWLIST_CASES` parametrized → **zero findings** (each token verified to pass all three gates, so each allowlist entry is live): `fqdn` `core-switch-01.prod.internal.company.com`; `slug` `cato-ipsec-guide-ikev1-vs-ikev2-2026`; `snake` `get_link_quality_24h_window_x`; `uuid_upper` `123E4567-E89B-12D3-A456-426614174000`; `url` `https://knowledge.catonetworks.com/docs/cato-ipsec-guide-ikev1-vs-ikev2`; `email` `hana.kowalski.longname1@solsticemedia.com`; `ipv6` `fe80::a1b2:c3d4:e5f6:1234:5678`; `cidr6` `2001:db8:abcd:ef01:2345:6789:abcd:ef01/64`; `path` `/var/log/cato-socket/ipsec-2026-08.log`.
  - `test_url_with_userinfo_is_not_allowlisted`: `"https://admin:P4ss@host.example.com/a/b"` → `P4ss` redacted (KEY_VALUE), proving rule 3 does not shadow the structural rule.
  - `test_below_thresholds_is_not_flagged`: a 23-char high-entropy token (`q3Zx9LkP0mNb7VcR2tYwH5j`, length gate), `"ab" * 12` (24 chars, one class, low entropy), `abcdefghijklmnopqrstuvwxyzabcd` (30 chars, one class) → no findings.

- [ ] **Step 2: Run; confirm the entropy cases fail and allowlist cases are the only currently-green ones.**

- [ ] **Step 3: Implement the constants, allowlist, `_shannon_entropy`, `_entropy_hits`; wire into `redact`.**

- [ ] **Step 4: Mutation check (do not commit the mutations).** For each of the six allowlist patterns, comment it out, run `_ALLOWLIST_CASES`, and confirm at least one case fails; restore. Any entry whose removal fails nothing is dead — delete it and its case.

- [ ] **Step 5: Run tests, Ruff, Pyright; commit** — `feat(guardrails): add high-entropy redaction fallback with allowlist`

---

### Task 5: Corpus, evasion, idempotence, performance; exports; design sync

**Files:** create `tests/guardrails/conftest.py`; modify `tests/guardrails/test_redactor.py`, `guardrails/__init__.py`, `docs/plans/15-guardrails/design.md`.

**`tests/guardrails/conftest.py`** (reused by Plan 2): one session-scoped fixture.
```python
@pytest.fixture(scope="session")
def corpus() -> dict[str, str]: ...
```
Keys (stable, used directly by tests): `Q01`…`Q35` (question), `TCK-2026xxxx.subject` / `TCK-2026xxxx.body` for all 54 tickets in `data/tickets/tickets.jsonl`, `<scenario_id>.opening` and `<scenario_id>.followup<i>` from `data/eval/scenarios.jsonl` (customer text only, never `if_agent`). Read with `json` + `settings.repo_root / "data"`. Fixture asserts the expected counts (35 questions, 54 tickets, 12 scenarios) so a silent data change fails loudly.

- [ ] **Step 1: Write failing tests**
  - `test_seed_secrets_are_redacted`: `TCK-20264230.body` and `SC-08-psk-pasted.opening` → `Fg7!qwe-DC-2026-tunnel` absent, one finding `CONTEXTUAL`, finding hash equals `secret_hash("Fg7!qwe-DC-2026-tunnel")`.
  - `test_negative_corpus_has_no_findings`: for every key in `corpus` **except** `{"TCK-20264230.body", "SC-08-psk-pasted.opening"}`, `redact(text).findings == ()` and `.text == text`. Failure message lists the offending key and kind.
  - `test_redaction_is_idempotent`: for every positive case across the structural/vendor/contextual/entropy tables and both seed secrets, `redact(redact(x).text)` has no findings and equals `redact(x).text` (D6).
  - `test_placeholder_is_never_rewrapped`: `redact("password: [REDACTED:KEY_VALUE] and PSK is: [REDACTED:CONTEXTUAL]")` → no findings.
  - Evasion: `test_fullwidth_psk_is_caught` (`"ＰＳＫ is: Fg7!qwe-DC-2026-tunnel"`); `test_zero_width_inside_secret_is_caught_and_span_covers_it` (`"PSK is: Fg7!q​we-DC-2026-tunnel"` → finding `text[start:end]` contains the `​`; output has no fragment of the secret); `test_zero_width_outside_secret_is_preserved` (a `​` elsewhere survives in `.text`).
  - `test_large_adversarial_inputs_stay_fast`: for `"a_" * 25_000`, `"password " * 8_000`, `"-----BEGIN PRIVATE KEY-----" * 2_000`, `("Ab1!" * 10 + " ") * 5_000`, `"password" + "_a" * 20_000`, `"curl " + "x " * 20_000`, `"psk " + "w " * 20_000`: each `redact` call finishes in < 1 s (`time.perf_counter`; prototype measured ≤ 0.09 s).

- [ ] **Step 2: Run; fix only what fails.** Expected first failures: none in logic; if a corpus key fails, the rule — not the test — is wrong (tighten the rule, keep the corpus assertion).

- [ ] **Step 3: Finalize `guardrails/__init__.py`** exporting `RedactionFinding`, `RedactionResult`, `SecretKind`, `redact`, `secret_hash` with a sorted `__all__`.

- [ ] **Step 4: Sync `design.md`** — edit §3 (`SecretKind` values, `_GuardModel`), §4.1 (D2–D6 wording: separator, value-shape guard, key-list wildcard, allowlist, placeholder masking), §2 (add `normalize.py` row; the injection/validator rows stay untouched for Plan 2). Keep edits minimal; do not renumber sections.

- [ ] **Step 5: Final gates**
  - `uv run pytest tests/guardrails -q` and the existing suite `uv run pytest -q` (no regressions).
  - `ruff check guardrails tests/guardrails`; `pyright guardrails tests/guardrails`.
  - `wc -l guardrails/*.py` — `redactor.py` ≤ 220, `models.py` ≤ 60.
  - Grep audit: `grep -n "import " guardrails/*.py | grep -v "^[^:]*:[0-9]*:\(from\|import\)"` returns nothing (no inline imports); no `TODO`; every `_PATTERN_RULES` row is exercised by a named test case (list them next to the row ids in the PR description).

- [ ] **Step 6: Commit** — `test(guardrails): add redactor corpus, evasion, idempotence and performance tests`

---

## Risks & Notes

- **Contextual/entropy are heuristics.** The negative corpus is the contract; any new FP found later becomes a corpus row, not a special case in the detector.
- **`sha256` of a low-entropy secret is brute-forceable** (a 6-digit PIN). The design stores hashes in `SessionGuardHistory` and on `RedactionFinding`. Acceptable while Phase 2 keeps history in session memory and never traces findings verbatim; if findings are persisted, switch `secret_hash` to HMAC with a per-session key (one function changes, both call sites follow). Flagged for the Phase 2 conversation-state design.
- **`key 7 …` Cisco rule can over-redact prose** (`"press key 7 times"` → `times`). Accepted: the redaction direction is the safe one and POL-CRED treats pasted secrets as compromised.
