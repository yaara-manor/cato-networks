# ConversationState Snapshot, Migration and Rebuild Implementation Plan (Plan 2 of 2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `ConversationState` persists as one versioned jsonb snapshot on `conversations`, survives kill/restart with identical contents, migrates across versions, and falls back to safe defaults when missing.

**Architecture:** Storage keeps an opaque `StoredState(version, data)`; `orchestration/state.py` owns the typed `ConversationState`, the version constant, the migration chain and the rebuild rule. Read first inside the turn lock, written last in each turn (after `complete_turn`).

**Tech Stack:** Python 3.12, psycopg 3, Pydantic v2, pytest. No new dependency.

**Spec:** [design.md](design.md) sections 2.9-2.13, 3, 4, 5, 6. **Depends on:** plan 01 of this issue (lock in place), plans 21, 23. If 21 already shipped `state`/`state_version` columns, Task 1's migration is a no-op and only its tests matter.

## Global Constraints

Same as plan 01 of this issue. Additionally: pure transitions return new instances (no mutation); `MIGRATIONS` entries are pure functions.

## Review Focus

1. Snapshot version newer than code: `StateVersionError`, stored blob untouched. -> Tasks 2, 3.
2. Corrupt/invalid blob: rebuilt, turn proceeds. -> Task 2.
3. `apply_schema` run twice with populated `state` column: no-op, data kept. -> Task 1.
4. Crash between `complete_turn` and `save_state`: retry returns the stored reply, counters stale only in the safe direction. -> Task 3.
5. Pre-2.4 conversation (null `state`): first turn works and writes version `STATE_VERSION`. -> Task 3.

---

### Task 1: Migration and `StateStore` state methods

**Files:**
- Create: `db/migrations/20261002_0900_conversation-state.sql`
- Modify: `storage/models.py` (add `StoredState`), `storage/state_store.py` (add `load_state`, `save_state`), `storage/__init__.py`
- Test: `tests/storage/test_conversation_state.py`

**Interfaces:**
- Consumes: `db.init.seed.apply_schema(connection) -> None`; 21 `to_jsonb` / `strip_nul` helpers.
- Produces: `StoredState` frozen model (`version: int`, `data: dict[str, Any]`); `StateStore.load_state(conversation_id: UUID) -> StoredState | None` (None when the conversation is unknown or `state` is null or version 0); `StateStore.save_state(conversation_id: UUID, state: StoredState, at: AwareDatetime) -> None` (single `UPDATE` of `state`, `state_version`, `updated_at`; raises `LookupError` when zero rows matched).

- [ ] **Step 1: Write failing tests:** (a) `apply_schema` twice is a no-op and both columns exist, a saved blob survives the second apply; (b) `save_state` then `load_state` from a new connection returns equal `StoredState`; (c) unknown id -> `None` from `load_state`, `LookupError` from `save_state`; (d) fresh conversation -> `None`.
- [ ] **Step 2:** Run `uv run pytest tests/storage/test_conversation_state.py -v`. Expected: FAIL.
- [ ] **Step 3:** Write the migration (lowercase SQL, `add column if not exists` for `state jsonb null` and `state_version int not null default 0`, leading comment on re-application and runtime-table dump exclusion, no `%`) and the store methods.
- [ ] **Step 4:** Re-run, expect PASS; `uv run pytest tests/db -q` still green; ruff/pyright.
- [ ] **Step 5:** Commit `feat(storage): conversation state snapshot column and store methods`.

---

### Task 2: `ConversationState`, migration chain, rebuild

**Files:**
- Create: `orchestration/state.py`
- Modify: `orchestration/__init__.py` (re-export)
- Test: `tests/orchestration/test_state.py`

**Interfaces:**
- Consumes: `StoredState`, 23 plan 02 `DegradedSource`.
- Produces: `STATE_VERSION: int` (value 1); `MIGRATIONS: dict[int, Callable[[dict[str, Any]], dict[str, Any]]]` (empty); `StateVersionError(Exception)`; frozen `ConversationState(clarification_turns: int = 0, notices_shown: tuple[DegradedSource, ...] = ())` with `empty() -> ConversationState`, `from_stored(stored: StoredState | None) -> ConversationState`, `to_stored() -> StoredState`, `with_clarification(turns: int) -> ConversationState`, `with_notices_shown(sources: tuple[DegradedSource, ...]) -> ConversationState`. `from_stored` rules: `None` or invalid blob -> `empty()` (the safe-default rebuild); older version -> apply `MIGRATIONS[v]` for v from the stored version up to `STATE_VERSION - 1` in order, then validate; newer version -> `StateVersionError`; log invalid-blob rebuilds with stdlib `logging` (never the blob content).

- [ ] **Step 1: Write one parametrized failing test** over: missing -> empty; current version round-trips through `to_stored`; older version with `monkeypatch` setting `STATE_VERSION` to 2 and `MIGRATIONS` to one step that renames a field -> migrated value; newer version -> `StateVersionError`; invalid blob (wrong type) -> empty.
- [ ] **Step 2:** Run `uv run pytest tests/orchestration/test_state.py -v`. Expected: FAIL.
- [ ] **Step 3:** Implement `state.py`.
- [ ] **Step 4:** Re-run, expect PASS; ruff/pyright on `orchestration`.
- [ ] **Step 5:** Commit `feat(orchestration): versioned ConversationState with migration and rebuild`.

---

### Task 3: Wire state into the workflow, kill/restart functional tests

**Files:**
- Modify: `orchestration/recorder.py` (add `save_state(state: ConversationState) -> None`, single store call), `orchestration/workflow.py` (inside `_run_locked`: load state first via `store.load_state` + `ConversationState.from_stored`, before any customer-message write; the clarification cap and the once-per-outage notice flags of 23 read/write this object; `recorder.save_state` is the last write of the turn, after the reply is committed, also on the blocked-injection and agent-failure paths)
- Test: `tests/orchestration/test_state_recovery.py` (new)

**Interfaces:**
- Consumes: Task 1 and 2 outputs; plan 01 lock and `worker_factory` fixture; 23 stubs (scoping-question Triage stub, telemetry-down Diagnostics stub).
- Produces: nothing new for later plans.

- [ ] **Step 1: Write failing tests** (real Postgres, stub agents): (a) *kill/restart:* turn 1 returns a scoping question with a telemetry-down notice; record `ConversationState` via `load_state`; terminate the worker's backend, drop every reference, build a new worker; turn 2: loaded state equals the pre-kill one, clarification becomes 2, the notice is not repeated, history in the Triage stub equals the persisted messages. (b) *missing snapshot:* set `state` to null via raw SQL on a conversation with two completed turns; the next turn runs, no exception, the snapshot is written with version `STATE_VERSION`; counter restarts at the safe default 0 and the notice may repeat once. (c) *newer version:* write a blob with version 99 through `save_state`; `run_turn` raises `StateVersionError`, no customer message row is written for that `message_id`, blob unchanged. (d) *crash window:* patch the recorder so `save_state` raises after `complete_turn`; retry the same `message_id` returns the stored reply, stubs not called, and the next new turn works. (e) the two concurrency tests of plan 01 still pass.
- [ ] **Step 2:** Run `uv run pytest tests/orchestration/test_state_recovery.py -v`. Expected: FAIL.
- [ ] **Step 3:** Wire state load/save into `_run_locked` and `TurnRecorder`; replace the 23 clarification/notice flag reads with the state object.
- [ ] **Step 4:** Run `uv run pytest tests/orchestration tests/storage tests/guardrails -q`. Expected: PASS; ruff/pyright on touched paths.
- [ ] **Step 5:** Commit `feat(orchestration): persist and rebuild ConversationState across restarts`.

---

### Task 4: Docs and cleanup (final)

- [ ] **Step 1:** Update 23 `design.md` and plan 02 wording "flag in the 21 `StateStore` snapshot" to point to `ConversationState` (`orchestration/state.py`). Add the ADR for the state snapshot split and safe-default rebuild (or extend the plan 01 ADR).
- [ ] **Step 2:** Mark `design.md` of this issue "Implemented (see plan-01, plan-02)".
- [ ] **Step 3:** Read `orchestration/state.py`, `recorder.py`, `workflow.py`, `storage/state_store.py` diffs end to end; remove unused imports/fields/parameters; every `MIGRATIONS`/`STATE_VERSION` use is exercised by a test.
- [ ] **Step 4:** Grep `storage orchestration` for `datetime.now`, inline imports, `Literal` for enum-like fields. Run `uvx ruff check`, `uvx ruff format --check`, `uvx pyright storage orchestration`, `uv run pytest tests/storage tests/orchestration tests/db -q`. Expected: clean, PASS.
- [ ] **Step 5:** Commit `chore: turn locking and state rebuild cleanup`.

## Unresolved Questions
None.
