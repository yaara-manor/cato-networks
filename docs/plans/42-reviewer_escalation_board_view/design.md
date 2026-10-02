# Phase 4.2: Support Reviewer & Escalation Board View — Design Specification

**Issue**: `#12` ([Phase 4] 4.2: Support Reviewer & Escalation Board View)
**Date**: 2026-10-02
**Implementation**: [plan-01](plan-01-board-read-model.md) (needs 21-24 only), [plan-02](plan-02-reviewer-app.md) (needs 31, 32, 41).
**Status**: Draft for Review (final user decisions applied; aligned with final 31/32 designs)
**Depends on**: 21 (`StateStore`, `replay_trace`, approvals), 22 (`TriageResult`, `DiagnosticEvidence`, `KnowledgeBundle` in trace `output`), 23/24 (turn path, locking), 31 (action dispatcher, issue #9), 32 (approval lifecycle + resume, issue #10), 41 (customer chat, issue #11). Aligned with the final 32 (`ApprovalService.resolve` + `settle`) and 31 (`simulated_actions`, `list_simulated_actions`); 41 owns the shared trace component and `ui/session.py`.
**Target Files**: `ui/reviewer_app.py`, `ui/reviewer_view.py`, `ui/reviewer_session.py` (glue over 41's `orchestration/runtime.py`), `ui/trace_panel.py` (imported from 41, not modified), `ui/session.py` (41, read-only reuse), `storage/board_queries.py`, `storage/state_store.py` (one new read method), `storage/models.py` (one new row model), `pyproject.toml`, `docker-compose.yml`, `Dockerfile`, `tests/ui/*`, `tests/storage/test_board_summaries.py`

---

## 1. Objective & Scope

Deliverable B, reviewer half: one page where a support reviewer sees every conversation waiting on a human, inspects why the agent proposed an action, and approves / edits / rejects it with a logged note. Four panels from the ticket:

1. **Customer Context**: account id, tier, SLA countdowns, repeat-contact alert, open tickets.
2. **Telemetry & Evidence Inspector**: quoted tool outputs, raw metric values, link-quality charts.
3. **Pending Approvals Queue**: approve / edit / reject with `reviewer_notes`.
4. **Live Trace Viewer**: per-agent-step breakdown with latency, tokens, cost, retrieval scores, tool calls.

The view is a **pure read-model over Postgres plus one write path** (resolve approval). It holds no state of its own: closing the tab loses nothing (task: "approval lives in storage, not in memory").

```mermaid
flowchart LR
    Rev["Reviewer browser"] --> App["ui/reviewer_app.py (Streamlit)"]
    App --> View["ui/reviewer_view.py\npure builders: CaseView.from_*"]
    View --> SS["StateStore\nrehydrate / replay_trace / list_board_rows"]
    View --> Svc["CustomerService / TicketService\n(account, open tickets)"]
    App -- "approve / edit / reject" --> Life["ApprovalService.decide (issue #10)"]
    Life --> SS
    SS --> PG[("Postgres: conversations, approvals,\ntraces, tool_calls, messages")]
    Cust["Customer chat (41)"] --> SS
```

**Out of scope**: customer chat (41); the shared trace component itself (41); approval policy, resume, customer notification, action execution (32 / 31); auth / reviewer identity; async API or websockets; editing traces; new tables or migrations; eval harness.

---

## 2. Divergences: Ticket vs Code

| Ticket says | Code / sibling designs say | Decision |
|---|---|---|
| `ui/reviewer_app.py` only | Arch §10 layout also lists `ui/customer_app.py`; no `ui/` exists, no UI dependency in `pyproject.toml` | Add Streamlit; split render (`reviewer_app.py`) from pure builders (`reviewer_view.py`) so logic is testable without a browser |
| SLA countdowns, repeat-contact alerts | Not persisted as columns. `TriageResult.sla: SLADeadlines` and `.repeat_contact: RepeatContactResult` live in the triage trace `output` (22) | Read from latest `TRIAGE` trace of the conversation; countdown computed in view against `SimulationClock.now()` (ADR-001), never wall clock |
| "Open tickets" | `TicketService.get_ticket_history(account_id)` returns all; `include_open=False` filters `status != 'open'` (no unresolved-only mode); "open" must also cover `pending_customer` / `pending_approval` | Fetch history, keep every status except `closed` (`open`, `pending_customer`, `pending_approval`; `TicketStatus` is a `Literal` of those four) in the builder; no service change |
| "Retrieval scores" | 21 design had `traces.retrieval_scores`; shipped schema dropped it. Scores (`rrf_score`, `rerank_score`, ranks) sit inside KB-search `tool_calls.result` (`KBSearchResult.passages/candidates`) and in `KnowledgeBundle` in the `KNOWLEDGE` trace output | Read from tool calls; no schema change |
| "Link quality graphs" | `get_link_quality` returns `LinkMetricsSummary` aggregates per link (avg/max/latest loss, latency, jitter, throughput, `down_intervals`), not a time series | Chart = per-link bar charts of these aggregates over the returned window. True time-series needs a telemetry API change: open question |
| "Quoted tool outputs, raw metric values" | `TelemetryEvidence(tool_name, metric_key, raw_value, timestamp, is_anomaly)` on `StoredMessage.telemetry_evidence` and in `DiagnosticEvidence.evidence_items`; raw envelope in `tool_calls.result` | Evidence table from `evidence_items` (open turn included, before any reply exists); raw JSON expander from `tool_calls.result` |
| "Token consumption" | `traces.prompt_tokens/completion_tokens/cost_usd` | Direct |
| "Note logging" | `approvals.reviewer_notes`, `edited_payload` exist; `MessageSender` has no `REVIEWER` | Decided: notes live only on the approval row; no reviewer sender, no `resolved_by` |
| Escalation Board across conversations | `StateStore.list_pending_approvals(None)` exists; `list_conversations` was dropped in 21 plan-01 delta 4 | Add one summary read (§4) instead of N+1 `get_conversation` calls; board = pending approvals plus a small read-only tab of escalated/paged conversations |
| Resolve via `StateStore.resolve_approval` | Raw store call only flips the row. Final 32: `ApprovalService.decide(ReviewerDecision) -> DecisionResult` (single UI entry point; runs `resolve` CAS then `settle`: execute via #9, clear ticket, notify customer) | UI calls only `decide`, `list_pending`, `get_approval`; never the store directly (§7) |
| "Note logging" for the customer | 32 adds `ReviewerDecision.customer_reason` (optional, customer-safe, guard-checked) beside internal `reviewer_notes` | Two fields in the form: internal note, optional customer reason (reject only) |
| Dispatch outcome | 31 `simulated_actions` + `StateStore.list_simulated_actions(conversation_id)` | Shown on resolved approval cards (key `approval:{approval_id}`) |
| Enums via `AtiIntEnum` | Repo uses `StrEnum` everywhere (ADR-005); `novia_shared` not a dependency | Decided: `StrEnum` |

---

## 3. Approaches Considered

**A. Streamlit multi-panel app, direct in-process `StateStore` (chosen).** One Python file tree, same sync psycopg stack as every other layer, `st.fragment(run_every=...)` for live trace polling, `st.dataframe` / `st.bar_chart` cover tables and charts, `streamlit.testing.v1.AppTest` gives functional tests with no browser. Fits "any stack" in the task and the compose-up-in-10-minutes goal.
**B. FastAPI + JS SPA.** Best UX control, but needs an API layer (async wrapper around sync store, serializers, auth), a JS toolchain in Docker, and a second test stack. Most of the effort (80%) would go to plumbing the task does not grade. Rejected (YAGNI).
**C. Gradio.** Weak for master-detail layouts and per-row action buttons. Rejected. Stack is shared with 41 (Streamlit, confirmed).

Decision: A. Panels render from one frozen `CaseView` so swapping the front end later touches only `reviewer_app.py`.

---

## 4. Data Access (no migration)

All reads reuse existing store methods; one new read.

- **Board list (new)**: `StateStore.list_board_rows(limit: int) -> list[BoardRow]`, SQL in new `storage/board_queries.py` (same split as `approval_queries.py`). One query over `conversations` left-joined to a count of `approvals` with `status = 'PENDING'` and the oldest pending `requested_at`. Ordered pending-first, oldest pending first, then `updated_at desc`. Uses the existing partial index on pending approvals; no new index.
- **`BoardRow`** (frozen, in `storage/models.py`): `conversation_id`, `account_id`, `customer_tier`, `stage`, `pending_count`, `oldest_pending_at`, `updated_at`, `oncall_paged`.
- **Case detail**: `rehydrate(conversation_id)` for identity/messages/pending approvals, `replay_trace(conversation_id)` for turns/steps/tool calls/all approvals (single consistent-read snapshot each). Resolved approvals are included in replay, so the queue can show history.
- **Account + tickets**: `CustomerService.lookup_account(account_id)` (company), `TicketService.get_ticket_history(account_id)`.
- **Escalated/paged tab**: `list_board_rows` also carries `oncall_paged`, read from `conversations.state` (`StateSnapshot.data`, field `OrchestratorState.oncall_paged` in `orchestration/state.py`, confirmed in code and 31 §state update). `escalation_offered` is NOT persisted (only a `TurnResult` field, 31 sets it on failed actions), so it is not used; failed-action escalations are visible as `FAILED` rows via `list_simulated_actions` on the case detail. Tab = conversations with `oncall_paged` true.
- **Dispatch result**: `StateStore.list_simulated_actions(conversation_id)` (31); matched to an approval by `approval_id`.
- No writes besides `ApprovalService` calls.

---

## 5. Contracts (`ui/reviewer_view.py`)

Pure functions/classmethods, all frozen Pydantic, no Streamlit import, no I/O. Conversion lives on the target class (user rule).

- **`CaseView`**: `conversation_id`, `context: ContextPanel`, `evidence: EvidencePanel`, `approvals: tuple[ApprovalCard, ...]`; trace is rendered by the shared component from the same `TraceReplay`. Classmethod `from_rows(snapshot: ConversationSnapshot, replay: TraceReplay, account: CustomerAccount | None, tickets: Sequence[Ticket], actions: Sequence[SimulatedAction], now: AwareDatetime) -> CaseView`. `now` is passed in (from `SimulationClock`), keeping it deterministic.
- **`ContextPanel`**: `account_id`, `company`, `tier`, `contact_email`, `sla: tuple[SlaCountdown, ...]`, `repeat_contact: RepeatAlert | None`, `open_tickets: tuple[TicketRow, ...]`. `SlaCountdown`: `label` (first response / resolution), `due_at`, `remaining: timedelta`, `state: SlaState` (`OK`, `AT_RISK` under 25% of window left, `BREACHED`); `resolution_paused` shown as such. `RepeatAlert`: `reason`, matching ticket ids, prior closed ids. Both come from the latest `TRIAGE` trace's `TriageResult`; absent triage -> `None` (shown as "not triaged yet", never an empty-looking OK).
- **`EvidencePanel`**: `evidence: tuple[TelemetryEvidence, ...]` (from `DiagnosticEvidence.evidence_items` of the newest `DIAGNOSTICS` trace, falling back to reply messages), `unavailable_tools` (so an outage is visible, not silent), `link_charts: tuple[LinkChart, ...]` (per-link metrics built from `get_link_quality` tool-call results via `LinkMetricsSummary.model_validate`), `raw_calls: tuple[ToolCallRecord, ...]`, `kb_passages: tuple[PassageScore, ...]` (`citation_tag`, `rrf_score`, `rerank_score`, `lex_rank`, `vec_rank`, and whether it was cited vs candidate-only), `kb_status: KBSearchStatus`.
- **`ApprovalCard`**: `approval: Approval` (incl. `customer_reason`, `settled_at` from 32; fetched via `ApprovalService.list_pending` / `get_approval`), `action_label`, `proposing_turn`, `evidence_refs` (evidence items of the proposing turn), `can_resolve: bool` (status is `PENDING`), `dispatch: SimulatedAction | None` (from `list_simulated_actions`, status `DONE` / `FAILED` / `INVALID` / `REFUSED`; `None` while unsettled or on reject).
- **Trace panel**: imported from `ui/trace_panel.py` (owned by 41): `TracePanel`, `TraceTurn`, `TraceStep`, `TracePanel.from_replay(replay: TraceReplay)`, `render_trace_panel(panel, ...)`. 42 defines no trace models and no trace rendering; it passes the `replay_trace` result through `from_replay`. 41's shapes already include redacted input/output and the open-turn flag.
- **Decision form**: no 42 decision model. `DecisionForm.to_decision() -> ReviewerDecision` (in `ui/reviewer_view.py`) builds 32's `ReviewerDecision(approval_id, resolution: ApprovalResolution, customer_reason: str | None)`: `ApprovalResolution(status=APPROVED)`, `(status=EDITED, edited_payload=...)` or `(status=REJECTED, reviewer_notes=...)`. UI-only checks before calling: note required on reject, edited keys equal original keys. Result type is 32's `DecisionResult(approval, settle: SettleOutcome)`.

Rendering rules: `trace.input`/`model_messages` are already redacted at store write (21 §2.6); the view displays them as stored and never re-reads customer raw text. Reply/evidence text is shown through `st.code`/`st.text` (no HTML injection from customer-influenced strings; `unsafe_allow_html` never enabled).

---

## 6. App Layout (`ui/reviewer_app.py`)

Thin Streamlit script, no business logic beyond wiring.

- **Sidebar, Escalation Board**: two tabs. `Pending` (main): list from `list_board_rows`, each row: account, tier, pending badge, oldest pending age. Selecting sets `conversation_id` in `st.query_params` (shareable link, survives refresh). `Escalated` (read-only): conversations with `oncall_paged` or `escalation_offered`, no actions. Auto-refresh every 3 s via `st.fragment(run_every=3)` so new approvals appear in a live demo.
- **Main, tabs for the selected conversation**: `Context` (panel 1) above `Pending approvals` (panel 3); `Evidence` (panel 2); `Live trace` (panel 4). Context and approvals stay visible at the top because they drive the decision; evidence/trace are tabs.
- **Pending approvals card**: action type, payload table, proposing-turn evidence, note box. Fields: internal note (`reviewer_notes`, never shown to customer) and optional customer reason (becomes `customer_reason`, shown to customer after guard check). Buttons: Approve; Reject (note required); Edit opens a form pre-filled with `payload` (same keys only, values editable), submit = EDITED. Edited payloads are re-validated inside 32's `resolve` (`check_action` plus same-key-set check, final 32); a rejection of the edit surfaces as an inline error. Resolved cards show the settle outcome and the dispatch result. After click the card shows the resolved state from the DB, not optimistic UI.
- **Live trace** (`ui/trace_panel.py`): fragment polling `replay_trace` every 2 s while the selected conversation's stage is not `IDLE` (a turn is in flight; recorder writes a trace per step so rows appear incrementally), else static. The open turn's steps carry `is_open` and show "running" when a role has no `OK` trace yet.
- **Errors surfaced, not swallowed**: `ApprovalStateError` from `decide` (unknown id, already resolved by another reviewer, edit that changes/drops `ticket_id`, unsafe `customer_reason`) -> shown to the reviewer verbatim, no retry, card refreshes; `DecisionResult.settle != SETTLED` (`BUSY`, `EXECUTION_FAILED`) -> card shows "decision saved, customer notice pending" (the sweep finishes it), never an error implying the decision was lost; DB unreachable -> board banner, panels keep last good render. Missing triage/diagnostics/knowledge traces render explicit "no data" states per panel (partial failure from 23 means any role may be absent).

`ui/reviewer_session.py` (new, thin): `build_reviewer_runtime()` cached with `st.cache_resource` (config and service constructors only), see §6.1. Building it once at process start is the "app lifespan" of 32: it calls `ApprovalService.settle_unsettled()` once there. No timer. One autocommit connection per session; no pool.

### 6.1 Resilience rules (found while planning)

- **Trace-derived panels are best-effort.** Triage/diagnostics/knowledge data are read by `model_validate` of the trace `output` dict (`TriageResult`, `DiagnosticEvidence`, `KnowledgeBundle`). Pick the newest trace of the role with status `OK` and non-null `output`; a `ValidationError` (schema drift after a deploy) or no such trace yields the panel's explicit no-data state, never an exception that blanks the page.
- **Reuse 41's composition root, skip the heavy parts.** 41 final puts assembly in `orchestration/runtime.py` (`build_workflow(connection, clock)`, separate `warm_models()`; connections per call, only warm-up cached). The reviewer never runs agents, so `ui/reviewer_session.py` is thin glue: it never calls `warm_models()` (no embedder/reranker load) and never builds a `Workflow`. It needs a smaller entry from the same module. **Requested on 41's side:** `orchestration/runtime.py` exposes the service assembly (`CustomerService`, `TicketService`, `TelemetryService`, clock) as its own factory that `build_workflow` itself calls, and the factory must not construct `RetrievalService`/the LLM model or load models eagerly. If 41 keeps one monolithic `build_workflow`, fallback is calling it without `warm_models()` provided `RetrievalService` construction is lazy (to verify in 41 plan-01 Task 3). The reviewer adds only `ApprovalService` (imported from `services.approval_service`, never from `services/__init__.py`: import cycle with `actions`) on top; no duplicated connection or composition code.
- **Connections are per script run / fragment run, never cached.** Streamlit reruns and fragments execute on different threads; `StateStore` needs one autocommit connection per concurrent caller (24). Open with a context manager at the top of each render function; the cached resource holds only config and services' constructors, not live connections. Supersedes the earlier "one connection per session" line.
- **Stuck stage.** A crashed turn leaves stage non-`IDLE` (21 §5), so the live-trace fragment would poll forever. Acceptable (cheap read); the trace shows the last real step with its `is_open` marker so the reviewer can see it stalled.
- **SLA countdown while paused.** `resolution_paused` freezes the resolution countdown (shown as "paused"); `due_at` is already business-hours-adjusted by `calculate_sla_deadlines`, so remaining is plain `due_at - now`.

---

## 7. Approval Resolution Flow

1. Reviewer clicks a button; the app builds `ReviewerDecision` via `DecisionForm.to_decision` after UI checks.
2. App calls `ApprovalService.decide(decision) -> DecisionResult`, which runs `resolve` (CAS from PENDING; losing reviewer gets `ApprovalStateError`) then `settle` (execute via #9 `dispatch_approved` on approve/edit, clear ticket `pending_approval`, write customer notice under `turn_lock`). Decision is durable even if settle does not complete; runtime-start sweep finishes it.
3. UI renders from `DecisionResult.approval` and `.settle`, then re-reads `get_approval` and `list_simulated_actions`.
4. The UI never calls `resolve`/`settle` separately, never executes actions, never writes customer messages or `approvals` rows, never calls `StateStore.resolve_approval`.

Idempotency: replayed click -> `ApprovalStateError` or `ALREADY_SETTLED`; dispatcher key `approval:{approval_id}` makes re-execution impossible.

---

## 8. Testing (functional first)

Real Postgres via existing `tests/storage/conftest.py` fixtures; no mocks of the store. LLM never called: conversations are seeded by driving `Workflow.run_turn` with the existing fake `AgentPorts` from `tests/orchestration/conftest.py`.

- `tests/ui/test_reviewer_board.py` (`AppTest`): seed an SC-03-style credit proposal -> board lists it pending-first; open it -> context shows tier, SLA countdown from the frozen clock, repeat-contact alert; evidence tab shows quoted raw value and `is_anomaly`; unavailable telemetry tool shows as unavailable.
- Approve / edit / reject paths through the real `ApprovalService`: row status, `reviewer_notes`, `edited_payload`, `customer_reason` persisted; approve shows a `DONE` dispatch result from `simulated_actions`; customer notice message exists; reject without note refused; edit with an added key or a `check_action`-failing edit shows inline error; second resolve shows "already resolved" and leaves the first intact; resolve without settle then runtime restart sweeps it.
- Live trace: a conversation interrupted mid-turn (traces without reply) renders steps with `is_open`; completed turn shows totals equal to summed trace rows.
- Partial failure: conversation with no triage trace and a telemetry `UNAVAILABLE` still renders all panels with explicit no-data states.
- Secret safety: SC-08 PSK conversation: rendered page text never contains the PSK.
- `tests/storage/test_board_summaries.py`: `list_board_rows` ordering and counts across conversations with mixed approval states.
- Unit tests only for `SlaCountdown` state thresholds (isolated, date math).

---

## 9. Coupling to Parallel Designs

- **#10 (32, §5b)**: `ApprovalService.decide`, `list_pending`, `get_approval`, `settle_unsettled` (runtime start); `ReviewerDecision`, `DecisionResult`, `SettleOutcome`, `Approval.settled_at/customer_reason`. Final names used as-is.
- **#9 (31)**: `StateStore.list_simulated_actions`, `SimulatedAction` / `SimulatedActionStatus`. Read-only.
- **#11 (41)**: shared Streamlit stack, `ui/session.py`, and `ui/trace_panel.py` (imported, not duplicated). Separate processes, one DB.

---

## 10. Cleanup & Delivery

- `pyproject.toml`: add `streamlit`; `uv.lock` regenerated. `Dockerfile` (deps are pip-listed by hand, per 41)/`docker-compose.yml`: service `reviewer` running `streamlit run ui/reviewer_app.py` on its own port, same env as `app`; README reviewer-quickstart gets one line.
- Add arch §10 note: `list_board_rows`, `ui/reviewer_view.py`.
- Final step: lint/type pass on new code (every parameter/return typed, no unused imports/functions, imports at top, no `Literal` for enums).

---

## Decisions

1. Stack: Streamlit, shared with 41 (task allows any stack).
2. Resolve path: `ApprovalService.decide` (32 §5b); no `StateStore.resolve_approval` fallback; sweep runs once at reviewer runtime start.
3. Edited payloads re-validated by `check_action` inside 32.
4. No `resolved_by` column, no reviewer identity, no `REVIEWER` sender; internal `reviewer_notes` plus optional customer-safe `customer_reason`.
5. Link graphs: bar charts from `LinkMetricsSummary` aggregates; no telemetry API change.
6. Board: pending approvals main view plus small read-only escalated/paged tab.
7. SLA `AT_RISK` below 25% of window remaining.
8. Polling 2-5 s (board 3 s, live trace 2 s); no push.
9. `StrEnum` per repo convention.
10. Dispatch result shown from `simulated_actions` via `list_simulated_actions`.
11. Trace panel is `ui/trace_panel.py` from 41; 42 imports it and defines none.

## Open questions

1. Reviewer-only trace extras (raw input/output) needed beyond 41's `TracePanel` shape? Assumed no.
