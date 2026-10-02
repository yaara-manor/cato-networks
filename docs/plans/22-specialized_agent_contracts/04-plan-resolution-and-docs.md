# Resolution Agent, Exports & Docs Implementation Plan (22 / plan 4 of 4)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax. User rule: no code lines in this plan.

**Goal:** `run_resolution()` returning `AgentRun[ResolutionPlan]` with guardrail-backed PydanticAI output validators, a canned escalation fallback, public exports, and architecture/ADR doc updates.

**Architecture:** No tools. `ResolutionPlan` is both LLM output and final result. Two output validators call existing `guardrails.check_citations` and `guardrails.check_outgoing_message`; any violation raises `ModelRetry` (budget 1). Exhausted retries or model failure map to a constant holding plan with `escalate_to_human=True`.

**Tech Stack:** pydantic-ai 2.51, existing `guardrails/`.

**Spec:** design §3.5, §4.4, §4.5, §6. **Depends on:** plans 01-03.

## Global Constraints

Same as plan 01 (typed, no inline imports, frozen contracts, functional tests, no brainstruct, f-strings only, no new dependencies).

## Design Decisions (this plan)

- Validators are plain module-level functions registered by `build_resolution_agent`; each does one check and returns the plan unchanged or raises `ModelRetry` with fixed text built from violation kind names only (never customer text, never matched secret text). Shared message formatting is one small helper.
- `deps.grounding` is set by `run_resolution` via `dataclasses.replace(deps, grounding=data.grounding_context())`; validators read it and raise a clear programming error if `None`.
- Canned holding message: one module constant in `agents/resolution.py`, no markers/numbers; test asserts it passes `check_citations` (as a refusal grounding) and `check_outgoing_message`.
- Sev-1 hard gate lives in `guardrails.validator.check_action` (design §4.4), not in `agents/`: Resolution only proposes `PAGE_ON_CALL`; the orchestrator consumes the decision. Gate = Triage `P1` AND `sev1_corroborated` (code-derived from telemetry, design §4.4) AND not already paged; LLM-judged priority alone never pages.
- `identity.account is None`: `run_resolution` drops all actions (validated in code, not trusted to the prompt). `target_account_id` for `to_proposed_action` always comes from `identity.account`; the orchestrator calls it, this plan only guarantees the mapping.
- Approval is not a model field (design §3.5); the 23 orchestrator derives pending approvals from `check_action`.
- Escalation reason is a fixed string ("output validation retries exhausted" or "model failure") per plan 01 decision 7.

## Review Focus

- Uncited technical claim then cited rewrite: one retry, final message grounded.
- Money amount sentence ("$3,600 credit") on both attempts without `CREDIT` approval: canned plan, `escalate_to_human`; with `CREDIT` in `approved_actions` passes.
- Refusal grounding (`is_refusal`) with a `[kb:...]` marker: retry.
- Marker for a KB slug not in retrieved passages (fabricated citation): retry.
- Model failure (invalid output past budget): canned plan, trace still returned.
- Echoing a redacted secret from `guard_history.secret_hashes`: `SECRET_ECHO` retry.

## File Structure

- `guardrails/models.py` (modify, small): add `ActionType.PAGE_ON_CALL`.
- `guardrails/validator.py` (modify, small): `check_action` gains a `PAGE_ON_CALL` rule and three keyword arguments with defaults (`priority: TicketPriority | None = None`, `sev1_corroborated: bool = False`, `already_paged: bool = False`) so existing callers/tests stay valid; ALLOW only when priority is `P1`, `sev1_corroborated` and not already paged, else DENY `POL-SEV1`. Read the existing match statement and exhaustiveness handling first; `SupportActionKind` stays a separate enum (it has ungated kinds), mapped via the table.
- `tests/guardrails/test_validator.py` (modify): P1 + corroborated + not paged -> ALLOW; non-P1 -> DENY; P1 without corroboration -> DENY; already paged -> DENY; unknown identity -> existing POL-IDV DENY.
- `agents/resolution.py` (create): `HOLDING_MESSAGE`, two output validators, `build_resolution_agent`, `run_resolution`.
- `prompts/resolution.md` (create).
- `agents/__init__.py` (modify): re-exports only; public contracts, `build_*`, `run_*`, `SupportDeps`, `AgentRun`, `AgentTrace`.
- `tests/agents/test_resolution.py` (create); prompt smoke tests across all four prompts in `tests/agents/test_prompts.py` (create, tiny).
- `docs/architecture/system-architecture-design.md` and `docs/overview/decisions.md` (modify).

## Tasks

### Task 0: Sev-1 hard gate in `check_action`

**Files:** modify `guardrails/models.py`, `guardrails/validator.py`, `tests/guardrails/test_validator.py`.

- [ ] **Step 1: Failing tests** per the file list above.
- [ ] **Step 2:** Run `uv run pytest tests/guardrails -v`; FAIL. Implement; PASS (all existing guardrail tests still green).
- [ ] **Step 3: Commit** `feat(guardrails): Sev-1 PAGE_ON_CALL hard gate`.

### Task 1: Validators and fallback

**Files:** create `agents/resolution.py`, `tests/agents/test_resolution.py`.

**Interfaces:** `build_resolution_agent(model: Model | None = None) -> Agent[SupportDeps, ResolutionPlan]` (no tools, output retry budget 1, both validators registered); `run_resolution(data: ResolutionInput, deps: SupportDeps, model: Model | None = None) -> AgentRun[ResolutionPlan]`.

- [ ] **Step 1: Failing tests** (scripted `FunctionModel` that returns a different `ResolutionPlan` per attempt; build `ResolutionInput` with real knowledge/triage objects from earlier plans' fixtures; expected sentences chosen from `tests/guardrails/test_validator.py` cases so they are known to trip the real guards):
  - uncited-claim first attempt, cited second: one retry, final passes `check_citations`;
  - credit sentence on both attempts: canned plan, `escalate_to_human=True`, empty `actions`, escalation reason fixed string; same sentence with `CREDIT` in `approved_actions` passes;
  - refusal grounding with `[kb:...]` marker: retry;
  - `identity.account is None` with actions in the plan: actions dropped;
  - model failure: canned plan, trace present;
  - grounding excludes a failed telemetry tool: a `[telemetry:<failed_tool>]` marker triggers a retry;
  - canned message passes both guards.
- [ ] **Step 2:** Run `uv run pytest tests/agents/test_resolution.py -v`; FAIL. Implement; PASS.
- [ ] **Step 3: Commit** `feat(agents): run_resolution with guard validators`.

### Task 2: Resolution prompt

**Files:** create `prompts/resolution.md`; create `tests/agents/test_prompts.py`.

Content per design §4.4/§4.5: empathetic tone under pressure; follow KB diagnostic order, commands only in backticks; marker grammar (`[kb:<slug>#<anchor>]`, `[policy:POL-X]`, `[telemetry:<tool>]`) with one worked example (read exact grammar from `guardrails/validator.py` regexes, do not paraphrase from memory); quote telemetry evidence verbatim; SLA statements copied only from `triage.sla`; never state credits, MFA resets or verdict overrides as done (propose the action, state Escalation Board approval is needed, keep the conversation open); decline malware/C2 overrides and propose escalation to Security Ops (`POL-SEC`); Sev-1 `PAGE_ON_CALL` only per `POL-SEV1` with one-line `reason`; one scoping question when `triage.scoping_question` is set; refusal wording for LOW_CONFIDENCE_REFUSAL/UNAVAILABLE with human routing and no technical claims; never repeat redacted secrets. Fixed headings as in other prompts; no `SC-`/`expected`.

- [ ] **Step 1: Failing test**: parameterized over the four prompt names: loads non-empty, has the six required headings, contains no `SC-` or `expected`; Resolution prompt additionally contains all three marker prefixes.
- [ ] **Step 2:** Run; FAIL (resolution prompt missing). Write prompt; PASS.
- [ ] **Step 3: Commit** `feat(agents): resolution prompt`.

### Task 3: Exports and end-to-end contract flow

**Files:** modify `agents/__init__.py`; add `tests/agents/test_pipeline_contracts.py`, `tests/agents/test_live_smoke.py`.

- [ ] **Step 1: Failing test**: one scripted full chain (Triage, Diagnostics, Knowledge, Resolution) over a seeded account with scripted models, checking each role's assembled output is accepted as the next role's input and that `ResolutionPlan.customer_message` passes `check_citations` and `check_outgoing_message` end to end; also `from agents import ...` for every public name.
- [ ] **Step 2:** Run; FAIL. Update `__init__.py` (re-exports only, zero logic); PASS.
- [ ] **Step 2b:** `test_live_smoke.py`: one Triage run against the real `settings.llm_model`, `pytest.mark.skipif` on missing `OPENAI_API_KEY`; asserts only that a valid `TriageResult` returns.
- [ ] **Step 3: Commit** `feat(agents): exports and chain test`.

### Task 4: Docs

**Files:** modify `docs/architecture/system-architecture-design.md` (§4.1 `SupportDeps`, §4.2 role outputs split + `ResolutionPlan` without `pending_approval` + no `propose_action` tool + identity resolved by the orchestrator and passed in `TriageInput` + Sev-1 gate in `check_action`), `docs/overview/decisions.md` (next free ADR number at implementation time, "LLM decides, code records; native output-validator retry; no brainstruct, PydanticAI-native tracing").

- [ ] **Step 1:** Edit both docs; grep the architecture doc and `docs/` for `brainstruct` and replace per decision 1 of plan 01.
- [ ] **Step 2: Commit** `docs: agent contracts ADR and architecture updates`.

### Task 5: Cleanup, lint, type check (final)

- [ ] Ruff and pyright (repo config) over the whole `agents/` and `tests/agents/`; fix.
- [ ] Final unused-code sweep across plans 1-4: every `Intent` and `SupportActionKind` member exercised by a test; no unused contract field; no unused helper.
- [ ] Confirm file sizes stay small (`agents/models.py` under about 350 lines, others well below); split only if exceeded.
- [ ] Grep: no `brainstruct`, no inline imports, no `datetime.now`, no `Literal` for enum-like fields in `agents/`.
- [ ] Run `uv run pytest tests/agents -v`; all green. Commit `chore(agents): final cleanup`.

## Unresolved Questions

None.

Decisions recorded:
- Sev-1 gate: `P1` AND `sev1_corroborated` AND not paged (design §4.4). `sev1_corroborated` is built in plan 03 (`DiagnosticEvidence.from_tool_results`); the orchestrator passes it (False if Diagnostics skipped).
- Live-LLM smoke test lives here: `tests/agents/test_live_smoke.py` (Task 3), skipped without `OPENAI_API_KEY`, one Triage run against the real model; no Phase 5 deferral.
- Single `settings.llm_model` for all roles; no per-role split.
- `check_claims` stays in the 23 ingestion guard (design §8); not called from `run_resolution`.

