# Diagnostics & Knowledge Agents Implementation Plan (22 / plan 3 of 4)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax. User rule: no code lines in this plan.

**Goal:** `run_diagnostics()` and `run_knowledge()` returning `AgentRun[DiagnosticEvidence]` / `AgentRun[KnowledgeBundle]`, with evidence, passages and policies assembled from tool results in code and an account-ownership guard around all telemetry tools.

**Architecture:** Thin tool wrappers return the services' typed envelopes unchanged (`TelemetryToolResult[T]`, `KBSearchResult`, `PolicyDocument | None`). `DiagnosticEvidence.from_tool_results` and `KnowledgeBundle.from_tool_results` classmethods build the assembled outputs from `agents.messages.tool_returns`. One ownership check helper serves all 7 telemetry wrappers (no per-tool copy).

**Tech Stack:** pydantic-ai 2.51, existing `tools.TelemetryService`, `retrieval.RetrievalService`.

**Spec:** design §3.3, §3.4, §4.2, §4.3. **Depends on:** plan 01 (and plan 02 only for test fixtures of a `TriageResult`; build one directly with a scripted decision, no Triage run needed).

## Global Constraints

Same as plan 01 (typed, no inline imports, frozen tuples, functional tests with scripted `FunctionModel`, real services and seeded DB, no brainstruct, f-strings only, conversions as classmethods, no new dependencies).

## Design Decisions (this plan)

- **Ownership guard is the 80%-effort item** (security: SC-05 `ACC-1005` site while caller is `ACC-1007`). One private helper `_site_belongs_to_caller(deps, site_id) -> bool` using membership in `deps.telemetry.list_sites(account_id).data.sites`; the shared wrapper path returns an `INVALID_ARGUMENT` `TelemetryToolResult` with error "site not in caller account" built by one helper, tool name preserved. `get_client_diagnostics(user_email)` has no site id: call, then compare `data.customer_id` with the account; mismatch returns the same refusal envelope with `data=None`, `evidence=[]`. `identity.account is None` or `not is_verified_account_member` refuses all 7 tools, including `list_sites` (its `account_id` argument is ignored in favour of `identity.account`; the wrapper takes no account argument so the model cannot pick one).
- **Wrappers**: 7 functions, each 1-3 lines over the guard helper; tool docstrings are the model-visible tool descriptions (keep them short, with window/event_type argument semantics copied from `tools/telemetry.py`).
- **Dedup/ordering in classmethods** (one place each): `inspected_tools` dedupes preserving call order via `dict.fromkeys`; passages dedupe by `passage_id` keeping highest `rerank_score`, then sort by `rerank_score` descending.
- **Hypothesis with zero evidence is dropped** inside `run_diagnostics` by `model_copy` on findings (not by prompt trust).
- **Status rule (KnowledgeBundle)**: any CONFIDENT call gives CONFIDENT; else any UNAVAILABLE gives UNAVAILABLE; else (including no call) LOW_CONFIDENCE_REFUSAL. Gate stays in `RetrievalService`; no second threshold in agents.
- **`snapshot_date`**: from the first non-None `KBSearchResult.snapshot_date`; if only policies were fetched it is `None`.

## Review Focus

- Foreign-account site id (prompt-injected): refused, zero evidence, listed in `unavailable`; the foreign data never enters message history as usable evidence (the refused envelope has no data).
- Unverified caller (domain mismatch) cannot read any telemetry.
- Corrupt/empty telemetry dir: every tool returns `UNAVAILABLE`-style envelope, run completes, `unavailable` populated.
- Model skips telemetry entirely: `inspected_tools == ()`, hypothesis `None`.
- `get_policy` with unknown id returns `None`: absent from `referenced_policies`, no exception; policy id normalisation is done inside `RetrievalService.get_policy` (reuse, do not repeat).
- Search returns `UNAVAILABLE` but a policy fetch succeeds: bundle status `UNAVAILABLE`, policies still present.
- Two searches returning the same passage: single copy in `retrieved_passages`; `candidates` also deduped.

## File Structure

- `agents/diagnostics.py` (create): wrappers, ownership guard helper, `build_diagnostics_agent`, `run_diagnostics`.
- `agents/knowledge.py` (create): 2 tools, `build_knowledge_agent`, `run_knowledge`.
- `agents/models.py` (modify): bodies of the two `from_tool_results` classmethods.
- `prompts/diagnostics.md`, `prompts/knowledge.md` (create).
- `tests/agents/test_diagnostics.py`, `tests/agents/test_knowledge.py` (create); truth table for the status rule added to `tests/agents/test_contracts.py`.

## Tasks

### Task 1: `KnowledgeBundle` and `DiagnosticEvidence` assembly

**Files:** modify `agents/models.py`, `tests/agents/test_contracts.py`.

**Interfaces:** `DiagnosticEvidence.from_tool_results(findings: DiagnosticsFindings, results: Sequence[TelemetryToolResult[Any]]) -> DiagnosticEvidence` (evidence of `OK` results flattened in call order; every non-OK result becomes `UnavailableTool(tool_name, status, error)`). `KnowledgeBundle.from_tool_results(findings: KnowledgeFindings, searches: Sequence[KBSearchResult], policies: Sequence[PolicyDocument]) -> KnowledgeBundle` per the rule above; `queries` = each search's `query` in call order.

- [ ] **Step 1: Failing test** status truth table (the only unit-style test; high-risk rule): all combinations of {CONFIDENT, LOW_CONFIDENCE_REFUSAL, UNAVAILABLE} over 0-2 searches, parameterized; dedup of duplicate passage ids; policy dedup.
- [ ] **Step 2: Failing test** diagnostics assembly with real envelopes from `TelemetryService` (S-1007-01 BGP): `evidence_items` includes the `routes_count` anomaly entry, `has_anomaly` true, `unavailable_tools` empty; a `NOT_FOUND` envelope lands in `unavailable`.
- [ ] **Step 3:** Run `uv run pytest tests/agents/test_contracts.py -v`; FAIL. Implement; PASS.
- [ ] **Step 4: Commit** `feat(agents): evidence and knowledge assembly`.

### Task 2: Diagnostics tools with ownership guard

**Files:** create `agents/diagnostics.py` (tools + guard), `tests/agents/test_diagnostics.py`.

**Interfaces:** 7 tool functions `list_sites`, `get_site_status`, `get_link_quality(site_id, window="24h")`, `get_events(site_id, event_type=None, window="24h")`, `get_bgp_status`, `get_ipsec_status`, `get_client_diagnostics(user_email)`; all take `RunContext[SupportDeps]` first; return the service envelope or the refusal envelope.

- [ ] **Step 1: Failing tests** (call tools through a scripted agent run so the real PydanticAI tool path is exercised): own site returns OK with evidence; SC-05-style foreign site refused (`INVALID_ARGUMENT`, no data, no evidence); client diagnostics for a foreign customer's email refused after the call; unverified identity refuses everything; `account is None` refuses everything. Read the account/site pairs from `data/telemetry/` and the scenario fixtures, not from literals copied from the design where avoidable.
- [ ] **Step 2:** Run; FAIL. Implement guard + wrappers; PASS.
- [ ] **Step 3: Commit** `feat(agents): guarded telemetry tools`.

### Task 3: Diagnostics prompt, factory, `run_diagnostics`

**Files:** modify `agents/diagnostics.py`; create `prompts/diagnostics.md`; extend tests.

**Interfaces:** `build_diagnostics_agent(model: Model | None = None) -> Agent[SupportDeps, DiagnosticsFindings]`; `run_diagnostics(data: DiagnosticsInput, deps: SupportDeps, model: Model | None = None) -> AgentRun[DiagnosticEvidence]`: `run_role`, then `DiagnosticEvidence.from_tool_results(findings, tool_returns(...) over all 7 tool names)`; empty `inspected_tools` forces `root_cause_hypothesis=None`; `output is None` gives empty findings plus whatever evidence was gathered. Prompt per design §4.2/§4.5 (inspection order; verbatim evidence via `TelemetryEvidence.format_citation()` wording; anomalies first; `kb_query_hints` carry exact error strings; per-status wording; two examples: BGP route limit, IPsec `NO_PROPOSAL_CHOSEN`; no `SC-` ids).

- [ ] **Step 1: Failing tests**: scripted `get_bgp_status("S-1007-01")` then findings gives `inspected_tools == ("get_bgp_status",)` and the anomaly in `evidence_items`; telemetry dir pointed at an empty tmp dir gives populated `unavailable` and a completed run; no tool call gives hypothesis `None` even when the scripted findings supply one; model failure gives empty findings with evidence gathered so far; prompt smoke test (headings, no `SC-`/`expected`).
- [ ] **Step 2:** Run; FAIL. Implement; PASS.
- [ ] **Step 3: Commit** `feat(agents): run_diagnostics`.

### Task 4: Knowledge agent

**Files:** create `agents/knowledge.py`, `prompts/knowledge.md`, `tests/agents/test_knowledge.py`.

**Interfaces:** tools `search_knowledge_base(ctx, query: str) -> KBSearchResult` (default `top_k`) and `get_policy(ctx, policy_id: str) -> PolicyDocument | None`; `build_knowledge_agent(model=None) -> Agent[SupportDeps, KnowledgeFindings]`; `run_knowledge(data: KnowledgeInput, deps: SupportDeps, model=None) -> AgentRun[KnowledgeBundle]` using `tool_returns` for both tools; model failure gives bundle from results already obtained with empty `uncovered_topics`. Prompt per design §4.3 (1-3 focused queries, error strings from `kb_query_hints`, no PII; policy-selection table POL-CREDIT/IDV/SEC/SEV1/SLA/CRED; honest `uncovered_topics`).

- [ ] **Step 1: Failing tests**: scripted search for the Q10 `NO_PROPOSAL_CHOSEN` question gives `CONFIDENT`, non-empty passages, `snapshot_date` set; off-domain question (use the off-domain fixture/ADR-007 tests in `tests/retrieval/test_search_kb.py` as source) gives `LOW_CONFIDENCE_REFUSAL`, empty passages, non-empty candidates; closed DB connection (use a throwaway connection that is closed) gives `UNAVAILABLE` while `get_policy("POL-CREDIT")` is still served (policies are in memory); unknown policy id absent; two searches with overlapping passages are deduped; prompt smoke test.
- [ ] **Step 2:** Run; FAIL. Implement; PASS.
- [ ] **Step 3: Commit** `feat(agents): run_knowledge`.

### Task 5: Cleanup, lint, type check

- [ ] Ruff and pyright (repo config) on `agents` and `tests/agents`; fix.
- [ ] Confirm the ownership guard exists once; no duplicated refusal-envelope construction; no unused tool wrapper (each of the 7 is exercised by at least one test).
- [ ] Grep: no `brainstruct`, no inline imports, no `SC-`/`expected` in the two prompts.
- [ ] Commit `chore(agents): diagnostics/knowledge cleanup`.

## Unresolved Questions

1. Refuse `list_sites` for unverified callers too (plan says yes)?
2. Evidence from `get_client_diagnostics` of a same-account but different user: allowed?
3. Show scores/candidates to the Knowledge model, or hide (experiments D variants hid scores)?
