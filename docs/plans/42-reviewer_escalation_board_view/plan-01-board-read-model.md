# 42 / Plan 01 — Board Read Model & Case View Builders — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A Streamlit-free read model: one new board-list query and pure frozen view models that turn existing store rows into the Context, Evidence and Approval-card panels.

**Architecture:** (no migration of ours; reads `messages.result` added by `20261002_1000_message-result.sql`) `StateStore.list_board_rows` (SQL in `storage/board_queries.py`, same split as `approval_queries.py`) plus `ui/reviewer_view.py` with `CaseView.from_rows`. Everything else is reuse: `rehydrate`, `replay_trace`, `CustomerService.lookup_account`, `TicketService.get_ticket_history`, existing agent output models validated from trace `output`. No migration, no UI dependency, no 31/32/41 dependency.

**Tech Stack:** Python 3.12, psycopg 3, Pydantic v2, pytest. No LLM calls; no Braintrust (PydanticAI-native traces already in `traces` rows).

**Spec:** [design.md](design.md) §2, §4, §5, §6.1; prerequisites: designs 21-24 merged (they are on this branch).

## Global Constraints

- Sync, fully typed (every parameter and return), imports at top, f-strings, `StrEnum` for enums, frozen Pydantic models, conversions as classmethods on the target class (no `format_x` functions).
- Timestamps passed in (`now: AwareDatetime` from `SimulationClock`); builders never read a clock, never do I/O.
- Reuse, do not rewrite: `storage.sql.fetch_all` / `class_row` mapping, `storage.models.*`, `agents.models` (`TriageResult`, `DiagnosticEvidence`, `KnowledgeBundle`, `AgentRole`, `TraceStatus`; `AgentRole` now lives there, not in `storage.models`), `retrieval.models.KBSearchResult`, `tools.models.LinkQualityPayload` / `LinkMetricsSummary` / `TelemetryEvidence`, `services.models.SLADeadlines` / `RepeatContactResult`.
- Functional tests on real Postgres via `tests/storage/conftest.py` fixtures; conversations seeded by the existing `Workflow` + scripted agents harness (`tests/orchestration/conftest.py`). Unit test only for SLA state thresholds.
- `ui/reviewer_view.py` stays under ~250 lines; if it grows, split panels into `ui/reviewer_panels.py` by panel, not by layer.
- No `ApprovalCard.dispatch` here (needs 31); added in plan 02.

## Review Focus

1. Conversation with no triage/diagnostics/knowledge trace (partial failure): every panel returns its explicit no-data state. -> Task 2.
2. Trace `output` that no longer validates (schema drift): panel falls back to no-data, no exception. -> Task 2.
3. Newest role trace has status ERROR / null output: older OK trace is used. -> Task 2.
4. Ticket statuses `pending_customer` / `pending_approval` count as open; `closed` does not. -> Task 2.
5. `state` jsonb missing `data`, or `messages.result` null/malformed: flags false, board still lists the row; null-result event message does not hide `escalation_offered`. -> Task 1.

---

### Task 1: Board list query

**Files:**
- Create: `storage/board_queries.py`, `tests/storage/test_board_rows.py`
- Modify: `storage/models.py` (add `BoardRow`), `storage/state_store.py` (add `list_board_rows`), `storage/__init__.py` (export `BoardRow`)

**Interfaces:**
- Consumes: `fetch_all` from `storage/sql.py`; tables `conversations`, `approvals`.
- Produces: `BoardRow` (frozen: `conversation_id: UUID`, `account_id: str | None`, `customer_tier: AccountTier`, `stage: ConversationStage`, `pending_count: int`, `oldest_pending_at: AwareDatetime | None`, `updated_at: AwareDatetime`, `oncall_paged: bool`, `escalation_offered: bool`); `StateStore.list_board_rows(limit: int) -> list[BoardRow]`.

- [ ] **Step 1:** Write failing functional test: three conversations (two with pending approvals of different `requested_at`, one with only a resolved approval, one paged via state snapshot flag) created through `StateStore`; assert order is pending-first by oldest pending, then `updated_at` desc; counts exclude resolved; `oncall_paged` true only for the flagged one; `limit` respected; a conversation whose `state` has no `data` key reports false; a conversation whose newest reply result has `escalation_offered` true is flagged, a later reply without it clears it, and a later null-result event message (AGENT, as 32 writes) does not clear it; a conversation with a malformed `result` stays false. Approvals in tests are created with a customer message of the same conversation (composite FK `message_id, conversation_id`).
- [ ] **Step 2:** Run the test, expect failure (method missing).
- [ ] **Step 3:** Add `BoardRow`. In `board_queries.py` add one module function taking the connection and limit: single SELECT over conversations left-joined to an aggregate of PENDING approvals (count, min `requested_at`), `oncall_paged` read from the state jsonb path data -> oncall_paged and `escalation_offered` read from the newest non-null `messages.result` per conversation (highest turn, lateral or aggregate subquery), both coalesced to false, ordered as specified. `StateStore.list_board_rows` delegates in one line (as approval methods do).
- [ ] **Step 4:** Run test, expect pass; run `tests/storage` fully.
- [ ] **Step 5:** Cleanup: ruff, pyright, no unused imports or functions; confirm the pending partial index is used (EXPLAIN once, no new index).
- [ ] **Step 6:** Commit.

### Task 2: `CaseView` builders

**Files:**
- Create: `ui/__init__.py` (only if 41 has not created it; otherwise leave), `ui/reviewer_view.py`, `tests/ui/__init__.py`, `tests/ui/conftest.py` (seed helpers), `tests/ui/test_case_view.py`, `tests/ui/test_sla_state.py`

**Interfaces:**
- Consumes: `ConversationSnapshot`, `TraceReplay`, `CustomerAccount | None`, `Sequence[Ticket]`, `now: AwareDatetime`; `Approval`.
- Produces (all frozen, StrEnum for `SlaState`): `SlaState` (OK, AT_RISK, BREACHED, PAUSED); `SlaCountdown`; `RepeatAlert`; `TicketRow`; `ContextPanel`; `LinkChart`; `PassageScore`; `EvidencePanel`; `ApprovalCard`; `CaseView` with classmethod `from_rows(snapshot, replay, account, tickets, now) -> CaseView`. Field lists exactly as design §5 minus `dispatch`.

- [ ] **Step 1:** Write `tests/ui/conftest.py`: helper that runs one SC-03-style turn (credit proposal pending, repeat contact, anomalous telemetry evidence, one link-quality tool call, one KB search tool call with scores) through the existing scripted `Workflow` harness on a frozen `SimulationClock`, returning the conversation id; a second helper for a degraded turn (no triage/diagnostics output, telemetry UNAVAILABLE).
- [ ] **Step 2:** Write failing functional tests in `test_case_view.py` for Review Focus 1-4 and the happy path: context tier/account/SLA remaining from the frozen clock, repeat alert reason and ticket ids, open tickets exclude `closed`; evidence items with raw value and anomaly flag, unavailable tools listed, link charts per link from `get_link_quality` result, KB passages with `rrf_score` / `rerank_score` / `citation_tag`; approval card `can_resolve` true for PENDING, false after resolution via `StateStore.resolve_approval` (test setup only). Add the PSK case: SC-08 text never appears in any `CaseView` field dump.
- [ ] **Step 3:** Write `test_sla_state.py`: thresholds (more than 25% of window left = OK, at or under = AT_RISK, past due = BREACHED, paused flag = PAUSED). The only unit test.
- [ ] **Step 4:** Run, expect failures.
- [ ] **Step 5:** Implement `ui/reviewer_view.py`. One private helper `_latest_ok_output(replay, role, model_type)` returning the validated model or `None` (newest OK trace with output, `ValidationError` -> `None`); every panel classmethod calls it, so the fallback logic exists once. `ContextPanel.from_*`, `EvidencePanel.from_*`, `ApprovalCard.from_approval` as classmethods; `CaseView.from_rows` only composes them. No branching ladders: each panel builds from its own optional source.
- [ ] **Step 6:** Run tests, expect pass; run `tests/storage tests/orchestration` for regressions.
- [ ] **Step 7:** Cleanup: ruff, pyright standard, no unused imports/functions, no inline imports, file under size cap; confirm no Streamlit import in the module.
- [ ] **Step 8:** Commit.

## Self-Review

- Spec coverage: §4 (Task 1 and Task 2 consume), §5 panels (Task 2), §6.1 best-effort and SLA pause rules (Task 2). Streamlit, decision form, session, dispatch, docker: plan 02.
- Types: `BoardRow` and `CaseView` names match plan 02 consumers.
