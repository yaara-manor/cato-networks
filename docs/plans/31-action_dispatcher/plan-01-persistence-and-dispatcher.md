# 31 / Plan 01 — Audit Table, Payloads, Handlers, ActionDispatcher — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land everything the dispatcher stands on and the dispatcher itself, testable without the workflow: `simulated_actions` table + store methods, `TicketService.update_ticket`, typed payloads and `ActionResult`, the six handlers, and `ActionDispatcher` (`dispatch_turn`, `dispatch_approved`, `mark_pending`).

**Architecture:** One Postgres table is both audit log and idempotency store (unique key claimed before the effect). Handlers are small functions in a `SupportActionKind`-keyed dict; page/credit/MFA "effects" are the finalized `result` JSON of the claimed row, ticket kinds go through `TicketService`. Policy stays in `check_action`; the dispatcher only re-checks it.

**Tech Stack:** Python 3.12, psycopg 3 sync, PostgreSQL, Pydantic v2 (frozen models, `StrEnum`), pytest against real Postgres. No new dependency. NO Braintrust; no new tracing: the audit table is the record, one stdlib `logging` line per action.

**Spec:** [design.md](design.md) §1-§5, §7 (items 1, 3, 5, 6). Plan 02 wires this into the workflow.

## Global Constraints

- Sync-only; store/service take `psycopg.Connection[Any]`; named `%(name)s` placeholders; reuse `storage/sql.py` helpers (`fetch_one`, `fetch_all`, `insert_row`, `jsonable`) and the `approval_queries.py` shape. No hand-written row mappers (`class_row`).
- Every function fully typed (`-> None` included), Pyright `standard` and ruff clean, imports at top, f-strings, no `datetime.now` (timestamps from `SimulationClock`), enums are `StrEnum`, frozen Pydantic, tuples over lists.
- Functional tests over unit tests; one parametrized pure test allowed for payload parsing only.
- Tests need compose `postgres` up. If not, STOP and report.
- Verify: `uv run pytest <path> -v`, `uvx ruff check <paths>`, `uvx pyright <paths>`.
- Branch `design/31-action-dispatcher` is design-only; implementation runs on a new branch off `p-2-agent` (`p-3-1_action-dispatcher`). Commit per task. Never merge, never push.
- Sibling contracts that must not drift (32/41/42 read these): `ActionDispatcher(store, tickets, clock)`, `dispatch_approved(approval, context) -> ActionResult`, `mark_pending(approval, context) -> ActionResult`, key `approval:{approval_id}`, `StateStore.list_simulated_actions(conversation_id) -> list[SimulatedAction]`, `SimulatedAction`, `SimulatedActionStatus`, `simulated_actions.approval_id` set on approval-path rows.

## Review Focus

1. Two claims of the same key (two connections) -> exactly one effect. -> Task 1 test.
2. Table re-applied on every boot with rows present -> no-op, rows kept; dump never contains it. -> Task 1.
3. Payload with extra/missing/blank/NUL keys, non-numeric amount -> `INVALID`, no effect, never an exception. -> Task 3.
4. Customer tries another account's ticket id -> `REFUSED`. -> Task 5.
5. Handler raises mid-way -> row `FAILED`, no secret or exception text stored or logged. -> Task 5.

---

### Task 1: `simulated_actions` table and store methods

**Files:**
- Create: `db/migrations/20261002_0900_simulated-actions.sql`, `storage/action_queries.py`
- Modify: `storage/models.py` (add `SimulatedActionStatus` StrEnum: CLAIMED, DONE, FAILED, INVALID, REFUSED; frozen `SimulatedAction` with the design §3 columns; `ClaimedAction(action: SimulatedAction, is_new: bool)`), `storage/state_store.py` (three thin methods), `storage/__init__.py` (exports), `db/init/build.py` (add table to `RUNTIME_TABLES`), `tests/storage/conftest.py` and `tests/orchestration/conftest.py` (cleanup SQL deletes `simulated_actions` first, FK RESTRICT), `tests/storage/test_schema.py` (table list)
- Test: `tests/storage/test_simulated_actions.py`

**Interfaces:**
- Produces: `StateStore.claim_action(conversation_id: UUID, message_id: UUID | None, approval_id: UUID | None, kind: str, idempotency_key: str, payload: dict[str, Any], at: datetime) -> ClaimedAction` (insert `on conflict (idempotency_key) do nothing`, then read back, `is_new` from whether the insert returned a row); `StateStore.finish_action(action_id: UUID, status: SimulatedActionStatus, result: dict[str, Any], at: datetime) -> SimulatedAction` (update only from `CLAIMED`, else raise a caller-bug error mirroring `ApprovalStateError`); `StateStore.list_simulated_actions(conversation_id: UUID) -> list[SimulatedAction]` ordered by `(claimed_at, id)`.
- Consumes: `storage/sql.py` helpers, `StateStore._lock_conversation` pattern not needed (unique key is the lock).

- [ ] **Step 1: Write failing functional tests** in `test_simulated_actions.py`: claim twice (same key) returns same row, `is_new` True then False; two connections racing the same key yield one new; finish moves `CLAIMED` to terminal once, second finish raises; list is ordered; approval-path row keeps `approval_id`; a NUL byte in payload is stripped, not a crash; new rows survive a "restart" (new connection).
- [ ] **Step 2: Run them**, expect failure (table/method missing).
- [ ] **Step 3: Write the migration**: idempotent (`create table if not exists`, `create index if not exists`), columns exactly as design §3 (id, conversation_id FK restrict, message_id nullable no FK, idempotency_key unique, kind text, approval_id nullable FK restrict to `approvals`, payload jsonb, status text, result jsonb nullable, claimed_at, completed_at nullable), index on `(conversation_id, claimed_at)`. No `%` or unbalanced braces (applied through `psycopg.sql.SQL`). No CHECK constraints (21 plan delta 3: enum validation in Pydantic only; design §3's CHECK + drift test is superseded here and in design cleanup).
- [ ] **Step 4: Implement** models, `action_queries.py` (three functions, `class_row`), the three `StateStore` methods, exports, `RUNTIME_TABLES` entry, conftest cleanup lines, schema test list.
- [ ] **Step 5: Run** `tests/storage` fully (hygiene edits must not break existing tests) and `tests/db` (dump exclusion test), expect PASS. If a committed `db/seed.dump` contains the table, regenerate per 21 (`python -m db.init.build`) and note it.
- [ ] **Step 6: Cleanup**: ruff, pyright on touched files; no unused import or model; read the diff end to end.
- [ ] **Step 7: Commit.**

---

### Task 2: `TicketService.update_ticket` and public action-type map

**Files:**
- Modify: `services/ticket_service.py`, `agents/models.py` (rename private `_GATED_ACTION_TYPES` to public `GATED_ACTION_TYPES` plus a one-line inverse accessor `support_kind_for(action_type) -> SupportActionKind`; update the one internal reader)
- Test: `tests/services/test_ticket_update.py`

**Interfaces:**
- Produces: `TicketService.update_ticket(ticket_id: str, status: TicketStatus | None = None, site_id: str | None = None, priority: TicketPriority | None = None) -> Ticket` (at least one field required else `ValueError`; unknown id raises `ValueError`, same as `update_ticket_status`; commits like siblings). `update_ticket_status` becomes a one-line delegate (DRY; its callers unchanged).
- Consumes: existing `_row_to_ticket`, `_TICKET_COLUMNS`.

- [ ] **Step 1: Write failing functional tests** against the real tickets table with a ticket created in the test and deleted in a fixture: each field alone, all three together, nothing given raises, unknown id raises, `update_ticket_status` still behaves as before.
- [ ] **Step 2: Run**, expect failure.
- [ ] **Step 3: Implement** building the `set` clause from only the provided fields (psycopg `sql` composition, no string-formatted SQL); delegate `update_ticket_status`.
- [ ] **Step 4: Rename the map** in `agents/models.py`; run `tests/agents` and `tests/orchestration` to confirm nothing else read the private name.
- [ ] **Step 5: Run** the new and existing `tests/services`, expect PASS.
- [ ] **Step 6: Cleanup**: ruff, pyright, no leftover private-name references (grep).
- [ ] **Step 7: Commit.**

---

### Task 3: Payload models and `ActionResult`

**Files:**
- Create: `actions/__init__.py` (re-exports only), `actions/models.py` (`ActionStatus`, `DispatchContext`, `ActionResult`, `DispatchRequest`), `actions/payloads.py` (the six payload models; separate file so neither passes ~250 lines)
- Test: `tests/actions/test_payloads.py`

**Interfaces:**
- Produces per design §4: `ActionStatus` (DONE, FAILED, INVALID, REFUSED), `DispatchContext(identity, priority, sev1_corroborated, already_paged, conversation_id, message_id)`, `ActionResult` with classmethods `done`, `failed`, `invalid`, `refused`, `from_stored(SimulatedAction)`, field `replayed`; payload models `CreateTicketPayload`, `UpdateTicketPayload`, `CloseTicketPayload`, `PageOnCallPayload`, `CreditPayload` (`ticket_id` required, amount as `Decimal`), `MfaResetPayload` (`ticket_id` required), each with `from_payload(raw: dict[str, str]) -> Self` that rejects unknown keys, missing required keys, blank values, and `UpdateTicketPayload` with no change field; a shared tiny base class holds the unknown-key check (one place).
- Consumes: `agents.SupportAction`/`SupportActionKind`, `core.models` literals (reused, not copied), `services.models.CallerIdentity`, `storage.SimulatedAction`.

- [ ] **Step 1: Write one parametrized test** over (kind, raw dict, valid or not): valid sets, extra key, missing key, blank, bad amount, bad priority literal, update with no field, NUL in value.
- [ ] **Step 2: Run**, expect failure.
- [ ] **Step 3: Implement** models; `from_payload` raises `ValueError` only; the dispatcher (Task 5) turns that into `INVALID`.
- [ ] **Step 4: Run**, expect PASS.
- [ ] **Step 5: Cleanup**: ruff, pyright; every model used by Task 4/5 or a test (delete otherwise); `__init__` re-exports only.
- [ ] **Step 6: Commit.**

---

### Task 4: Handlers (`actions/simulated.py`)

**Files:**
- Create: `actions/simulated.py`
- Test: covered by Task 5's functional tests (handlers are not unit-tested alone, per the functional-over-unit rule)

**Interfaces:**
- Produces: a `HANDLERS` dict from `SupportActionKind` to handler, and `REFUSED_KINDS = {VERDICT_OVERRIDE}`. Handler signature: takes a `HandlerInput` (validated payload, `DispatchContext`, `TicketService`, claimed `SimulatedAction`) and returns `ActionOutcome(reference: str, result: dict[str, Any], customer_line: str | None)`; failures raise (the dispatcher converts). Handlers: create ticket (customer_name and requester_email both `identity.caller_email`, `None` -> raise `ValueError`), update ticket, close ticket, page on call (incident ref `INC-` + 8 hex chars of the action id, summary, sites, priority, ack minutes 15 per POL-SEV1), credit (amount, currency, incident, period, ticket), MFA reset (user email, ticket, identity basis from `is_registered_admin` and caller email).
- Ticket handlers share one private ownership check (ticket `customer_id` equals account id; else raise a dedicated `OwnershipError` the dispatcher maps to `REFUSED`).
- Customer-line templates are module constants (ticket created with id, ticket updated, ticket closed, paged with incident ref and 15 minutes), asserted verbatim in Task 5 tests. Credit/MFA handlers return no customer line (issue #10).

- [ ] **Step 1: Implement** the six handlers plus constants; each function small, one effect.
- [ ] **Step 2: Add the exhaustiveness check** as a test in `tests/actions/test_schema.py`: every `SupportActionKind` is in `HANDLERS` or `REFUSED_KINDS`, and the two sets are disjoint.
- [ ] **Step 3: Run** that test, expect PASS.
- [ ] **Step 4: Cleanup**: ruff, pyright; no handler calls `check_action` or reads settings; no duplicate ownership logic.
- [ ] **Step 5: Commit.**

---

### Task 5: `ActionDispatcher`

**Files:**
- Create: `actions/dispatcher.py`, `tests/actions/conftest.py` (fixtures: connection, store, `TicketService`, clock, a verified-member identity and a registered-admin identity from seeded accounts, cleanup of created conversations, `simulated_actions` rows and tickets)
- Modify: `actions/__init__.py`
- Test: `tests/actions/test_dispatch_tickets.py`, `tests/actions/test_sev1_paging.py` (dispatcher-level part), `tests/actions/test_dispatch_approved.py`, `tests/actions/test_schema.py` (finish)

**Interfaces:**
- Produces: `ActionDispatcher(store: StateStore, tickets: TicketService, clock: SimulationClock)`; `dispatch_turn(actions: tuple[SupportAction, ...], context: DispatchContext) -> tuple[ActionResult, ...]` (key `{message_id}:{kind}:{index}`, page key `{conversation_id}:PAGE_ON_CALL`); `dispatch_approved(approval: Approval, context: DispatchContext) -> ActionResult` (key `approval:{approval_id}`; `EDITED` uses `edited_payload` and rejects an edit that drops or changes `ticket_id` as `INVALID`; `PENDING`/`REJECTED` -> `REFUSED`); `mark_pending(approval: Approval, context: DispatchContext) -> ActionResult` (key `approval:{approval_id}:pending`, sets ticket `pending_approval` via the shared ticket-handler path, ownership checked); private `_run(request)` implementing design §5.1 in order: defensive `check_action` re-check, payload validation, claim, handler in one `try/except Exception` (class name only logged), finish, one log line.
- Consumes: Tasks 1-4, `guardrails.check_action`, `agents.GATED_ACTION_TYPES` and its inverse.

- [ ] **Step 1: Write failing functional tests** (real Postgres, real `TicketService`):
  - tickets: create writes a ticket for the caller's account and a `DONE` row with the ticket id and the exact customer line; update each field; unknown ticket `FAILED`; other account's ticket `REFUSED`; invalid payload `INVALID` with no ticket written; close; missing `caller_email` `INVALID`; duplicate `dispatch_turn` call returns stored results with `replayed` and creates no second ticket; stored `CLAIMED` row without result surfaces `FAILED` "outcome unknown".
  - paging (dispatcher level): corroborated P1 context -> `DONE`, row has incident ref and 15 minute ack; `sev1_corroborated=False` or P2 -> `REFUSED`, no row finalized as `DONE`; a second page in the same conversation from a different message id -> `REFUSED`, one `DONE` row total; same message id retry -> replayed `DONE`.
  - approved: credit approved -> event with payload amount, row `approval_id` set; edited -> uses `edited_payload`, original payload untouched; edit dropping `ticket_id` -> `INVALID`; rejected/pending -> `REFUSED`, no row; MFA reset with non-admin identity -> `REFUSED`; `VERDICT_OVERRIDE` -> `REFUSED`; `mark_pending` flips ticket to `pending_approval` and a replay is a no-op; handler failure (monkeypatch the ticket service to raise) -> `FAILED`, row `FAILED`, no exception text stored.
- [ ] **Step 2: Run them**, expect failure.
- [ ] **Step 3: Implement the dispatcher**, one private method per §5.1 step so `_run` reads as a list; no `match` over kinds in the dispatcher (the dict does that); no policy beyond calling `check_action`.
- [ ] **Step 4: Run** `tests/actions` and `tests/storage`, expect PASS.
- [ ] **Step 5: Cleanup (final)**: ruff, pyright on `actions/`, `storage/`, `services/`; grep `actions/` for `datetime.now`, inline imports, `Literal`, `Braintrust`; delete any unused model or helper; confirm file sizes under ~250 lines; read the diff end to end.
- [ ] **Step 6: Commit.**
