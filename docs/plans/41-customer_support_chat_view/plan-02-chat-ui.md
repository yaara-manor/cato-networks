# Customer Chat UI Implementation Plan (Plan 2 of 2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A Streamlit customer chat with citation badges, telemetry chips, approval banners, scenario switcher and a trace panel (shared with 42).

**Architecture:** Pure frozen view models (`ui/chat_view.py`, `ui/trace_panel.py`) built from `ConversationSnapshot`, `Approval` rows and `TraceReplay`; thin Streamlit scripts render them; `ui/session.py` opens one connection per call and uses plan 01's `build_workflow`. Tests drive the app with Streamlit's own `AppTest`.

**Tech Stack:** Python 3.12, Streamlit (only new dependency), pydantic frozen models, PydanticAI agents via `build_workflow` (no Braintrust, no extra tracing), psycopg 3, pytest.

**Spec:** [design.md](design.md) sections 3, 4, 6, 8. Depends on plan 01 and on 31/32 for approval flows (use `ApprovalService.resolve/settle` in tests; if 32 is not merged, seed approval rows via `StateStore.create_approval/resolve_approval` and a hand-inserted AGENT message, and mark the settle test skipped with reason).

## Global Constraints

- Full typing, Pyright `standard`, ruff, top-level imports, f-strings, `StrEnum`, frozen models, classmethods not `format_x`, no `datetime.now`, no `unsafe_allow_html`, exhaustive `match` with `assert_never` on enums, never read `.env`.
- Functional `AppTest` tests on real Postgres with scripted agents; one pure parametrized unit test (`ChatView.from_snapshot`) only.
- Commit per task; never merge, never push.

## Review Focus

1. Customer page never contains `reviewer_notes`, `edited_payload`, payload amounts or ticket status. -> Tasks 2, 3.
2. Garbage/unknown `conversation_id` in query params starts a fresh conversation, no crash. -> Task 3.
3. Retry after `TurnLockTimeout` reuses the `message_id`: one customer row. -> Task 3.
4. Message text with HTML/markdown from the customer or agent cannot inject markup. -> Task 3.
5. Reply with zero citations/evidence renders cleanly; very long reply and 50+ messages render. -> Task 3.

---

### Task 1: Dependency, scenarios, chat view models

**Files:**
- Modify: `pyproject.toml` (add `streamlit`; lockfile via `uv lock`)
- Create: `ui/__init__.py`, `ui/scenarios.py`, `ui/chat_view.py`
- Test: `tests/ui/test_chat_view.py`, `tests/ui/test_scenarios.py`

**Interfaces:**
- Consumes: `ConversationSnapshot`, `Approval`, `StoredMessage` (21, plan 01 citation rows: `kind, ref, title, url`), `strip_markers` (plan 01), `MessageSender`, `ApprovalStatus`, `ActionType`, `Approval.settled_at` (32).
- Produces: `Scenario` + `load_scenarios(path: Path) -> tuple[Scenario, ...]`; `BadgeKind`, `CitationBadge`, `EvidenceChip`, `MessageView`, `ApprovalBannerState` (PENDING, FINALIZING, APPROVED, REJECTED), `ApprovalBanner`, `ChatView` with `ChatView.from_snapshot(snapshot: ConversationSnapshot, approvals: Sequence[Approval]) -> ChatView`. Banner title derived from `ActionType` only (exhaustive match); payload never read. Evidence chips deduped by (tool, metric, value).

- [ ] **Step 1:** Failing tests: scenarios loader returns 12 entries from `data/eval/scenarios.jsonl`; one parametrized `from_snapshot` check covering marker stripping, customer vs support role (any non-customer sender), chip dedupe, each approval status/`settled_at` combination mapping.
- [ ] **Step 2:** Run; expect FAIL.
- [ ] **Step 3:** Add dependency, implement modules.
- [ ] **Step 4:** Run `uv run pytest tests/ui -v`; expect PASS.
- [ ] **Step 5:** Cleanup: ruff + pyright on `ui`; no unused field (every view field is rendered in Task 3).
- [ ] **Step 6:** Commit `feat(ui): chat view models and scenarios`.

---

### Task 2: Shared trace panel (used by 42)

**Files:**
- Create: `ui/trace_panel.py`
- Test: `tests/ui/test_trace_panel.py`

**Interfaces:**
- Consumes: `TraceReplay`, `ReplayStep`, `TraceRecord`, `ToolCallRecord` (21 `replay.py`).
- Produces: frozen `TracePanel`, `TraceTurn`, `TraceStep` (shapes per 42 design: per turn customer/reply text, steps with role, status, latency, tokens, cost, tool calls, redacted input/output, open flag, totals); `TracePanel.from_replay(replay: TraceReplay) -> TracePanel` (uses turns and steps only, never `replay.approvals`); `render_trace_panel(panel: TracePanel) -> None` (Streamlit, `st.expander` per turn, text via `st.code`/`st.text`). Tell 42 to import this module and delete its own copy; no other module defines trace view models.

- [ ] **Step 1:** Failing `AppTest` test: seed a conversation via scripted turn, render a tiny script calling `render_trace_panel`; assert each agent step and totals visible; assert a seeded approval with reviewer note does not appear.
- [ ] **Step 2:** Run; expect FAIL.
- [ ] **Step 3:** Implement models and renderer.
- [ ] **Step 4:** Run the file; expect PASS.
- [ ] **Step 5:** Cleanup: ruff + pyright; confirm no duplicate of 42's models exists (grep sibling worktree).
- [ ] **Step 6:** Commit `feat(ui): shared trace panel`.

---

### Task 3: Session glue and customer app

**Files:**
- Create: `ui/session.py` (cached `warm_models`; `connection()` context manager yielding a fresh autocommit connection; `run_customer_turn(conversation_id, text, message_id) -> TurnResult` building `StateStore` and `build_workflow` on that connection), `ui/customer_app.py`
- Test: `tests/ui/test_customer_chat_flow.py`

**Interfaces:**
- Consumes: plan 01 `build_workflow`, `warm_models`; `CustomerService.authenticate_caller`; `StateStore.create_conversation/rehydrate/list_approvals/replay_trace`; `RetrievalService.get_policy`; Task 1 and 2 models; `TurnLockTimeout`, `StateVersionError`.
- Produces: runnable `streamlit run ui/customer_app.py`. Behavior: sidebar scenario select + email field + "new conversation" (identity via `authenticate_caller`, no tier/account claim inputs); "load opening message" prefills the input; transcript with citation badges (KB as link buttons to `url`, policy as button opening an `st.dialog` with the policy body), evidence chips (anomaly styled), banners fragment polled every 5 s with rerun on state change, trace expander via Task 2; `conversation_id` mirrored to query params; pending `message_id` held in session state until the turn returns; fixed notices for lock timeout (retry reuses id) and state-version error; spinner only; input stays enabled during pending approvals.

- [ ] **Step 1:** Write failing `AppTest` tests (scripted ports injected through a test seam: `ui/session.py` accepts an optional ports factory via a module-level setter used only by tests): scenario pick + send + reply; second turn sees history; reload with `conversation_id` restores; garbage id starts fresh; citations/chips render; CREDIT proposal shows PENDING banner titled by action only, amount absent, input enabled; resolve and settle flips banner and shows the AGENT notice; REJECTED with `customer_reason`; lock timeout then retry gives one customer row; HTML in a message is escaped; trace expander lists the turn.
- [ ] **Step 2:** Run; expect FAIL.
- [ ] **Step 3:** Implement session and app; keep `customer_app.py` rendering-only (small functions per widget group, no SQL, no parsing; split into `ui/customer_widgets.py` if it passes about 150 lines).
- [ ] **Step 4:** Run `uv run pytest tests/ui -v`; expect PASS.
- [ ] **Step 5:** Cleanup: ruff + pyright on `ui`; no unused imports/functions/session keys; grep no `unsafe_allow_html`, no `datetime.now`, no inline imports.
- [ ] **Step 6:** Commit `feat(ui): customer support chat app`.

---

### Task 4: Packaging and docs

**Files:**
- Modify: `Dockerfile` (add `streamlit` to the explicit pip list), `docker-compose.yml` (UI service/command `streamlit run ui/customer_app.py`), `README.md` (run line), `docs/architecture/system-architecture-design.md` (UI section; fix `[telemetry]` to `[telemetry:<tool>]`), `docs/overview/decisions.md` (next ADR: Streamlit; citations persisted at write time; banners derived from approvals; query-param conversation id is demo-only)

- [ ] **Step 1:** Make the edits; `streamlit` appears once per file.
- [ ] **Step 2:** Run `docker compose config` (syntax only) and the full `uv run pytest tests/ui tests/orchestration tests/guardrails -v`.
- [ ] **Step 3:** Final cleanup over the whole branch: ruff and pyright on touched dirs; grep for unused functions/constants/imports, duplicated regexes, `Literal` enums, `format_*` helpers, leftover `Braintrust` mentions.
- [ ] **Step 4:** Commit `docs: ui packaging and ADR`.
