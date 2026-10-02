# 31 / Plan 02 — Workflow Integration, Ticket Binding, Prompt — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `Workflow` dispatch gate-cleared actions, bind credit/MFA approvals to the conversation's ticket, mark that ticket `pending_approval`, and show deterministic confirmations; update the Resolution prompt and contracts accordingly.

**Architecture:** `Workflow._answer` keeps gating, then dispatches ticket and page actions, records `active_ticket_id` in `OrchestratorState`, stamps `ticket_id` into approval payloads in code, creates approvals, calls `mark_pending`, and finishes with dispatch before `save_state` before `complete_turn`. No new component beyond plan 01's dispatcher.

**Tech Stack:** as plan 01. NO Braintrust; agent runs stay PydanticAI via the existing `run_<role>` ports; tracing stays the existing `TurnRecorder` / `traces` tables (this plan adds none).

**Spec:** [design.md](design.md) §2.2 (5-7), §5.4a, §6, §7 (items 2, 4). Depends on plan 01 merged.

## Global Constraints

- Same as plan 01, plus: `orchestration/workflow.py` is already ~260 lines; new logic goes into small pure helpers in a new `orchestration/actions_step.py` (stamping, ticket-id selection, confirmation collection), not into `_answer` bodies. `_answer` may only gain calls.
- Merge order: 31 after 21-24 (already on `p-2-agent`); 32 builds on this plan's `mark_pending` and `active_ticket_id`.
- Scripted stub agents (`tests/orchestration/conftest.py` `Scripted`), zero LLM.
- Implementation branch continues `p-3-1_action-dispatcher`; never merge, never push.

## Review Focus

1. Model writes a wrong or hallucinated `ticket_id` in a credit payload -> stored approval carries the state ticket id. -> Task 2.
2. `CREATE_TICKET` and `CREDIT` in one plan -> approval bound to the new ticket, ordering correct. -> Task 2.
3. Crash after dispatch, before reply -> retry yields one ticket, one page, one reply. -> Task 3.
4. Corrupt/empty state snapshot -> second page still blocked by the DB key; no repeated "paged" line. -> Task 3.
5. Failed action never reads as success; `escalation_offered` set; turn still completes. -> Task 2.

---

### Task 1: State, contract and prompt changes

**Files:**
- Modify: `orchestration/state.py` (`STATE_VERSION` 2, `MIGRATIONS[1]` identity step, field `active_ticket_id: str | None = None`, method `with_active_ticket(ticket_id)` returning a copy), `agents/models.py` (`ResolutionInput.known_ticket_id: str | None = None`), `prompts/resolution.md` (design §6 prompt change a-d; also state that credit/MFA `ticket_id` is overwritten by the system so the model must not invent one), `tests/orchestration/test_state.py` and `tests/orchestration/test_state_snapshot.py` (version constants, new field round trip, v1 snapshot loads with `None`, v3 raises `StateVersionError`)
- Test: `tests/agents/test_prompts.py` (drift guard: prompt text names each payload key of every payload model and the words `known_ticket_id`; existing agent tests untouched)

**Interfaces:**
- Produces: `OrchestratorState.active_ticket_id`, `with_active_ticket`, `ResolutionInput.known_ticket_id`.
- Consumes: plan 01 payload models (the drift test iterates their field names; no hardcoded key list).

- [ ] **Step 1: Write failing tests** (state round trip and migration; prompt drift).
- [ ] **Step 2: Run**, expect failure.
- [ ] **Step 3: Implement** state field, version bump, identity migration, contract field, prompt edits.
- [ ] **Step 4: Run** `tests/orchestration/test_state*.py`, `tests/agents`, expect PASS.
- [ ] **Step 5: Cleanup**: ruff, pyright; no stray version literal (tests use `STATE_VERSION`).
- [ ] **Step 6: Commit.**

---

### Task 2: Workflow dispatch, stamping, pending marker, replies

**Files:**
- Create: `orchestration/actions_step.py` (pure helpers: split the gated executable actions into immediate kinds vs none; `stamp_ticket_id(pending, ticket_id) -> tuple[...]` returning new `ProposedAction`s with the state ticket id, or marking them unbindable when `ticket_id` is `None`; `confirmations(results) -> tuple[str, ...]`; `failure_line(results) -> tuple[str, ...]`; `next_active_ticket(results, current) -> str | None`)
- Modify: `orchestration/workflow.py` (new `dispatcher: ActionDispatcher` field; `_answer` order per design §5.4a: gate, dispatch executable, update `active_ticket_id`, stamp pending, create approvals via recorder, `mark_pending` each, derive notices; `_finish` order dispatch results -> `save_state` -> `complete_turn`; `oncall_paged` set only from a `DONE` page result; failed results set `escalation_offered`; pass `known_ticket_id` into `ResolutionInput` in `_resolve`), `orchestration/models.py` (`TurnResult.action_results` replaces `executable_actions`), `orchestration/routing.py` (`compose_reply` gains `confirmations` placed after the model message, before denial reasons), `orchestration/recorder.py` (`create_approval` returns the created `Approval` so `mark_pending` can use it; if it already returns nothing, change it to return what the store returned), `orchestration/canned.py` (fixed line for "a ticket is needed first"), `tests/orchestration/conftest.py` (harness builds `ActionDispatcher`; cleanup also deletes tickets created per test)
- Test: `tests/orchestration/test_action_flow.py`

**Interfaces:**
- Consumes: plan 01 `ActionDispatcher.dispatch_turn` / `mark_pending`, `DispatchContext` (built from identity, triage priority, `diagnostics.sev1_corroborated`, state `oncall_paged`, conversation and message ids), Task 1 state/contract.
- Produces: `TurnResult.action_results: tuple[ActionResult, ...]`; replies containing confirmation lines.

- [ ] **Step 1: Write failing functional tests** in `test_action_flow.py` using `Scripted.actions`: ticket creation reply holds the exact confirmation line after the agent text and `active_ticket_id` is saved; credit with a model-written wrong `ticket_id` -> approval payload carries the state id, ticket `pending_approval`, no `simulated_actions` row for the credit; `CREATE_TICKET` + `CREDIT` same plan -> approval bound to the new ticket; credit with no ticket in the conversation -> no approval row, fixed line in reply; handler failure (monkeypatched ticket service) -> `FAILED`, failure line, `escalation_offered`, turn completes, state saved; duplicate `message_id` -> no extra ticket, same reply; `active_ticket_id` survives a restart (new connection and workflow); `TurnResult.pending_actions` still lists the credit.
- [ ] **Step 2: Run them**, expect failure.
- [ ] **Step 3: Implement** helpers first (pure), then the workflow wiring, then models/routing/recorder/canned edits.
- [ ] **Step 4: Fix existing tests** that read `executable_actions` (grep tests and the UI-facing code); run all of `tests/orchestration`, expect PASS.
- [ ] **Step 5: Cleanup**: ruff, pyright; `_answer` not longer than before plus the new calls; no leftover `executable_actions` anywhere (grep); helpers all used.
- [ ] **Step 6: Commit.**

---

### Task 3: Sev-1 through the workflow, crash and concurrency

**Files:**
- Test: `tests/orchestration/test_sev1_flow.py`, `tests/orchestration/test_action_crash.py`
- Modify: only what the tests prove broken (expected: none)

**Interfaces:** consumes Task 2 workflow; uses `Scripted.sev1`, real `TelemetryService` evidence where the existing harness supports it (else the scripted `sev1_corroborated` flag, plus one test with real telemetry for two disconnected sites in one country, to prove the gate input is code-derived).

- [ ] **Step 1: Write the tests**: P1 + corroborated -> page row `DONE`, reply has the paged line; P2 or uncorroborated or single site -> DENY text in reply, no row; second page in same conversation denied by the gate; empty/corrupt state snapshot (wipe `conversations.state`) then a new turn proposing a page -> dispatcher `REFUSED`, one `DONE` row, no repeated paged line; crash after dispatch before reply (terminate the connection's backend as in `test_turn_serialization.py`) -> retry completes with one ticket and one page row, one reply; two workers, same `message_id` -> one effect (turn lock plus key); page failure leaves `oncall_paged` false and a later turn may page.
- [ ] **Step 2: Run**, expect PASS or fix the implementation where a test exposes a gap (record each fix in the commit message).
- [ ] **Step 3: Cleanup**: ruff, pyright; remove any test helper that duplicates `tests/orchestration/conftest.py`.
- [ ] **Step 4: Commit.**

---

### Task 4: Docs and final cleanup

**Files:**
- Modify: `docs/architecture/system-architecture-design.md` (dispatcher box, `actions/` layout, `simulated_actions` ER entry, Sev-1 wording aligned to POL-SEV1), `docs/overview/decisions.md` (next free ADR: dispatcher after gate, Postgres audit with unique keys, conversation-scoped page key, dispatch-before-state-save order, ticket binding from state, `pending_approval` set here / cleared by #10), `data/README.md` (runtime tickets created in Postgres), `docs/plans/31-action_dispatcher/design.md` (status "Implemented", note the CHECK-constraint deviation)

- [ ] **Step 1: Edit docs** as listed; keep each edit to the affected section.
- [ ] **Step 2: Whole-change audit**: read every new/modified file end to end; delete unused imports, models, helpers, handlers; grep the branch for `Braintrust`, `datetime.now`, inline imports, `Literal` for enum-like fields, `executable_actions`; confirm no file over ~250 lines and that nothing in `actions/` re-implements `check_action` or `OrchestratorState` logic.
- [ ] **Step 3: Full gates**: `uv run pytest tests -x`, `uvx ruff check .`, `uvx pyright`; all clean.
- [ ] **Step 4: Confirm sibling contracts** listed in plan 01 Global Constraints still match 32/41/42 designs (names, keys, `SimulatedAction` fields); fix the code, not the siblings, unless a sibling is wrong (report it).
- [ ] **Step 5: Commit.**
