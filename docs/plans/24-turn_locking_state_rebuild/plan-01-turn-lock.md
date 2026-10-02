# Per-Conversation Turn Lock Implementation Plan (Plan 1 of 2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Two workers never run a turn for the same conversation concurrently; a killed worker never leaves the conversation locked; a client retry of an answered `message_id` never re-runs agents.

**Architecture:** One session-level Postgres advisory lock per conversation, acquired on the same connection `StateStore` writes through, wrapped around the whole of `Workflow.run_turn` (23's `_ingest` dedupe runs inside it). Release is a `finally` unlock, or the server dropping the lock when the backend dies.

**Tech Stack:** Python 3.12, psycopg 3 (sync), PostgreSQL 18, pytest, threads for concurrency tests. No new dependency.

**Spec:** [design.md](design.md) sections 2.1-2.7, 3, 4. Depends on plans 21 and 23 merged (`StateStore`, `Workflow`, `TurnRecorder`). The `message_id` dedupe already lives in 23 `_ingest` and is reused, not rewritten.

## Global Constraints

- Sync, every function/method fully typed (`-> None` included), Pyright `standard` and ruff clean, imports at module top, f-strings only, `StrEnum` for enums, frozen pydantic models, no `datetime.now`, no new dependency.
- SQL named `%(name)s` placeholders, `LiteralString` SQL (as `retrieval/service.py`).
- Functional tests against real seeded Postgres; if it is not up, STOP and report. Verify with `uv run pytest <path> -v`, `uvx ruff check <paths>`, `uvx pyright <paths>`.
- Branch `p-2-4_turn-locking-state-rebuild`; commit per task; never merge, never push.
- Files stay small: `storage/turn_lock.py` under ~60 lines.

## Review Focus

1. Killed lock holder (`pg_terminate_backend`): waiter acquires, no deadlock. -> Task 1.
2. Timeout leaves nothing behind: after `TurnLockTimeout` the next acquire works and no row was written. -> Tasks 1, 2.
3. Two workers retrying the same `message_id` simultaneously: stubs run once. -> Task 2.
4. Unlock on an already-dead connection must not mask the original exception. -> Task 1.
5. Same-connection reentrancy: documented, pinned by test so nobody shares a connection across threads. -> Task 1.

---

### Task 1: `turn_lock` and the `StateStore` entry point

**Files:**
- Modify: `core/config.py` (add `turn_lock_timeout_s: float = 30.0` to `Settings`)
- Create: `storage/turn_lock.py`
- Modify: `storage/state_store.py` (add `turn_lock`), `storage/__init__.py` (export `TurnLockTimeout`)
- Test: `tests/storage/test_turn_lock.py`

**Interfaces:**
- Consumes: `core.config.settings`; 21 `StateStore.__init__(connection)` (autocommit connection stored privately).
- Produces:
  - `TurnLockTimeout(Exception)`.
  - `turn_lock(connection: psycopg.Connection[Any], conversation_id: UUID, timeout_s: float) -> Iterator[None]`, a `contextmanager`. Behavior: set session `lock_timeout` (milliseconds from `timeout_s`) with `set_config`, run `select pg_advisory_lock(hashtextextended(<'turn:' + id>, 0))`, reset `lock_timeout` right after the acquire, yield, then `pg_advisory_unlock` in `finally`. `psycopg.errors.LockNotAvailable` on acquire becomes `TurnLockTimeout`. `psycopg.OperationalError` raised by the unlock is swallowed (lock already gone with the backend); any other error propagates. Add a `ponytail:` comment: one connection per in-flight turn, pool when concurrency grows.
  - `StateStore.turn_lock(conversation_id: UUID) -> AbstractContextManager[None]`, delegating with `settings.turn_lock_timeout_s`.

- [ ] **Step 1: Write failing tests** in `test_turn_lock.py`, each using separate `psycopg.connect(settings.database_url, autocommit=True)` connections and fresh `uuid4()` ids: (a) A holds, B in a thread blocks (assert B has not acquired after 0.3 s), A releases, B acquires; (b) different conversations do not block; (c) A holds, B with `timeout_s=0.3` raises `TurnLockTimeout` after about 0.3 s, then acquires after A releases; (d) crash release: A holds, a third connection runs `pg_terminate_backend` on A's backend pid (`pg_backend_pid()` captured beforehand), B acquires within 5 s; (e) the `with` block raising `ValueError` still unlocks (B acquires) and the `ValueError` propagates; (f) A acquires twice on one connection without blocking (pins the reentrancy rule).
- [ ] **Step 2:** Run `uv run pytest tests/storage/test_turn_lock.py -v`. Expected: FAIL (module missing).
- [ ] **Step 3:** Implement `turn_lock`, the setting and `StateStore.turn_lock`. If `lock_timeout` turns out not to interrupt `pg_advisory_lock` on this server, switch the acquire to a `pg_try_advisory_lock` poll loop (0.05 s sleep) bounded by `timeout_s`; the contract and tests stay identical.
- [ ] **Step 4:** Re-run the file. Expected: PASS. Run `uvx ruff check storage core tests/storage` and `uvx pyright storage`.
- [ ] **Step 5:** Commit `feat(storage): per-conversation advisory turn lock`.

---

### Task 2: Wrap `run_turn` in the lock

**Files:**
- Modify: `orchestration/workflow.py` (split `run_turn` into the locking shell and private `_run_locked`; no behavior change inside)
- Test: `tests/orchestration/test_turn_serialization.py` (new; state-related tests arrive in plan 02)
- Test: `tests/orchestration/conftest.py` (add a `worker_factory` fixture: opens a fresh autocommit connection, builds `StateStore` and a `Workflow` with stub ports; closes on teardown)

**Interfaces:**
- Consumes: 23 `Workflow.run_turn(conversation_id: UUID, message: str, message_id: UUID) -> TurnResult`, `StateStore.turn_lock`, stub agents from `conftest.py` (sleeping stub variant records enter/exit `time.monotonic()` pairs).
- Produces: unchanged public signature. `run_turn` = `with store.turn_lock(conversation_id)` around `_run_locked(...)` (23's current body, untouched; its `_ingest` already returns the stored result for an answered `message_id`, now race-free). No new dedupe code. `TurnLockTimeout` propagates (the 23 agent-exception boundary lives inside `_run_locked`, so it cannot swallow it).

- [ ] **Step 1: Write failing tests:** (a) *serialize:* two threads, two workers, one conversation, different `message_id`s, Triage stub sleeps 0.5 s; enter/exit intervals do not overlap; stored turns are 1 and 2; the second Triage call's history contains the first turn's reply. (b) *concurrent duplicate:* two threads, same `message_id`; Triage/Resolution stubs each called exactly once in total, both callers return the same reply, one customer message row. (c) *timeout:* worker A stuck in a 2 s stub, worker B built with a small lock timeout (monkeypatch `settings.turn_lock_timeout_s` to 0.3) raises `TurnLockTimeout`; afterwards zero rows for B's `message_id`. (d) *crash:* the Diagnostics stub of worker A sleeps; a watcher thread terminates A's backend; A's `run_turn` raises a psycopg error; worker B retries the same `message_id`, acquires the lock, finishes, exactly one agent reply in the conversation and stage `IDLE`.
- [ ] **Step 2:** Run `uv run pytest tests/orchestration/test_turn_serialization.py -v`. Expected: FAIL.
- [ ] **Step 3:** Implement the shell/`_run_locked` split and the in-lock dedupe check.
- [ ] **Step 4:** Run the file, then `uv run pytest tests/orchestration tests/storage -q` (23 and 21 suites still green). Expected: PASS; ruff/pyright on touched paths.
- [ ] **Step 5:** Commit `feat(orchestration): serialize turns per conversation`.

---

### Task 3: Docs and cleanup (final)

- [ ] **Step 1:** Add a short "Concurrency" section to `docs/architecture/system-architecture-design.md`: lock scope, key, timeout behavior, and the production DSN requirement for TCP keepalives (`keepalives_idle`, `keepalives_interval`, `keepalives_count`) so half-open connections release locks.
- [ ] **Step 2:** Add the ADR to `docs/overview/decisions.md` (next free number): session-level advisory lock on the store's own connection; no lease, no fencing token, rationale from design 2.3.
- [ ] **Step 3:** Read `storage/turn_lock.py`, the `state_store.py` diff and `workflow.py` diff end to end. Remove unused imports/constants/fixtures; confirm every export in `storage/__init__.py` is used.
- [ ] **Step 4:** Grep `storage orchestration` for `datetime.now`, inline imports, `Literal` for enum-like fields. Run `uvx ruff check storage orchestration core tests`, `uvx ruff format --check`, `uvx pyright storage orchestration`, `uv run pytest tests/storage tests/orchestration -q`. Expected: clean, PASS.
- [ ] **Step 5:** Commit `chore(storage): turn lock cleanup and docs`.

## Unresolved Questions
None.
