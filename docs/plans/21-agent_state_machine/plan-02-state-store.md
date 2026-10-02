# 21 / Plan 02 — `StateStore`, Rehydration, Trace Replay, Docs — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A sync `StateStore` that persists conversations, messages, agent traces, tool calls and approvals in Postgres, rehydrates a conversation from its id alone after a restart, and replays the full conversation graph from trace rows alone.

**Architecture:** One class `storage/state_store.py::StateStore` over one autocommit `psycopg.Connection`; every write method is one `connection.transaction()` that first locks the conversation row (`SELECT ... FOR UPDATE`) so turn/seq counters, idempotent retries and stage updates serialize per conversation. Reads map rows straight into frozen Pydantic models with `psycopg.rows.class_row` (the pattern in `retrieval/service.py`). Replay assembly is a pure classmethod in `storage/replay.py`. Tracing is PydanticAI message history stored in `traces.model_messages` plus these tables; no Braintrust.

**Tech Stack:** Python 3.12, psycopg 3, Pydantic v2, pydantic-ai 2.51, pytest.

**Spec:** [design.md](design.md) §5, §6, §7, §8; prerequisite: [plan-01-schema-contracts.md](plan-01-schema-contracts.md) (schema, models, `to_jsonb`, `strip_nul`, fixtures `conn` / `new_conversation` / `restart`).

## Global Constraints

Same as plan 01 (sync, fully typed, no inline imports, f-strings, StrEnum, frozen models, timestamps passed in, no `now()`, no Braintrust, functional tests against real Postgres, verify with pytest/ruff/pyright).

- Reuse, do not rewrite: `psycopg.rows.class_row` (row mapping), `psycopg.types.json.Jsonb` via `storage/jsonb.py::to_jsonb`, `core.config.settings.database_url`, `core.clock.SimulationClock` (tests only; the store never reads it), `guardrails.models.SessionGuardHistory/ActionType/ProposedAction`, `guardrails.redactor.redact` (tests), `tools.TelemetryService` and `retrieval` result envelopes (replay test), `pydantic_ai.messages.ModelMessagesTypeAdapter` (message-history serialization, in the test only; production caller is plan 22).
- File size rule: `storage/state_store.py` stays under ~300 lines. If it would exceed, move approval methods to `storage/approval_queries.py` as module functions taking the connection, and have `StateStore` delegate (one-line methods). Do not create the split up front.
- No `ApprovalService`, no async wrapper, no pool, no dispatcher; all stay out of scope. Also out of scope: cross-worker turn locking and `ConversationState` rebuild from snapshot (issue #34 / 2.4), customer reply after approval (issue #10 / 3.2).

## Concurrency & recovery contract (design issues resolved up front)

1. **Autocommit required.** `StateStore.__init__` raises `ValueError` if `connection.autocommit` is false. Reason: on a non-autocommit connection `connection.transaction()` degrades to a savepoint inside an implicit transaction and nothing commits, so "survives restart" would silently fail.
2. **Per-conversation serialization:** each write begins with `SELECT ... FROM conversations WHERE id = ... FOR UPDATE`. That row lock orders concurrent writers (customer turn, reviewer resolving an approval, background retry), makes `last_turn`/`last_seq` gapless and collision-free, and makes "exists? then insert" idempotency checks race-free. Cross-conversation writes never contend.
3. **Idempotent retries:** `append_customer_message`, `complete_turn`, `record_trace` and `create_approval` take a caller-supplied id (or idempotency key); under the lock, an existing id/key returns the stored row with no counter or stage side effect. A turn retried after a crash therefore never duplicates rows.
4. **Crash resume:** state is whatever committed last. Customer message commit sets stage `INGESTION_GUARD`; each node does `set_stage` + `record_trace` (separate transactions, in this order: trace first, then stage, so the stage never claims progress the trace log lacks); `complete_turn` commits the reply and `IDLE` together. `rehydrate` returns the open turn's traces; resume rule for the orchestrator: reuse `output` of `OK` traces per role, redo roles lacking an `OK` trace, reusing the same `message_id`.
5. **Stuck-stage hazard:** a crash leaves stage non-`IDLE`; the store never rejects a new customer message because of it (that would brick the conversation). The new message opens the next turn; the orphaned older turn is ignored by `rehydrate` (only the highest customer turn without a reply is "open"). Serializing concurrent turns across workers is out of scope for 21: new issue #34 (2.4).
6. **Approvals:** resolve is a compare-and-set (`UPDATE ... WHERE id AND status = 'PENDING' RETURNING`), so two reviewers racing yield exactly one winner and one `ApprovalStateError`. Resolution never changes conversation stage (non-blocking HITL).
7. **Consistent reads:** `rehydrate` and `replay_trace` each run in one transaction whose first statement is `SET TRANSACTION ISOLATION LEVEL REPEATABLE READ`, so a concurrent writer cannot yield a snapshot with a reply but without its traces.
8. **Hostile text:** all text/jsonb writes pass through `strip_nul` / `to_jsonb`.
8a. **Trace input:** `record_trace` passes `traces.input` through the existing `guardrails/redactor.py::redact` (reuse, no new redaction code) and truncates to 20 KB before `to_jsonb`. `cost_usd` is stored as given (computed by plan 22 `AgentTrace.from_run` via `genai_prices`; nullable).
9. **Customer-message redaction** stays at the orchestrator chokepoint (guardrails design §4.1); a test pins the invariant for all columns, incl. `traces.input` redacted by the store.

## Review Focus

1. **Duplicate delivery of the same customer message id** (client retry): one row, one turn number, stage unchanged on the retry. -> Task 1.
2. **Two writers racing on one conversation** (threads, two connections, 20 `record_trace` each): seqs are exactly `1..40`, unique, no deadlock. -> Task 2.
3. **Two reviewers resolving the same approval at once:** exactly one succeeds. -> Task 3.
4. **Message with NUL byte, emoji, 50 KB body:** stored and read back identically (minus NUL), no `DataError`. -> Task 1.
5. **Rehydrate/replay of an unknown id or an empty conversation:** `None` / empty tuples, no exception. -> Tasks 4, 5.

---

### Task 1: `StateStore` core: conversations and messages

**Files:**
- Create: `storage/state_store.py`
- Modify: `storage/__init__.py` (export `StateStore`)
- Test: `tests/storage/test_conversations_and_messages.py`

**Interfaces (all `-> ` typed, `at: AwareDatetime`):**
- `StateStore.__init__(connection: psycopg.Connection[Any]) -> None` (autocommit guard).
- `create_conversation(account_id: str | None, contact_email: str | None, customer_tier: AccountTier, at, conversation_id: UUID | None = None) -> Conversation` (stage `IDLE`, empty guard history, counters 0; idempotent on a passed id).
- `get_conversation(conversation_id: UUID) -> Conversation | None`.
- `set_stage(conversation_id: UUID, stage: ConversationStage, at) -> None`.
- `update_identity(conversation_id: UUID, account_id: str | None, contact_email: str | None, customer_tier: AccountTier, active_site_id: str | None, at) -> None` (persists Triage's `CallerIdentity` outcome so tier/site are not re-derived after restart).
- `save_guard_history(conversation_id: UUID, history: SessionGuardHistory, at) -> None` (whole-object overwrite via `to_jsonb(history.model_dump(mode="json"))`; safe because the history is immutable and the orchestrator holds the latest).
- `append_customer_message(conversation_id: UUID, message_id: UUID, content: str, at) -> StoredMessage`: locks, returns existing row if `message_id` exists, else increments `last_turn`, inserts with that turn, sets stage `INGESTION_GUARD`.
- `complete_turn(conversation_id: UUID, turn: int, sender: MessageSender, content: str, citations: Sequence[dict[str, str]], telemetry_evidence: Sequence[TelemetryEvidence], message_id: UUID, at) -> StoredMessage`: guard clause rejects `MessageSender.CUSTOMER` with `ValueError`; idempotent on `message_id`; inserts the reply for `turn` and sets stage `IDLE` only when `turn == last_turn` (a stale retry of an old turn must not flip a newer turn's stage), in the same transaction.
- `list_messages(conversation_id: UUID) -> list[StoredMessage]` ordered by `(turn, created_at, id)`.
- Private: a column-list `LiteralString` per row type and one `_lock_conversation(conversation_id) -> Conversation` helper used by every write; one private `_fetch_one`-style helper is acceptable only if it removes real repetition.

- [ ] **Step 1: Write failing tests (functional, real DB):**
  (a) create -> append customer message -> `complete_turn` AGENT reply with a citation and a real `TelemetryEvidence` -> `list_messages` ordered, turns 1/1, stage `IDLE`; (b) same `message_id` appended twice returns equal row, still one DB row, `last_turn == 1`; (c) after `append_customer_message` stage is `INGESTION_GUARD`; `complete_turn` for a stale turn (turn 1 while `last_turn == 2`) leaves stage as is; (d) `complete_turn` with `MessageSender.CUSTOMER` raises `ValueError`; (e) NUL/emoji/50 KB content round-trip; (f) `save_guard_history` + `restart()` fresh connection + `get_conversation`: history equal, `secret_hashes` still a frozenset; (g) constructing `StateStore` on a non-autocommit connection raises `ValueError`; (h) `update_identity` round-trips tier and site after restart.
- [ ] **Step 2:** `uv run pytest tests/storage/test_conversations_and_messages.py -v`, expect FAIL.
- [ ] **Step 3:** Implement the methods above, nothing else.
- [ ] **Step 4:** Run, expect PASS; `uvx ruff check storage tests/storage` and `uvx pyright storage`.
- [ ] **Step 5:** Commit `feat(storage): StateStore conversations and messages`.

---

### Task 2: Traces and tool calls

**Files:**
- Modify: `storage/state_store.py`
- Test: `tests/storage/test_traces.py`

**Interfaces:**
- Consumes: `TraceRecord`, `ToolCallRecord`, `to_jsonb` (plan 01 Task 4).
- Produces:
  - `record_trace(trace: TraceRecord, tool_calls: Sequence[ToolCallRecord]) -> None`: single transaction; locks conversation; if `trace.id` already exists returns without side effects (idempotent); else assigns `seq = last_seq + 1`, bumps `last_seq`, inserts the trace, and inserts each tool call with `seq` = its position in the sequence (caller-supplied `ToolCallRecord.seq` is ignored/overwritten to avoid caller skew; document in the method by naming, not prose). Tool call rows get `trace_id` and `conversation_id` from the trace.
  - `list_traces(conversation_id: UUID, turn: int | None = None) -> list[TraceRecord]` ordered by `seq`.
  - `list_tool_calls(conversation_id: UUID, trace_id: UUID | None = None) -> list[ToolCallRecord]` ordered by `(trace_id's seq, tool seq)` via a join, or simpler by `created_at, seq`; pick join on `traces.seq` for deterministic order.

- [ ] **Step 1: Write failing tests:**
  (a) trace with two tool calls round-trips; tool call order preserved; `result` contains the full `TelemetryToolResult` dump for `S-1007-01` from the real `TelemetryService` (reuse how `tests/tools/test_telemetry.py` constructs it) incl. `evidence`; (b) idempotent: `record_trace` twice with the same id -> one trace, `last_seq == 1`, tool calls not duplicated; (c) atomicity: a trace whose second tool call violates a constraint (e.g. `trace_id` forced duplicate seq via a malformed record, or a `conversation_id` unknown to FK) leaves zero trace rows and counter unchanged; (d) concurrency: two threads, each with its own `psycopg.connect(autocommit=True)` + `StateStore`, each recording 20 traces for one conversation with distinct ids; afterwards `[t.seq for t in list_traces]` equals `list(range(1, 41))`; (e) parent/child: a retry trace with `parent_trace_id` set persists and orders after its parent; (g) `traces.input` containing the SC-08 PSK is stored redacted, input over 20 KB truncated to 20 KB; `cost_usd` None and a Decimal both round-trip; (f) a KB search `KBSearchResult` envelope (build one directly from `retrieval.models` with two scored candidates; no DB model load) keeps `rerank_score` values in `result`.
- [ ] **Step 2:** Run, expect FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run, expect PASS; ruff/pyright on touched paths.
- [ ] **Step 5:** Commit `feat(storage): atomic trace + tool call log`.

---

### Task 3: Approvals

**Files:**
- Modify: `storage/state_store.py` (apply the 300-line split rule here if needed)
- Test: `tests/storage/test_approvals.py`

**Interfaces:**
- `create_approval(conversation_id: UUID, trace_id: UUID | None, action_type: ActionType, payload: dict[str, str], idempotency_key: str, at, approval_id: UUID | None = None) -> Approval`: locks conversation; `INSERT ... ON CONFLICT (conversation_id, idempotency_key) DO NOTHING`, then reads the row by key; same key with a different payload returns the ORIGINAL (first write wins). Orchestrator key convention for 2.4: `f"{trace_id}:{action_index}"`.
- `get_approval(approval_id: UUID) -> Approval | None`.
- `list_pending_approvals(conversation_id: UUID | None = None) -> list[Approval]`, ordered by `requested_at, id`; `None` spans conversations (reviewer queue).
- `resolve_approval(approval_id: UUID, resolution: ApprovalResolution, at) -> Approval`: compare-and-set from `PENDING`; zero rows -> `ApprovalStateError`. Validation of status/edited_payload lives in `ApprovalResolution`, not here. `edited_payload` stored beside the untouched original `payload`.

- [ ] **Step 1: Write failing tests:**
  (a) SC-03-shaped `CREDIT` approval across `restart()`: pending visible from a fresh connection, a THIRD connection resolves it `APPROVED`, rehydrate (Task 4 not yet; use `list_pending_approvals`) shows none, second resolve raises `ApprovalStateError`, unknown id raises it too; (b) idempotent create on same key -> one row, first payload kept; (c) `EDITED` keeps original payload and stores edited; (d) queue spans two conversations; (e) race: two threads/connections resolve the same approval, exactly one returns, one raises; (f) every `ActionType` value round-trips; (g) non-blocking: with a pending approval, a new customer message is accepted and stage progresses/returns to `IDLE` via `complete_turn`.
- [ ] **Step 2:** Run, expect FAIL. **Step 3:** Implement. **Step 4:** PASS + ruff/pyright. 
- [ ] **Step 5:** Commit `feat(storage): approvals with idempotent create and CAS resolve`.

---

### Task 4: `rehydrate`

**Files:**
- Modify: `storage/state_store.py`
- Test: `tests/storage/test_rehydrate.py`

**Interfaces:**
- `rehydrate(conversation_id: UUID) -> ConversationSnapshot | None`: one transaction opened with `SET TRANSACTION ISOLATION LEVEL REPEATABLE READ` as first statement; reads conversation (None -> return None), all messages, pending approvals for the conversation, and `open_turn_traces` = traces of the highest turn that has a CUSTOMER message and no AGENT/SYSTEM message (empty tuple otherwise). A private contextmanager `_consistent_read()` implements the transaction preamble and is shared with Task 5.

- [ ] **Step 1: Write failing tests (the issue's headline crash tests, no mocks):**
  (a) *Mid-conversation restart:* write customer + agent turn, guard history with a blocked injection verdict and a secret hash, stage `RESOLUTION` via `set_stage`, a trace; drop all references (`del` store/connection/snapshot), `restart()` -> new connection + new `StateStore`; `rehydrate` returns identical messages (order, content, citations), stage `RESOLUTION`, identical `guard_history` (`agent_context_note()` equal; `secret_hashes` still contains the hash so `SECRET_ECHO` logic still sees it, assert via `SessionGuardHistory.secret_hashes`, not by invoking the validator);
  (b) *Crash mid-turn:* customer message + Triage trace(OK) + `set_stage(DIAGNOSTICS)`, no reply; restart; `open_turn_traces` has the Triage trace, stage is `DIAGNOSTICS`; after `complete_turn`, `open_turn_traces` is empty and stage `IDLE`;
  (c) *Orphan turn:* turn 1 never replied, turn 2 completed -> `open_turn_traces` empty (older orphan ignored, documented behavior);
  (d) *Pending approval after restart* appears in `pending_approvals`; resolved one does not;
  (e) unknown id -> `None`; fresh empty conversation -> empty messages/traces.
- [ ] **Step 2:** Run, expect FAIL. **Step 3:** Implement. **Step 4:** PASS + ruff/pyright.
- [ ] **Step 5:** Commit `feat(storage): rehydrate conversation snapshot`.

---

### Task 5: Trace replay

**Files:**
- Create: `storage/replay.py` (models `ReplayStep`, `ReplayTurn`, `TraceReplay`; classmethod `TraceReplay.from_rows(conversation_id, messages, traces, tool_calls, approvals) -> TraceReplay`; pure, no DB)
- Modify: `storage/state_store.py` (`replay_trace(conversation_id: UUID) -> TraceReplay | None`: inside `_consistent_read()` load messages, traces, tool calls, approvals via the existing list methods' queries, then `TraceReplay.from_rows`)
- Modify: `storage/__init__.py` exports
- Test: `tests/storage/test_trace_replay.py`

**Models:** `ReplayStep(trace: TraceRecord, tool_calls: tuple[ToolCallRecord, ...])`; `ReplayTurn(turn: int, customer_message: StoredMessage | None, steps: tuple[ReplayStep, ...], reply: StoredMessage | None)`; `TraceReplay(conversation_id: UUID, turns: tuple[ReplayTurn, ...], approvals: tuple[Approval, ...])`. Steps are flat in `seq` order; the parent/child graph is `trace.parent_trace_id` (no tree, KISS; deltas in plan 01). Approvals stay conversation-level and link to a step via `trace_id`.

- [ ] **Step 1: Write failing test (functional, scripted, zero LLM):** build one telemetry-diagnosis turn the way the orchestrator would: `redact()` the customer text, `append_customer_message`; triage trace; diagnostics trace with a real `TelemetryToolResult` from `TelemetryService` for `S-1007-01` as a `ToolCall`; knowledge trace with a hand-built `KBSearchResult` with scored candidates; resolution trace OK plus a retry child (`parent_trace_id` = first resolution trace, first one status `RETRIED`); a `CREDIT` approval linked to the resolution trace; `complete_turn` reply. Also set one trace's `model_messages` from a PydanticAI `TestModel` agent run (`ModelMessagesTypeAdapter.dump_python(result.all_messages(), mode="json")`, same `TestModel` style as `tests/services/test_support_intake_functional.py`) so the PydanticAI-native trace path is exercised end to end. Then discard every Python object, `restart()`, and from `replay_trace` output ONLY assert: who said what, steps in `seq` order, parent/child retry link, each tool call exactly once with full envelope (evidence + scores), summed latency/tokens/cost equal inputs, approval present and linked, `model_messages` re-validates with `ModelMessagesTypeAdapter.validate_python`. Second test: `replay_trace` of unknown id -> `None`; conversation with only a customer message -> one turn, no steps, `reply is None`. Third test (property-style, plain loop over a 3-turn script): every persisted message and tool call appears exactly once in the replay.
- [ ] **Step 2:** Run, expect FAIL. **Step 3:** Implement. **Step 4:** PASS + ruff/pyright.
- [ ] **Step 5:** Commit `feat(storage): trace replay`.

---

### Task 6: Redaction invariant and package surface

**Files:**
- Test: `tests/storage/test_no_secret_in_rows.py`
- Modify: `storage/__init__.py` (final `__all__`: models, `StateStore`, `TraceReplay`, `ApprovalStateError`)

- [ ] **Step 1: Write test:** take the guardrails SC-08 PSK message (from `data/eval/scenarios.jsonl`, same lookup as `tests/guardrails/test_redactor.py`), run `redact()`, write the orchestrator-shaped sequence (customer message with redacted text, guard-history save with the secret hash, trace whose `input` is the redacted text, a reply); then query every text and jsonb column of the five runtime tables for rows of that conversation, cast to text, and assert the raw PSK appears nowhere while the `[REDACTED...]` marker and the sha256 do. This documents that the chokepoint, not the store, owns redaction.
- [ ] **Step 2:** Run (should PASS immediately because redaction happens in the test's caller; it is a regression pin, not new logic). If it fails, the store is mutating text; fix the store.
- [ ] **Step 3:** Commit `test(storage): redaction invariant`.

---

### Task 7: Docs and ADR

**Files:**
- Modify: `docs/overview/decisions.md`: add ADR-008 ("State as rows; per-conversation row lock + counters; append-only traces and `tool_calls` child table; runtime tables excluded from seed dump via `--exclude-table`; PydanticAI message history + Postgres traces replace Braintrust"). Also update the ADR-005 line mentioning `ApprovalRecord` (deleted).
- Modify: `docs/architecture/system-architecture-design.md`: §6 ER (new columns, `tool_calls`, `approvals.edited_payload/idempotency_key/trace_id`, `conversations.stage/guard_history/last_turn/last_seq`, `traces.model_messages`; migration filename `20261001_0900_agent-runtime.sql`; drop `simulated_actions` from this migration's description), §12 layout (add `storage/`, remove `ApprovalRecord` from `services/models.py` description at line ~522), §8 as already rewritten in plan 01.
- Modify: `README.md` (mention `storage/` and that runtime tables are intentionally absent from `db/seed.dump`).
- Modify: `docs/plans/21-agent_state_machine/design.md`: header note pointing to the two plans, plus a one-line "superseded by plan deltas" for §2.8 (`--exclude-table`), §3.1 (counters, dropped `simulated_actions`/`status`), §4 (`ConversationSnapshot` open-turn definition), §1/§6 (no Braintrust).

- [ ] **Step 1:** Make the edits. **Step 2:** `grep -rn -i "braintrust\|ApprovalRecord\|exclude-table-data" docs README.md` shows only historical ADR text. **Step 3:** Commit `docs: ADR-008 and architecture update for runtime state`.

---

### Task 8: Cleanup, lint, type check (final)

- [ ] **Step 1:** Read every created/modified file end to end; audit with the `ponytail` mindset and `thermo-nuclear-code-quality-review` (file size, one concern per method, no spaghetti conditions, no giant file; apply the split rule of Global Constraints only if `state_store.py` exceeds ~300 lines).
- [ ] **Step 2:** Confirm removed/absent: `braintrust` (code, pyproject, uv.lock, .env.example), `ApprovalRecord` and its export, `simulated_actions`, any unused model, enum member, helper or import in `storage/` and `agents/models.py` (every model used by `StateStore` or a test). Grep: no `datetime.now`, no `now()` in SQL, no inline imports, no `Literal` for enum-like fields in `storage/`.
- [ ] **Step 3:** `uvx ruff check storage agents services db tests/storage tests/db` and `uvx pyright storage agents services db`, zero findings; every function typed incl. `-> None`; f-strings only.
- [ ] **Step 4:** Full run: `uv run pytest tests/storage tests/db tests/services tests/guardrails tests/tools tests/retrieval -v`.
- [ ] **Step 5:** Commit `chore(storage): cleanup and lint`.

---

## Self-review

- Spec coverage: §5.1 Task 1 (minus dropped `list_conversations`/`close_conversation`); §5.2 Task 1 (turn assignment now atomic via counter); §5.3 Task 2; §5.4 Task 3; §5.5 Tasks 4-5 (`record_simulated_action` dropped, plan 01 delta 4); §6 tests 1-5 mapped to Tasks 1-6 plus plan 01 Tasks 2-3 (schema, dump); §7 cross-package in plan 01 Task 4 and Task 7 here; §8 cleanup Task 8.
- Interface seams: **22** fills `AgentTrace` (incl. `ToolCall`, `model_messages`, `cost_usd`) and calls `TraceRecord.from_agent_trace`; **23** `run_turn` stays DB-free; its `TurnResult.pending_actions` become `create_approval` calls and its visited `path` becomes one `ORCHESTRATOR`/guard `TraceRecord` per state in Phase 2.4; `ConversationState` is rebuilt in 2.4 (issue #34) from `ConversationSnapshot` (identity from `update_identity` columns, triage/awaiting-scope from the latest `OK` Triage trace `output`, evidence from stored messages, `guard_history` as saved). Stage names map 1:1 to `WorkflowState` where both exist.
- Names consistent across plans: `append_customer_message`, `complete_turn`, `record_trace`, `ApprovalResolution`, `ConversationSnapshot`, `TraceReplay`, `to_jsonb`, `strip_nul`.

## Unresolved questions

1. Persist `ConversationState` pieces (identity json, triage decision) as columns vs derive from traces? Assumed derive (design §2.3).
2. Keep `ApprovalService` split from `StateStore`? Assumed yes.
3. Tool-call `latency_ms` precision (message timestamps, approximate) ok?
4. Pool in `db/connection.py`: later, ok?

**Notes for other issues (not 21 questions)**
- Issue #10 (3.2) resume path: re-invoke the Resolution step (22 `run_resolution`) with the approval outcome as input for consistent grounded tone; rejection uses a deterministic template. 21 only persists the approval outcome + exposes it.
- Issue #34 (2.4): cross-worker turn locking, `ConversationState` rebuild.
- Merge order 21 -> 22 -> 23.
