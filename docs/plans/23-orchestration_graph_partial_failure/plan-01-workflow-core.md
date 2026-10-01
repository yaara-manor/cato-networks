# Orchestration Workflow Core Implementation Plan (Plan 1 of 2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A sync, LLM-free `Workflow.run_turn` that runs one customer turn through ingestion guard, Triage, optional Diagnostics, Knowledge, Resolution and the action gate, persisting every step through issue 6's `StateStore`.

**Architecture:** One plain-Python pipeline (no graph framework). Routing is a pure function over `TriageResult`. Agents are injected callables (the issue 7 `run_<role>` functions, or scripted stubs in tests). All state lives in Postgres via `StateStore`; the workflow keeps no state between turns.

**Tech Stack:** Python 3.12, pydantic (frozen models), pytest, psycopg (via `StateStore`). PydanticAI is used only inside the agents (issue 7); the workflow imports `AgentRun` and the contracts, not `Agent`.

**Spec:** `docs/plans/23-orchestration_graph_partial_failure/design.md` (read with `docs/plans/21-agent_state_machine/design.md` and `docs/plans/22-specialized_agent_contracts/design.md`). Where this plan and design.md disagree, this plan wins (see Design Decisions).

**Depends on:** issues 6 and 7 merged (`storage/*`, `agents/*` contracts and `run_<role>` do not exist in the repo yet). If they land first with different signatures, Task 1 is the only place to adapt.

## Design Decisions (overrides of design.md, with reasons)

1. **Hand-rolled pipeline, not `pydantic_graph`.** The flow has one real branch (after Triage), no loops (see 5), and persistence is already decided by issue 6 as rows plus `set_stage` per node. `pydantic_graph` would add node classes, a second persistence mechanism (its state persistence vs `StateStore` rows) and an async-only run model, for a graph of 6 nodes. Revisit only if resumable mid-turn execution or graph visualisation becomes a requirement.
2. **Sync, not async.** Issue 7 makes `run_<role>` sync (`run_sync`); `StateStore` is sync. design.md's async ports would force `asyncio.to_thread` around every call for nothing. Issue 9/API layer wraps `run_turn` in `asyncio.to_thread` once.
3. **No `ConversationState` model.** Issue 6's `ConversationSnapshot` (from `StateStore.rehydrate`) is the state. History for agents is the snapshot's messages mapped to issue 7's `ConversationTurn`. Prior Triage decision is not fed back explicitly: issue 7's `TriageInput` has only `history`, and the scoping question plus the customer's answer are in that history. This deletes `awaiting_scoping_answer`, `with_*` methods and a duplicate persistence story.
4. **Workflow owns persistence, through `StateStore` only.** design.md says the caller persists; but issue 6 needs `set_stage` at every node and traces per agent call, which only the workflow can do. A small `TurnRecorder` keeps that out of the routing code (Single Responsibility). Issue 9/API layer only supplies a connection and a `message_id`.
5. **No Diagnostics <-> Knowledge back-edge, no `MAX_DIAG_KB_ROUNDS`.** Issue 7's contracts have no `needs_more_telemetry` signal; the forward hand-off already exists (`DiagnosticsFindings.kb_query_hints`). Adding a back-edge needs two contract changes in issue 7 for a speculative case. Open question 1.
6. **No `OUTPUT_GUARD` re-prompt in the workflow.** Issue 7's `run_resolution` already validates citations and the outgoing message with PydanticAI output validators, retries once, then returns the canned human-handoff plan. Re-doing it here is duplicate logic. The workflow reuses `ConversationStage.OUTPUT_GUARD` only if Plan 2 needs it (it does not).
7. **Reuse `ConversationStage` (issue 6) as the state enum.** No new `WorkflowState`. Visited stages are returned in `TurnResult.path` for tests.
8. **No `GroundingContext.from_turn`.** Issue 7's `ResolutionInput.grounding_context()` already does it.
9. **No brainstruct / Braintrust tracing anywhere.** design.md and architecture mention Braintrust export; this plan overrides it. Observability is the issue 6 `traces` / `tool_calls` tables (`StateStore.record_trace`, `replay_trace`) plus PydanticAI's own `result.usage()` and message history, which agents already convert into `AgentTrace`. Do not add or import `braintrust` in `orchestration/`.
10. **Retrying a turn is idempotent where it is cheap.** `run_turn` takes a caller `message_id`; `append_message` dedupes on it, approvals dedupe on `idempotency_key` derived from it. Agents re-run on retry (new trace rows, append-only); stated limit, not worth a replay cache.

## Global Constraints

- Every function, method and generator fully typed, `-> None` included; Pyright `standard` clean.
- All imports at module top; no inline imports.
- Frozen pydantic models, tuples not lists, `StrEnum` for enums (repo ADR-005; `AtiIntEnum` / `novia_shared` do not exist in this repo).
- f-strings only; conversion logic as `@classmethod` on the target class, not `format_x` functions.
- No `datetime.now`; time from `SimulationClock.now()` passed into every `StateStore` write.
- No new dependencies. Reuse, do not re-implement: `guardrails.redactor.redact`, `guardrails.injection.detect`, `guardrails.validator.check_claims` / `check_action`, `guardrails.models.SessionGuardHistory` / `ProposedAction` / `GateOutcome`, `services.models.CallerIdentity`, `core.clock.SimulationClock`, issue 6 `StateStore` / `ConversationStage` / `Approval` / `TraceRecord.from_agent_trace` / `MessageSender`, issue 7 `TriageInput` / `TriageResult` / `Intent` / `DiagnosticsInput` / `KnowledgeInput` / `ResolutionInput` / `ResolutionPlan` / `SupportAction.to_proposed_action` / `AgentRun` / `SupportDeps` / `ConversationTurn`.
- Tests are functional and multi-turn (real `guardrails`, real Postgres `StateStore`, scripted agent callables). No per-function unit tests; the one pure routing table gets one parametrized check.
- Each file stays under ~150 lines; `orchestration/__init__.py` re-exports only.

## Review Focus

1. Customer message containing a PSK: only the redacted text reaches agents, `messages`, `traces` and `guard_history` (asserted by scanning persisted columns).
2. Injection-blocked opener, then a genuine follow-up in the next turn: conversation not closed, follow-up answered normally, agents never called on the blocked turn.
3. Unrecognised caller (`identity.account is None`) whose Resolution proposes an action: action dropped, nothing persisted as approval.
4. Same `message_id` submitted twice (client retry): one customer message row, no duplicate approval.
5. `ProposedAction` for a different account than the caller (SC-05): `DENY`, reason shown, never in `pending_actions`.

## File Structure

| File | Responsibility |
|---|---|
| `orchestration/models.py` | `AgentPorts` (frozen dataclass of the four callables), `TurnResult`. |
| `orchestration/routing.py` | Pure `next_stage_after_triage(result: TriageResult) -> ConversationStage`; pure `compose_reply(...)`. |
| `orchestration/canned.py` | Fixed text constants: injection refusal, agent-failure pause message. |
| `orchestration/recorder.py` | `TurnRecorder`: thin wrapper over `StateStore` for stage, message, trace, guard-history, approval writes of one turn. |
| `orchestration/workflow.py` | `Workflow.run_turn` plus one private method per step (`_ingest`, `_triage`, `_evidence`, `_resolve`, `_gate`). |
| `orchestration/__init__.py` | Re-exports. |
| `tests/orchestration/conftest.py` | Fixtures: `StateStore` on the seeded Postgres (reuse `db_conn`-style fixture from `tests/services/test_support_intake_functional.py` and the `_identity` helper pattern in `tests/guardrails/conftest.py`), scripted agent stubs recording calls. |
| `tests/orchestration/test_routing.py`, `test_guard_flow.py`, `test_persistence.py` | Functional tests below. |

---

### Task 1: Contracts and canned text

**Files:**
- Create: `orchestration/models.py`, `orchestration/canned.py`, `orchestration/__init__.py`
- Test: none (types only; exercised by Tasks 2-4)

**Interfaces:**
- Consumes: issue 7 `TriageInput` / `TriageResult` / `DiagnosticsInput` / `DiagnosticEvidence` / `KnowledgeInput` / `KnowledgeBundle` / `ResolutionInput` / `ResolutionPlan` / `AgentRun[T]` / `SupportDeps` / `SupportAction`; issue 6 `ConversationStage`; `guardrails.models.ProposedAction`.
- Produces:
  - `AgentPorts`: frozen dataclass with fields `triage`, `diagnostics`, `knowledge`, `resolution`, each a `Callable[[<Role>Input, SupportDeps], AgentRun[<Role output>]]` (the exact shape of issue 7's `run_<role>` once its model argument is bound with `functools.partial`). Output types: `TriageResult`, `DiagnosticEvidence`, `KnowledgeBundle`, `ResolutionPlan`.
  - `TurnResult` (frozen): `reply: str`, `path: tuple[ConversationStage, ...]`, `pending_actions: tuple[ProposedAction, ...]`, `executable_actions: tuple[SupportAction, ...]` (ALLOW or ungated kinds, for issue 9's dispatcher), `degradations` (added in Plan 2 Task 1, left out here), `escalation_offered: bool`.
  - `canned.py`: `INJECTION_REFUSAL`, `AGENT_FAILURE_PAUSE` string constants.

- [ ] **Step 1:** Create the three files with the models above. If issue 7's `run_<role>` signatures differ from the assumed shape (open question 2), change only the `AgentPorts` field types.
- [ ] **Step 2:** Run `uv run pyright orchestration` and `uv run ruff check orchestration`. Expected: clean.
- [ ] **Step 3:** Commit: `feat(orchestration): contracts and canned text`.

### Task 2: Pure routing and reply composition

**Files:**
- Create: `orchestration/routing.py`
- Test: `tests/orchestration/test_routing.py`

**Interfaces:**
- Consumes: `TriageResult` (property `scoping_question`, `decision.intent`), `Intent`, `ConversationStage`.
- Produces: `next_stage_after_triage(result: TriageResult) -> ConversationStage` returning `RESOLUTION` when `scoping_question` is set or intent is `ADVERSARIAL`, `DIAGNOSTICS` for `TELEMETRY_DIAGNOSIS`, `KNOWLEDGE_RETRIEVAL` for `KB_INQUIRY` / `POLICY_REQUEST`; exhaustive `match` with an `assert_never` default. `compose_reply(prefix_notices: tuple[str, ...], message: str, denial_reasons: tuple[str, ...]) -> str` joining notice text first, then the message, then denial reasons, separated by blank lines.

- [ ] **Step 1:** Write one parametrized test `test_next_stage_after_triage` over the four intents plus the scoping-question and adversarial overrides, using real `TriageResult` objects built with `identity` from the guardrails `_identity` helper pattern. Add one assertion in a second test that `compose_reply` orders notices, message, denials and omits empty parts.
- [ ] **Step 2:** Run `uv run pytest tests/orchestration/test_routing.py -v`. Expected: FAIL (module missing).
- [ ] **Step 3:** Implement `routing.py`.
- [ ] **Step 4:** Re-run. Expected: PASS.
- [ ] **Step 5:** Commit: `feat(orchestration): triage routing table`.

### Task 3: TurnRecorder and Workflow happy path with persistence

**Files:**
- Create: `orchestration/recorder.py`, `orchestration/workflow.py`
- Test: `tests/orchestration/conftest.py`, `tests/orchestration/test_persistence.py`

**Interfaces:**
- Consumes: Task 1 and 2 outputs; `StateStore.rehydrate`, `set_stage`, `append_message`, `record_trace`, `save_guard_history`, `update_identity`, `create_approval`; `TraceRecord.from_agent_trace`; `guardrails.redactor.redact`; `guardrails.injection.detect`; `guardrails.validator.check_claims`, `check_action`; `SessionGuardHistory.with_redaction` / `with_injection` / `with_entitlement`.
- Produces:
  - `TurnRecorder(store: StateStore, clock: SimulationClock, conversation_id: UUID)` with methods `enter(stage)`, `record_message(sender, text, message_id | None)`, `record_run(role, run, parent_trace_id | None) -> UUID` (returns trace id), `save_guard_history(history)`, `save_identity(identity)`, `create_approval(trace_id, action, idempotency_key)`. Each is a single store call; no logic.
  - `Workflow(ports: AgentPorts, store: StateStore, clock: SimulationClock, base_deps: SupportDeps)`.
  - `Workflow.run_turn(conversation_id: UUID, message: str, message_id: UUID) -> TurnResult`.

Step order inside `run_turn` (each a private method, one concern):
1. `_ingest`: `redact` -> `history.with_redaction`; `detect` -> `with_injection`; persist redacted customer message and history. If blocked: append `INJECTION_REFUSAL` as an agent message, `enter(IDLE)`, return with path `(INGESTION_GUARD, IDLE)`; agents untouched.
2. `_triage`: build `TriageInput` from the snapshot (history mapped to `ConversationTurn`), call `ports.triage`, record the run, persist identity, then `check_claims(redacted, result.identity)` -> `with_entitlement` -> persist history. Rebuild deps with `dataclasses.replace` (identity and guard history) for later steps.
3. Route with `next_stage_after_triage`; `_evidence` runs Diagnostics (if routed) then Knowledge (always after Diagnostics, or directly for KB intents), skipping both for the Resolution-direct routes. Each run recorded with the previous trace id as parent.
4. `_resolve`: build `ResolutionInput` (diagnostics / knowledge `None` when skipped), call `ports.resolution`, record.
5. `_gate`: map each `SupportAction` through `to_proposed_action(identity.account.account_id)`; no account -> drop all actions. `None` result -> `executable_actions`; else `check_action`: `ALLOW` -> `executable_actions`, `REQUIRE_APPROVAL` -> `pending_actions` + `create_approval` (idempotency key built from `message_id` and action index), `DENY` -> reason text into `denial_reasons`.
6. Append the composed reply as an agent message, `enter(IDLE)`, return `TurnResult`.
Each step calls `enter(<stage>)` first so a crash resumes at the last committed node (issue 6 semantics).

- [ ] **Step 1:** Write `conftest.py` (store fixture mirroring the existing `db_conn` fixture; stub agent factory returning typed outputs and recording calls) and `test_persistence.py` with: (a) SC-01 style turn with scripted Triage (`TELEMETRY_DIAGNOSIS`), Diagnostics, Knowledge, Resolution: assert `path` equals `(INGESTION_GUARD, TRIAGE, DIAGNOSTICS, KNOWLEDGE_RETRIEVAL, RESOLUTION, ACTION_EVALUATION, IDLE)`, and that after dropping the `Workflow` and opening a new connection `rehydrate` shows the customer and agent messages and stage `IDLE`; (b) retry with the same `message_id`: one customer message row; (c) SC-08 PSK message: scan every text and jsonb column of the runtime rows for the PSK, absent, and each stub received only redacted text.
- [ ] **Step 2:** Run `uv run pytest tests/orchestration/test_persistence.py -v`. Expected: FAIL.
- [ ] **Step 3:** Implement `recorder.py` and `workflow.py` per the step order.
- [ ] **Step 4:** Re-run. Expected: PASS.
- [ ] **Step 5:** Commit: `feat(orchestration): workflow core with state store persistence`.

### Task 4: Routing and guard flow functional tests

**Files:**
- Test: `tests/orchestration/test_routing.py` (extend), `tests/orchestration/test_guard_flow.py`

**Interfaces:** consumes Task 3 `Workflow`, stubs from `conftest.py`. Produces nothing.

- [ ] **Step 1:** Add tests, each a multi-turn run on a real store:
  - SC-02: turn 1 vague, Triage stub returns a scoping question -> path `(INGESTION_GUARD, TRIAGE, RESOLUTION, ACTION_EVALUATION, IDLE)`, Diagnostics and Knowledge stubs not called; turn 2 answer -> Triage stub receives history containing the question and the answer; path includes `DIAGNOSTICS`, `KNOWLEDGE_RETRIEVAL`.
  - `KB_INQUIRY` skips Diagnostics; `ADVERSARIAL` skips both.
  - SC-05: opener blocked -> refusal text, agents never called, `guard_history` has the verdict, stage `IDLE`; follow-up turn answered normally and Triage stub sees the guard note via deps.
  - SC-07 style false Premium claim: `guard_history.false_claims` populated after Triage, persisted.
  - Action gate: stub Resolution proposing `CREDIT` for the caller -> `pending_actions` has it, one `approvals` row `PENDING`, reply unblocked; proposing an action for another account -> `DENY`, reason in reply, no approval row; unrecognised caller -> actions dropped.
- [ ] **Step 2:** Run `uv run pytest tests/orchestration -v`. Expected: PASS (fix workflow where a test exposes a real gap).
- [ ] **Step 3:** Commit: `test(orchestration): routing and guard flow`.

### Task 5: Cleanup, lint, type check (final)

- [ ] **Step 1:** Read every new file end to end; delete unused imports, constants, fields (every `AgentPorts` field, `TurnResult` field and `canned` constant must be used by code or a test; `TurnResult.degradations` arrives in Plan 2).
- [ ] **Step 2:** Run `uv run ruff check orchestration tests/orchestration`, `uv run ruff format --check`, `uv run pyright orchestration`. Expected: clean.
- [ ] **Step 3:** Grep: no `datetime.now`, no `braintrust`, no inline imports, no `Literal` for enum-like fields in `orchestration/`.
- [ ] **Step 4:** Run `uv run pytest tests/orchestration tests/guardrails -q`. Expected: PASS.
- [ ] **Step 5:** Commit: `chore(orchestration): cleanup`.

## Unresolved Questions

1. Add Knowledge -> Diagnostics back-edge (needs `needs_more_telemetry` on issue 7 contracts)? Default: no.
2. Exact `run_<role>` signature / who builds `SupportDeps` (placeholder identity for Triage pre-step)? Assumed `(Input, SupportDeps)`.
3. `message_id` supplied by caller OK, or workflow generates?
4. Drop `OUTPUT_GUARD` stage from workflow (issue 7 validators cover it) OK?
5. Sync workflow + `to_thread` in API layer OK?
