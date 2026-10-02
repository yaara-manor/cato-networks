# Approval Storage, Per-Payload Grants & Workflow Wiring Implementation Plan (Plan 1 of 2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Everything the approval lifecycle needs below the service: durable settle columns and atomic event-message write in `StateStore`, payload-bound output grants replacing the type-level `approved_actions`, and the Workflow/Resolution wiring so customer status questions and post-approval replies behave correctly.

**Architecture:** Additive migration (`settled_at`, `customer_reason`) plus three thin `StateStore` methods (SQL in `approval_queries.py`, same split as 21). Guardrails take `ApprovedGrant` tuples instead of an action-type set. One pure `ApprovalContext` in `orchestration/approvals.py` derives grants and status views from a single `list_approvals` read.

**Tech Stack:** Python 3.12, psycopg 3 (sync), PostgreSQL 18, PydanticAI agents (unchanged except one input field), pytest. No new dependency. No Braintrust; tracing is the existing `traces` table only.

**Spec:** [design.md](design.md) sections 3 (2, 3, 4, 5), 4.4, 4.5, 4.6, 4.7. Depends on 21-24 and on **31 merged first** (`simulated_actions`, `ActionDispatcher`, `TicketService.update_ticket`, payload `ticket_id`, `OrchestratorState.active_ticket_id`). Plan 02 builds the service on this plan.

## Global Constraints

- Sync, every function fully typed (`-> None` included), Pyright `standard` and ruff clean, imports at module top, f-strings only, `StrEnum` for enums, frozen pydantic models, no `datetime.now` (timestamps passed in from `SimulationClock`), no new dependency.
- SQL named `%(name)s` placeholders, `LiteralString`. Migration idempotent (re-applied by `db.init.seed.apply_schema` after every restore).
- Functional tests on real seeded Postgres; if it is not up, STOP and report. Verify with `uv run pytest <path> -v`, `uvx ruff check <paths>`, `uvx pyright <paths>`.
- Work on the branch named by the executor, commit per task, never merge or push.
- No file above ~400 lines after the change; `storage/state_store.py` and `storage/approval_queries.py` receive only the methods listed.

## Review Focus

1. Event message gets its own turn and can never be mistaken for a customer turn's reply. -> Task 1.
2. `settle_approval` replay returns the same message, no second row, `settled_at` set once. -> Task 1.
3. $500 grant does not license $5,000; edited $300 grant does not license $500; currency mismatch is a violation. -> Task 2.
4. A grant exists only for settled approvals (failed/retrying dispatch grants nothing). -> Task 3.
5. Status question during the approved-but-unsettled window still gives Resolution something to say. -> Task 3.

---

### Task 1: Migration, models and `StateStore` settle primitives

**Files:**
- Create: `db/migrations/20261002_1000_approval-settled.sql`
- Modify: `storage/models.py` (`Approval` gains `settled_at: AwareDatetime | None`, `customer_reason: str | None`, property `effective_payload` = `edited_payload` when set else `payload`), `storage/approval_queries.py` (`resolve_approval` takes optional `customer_reason`; new `settle_approval` SQL part and `list_unsettled_approvals`), `storage/state_store.py` (three public methods below, `resolve_approval` pass-through of `customer_reason`), `storage/__init__.py`
- Test: `tests/storage/test_approval_settle.py` (new), `tests/storage/test_schema.py` (extend)

**Interfaces:**
- Consumes: 21 `StateStore._lock_conversation`, `_insert_message`, `_update_conversation`; `MessageSender.AGENT`.
- Produces:
  - `StateStore.resolve_approval(approval_id: UUID, resolution: ApprovalResolution, at: datetime, customer_reason: str | None = None) -> Approval` (existing CAS, one new column written).
  - `StateStore.settle_approval(approval_id: UUID, content: str, at: datetime) -> StoredMessage`: one transaction; rejects `PENDING` with `ApprovalStateError`; locks the conversation; if `settled_at` is already set returns the stored event message; else inserts an `AGENT` message with `turn = last_turn + 1`, bumps `last_turn`, leaves `stage` untouched, message id derived deterministically from the approval id with a fixed label (`uuid5`), and sets `settled_at = at`.
  - `StateStore.list_unsettled_approvals(limit: int) -> list[Approval]`: status not `PENDING` and `settled_at is null`, ordered by `resolved_at`, then `id`.

- [ ] **Step 1: Write failing tests.** Real DB, 21 `conftest.py` fixtures (`store`, `new_conversation`, `restart`). Cases: (a) approve a row, `settle_approval` returns an AGENT message in turn `last_turn + 1`, `settled_at` set, conversation `stage` unchanged; (b) second call returns equal message, one DB row, `settled_at` unchanged; (c) `PENDING` row raises `ApprovalStateError`; (d) with a customer turn open (customer row, no reply) `settle_approval` adds a later turn and `rehydrate(...).open_turn_traces` plus the turn's own reply logic are unaffected: a following `complete_turn` for the open turn still sets stage `IDLE` only if no event bumped `last_turn` first, so the test documents why plan 02 takes `turn_lock` (assert the stale-turn guard behaviour, not a fix); (e) `list_unsettled_approvals` returns resolved-unsettled rows only, oldest first, honours `limit`; (f) `customer_reason` round-trips after `restart()`; (g) `effective_payload` is edited for EDITED, original otherwise. In `test_schema.py`: migration applied twice is a no-op, new columns and partial index exist, `approvals` data still excluded from the dump.
- [ ] **Step 2:** Run `uv run pytest tests/storage/test_approval_settle.py -v`; expect FAIL.
- [ ] **Step 3:** Write the migration (`add column if not exists` x2, `create index if not exists` on `(resolved_at)` where `status <> 'PENDING' and settled_at is null`), model fields/property, queries and the three store methods. Reuse `fetch_one` / `insert_row` / `jsonable` from `storage/sql.py`; no new helpers.
- [ ] **Step 4:** Re-run storage tests (`uv run pytest tests/storage -v`); expect PASS.
- [ ] **Step 5 (cleanup):** `uvx ruff check storage db tests/storage`, `uvx pyright storage`; confirm no unused imports/constants, no `datetime.now`, no inline imports, nothing duplicates 21 SQL helpers.
- [ ] **Step 6:** Commit `feat(storage): approval settle columns and event message write`.

---

### Task 2: Payload-bound grants in guardrails and agents

**Files:**
- Modify: `guardrails/models.py` (new frozen `ApprovedGrant`: `action_type: ActionType`, `approval_id: UUID`, `payload: dict[str, str]`), `guardrails/validator.py` (`check_outgoing_message` takes `grants: tuple[ApprovedGrant, ...]`; `_OutputRule.approved_by` replaced by a per-rule matcher function chosen from a table), `guardrails/__init__.py`, `agents/base.py` (`SupportDeps.approved_actions` -> `approved_grants: tuple[ApprovedGrant, ...]`), `agents/resolution.py` (pass grants)
- Modify tests: `tests/guardrails/test_validator.py`, `tests/agents/conftest.py`, `tests/agents/test_resolution.py`, `tests/agents/test_pipeline_contracts.py`, `tests/orchestration/conftest.py` (replace every `frozenset[ActionType]()` / `approved_actions=` with an empty grants tuple, default `()`)

**Interfaces:**
- Consumes: 15 `check_outgoing_message` rule table; 22 `SupportDeps`.
- Produces: `check_outgoing_message(message: str, history: SessionGuardHistory, grants: tuple[ApprovedGrant, ...]) -> list[OutputViolation]`. Matching rules: `CREDIT_AMOUNT_PROMISE` passes only if every currency amount in the sentence equals, as `Decimal` after stripping thousands separators and with the same currency (payload `currency`, default `USD`; symbol `$`/`€`/`£` or code adjacent), the `amount` of some `CREDIT` grant. `MFA_RESET_CLAIM` passes if any `MFA_RESET` grant exists (user-accepted: not payload-bound). No matching grant -> violation exactly as today.

- [ ] **Step 1: Write failing tests** in `test_validator.py` (one parametrized table): no grant -> violation; `$500` grant + `$500` sentence -> clean; `$500` grant + `$5,000` sentence -> violation; two amounts in one sentence where one is unapproved -> violation; `$300` (edited) grant + `$500` sentence -> violation; `€500` sentence with USD grant -> violation; `500.00` equals `500`; MFA claim with/without grant. Existing no-grant assertions keep passing with `()`.
- [ ] **Step 2:** Run `uv run pytest tests/guardrails/test_validator.py -v`; expect FAIL.
- [ ] **Step 3:** Implement. Keep the rule loop free of rule-specific branches: the table row carries the matcher callable; amount parsing reuses the existing currency regex of `CREDIT_AMOUNT_PROMISE` rather than adding a second one.
- [ ] **Step 4:** Update all fixture/callers listed above; run `uv run pytest tests/guardrails tests/agents tests/orchestration -v`; expect PASS.
- [ ] **Step 5 (cleanup):** grep the repo for `approved_actions` and `frozenset[ActionType]` approval params: none left; ruff + pyright on `guardrails agents tests`.
- [ ] **Step 6:** Commit `refactor(guardrails): bind output approvals to approved payload`.

---

### Task 3: `ApprovalContext`, Workflow wiring, status view and prompt

**Files:**
- Create: `orchestration/approvals.py` (frozen `ApprovalContext(grants: tuple[ApprovedGrant, ...], unsettled: tuple[UnsettledApprovalView, ...])` with classmethod `from_approvals(approvals: Sequence[Approval]) -> ApprovalContext`)
- Modify: `agents/models.py` (frozen `UnsettledApprovalView(action_type, status: ApprovalStatus, requested_at)`; `ResolutionInput.unsettled_approvals: tuple[UnsettledApprovalView, ...] = ()`), `orchestration/workflow.py` (`_run_locked` reads `store.list_approvals(conversation_id)` once, builds the context, sets `SupportDeps.approved_grants`; `_resolve` passes `unsettled`), `prompts/resolution.md`, `agents/__init__.py`, `orchestration/__init__.py` (re-export)
- Test: `tests/orchestration/test_approval_context.py` (new)

**Interfaces:**
- Consumes: Task 1 (`Approval.settled_at`, `effective_payload`), Task 2 (`ApprovedGrant`, `approved_grants`), 21 `list_approvals`.
- Produces: `ApprovalContext.from_approvals`: grants = APPROVED/EDITED rows with `settled_at` set (effective payload); unsettled = every row with `settled_at` null (any status) as views, payload deliberately absent.

- [ ] **Step 1: Write failing functional tests** (23 conftest stub agents, real guardrails, real Postgres): (a) pending credit + customer status question -> stub Resolution input holds one `PENDING` view, no amount anywhere in the input dump; (b) row approved but unsettled -> view status `APPROVED`, grants empty, a stub reply quoting the amount is rejected and replaced by the handoff (existing re-prompt path); (c) after `settle_approval` the same reply passes and the grant carries the edited payload for an EDITED row; (d) non-blocking: second customer turn answered while the approval stays `PENDING`, stage `IDLE`; (e) override proposal (`VERDICT_OVERRIDE`) -> denial text in reply, zero approval rows; (f) prompt drift: `prompts/resolution.md` names the `unsettled_approvals` field (scripted assertion like 22's prompt tests).
- [ ] **Step 2:** Run `uv run pytest tests/orchestration/test_approval_context.py -v`; expect FAIL.
- [ ] **Step 3:** Implement the context, view model, workflow wiring (no new branches in `_answer`; `_run_locked` gains the read, `_resolve` one argument), prompt paragraph (PENDING -> awaiting Escalation Board review; other unsettled statuses -> "you will get a confirmation here shortly", never the decision, never an amount).
- [ ] **Step 4:** Run `uv run pytest tests/orchestration tests/agents -v`; expect PASS.
- [ ] **Step 5 (cleanup):** ruff + pyright on touched dirs; confirm `Workflow` file did not grow beyond a handful of lines, no leftover `approved_actions`, no unused view fields (every `UnsettledApprovalView` field read by the prompt or a test).
- [ ] **Step 6:** Commit `feat(orchestration): per-conversation approval grants and status view`.
