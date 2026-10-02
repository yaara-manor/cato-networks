# ApprovalService, Notices & Resume Tests Implementation Plan (Plan 2 of 2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reviewer decisions become durable, execute through #9's dispatcher, clear the ticket, and reach the customer as an AGENT event message, surviving crashes at every step.

**Architecture:** `ApprovalService` (sync) orchestrates existing parts only: `StateStore` CAS and settle primitives (plan 01), `ActionDispatcher.dispatch_approved` (31), `TicketService`, `StateStore.turn_lock` (24). `decide` = `resolve` then `settle`; `settle_unsettled` is a lifespan sweep over `list_unsettled_approvals`. Notice text is a deterministic table in its own module.

**Tech Stack:** Python 3.12, psycopg 3, PostgreSQL 18, pytest, threads for interleaving. No new dependency, no Braintrust, no LLM.

**Spec:** [design.md](design.md) sections 3, 4.1-4.3, 5, 5b, 6, 7. Depends on plan 01 and on 31 (`ActionDispatcher`, `DispatchContext`, `ActionResult`, `TicketService.update_ticket`).

## Global Constraints

- Sync, fully typed, Pyright `standard` + ruff clean, imports at top, f-strings only, `StrEnum`, frozen pydantic, classmethod converters (no `format_x`), no `datetime.now` (use `SimulationClock`).
- Import cycle rule: `services/approval_service.py` imports `actions`; do NOT re-export `ApprovalService` or its models from `services/__init__.py`. Consumers (#12, #11) import by module path.
- Logs carry exception class names only, never messages or payloads.
- Functional tests on real Postgres; "restart" = new connection + new `StateStore` + new service (21 pattern). Verify with `uv run pytest`, `uvx ruff check`, `uvx pyright`.
- Branch per executor, commit per task, never merge or push. New files stay under ~250 lines.

## Review Focus

1. Dispatcher failure never produces a customer notice; sweep retries until success. -> Task 3.
2. Crash after CAS (no settle), after dispatch (settle tx fails once): one `simulated_actions` row, one notice. -> Task 3.
3. Settle racing an open customer turn: notice lands in a later turn, open turn's reply is the real answer, stage ends `IDLE`. -> Task 3.
4. `reviewer_notes` and non-allowlisted payload keys never reach the customer; unsafe `customer_reason` rejected before CAS. -> Tasks 1, 2.
5. Edit that changes the key set (drops `ticket_id`) or fails `check_action` is rejected before CAS. -> Task 2.

---

### Task 1: Decision models and deterministic notices

**Files:**
- Create: `services/approval_models.py` (`ReviewerDecision(approval_id: UUID, resolution: ApprovalResolution, customer_reason: str | None = None)`, `SettleOutcome(StrEnum)`: `SETTLED`, `ALREADY_SETTLED`, `EXECUTION_FAILED`, `BUSY`; `DecisionResult(approval: Approval, settle: SettleOutcome)`), `services/approval_notice.py` (`ApprovalNotice` with classmethod `from_approval(approval: Approval) -> ApprovalNotice`; one module-level table keyed by `(ActionType, ApprovalStatus)` for CREDIT and MFA_RESET x APPROVED/EDITED/REJECTED; per-`ActionType` allowlist of payload keys shown, from `effective_payload`; rejected text appends `customer_reason` when set)
- Test: `tests/services/test_approval_notice.py`

**Interfaces:**
- Consumes: plan 01 `Approval.effective_payload`, `ApprovedGrant`/`check_outgoing_message`, `redact`.
- Produces: `ApprovalNotice.text: str`; `from_approval` raises `ValueError` for `PENDING` or an unsupported `(ActionType, status)` (fail fast, caught as a bug by the table test).

- [ ] **Step 1: Write the failing test** (one parametrized functional check): every supported `(type, status)` renders; text contains allowlisted values from the effective payload (edited value for EDITED), never `reviewer_notes`, never a non-allowlisted key or the `ticket_id`; for APPROVED/EDITED the text passes `check_outgoing_message` and is unchanged by `redact` once the approval's own grant is supplied, and a credit notice is a violation without it (pins why grants exist); `PENDING` raises.
- [ ] **Step 2:** Run `uv run pytest tests/services/test_approval_notice.py -v`; expect FAIL.
- [ ] **Step 3:** Implement models and notice table.
- [ ] **Step 4:** Run; expect PASS.
- [ ] **Step 5 (cleanup):** ruff/pyright on `services tests/services`; every table entry and model field exercised by a test; no unused imports.
- [ ] **Step 6:** Commit `feat(services): approval decision models and notices`.

---

### Task 2: `ApprovalService` lifecycle (`resolve`, `settle`, `decide`, `settle_unsettled`)

**Files:**
- Create: `services/approval_service.py`
- Test: `tests/services/test_approval_service.py`

**Interfaces:**
- Consumes: Task 1; plan 01 store methods; 31 `ActionDispatcher.dispatch_approved(approval, context) -> ActionResult` (`ActionStatus.DONE` is success), `DispatchContext`; `TicketService.get_ticket` / `update_ticket`; `CustomerService.authenticate_caller`; `StateStore.turn_lock`, `record_trace`, `list_messages`; `check_action`, `check_outgoing_message`, `redact`; `SimulationClock`.
- Produces (all on `ApprovalService(store, dispatcher, tickets, customers, clock)`):
  - `list_pending(conversation_id: UUID | None = None) -> list[Approval]`, `get_approval(approval_id: UUID) -> Approval | None` (thin delegates).
  - `resolve(decision: ReviewerDecision) -> Approval`: pre-CAS fail-fast checks raising `ApprovalStateError`: unknown id; for EDITED the edited key set equals the original key set (keeps `ticket_id`) and `check_action` on the edited payload (identity from `customers.authenticate_caller` on the conversation row) is still `REQUIRE_APPROVAL`; `customer_reason`, when present, is clean under `redact` + `check_outgoing_message` with the conversation's `guard_history` and no grants. Then `StateStore.resolve_approval` with `customer_reason`.
  - `settle(approval_id: UUID) -> SettleOutcome`: `PENDING` -> `ApprovalStateError`; `settled_at` set -> `ALREADY_SETTLED`; APPROVED/EDITED -> `dispatch_approved` with a `DispatchContext` built from the conversation row (neutral `P4`/False/False), status not `DONE` -> log class/status only, return `EXECUTION_FAILED`; clear ticket (all outcomes): read `ticket_id` from `effective_payload`, if `get_ticket` shows `pending_approval` set `open`, any exception -> log class name and write an `ORCHESTRATOR`/`ERROR` trace through `StateStore.record_trace` (turn and message id of the proposing message found via `list_messages`, trace id derived from the approval id so replays do not duplicate) then continue; notice via `ApprovalNotice.from_approval`; `with store.turn_lock(conversation_id)`: `settle_approval`; `TurnLockTimeout` -> `BUSY`; else `SETTLED`.
  - `decide(decision: ReviewerDecision) -> DecisionResult`: `resolve` then `settle`, no logic of its own.
  - `settle_unsettled(limit: int = 50) -> tuple[SettleOutcome, ...]`: `list_unsettled_approvals` then `settle` each; one row failing never stops the rest (settle returns outcomes, only programmer errors raise and are logged per row).

- [ ] **Step 1: Write failing functional tests** with the real `ActionDispatcher` over a stub handler map or the 31 test fixtures, real `TicketService` and Postgres: APPROVED/EDITED/REJECTED lifecycle (dispatcher request carries the edited payload; reject dispatches nothing; notice text matches table; `reviewer_notes` absent; `customer_reason` present); second `decide` raises `ApprovalStateError` and writes no second message; `settle` twice -> `ALREADY_SETTLED`, one message, one `simulated_actions` row; ticket `pending_approval` -> `open` for all three outcomes, untouched when already moved; ticket update failure (monkeypatched) -> trace row exists, notice still sent; edit dropping `ticket_id` rejected, no state change; edit failing `check_action` rejected; unsafe `customer_reason` (credit amount promise) rejected before CAS; dispatcher stub returns `FAILED` -> `EXECUTION_FAILED`, no message, row still in `list_unsettled_approvals`; `settle_unsettled` settles it once the stub succeeds.
- [ ] **Step 2:** Run `uv run pytest tests/services/test_approval_service.py -v`; expect FAIL.
- [ ] **Step 3:** Implement the service. Keep each method single-purpose: private `_dispatch(approval)`, `_clear_ticket(approval)`, `_context(conversation)` helpers (each under ~25 lines); no SQL in the service; no second approval model.
- [ ] **Step 4:** Run; expect PASS.
- [ ] **Step 5 (cleanup):** ruff/pyright; confirm no import cycle (`python -c "import services; import services.approval_service"` in both orders via a test import), no `services/__init__.py` change, no unused helpers or imports.
- [ ] **Step 6:** Commit `feat(services): ApprovalService decide/settle/sweep`.

---

### Task 3: Crash, interleaving and end-to-end resume tests, docs

**Files:**
- Create: `tests/orchestration/test_approval_resume.py`
- Modify: `tests/orchestration/conftest.py` (cleanup SQL includes `simulated_actions` if 31 did not add it; a fixture building the service on a fresh connection), `docs/architecture/system-architecture-design.md` (section 9 sequence: decide, settle, event message; layout entries `services/approval_service.py`, `approval_models.py`, `approval_notice.py`, migration file; ER `approvals.settled_at`, `customer_reason`), `docs/overview/decisions.md` (next free ADR: deterministic settle plus sweep over resume-turn/outbox; notice as own-turn event message; per-payload grants)

**Interfaces:**
- Consumes: plans 01 and Task 2 above; 23 `Workflow` with stub agents; 24 `turn_lock`.
- Produces: tests only (plus docs).

- [ ] **Step 1: Write the functional tests** (real Postgres, stub agents, zero LLM): (a) non-blocking SC-03 flow: credit proposed -> PENDING row -> second customer turn answered, stage `IDLE`; (b) resume after restart: `decide(APPROVED)` in connection A with settle skipped (call `resolve` only), drop everything, new connections, `settle_unsettled` -> event message only in the right conversation, one `simulated_actions` row, next customer turn sees the event in agent history and a `$500` reply passes, `$5,000` is rejected; (c) crash after dispatch before the settle tx (force `settle_approval` to fail once) then sweep: one row, one notice; (d) interleaving: a customer turn blocked inside a stub agent while `settle` runs in another thread: settle waits on the lock, then the notice lands in a later turn, the open turn's stored reply is the real answer, final stage `IDLE`; (e) `TurnLockTimeout` -> `BUSY`, nothing written, next sweep settles; (f) dispatcher `FAILED` -> no notice, retried every sweep until success; (g) EDITED to `$300`: notice shows `$300`, `$500` reply rejected, `$300` passes; (h) UI contract smoke: `decide` result fields and `ApprovalStateError` on a second reviewer.
- [ ] **Step 2:** Run `uv run pytest tests/orchestration/test_approval_resume.py -v`; expect PASS or fix implementation gaps in Tasks 1-2 of this plan (not by weakening tests).
- [ ] **Step 3:** Update the architecture doc and ADR as listed.
- [ ] **Step 4 (final cleanup):** read every file created or modified across both plans end to end; delete unused imports/constants/models/helpers; grep for `approved_actions`, `ActionExecutor`, `PendingApprovalView`, `datetime.now`, inline imports, `Literal` for enum-like fields; full `uv run pytest tests -q`, `uvx ruff check .`, `uvx pyright`.
- [ ] **Step 5:** Commit `test(orchestration): approval resume, crash and interleaving`.
