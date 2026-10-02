# State Snapshot Version Hook and Recovery Tests Implementation Plan (Plan 2 of 2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 23's `OrchestratorState` snapshot (stored by 21 in `conversations.state` as `StateSnapshot`) migrates across versions, is refused when newer than the code, and rebuilds to safe defaults when empty or corrupt, with kill/restart continuity proven.

**Architecture:** No schema, store or recorder change: 21 owns the column, `StateSnapshot`, `save_state` and `rehydrate`; 23 owns `OrchestratorState`, its single end-of-turn save and `TurnRecorder.save_state`. 2.4 only adds the version constant, migration chain and `StateVersionError` in `orchestration/state.py` and refines `OrchestratorState.from_snapshot`.

**Tech Stack:** Python 3.12, Pydantic v2, pytest. No new dependency.

**Spec:** [design.md](design.md) sections 2.8-2.11, 3, 4. **Depends on:** plan 01 of this issue (lock, `worker_factory` fixture), plans 21 and 23 merged.

## Global Constraints

Same as plan 01 of this issue. Pure functions only in `MIGRATIONS`; `OrchestratorState` stays frozen. Do not add `load_state`, a state model, a migration SQL file or a second dedupe check (all exist in 21/23).

## Review Focus

1. Snapshot version newer than code: `StateVersionError`, stored blob untouched. -> Tasks 1, 2.
2. Corrupt/invalid `data`: rebuilt, turn proceeds. -> Task 1.
3. Pre-23 conversation (default `{"version": 1}`, empty `data`): first turn works, writes current version. -> Task 2.
4. Crash between `complete_turn` and `save_state`: retry returns the stored reply. -> Task 2.

---

### Task 1: Version hook in `orchestration/state.py`

**Files:**
- Modify: `orchestration/state.py` (23), `orchestration/__init__.py` (export `StateVersionError` only if the API layer needs it; otherwise skip)
- Test: `tests/orchestration/test_state.py`

**Interfaces:**
- Consumes: 21 `StateSnapshot(version: int, data: dict[str, Any])`; existing 23 `OrchestratorState.empty()`, `from_snapshot`, `to_snapshot`.
- Produces: `STATE_VERSION: int` (1; `to_snapshot` uses it instead of the literal); `MIGRATIONS: dict[int, Callable[[dict[str, Any]], dict[str, Any]]]` (empty); `StateVersionError(Exception)`; `OrchestratorState.from_snapshot(snapshot: StateSnapshot) -> OrchestratorState` rules: empty `data` -> `empty()`; older version -> apply `MIGRATIONS[v]` for v from stored version to `STATE_VERSION - 1`, then validate; newer version -> `StateVersionError`; validation failure -> `empty()` with a stdlib `logging` warning (never the blob content).

- [ ] **Step 1: Write one parametrized failing test:** empty data -> empty; current version round-trips via `to_snapshot`; older version with `monkeypatch` setting `STATE_VERSION` to 2 and one `MIGRATIONS` step renaming a field -> migrated value; newer version -> `StateVersionError`; invalid data (wrong type) -> empty.
- [ ] **Step 2:** Run `uv run pytest tests/orchestration/test_state.py -v`. Expected: FAIL.
- [ ] **Step 3:** Implement. Update the existing 23 `test_state_snapshot.py` expectation "unknown version -> empty" to "newer version -> `StateVersionError`".
- [ ] **Step 4:** Re-run, expect PASS; `uv run pytest tests/orchestration -q` green; ruff/pyright on `orchestration`.
- [ ] **Step 5:** Commit `feat(orchestration): versioned OrchestratorState migration and refusal`.

---

### Task 2: Propagate `StateVersionError`, kill/restart functional tests

**Files:**
- Modify: `orchestration/workflow.py` (state load stays after `_ingest` as in 23, but outside the single agent-exception boundary so `StateVersionError` propagates)
- Test: `tests/orchestration/test_state_recovery.py` (new)

**Interfaces:**
- Consumes: Task 1; plan 01 lock and `worker_factory`; 23 stubs (scoping-question Triage stub, telemetry-down Diagnostics stub); 21 `rehydrate().conversation.state`.
- Produces: nothing new for later plans.

- [ ] **Step 1: Write failing tests** (real Postgres, stub agents): (a) *kill/restart:* turn 1 returns a scoping question with a telemetry-down notice; read the stored snapshot via `rehydrate`; terminate the worker's backend, drop every reference, build a new worker; turn 2: loaded `OrchestratorState` equals the pre-kill one, clarification becomes 2, notice not repeated, `oncall_paged` unchanged. (b) *pre-23 conversation:* a conversation whose `state` is the 21 default; the next turn runs and the snapshot is written with `STATE_VERSION`. (c) *newer version:* `save_state` a blob with version 99; `run_turn` raises `StateVersionError`, blob unchanged, no agent stub called. (d) *crash window:* patch the recorder so `save_state` raises after `complete_turn`; retry the same `message_id` returns the stored reply with stubs not called, and the next new turn works. (e) plan 01 concurrency tests still pass.
- [ ] **Step 2:** Run `uv run pytest tests/orchestration/test_state_recovery.py -v`. Expected: FAIL (c at least).
- [ ] **Step 3:** Move the load outside the exception boundary if it is inside; nothing else.
- [ ] **Step 4:** Run `uv run pytest tests/orchestration tests/storage tests/guardrails -q`. Expected: PASS; ruff/pyright.
- [ ] **Step 5:** Commit `test(orchestration): state recovery across restarts and versions`.

---

### Task 3: Docs and cleanup (final)

- [ ] **Step 1:** In 23 docs, any wording that places rebuild/locking in 23 stays as "issue #34 / 2.4"; add the ADR (or extend plan 01's) for the snapshot version hook and safe-direction rebuild, incl. the `oncall_paged` note from design 2.10.
- [ ] **Step 2:** Mark this issue's `design.md` "Implemented (see plan-01, plan-02)".
- [ ] **Step 3:** Read the `orchestration/state.py` and `workflow.py` diffs end to end; remove unused imports/fields; every `MIGRATIONS`/`STATE_VERSION` use is exercised by a test; confirm nothing duplicates 21/23.
- [ ] **Step 4:** Grep `storage orchestration` for `datetime.now`, inline imports, `Literal` for enum-like fields. Run `uvx ruff check`, `uvx ruff format --check`, `uvx pyright storage orchestration`, `uv run pytest tests/storage tests/orchestration tests/db -q`. Expected: clean, PASS.
- [ ] **Step 5:** Commit `chore: turn locking and state snapshot cleanup`.

## Unresolved Questions
None.
