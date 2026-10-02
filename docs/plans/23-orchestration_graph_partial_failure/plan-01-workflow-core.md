# Orchestration Workflow Core Implementation Plan (Plan 1 of 2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A sync, LLM-free `Workflow.run_turn` that runs one customer turn through ingestion guard, Triage, optional Diagnostics, Knowledge, Resolution and the action gate, persisting every step through issue 6's `StateStore`.

**Architecture:** One plain-Python pipeline (no graph framework). Routing is a pure function over `TriageResult`. Agents are injected callables (the issue 7 `run_<role>` functions, or scripted stubs in tests). All state lives in Postgres via `StateStore`; the workflow keeps no state between turns.

**Tech Stack:** Python 3.12, pydantic (frozen models), pytest, psycopg (via `StateStore`). PydanticAI is used only inside the agents (issue 7); the workflow imports `AgentRun` and the contracts, not `Agent`.

**Spec:** `docs/plans/23-orchestration_graph_partial_failure/design.md` (read with `docs/plans/21-agent_state_machine/design.md` and `docs/plans/22-specialized_agent_contracts/design.md`). Where this plan and design.md disagree, this plan wins (see Design Decisions).

**Depends on:** issues 6 and 7 merged, order 21 -> 22 -> 23 (`storage/*`, `agents/*` contracts and `run_<role>` do not exist in the repo yet). If they land first with different signatures, Task 1 is the only place to adapt. Out of scope: cross-worker turn locking and `ConversationState` rebuild (GitHub #34, 2.4).

## Design Decisions (overrides of design.md, with reasons)

1. **Hand-rolled pipeline, not `pydantic_graph`.** The flow has one real branch (after Triage), no loops (see 5), and persistence is already decided by issue 6 as rows plus `set_stage` per node. `pydantic_graph` would add node classes, a second persistence mechanism (its state persistence vs `StateStore` rows) and an async-only run model, for a graph of 6 nodes. Revisit only if resumable mid-turn execution or graph visualisation becomes a requirement.
2. **Sync, not async.** Issue 7 makes `run_<role>(Input, SupportDeps)` sync (`run_sync`); `StateStore` is sync. design.md's async ports would force `asyncio.to_thread` around every call for nothing. Issue 9/API layer adapts `run_turn` with `asyncio.to_thread` once. `SupportDeps` is owned by issue 22. The orchestrator builds the Triage identity deterministically (`authenticate_caller`, plain function, no LLM) and passes it in `TriageInput`; no placeholder identity.
3. **No `ConversationState` model.** Issue 6's `ConversationSnapshot` (from `StateStore.rehydrate`) is the state. History for agents is the snapshot's messages mapped to issue 7's `ConversationTurn`. Prior Triage decision is not fed back explicitly: issue 7's `TriageInput` has only `history`, and the scoping question plus the customer's answer are in that history. This deletes `awaiting_scoping_answer`, `with_*` methods and a duplicate persistence story.
4. **Workflow owns persistence, through `StateStore` only.** design.md says the caller persists; but issue 6 needs `set_stage` at every node and traces per agent call, which only the workflow can do. A small `TurnRecorder` keeps that out of the routing code (Single Responsibility). Issue 9/API layer only supplies a connection and a `message_id`.
5. **Diagnostics <-> Knowledge back-edge restored, `MAX_DIAG_KB_ROUNDS = 2`.** Issue 22 adds `KnowledgeBundle.needs_more_telemetry` and `DiagnosticEvidence.unavailable_tools`. `_evidence` loops Diagnostics -> Knowledge while `needs_more_telemetry` is set, bounded by the constant, then proceeds to Resolution with what it has. Loop guard in one place, no recursion. Clarification is capped at 3 turns (counter in the 21 `StateStore` snapshot, see Task 4), then the workflow escalates instead of asking again.
6. **No `OUTPUT_GUARD` re-prompt in the workflow.** Issue 7's `run_resolution` already validates citations and the outgoing message with PydanticAI output validators, retries once, then returns the canned human-handoff plan. Re-doing it here is duplicate logic. The workflow reuses `ConversationStage.OUTPUT_GUARD` only if Plan 2 needs it (it does not).
7. **Reuse `ConversationStage` (issue 6) as the state enum.** No new `WorkflowState`. Visited stages are returned in `TurnResult.path` for tests.
8. **No `GroundingContext.from_turn`.** Issue 7's `ResolutionInput.grounding_context()` already does it.
9. **No Braintrust / Braintrust tracing anywhere.** design.md and architecture mention Braintrust export; this plan overrides it. Observability is the issue 6 `traces` / `tool_calls` tables (`StateStore.record_trace`, `replay_trace`) plus PydanticAI's own `result.usage()` and message history, which agents already convert into `AgentTrace`. Do not add or import `braintrust` in `orchestration/`.
10. **Retrying a turn is idempotent.** `message_id` is supplied by the caller (API/UI layer) and is the idempotency key. `append_customer_message(conversation_id, message_id, ...)` (21) returns the existing row for a seen id; if that turn already has an AGENT/SYSTEM reply, `run_turn` rebuilds the `TurnResult` from the stored reply plus the conversation's pending approvals and does not re-run agents. A seen id without a reply (crash mid-turn) resumes the turn. Approvals dedupe on `(conversation_id, idempotency_key)` with key `f"{message_id}:{action_index}"`.
11. **Workflow-owned state lives in one versioned snapshot.** Clarification-turn counter, per-source outage-notice flags and the on-call-paged flag are stored in the `conversations.state` `StateSnapshot` (owned by 21 `StateStore`), as one frozen model defined in `orchestration/state.py` (Task 4) serialized into `StateSnapshot.data`. Not derived from traces, not in memory. Approval rows (keyed by `conversation_id` + `message_id`-derived key) and trace `seq` (per conversation) stay 21's.

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
4. Same `message_id` submitted twice (client retry): one customer message row, no duplicate approval, no double-counted clarification turn.
5. `ProposedAction` for a different account than the caller (SC-05): `DENY`, reason shown, never in `pending_actions`.

## File Structure

| File | Responsibility |
|---|---|
| `orchestration/models.py` | `AgentPorts` (frozen dataclass of the four callables), `TurnResult`. |
| `orchestration/routing.py` | Pure `next_stage_after_triage(result: TriageResult) -> ConversationStage`; pure `compose_reply(...)`. |
| `orchestration/canned.py` | Fixed text constants: injection refusal, agent-failure pause message. |
| `orchestration/recorder.py` | `TurnRecorder`: thin wrapper over `StateStore` for stage, message, trace, guard-history, approval writes of one turn. |
| `orchestration/state.py` | `OrchestratorState`: frozen model of the workflow-owned snapshot payload (clarification counter, notice flags, paged flag, schema version) with pure transition methods (Task 4). |
| `orchestration/workflow.py` | `Workflow.run_turn` plus one private method per step (`_ingest`, `_triage`, `_evidence`, `_resolve`, `_gate`). |
| `orchestration/__init__.py` | Re-exports. |
| `tests/orchestration/conftest.py` | Fixtures: `StateStore` on the seeded Postgres (reuse `db_conn`-style fixture from `tests/services/test_support_intake_functional.py` and the `_identity` helper pattern in `tests/guardrails/conftest.py`), scripted agent stubs recording calls. |
| `tests/orchestration/test_routing.py`, `test_guard_flow.py`, `test_persistence.py`, `test_state_snapshot.py` | Functional tests below. |

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
- Consumes: Task 1 and 2 outputs; 21 `StateStore.rehydrate`, `set_stage`, `append_customer_message`, `complete_turn`, `record_trace(trace, tool_calls)`, `save_guard_history`, `update_identity`, `create_approval(conversation_id, trace_id, action_type, payload, idempotency_key, at)`; `TraceRecord.from_agent_trace` and `ToolCallRecord.from_tool_call` (21 owns the `AgentTrace` fields; the workflow only forwards `run.trace`); `guardrails.redactor.redact`; `guardrails.injection.detect`; `guardrails.validator.check_claims`, `check_action`; `SessionGuardHistory.with_redaction` / `with_injection` / `with_entitlement`.
- Produces:
  - `TurnRecorder(store: StateStore, clock: SimulationClock, conversation_id: UUID)` with methods `enter(stage)` (`set_stage`), `record_customer_message(message_id, text) -> StoredMessage` (`append_customer_message`), `complete_turn(turn, sender, text, message_id)` (`complete_turn`, which also sets `IDLE`), `record_run(role, run, turn, message_id, parent_trace_id | None) -> UUID` (builds `TraceRecord.from_agent_trace` plus `ToolCallRecord.from_tool_call` per tool call, then one `record_trace`; returns trace id), `save_guard_history(history)`, `save_identity(identity)`, `create_approval(trace_id, action: ProposedAction, idempotency_key)`. Each is a thin store call; no logic.
  - `Workflow(ports: AgentPorts, store: StateStore, clock: SimulationClock, base_deps: SupportDeps)`.
  - `Workflow.run_turn(conversation_id: UUID, message: str, message_id: UUID) -> TurnResult`, sync (the API layer wraps it once in `asyncio.to_thread`; each `run_<role>` is already sync); `message_id` caller-supplied, already-answered id returns the stored result (decision 10).

Step order inside `run_turn` (each a private method, one concern):
1. `_ingest`: `redact` -> `history.with_redaction`; `detect` -> `with_injection`; persist redacted customer message (`append_customer_message`, sets stage `INGESTION_GUARD`) and history. If that `message_id` already has a reply: return the stored result. If blocked: `complete_turn` with `INJECTION_REFUSAL` as an AGENT message (sets `IDLE`), return with path `(INGESTION_GUARD, IDLE)`; agents untouched.
2. `_triage`: resolve identity via `CustomerService.authenticate_caller` (plain function from `base_deps.customers`, never an LLM tool), build `TriageInput(message, identity, history)` with that identity; history is the stored messages mapped to `ConversationTurn` (CUSTOMER/AGENT/REVIEWER map 1:1; SYSTEM rows such as the pause message are skipped); call `ports.triage` via the sync port, record the run, persist identity, then `check_claims(redacted, result.identity)` -> `with_entitlement` -> persist history. Rebuild deps with `dataclasses.replace` (identity and guard history) for later steps.
3. Route with `next_stage_after_triage`; `_evidence` runs Diagnostics (if routed) then Knowledge (always after Diagnostics, or directly for KB intents), looping back to Diagnostics while `needs_more_telemetry` up to `MAX_DIAG_KB_ROUNDS = 2`, skipping both for the Resolution-direct routes. Each run recorded with the previous trace id as parent.
4. `_resolve`: build `ResolutionInput` (diagnostics / knowledge `None` when skipped), call `ports.resolution`, record.
5. `_gate`: map each `SupportAction` through `to_proposed_action(identity.account.account_id)`; no account -> drop all actions. `None` result (ticket kinds) -> `executable_actions`; else `check_action(action, identity, priority=triage.decision.priority, sev1_corroborated=evidence.sev1_corroborated, already_paged=state.oncall_paged)` (the Sev-1 `PAGE_ON_CALL` hard gate lives in 22's `check_action`; `sev1_corroborated` is the code-derived flag on 22's `DiagnosticEvidence`, `False` when Diagnostics was skipped; the workflow only supplies the three arguments): `ALLOW` -> `executable_actions` (an allowed `PAGE_ON_CALL` sets `oncall_paged` in the snapshot, Task 4), `REQUIRE_APPROVAL` -> `pending_actions` + `create_approval` (idempotency key `f"{message_id}:{action_index}"`), `DENY` -> reason text into `denial_reasons`.
6. `complete_turn` the composed reply as an AGENT message (sets `IDLE` atomically with the reply), return `TurnResult`.
Each step calls `enter(<stage>)` first so a crash resumes at the last committed node (issue 6 semantics).

- [ ] **Step 1:** Write `conftest.py` (store fixture mirroring the existing `db_conn` fixture; stub agent factory returning typed outputs and recording calls) and `test_persistence.py` with: (a) SC-01 style turn with scripted Triage (`TELEMETRY_DIAGNOSIS`), Diagnostics, Knowledge, Resolution: assert `path` equals `(INGESTION_GUARD, TRIAGE, DIAGNOSTICS, KNOWLEDGE_RETRIEVAL, RESOLUTION, ACTION_EVALUATION, IDLE)`, and that after dropping the `Workflow` and opening a new connection `rehydrate` shows the customer and agent messages and stage `IDLE`; (b) retry with the same `message_id`: one customer message row; (c) SC-08 PSK message: scan every text and jsonb column of the runtime rows for the PSK, absent, and each stub received only redacted text.
- [ ] **Step 2:** Run `uv run pytest tests/orchestration/test_persistence.py -v`. Expected: FAIL.
- [ ] **Step 3:** Implement `recorder.py` and `workflow.py` per the step order.
- [ ] **Step 4:** Re-run. Expected: PASS.
- [ ] **Step 5:** Commit: `feat(orchestration): workflow core with state store persistence`.

### Task 4: Workflow state snapshot (clarification counter, outage-notice flags, paged flag)

**Files:**
- Create: `orchestration/state.py`
- Modify: `orchestration/workflow.py`, `orchestration/recorder.py`
- Test: `tests/orchestration/test_state_snapshot.py`

**Interfaces:**
- Consumes: 21 `conversations.state jsonb` (default `{"version": 1}`), read via `ConversationSnapshot.conversation.state` (a frozen `StateSnapshot(version: int = 1, data: dict[str, Any] = {})` from `rehydrate`) and written whole by `StateStore.save_state(conversation_id, state: StateSnapshot, at) -> None`; `DegradedSource` (Plan 2 Task 1 adds it; until then the notice flags are an empty tuple and unused).
- Produces:
  - `OrchestratorState` (frozen, tuples not sets; lives in `StateSnapshot.data`, `version` is `StateSnapshot.version`, not a field here): `clarification_turns: int` (consecutive turns that ended in a scoping question), `notice_shown: tuple[DegradedSource, ...]` (sources whose outage notice was already shown), `oncall_paged: bool` (a `PAGE_ON_CALL` was ALLOWed in this conversation, feeds `check_action(already_paged=...)`). Classmethod `empty()`; classmethod `from_snapshot(snapshot: StateSnapshot) -> OrchestratorState` (empty `data` or unknown `version` -> `empty()`, fail safe, never raises); `to_snapshot() -> StateSnapshot` (`version=1`, `data` = the three fields JSON-dumped).
  - Pure transitions, each returning a new instance: `after_scoping_question()` (+1), `after_scoping_resolved()` (reset to 0), `clarification_exhausted() -> bool` (True at 3: the next scoping question is replaced by escalation, `escalation_offered=True`), `with_notice_shown(source)`, `with_source_healthy(source)` (clears that flag), `with_oncall_paged()`.
  - `Workflow` loads the state once at the start of `run_turn` (after `_ingest`), keeps it in a local, and saves it exactly once at the end via `save_state` next to the reply `complete_turn` (two calls, same turn end), so a crash-resumed retry recomputes from the same stored base and never double-counts. A turn that hits the agent-failure boundary (Plan 2 Task 3) saves nothing.
  - Counter rule: scoping question returned and not exhausted -> `after_scoping_question`; scoping question returned and exhausted -> escalate instead of asking; Triage returns no scoping question -> `after_scoping_resolved`. The blocked-injection turn leaves the state untouched.
- Out of scope: cross-worker locking and rebuild of state from the snapshot (GitHub #34, 2.4). Within one conversation 21's per-conversation row lock already serializes the write; the workflow adds no lock.

- [ ] **Step 1:** Write `tests/orchestration/test_state_snapshot.py`, multi-turn on the real store (functional, scripted agents):
  - Clarification cap: Triage stub asks a scoping question 3 turns in a row -> 3 questions asked, snapshot counter 3 after turn 3; turn 4 (still vague) -> escalation reply, `escalation_offered`, no 4th question; separate conversation where the answer arrives on turn 2 -> counter back to 0.
  - Restart: after turn 2 drop the `Workflow`, store and connection, open a new connection and `Workflow`; turn 3 continues from counter 2 (cap behaviour identical to the no-restart run).
  - Retry: same `message_id` resubmitted -> counter unchanged (not double-counted).
  - Blocked injection turn between two vague turns -> counter unchanged by the blocked turn.
  - Paged flag: P1 Triage plus Resolution proposing `PAGE_ON_CALL` -> ALLOWed, `oncall_paged` stored; the same proposal on the next turn -> `DENY` (no re-page); non-P1 -> `DENY` and flag stays false.
  - Unknown `version` payload in the column -> treated as empty, turn still runs.
  - Notice flags (needs Plan 2): covered in Plan 2 Task 2, which reuses `OrchestratorState`.
- [ ] **Step 2:** Run `uv run pytest tests/orchestration/test_state_snapshot.py -v`. Expected: FAIL.
- [ ] **Step 3:** Implement `state.py`; wire load, transitions and the single save into `workflow.py`; add a thin `save_state` pass-through to `recorder.py` (no logic).
- [ ] **Step 4:** Re-run. Expected: PASS.
- [ ] **Step 5:** Commit: `feat(orchestration): workflow state snapshot`.

### Task 5: Routing and guard flow functional tests

**Files:**
- Test: `tests/orchestration/test_routing.py` (extend), `tests/orchestration/test_guard_flow.py`

**Interfaces:** consumes Task 3 and 4 `Workflow`, stubs from `conftest.py`. Produces nothing. CI uses stub agents (real `run_resolution` with `FunctionModel`/`TestModel` where validators matter); plus one opt-in live-LLM smoke test, skipped without an API key.

- [ ] **Step 1:** Add tests, each a multi-turn run on a real store:
  - SC-02: turn 1 vague, Triage stub returns a scoping question -> path `(INGESTION_GUARD, TRIAGE, RESOLUTION, ACTION_EVALUATION, IDLE)`, Diagnostics and Knowledge stubs not called; turn 2 answer -> Triage stub receives history containing the question and the answer; path includes `DIAGNOSTICS`, `KNOWLEDGE_RETRIEVAL`.
  - `KB_INQUIRY` skips Diagnostics; `ADVERSARIAL` skips both.
  - Back-edge: Knowledge stub sets `needs_more_telemetry` once -> path has `DIAGNOSTICS, KNOWLEDGE_RETRIEVAL` twice; set forever -> stops at 2 rounds.
  - (Clarification cap and Sev-1 paged-flag tests live in Task 4.)
  - Duplicate `message_id`: second submit returns stored result, stubs not called again.
  - SC-05: opener blocked -> refusal text, agents never called, `guard_history` has the verdict, stage `IDLE`; follow-up turn answered normally and Triage stub sees the guard note via deps.
  - SC-07 style false Premium claim: `guard_history.false_claims` populated after Triage, persisted.
  - Action gate: stub Resolution proposing `CREDIT` for the caller -> `pending_actions` has it, one `approvals` row `PENDING`, reply unblocked; proposing an action for another account -> `DENY`, reason in reply, no approval row; unrecognised caller -> actions dropped.
- [ ] **Step 2:** Run `uv run pytest tests/orchestration -v`. Expected: PASS (fix workflow where a test exposes a real gap).
- [ ] **Step 3:** Commit: `test(orchestration): routing and guard flow`.

### Task 6: Cleanup, lint, type check (final)

- [ ] **Step 1:** Read every new file end to end; delete unused imports, constants, fields (every `AgentPorts` field, `TurnResult` field, `OrchestratorState` field and `canned` constant must be used by code or a test; `TurnResult.degradations` arrives in Plan 2).
- [ ] **Step 2:** Run `uv run ruff check orchestration tests/orchestration`, `uv run ruff format --check`, `uv run pyright orchestration`. Expected: clean.
- [ ] **Step 3:** Grep: no `datetime.now`, no `braintrust`, no inline imports, no `Literal` for enum-like fields in `orchestration/`.
- [ ] **Step 4:** Run `uv run pytest tests/orchestration tests/guardrails -q`. Expected: PASS.
- [ ] **Step 5:** Commit: `chore(orchestration): cleanup`.

## Unresolved Questions
None.
