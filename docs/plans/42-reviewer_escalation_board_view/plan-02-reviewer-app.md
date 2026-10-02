# 42 / Plan 02 — Reviewer App, Decisions, Packaging — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The working reviewer page: Escalation Board, four panels, approve / edit / reject through `ApprovalService.decide`, live trace, runnable via compose.

**Architecture:** Thin Streamlit script `ui/reviewer_app.py` over plan 01's `CaseView` and 41's shared `ui/trace_panel.py`; all writes go through 32's `ApprovalService`. A thin `ui/reviewer_session.py` reuses 41's `orchestration/runtime.py::build_services` (no model warm-up, no Workflow) and adds `ApprovalService`; connections are opened per run.

**Tech Stack:** Streamlit (`streamlit.testing.v1.AppTest`), psycopg 3, Pydantic v2, pytest. No Braintrust.

**Spec:** [design.md](design.md) §6, §7, §9, §10; prerequisites: plan-01 merged; designs 31 (`StateStore.list_simulated_actions`, `SimulatedAction`), 32 (`ApprovalService.decide / list_pending / get_approval / settle_unsettled`, `ReviewerDecision`, `DecisionResult`, `SettleOutcome`, `ApprovalStateError`), 41 (`ui/trace_panel.py`: `TracePanel.from_replay`, `render_trace_panel`; `ui/session.py` connection helper, `streamlit` dependency and Dockerfile line); `orchestration/runtime.py` (`build_services(connection, clock) -> Services`). Do not start until those are merged into the base.

## Global Constraints

- Same style rules as plan 01. `ui/reviewer_app.py` holds rendering and event wiring only: no SQL, no parsing, no policy. Max ~200 lines; each panel renders in its own small function.
- Never call `StateStore.resolve_approval`, `ApprovalService.resolve` or `settle` from the UI; never write `approvals` / `messages`. Never `unsafe_allow_html`; all customer-influenced text via `st.code` / `st.text`.
- Import `ApprovalService` only from `services.approval_service` (final 32: not re-exported, import cycle with `actions`). `SettleOutcome` is a StrEnum; `customer_reason` exists only on `ReviewerDecision`.
- Do not define trace models or trace rendering; import 41's. Do not modify `ui/trace_panel.py` or `ui/customer_app.py`.
- Connections: opened per script/fragment run with a context manager, autocommit; never cached. Only services/config are cached (`st.cache_resource`).
- Polling: board fragment 3 s, live trace fragment 2 s while stage is not `IDLE`.
- Approval rows seeded in tests use a customer message from the same conversation (composite FK). `AgentRole` is imported from `agents.models`.
- Functional `AppTest` tests, real Postgres, scripted agents, zero LLM.

## Review Focus

1. Two reviewers click on one approval: loser sees "already resolved", winner's resolution intact, one dispatch row. -> Task 2.
2. `decide` returns `settle` not `SETTLED` (BUSY / EXECUTION_FAILED): UI says decision saved, notice pending; not an error. -> Task 2.
3. Edit that adds or drops a payload key, or reject without a note: blocked in UI before any service call (32 `resolve` re-checks the same rules and raises `ApprovalStateError`, shown verbatim). -> Task 2.
4. Conversation id in the query string that does not exist: friendly "not found", no traceback. -> Task 3.
5. Process restart with an approved-but-unsettled row: runtime start sweeps it. -> Task 1.

---

### Task 1: Reviewer runtime and decision form

**Files:**
- Create: `ui/reviewer_session.py`, `tests/ui/test_reviewer_session.py`
- Modify: `ui/reviewer_view.py` (add `DecisionForm`, `ApprovalCard.dispatch`, `CaseView.from_rows` gains `actions: Sequence[SimulatedAction]`), `tests/ui/test_case_view.py`

**Interfaces:**
- Consumes: 32 `ApprovalService` (from `services.approval_service`), `ReviewerDecision`, `ApprovalResolution`; 31 `SimulatedAction`; `core.config.settings`; `SimulationClock`.
- Produces: `ReviewerRuntime` (frozen: clock plus a callable taking a connection and returning `ApprovalService`, built from `build_services` output; no duplicated assembly); `build_reviewer_runtime() -> ReviewerRuntime` (cached; never calls `build_workflow` / `warm_models`; runs `settle_unsettled` once on first build); `DecisionForm` (frozen: `approval_id`, `kind` StrEnum APPROVE/EDIT/REJECT, `note`, `customer_reason`, `edited_payload`, original payload) with `to_decision() -> ReviewerDecision` raising a typed `DecisionFormError` for: reject without note, edit with different key set; `ApprovalCard.dispatch: SimulatedAction | None` matched by `approval_id`.

- [ ] **Step 1:** Failing tests: building the runtime does not load the embedder/reranker; `DecisionForm` mapping for each kind into the correct `ApprovalResolution` and `customer_reason`; error cases (Review Focus 3); card shows the `DONE` dispatch row after an approved decision seeded via the real `ApprovalService`; runtime start with an approved-but-unsettled row (resolve without settle, then build runtime on a fresh connection) leaves the row settled with one notice and one `simulated_actions` row (Review Focus 5).
- [ ] **Step 2:** Run, expect failure.
- [ ] **Step 3:** Implement. `DecisionForm` validation lives in the model (a validator), not in app code.
- [ ] **Step 4:** Run tests, expect pass.
- [ ] **Step 5:** Cleanup: ruff, pyright, unused code, imports at top.
- [ ] **Step 6:** Commit.

### Task 2: Reviewer app, board and approvals

**Files:**
- Create: `ui/reviewer_app.py`, `tests/ui/test_reviewer_board.py`, `tests/ui/test_reviewer_decisions.py`

**Interfaces:**
- Consumes: plan 01 `BoardRow`, `CaseView`; Task 1 runtime and `DecisionForm`; 32 `DecisionResult`, `ApprovalStateError`, `SettleOutcome`; 41 `render_trace_panel`.
- Produces: Streamlit entry script runnable as `streamlit run ui/reviewer_app.py`. Functions (each one concern): `render_board`, `render_escalated_tab`, `render_context`, `render_evidence`, `render_approvals`, `render_live_trace`, `render_model_messages` (Task 3), `main`.

- [ ] **Step 1:** Failing `AppTest` tests: board lists pending-first with tier and age; escalated tab lists conversations flagged by `oncall_paged` or `escalation_offered` with separate badges; selecting a row sets the `conversation_id` query param; context panel shows SLA countdown and repeat alert; evidence tab shows raw values, anomaly marks, unavailable tools, link chart per link, KB scores; escalated tab has no buttons; approve, edit and reject paths through real `ApprovalService` (status, `reviewer_notes`, `edited_payload`, `customer_reason` persisted, customer notice present, `DONE` dispatch shown); Review Focus 1 and 2 (second decide shows already-resolved; forced `BUSY` shows "decision saved" message).
- [ ] **Step 2:** Run, expect failure.
- [ ] **Step 3:** Implement the script. Board and live trace as `st.fragment` with the intervals above; query-param driven selection; after any decision, re-read `get_approval` and `list_simulated_actions`; errors rendered via `st.error` with the service message verbatim.
- [ ] **Step 4:** Run tests, expect pass.
- [ ] **Step 5:** Cleanup: ruff, pyright, unused code, no duplicated trace code, file size cap.
- [ ] **Step 6:** Commit.

### Task 3: Live trace, resilience, packaging

**Files:**
- Modify: `ui/reviewer_view.py` (add `ModelMessagesView.from_replay`), `ui/reviewer_app.py` (add `render_model_messages`), `pyproject.toml` (only if 41 has not added `streamlit`), `Dockerfile` (same), `docker-compose.yml` (service `reviewer`, own port, `streamlit run ui/reviewer_app.py`, same env as `app`), `README.md` (one line in Reviewer Quickstart), `docs/architecture/system-architecture-design.md` (layout: `ui/reviewer_view.py`, `ui/reviewer_session.py`, `StateStore.list_board_rows`)
- Create: `tests/ui/test_reviewer_resilience.py`

- [ ] **Step 1:** Failing `AppTest` tests: model-messages expander per step shows redacted messages from `TraceRecord.model_messages` and "not recorded" for a null one, and the customer-visible page code path never imports it; turn interrupted mid-run renders open steps via shared trace panel and totals equal summed trace rows; conversation with no triage/diagnostics output renders all panels with no-data states and `UNAVAILABLE` tool visible; unknown `conversation_id` shows "not found" (Review Focus 4); SC-08 PSK never in rendered text.
- [ ] **Step 2:** Run, expect failure where behavior is missing.
- [ ] **Step 3:** Implement fixes; add packaging edits (merge with 41's edits, do not duplicate dependency lines or services).
- [ ] **Step 4:** Run `tests/ui tests/storage tests/orchestration`; bring up compose reviewer service and load the page once (manual smoke, record result in commit message).
- [ ] **Step 5:** Cleanup, final: ruff, pyright standard on all new files, no unused imports/functions, no leftover fallback code, no Braintrust references, docs references fixed.
- [ ] **Step 6:** Commit.

## Self-Review

- Coverage: §6 layout (Tasks 2-3), §6.1 (Tasks 1, 3), §7 flow (Tasks 1-2), §9 coupling (header prerequisites), §10 cleanup (Task 3).
- Types: `DecisionForm`, `CaseView.from_rows(..., actions, ...)` signature change is introduced in Task 1 and used in Task 2.
