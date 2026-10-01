# 21 / Plan 01 — Runtime Schema, Seed-Dump Isolation, Contracts — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land everything `StateStore` (plan 02) stands on: Braintrust removal, the `agent-runtime` migration, dump isolation of runtime tables, and the frozen Pydantic contracts in `storage/models.py` plus the `agents/models.py` trace extension.

**Architecture:** Runtime state is rows in five tables (`conversations`, `messages`, `traces`, `tool_calls`, `approvals`) created by one idempotent migration that `db.init.seed.apply_schema` already re-applies on every start. Runtime tables are kept OUT of `db/seed.dump` entirely, because the container entrypoint runs `pg_restore --clean --if-exists` on every boot. Contracts are frozen Pydantic models read straight from SQL with `psycopg.rows.class_row`, no hand-written row mappers.

**Tech Stack:** Python 3.12, psycopg 3 (sync), PostgreSQL 18, Pydantic v2, pydantic-ai 2.51 (installed), pytest.

**Spec:** [design.md](design.md) §2–§4, §7. **This plan overrides the design where noted in "Deltas from design" below.**

## Global Constraints

- Sync-only. Store takes `psycopg.Connection[Any]`, named `%(name)s` placeholders, `LiteralString` SQL (as `retrieval/service.py`, `services/ticket_service.py`).
- Every function/method fully typed (params and return, `-> None` included), Pyright `standard` clean, ruff clean. No bare `list`/`dict`, no implicit `Any`.
- Imports at module top only. f-strings. Enums are `StrEnum` (ADR-005, matches `tools/models.py`, `guardrails/models.py`); no `Literal` for enum-like fields.
- Frozen Pydantic models (`ConfigDict(frozen=True)`); timestamps `AwareDatetime` passed in by callers from `SimulationClock`; no `datetime.now`, no SQL `now()` for business timestamps.
- No new dependency; one dependency REMOVED (`braintrust`).
- NO Braintrust tracing anywhere. Tracing = PydanticAI message history (`result.all_messages()`, `ModelMessagesTypeAdapter`) + the Postgres trace tables of this plan. The design/architecture mentions of Braintrust are overridden (Task 1).
- Tests are functional against the real seeded Postgres (compose `postgres` up). If it is not up, STOP and report.
- Verify with `uv run pytest <path> -v`, `uvx ruff check <paths>`, `uvx pyright <paths>`.

## Branching

Single branch `p-2-1_agent-state-machine` (from `p-2-agent`). Commit per task. Never merge, never push.

## Deltas from design (decisions, so nobody re-litigates them)

1. **Dump isolation uses `pg_dump --exclude-table`, not `--exclude-table-data`.** If the runtime table definitions sit in the dump, `pg_restore --clean --if-exists` (Dockerfile entrypoint, every boot) drops and recreates them, wiping live conversations on every container restart. Tables absent from the dump are untouched by `--clean`; `apply_schema` creates them idempotently in `startup`. Runtime tables carry no FK into `accounts`/`tickets`/KB tables for the same reason.
2. **Counters on `conversations`, not `max()+1`.** `last_turn` and `last_seq` columns are advanced by locked `UPDATE ... RETURNING`; `max()+1` is racy under READ COMMITTED even inside a transaction. Unique `(conversation_id, turn)` for customer messages is not needed; unique `(conversation_id, seq)` on traces is the backstop.
3. **No CHECK constraints mirroring enums.** Pydantic enums validate every write and read; a second copy in SQL is the drift risk the design then needs a test for. Text columns, enum-typed in Python.
4. **Dropped as YAGNI:** `simulated_actions` table (dispatcher issues #9/#10 own it), `ConversationStatus` / `status` column and `close_conversation` / `list_conversations` (nothing closes or lists in Phase 2), `MessageSender.REVIEWER`, `traces.retrieval_scores` column (full envelope with scores is already in `tool_calls.result`; DRY), `ReplayStep.children` tree (flat ordered steps with `parent_trace_id`).
5. **`traces.model_messages jsonb`** added: PydanticAI's own serialized message history for the run (`ModelMessagesTypeAdapter`). This is the PydanticAI-native replacement for Braintrust spans, answers design question 1 (what to store in `input`), and gives full prompt/tool-call fidelity without custom serializers.
6. **`cost_usd` source:** computed by agent layer (plan 22 trace builder) from `ModelResponse.cost()` (genai-prices, already installed with pydantic-ai); `None` when the model is unknown (e.g. `TestModel`). No pricing table in the repo. Answers design question 2.
7. **Turn/stage atomicity:** stage transitions that must be atomic with a message write are done by the same store method (plan 02: `append_customer_message` sets stage `INGESTION_GUARD`; `complete_turn` appends the reply and sets `IDLE` in one transaction). Design's separate `set_stage` stays for mid-turn node transitions only.

## Review Focus

1. **Restart wipes runtime tables:** a rebuilt `seed.dump` must contain no runtime table schema or data, else `pg_restore --clean` destroys them each boot. -> Task 3 test.
2. **`apply_schema` run twice (every boot) must be a no-op** and must not break on populated runtime tables. -> Task 2 test.
3. **Migration text with `%`:** `apply_schema` feeds files through `psycopg.sql.SQL`; the migration must contain no `%` and no unbalanced braces. -> Task 2 (applied via the real `apply_schema`).
4. **`SessionGuardHistory` JSON round-trip** (frozensets serialize as lists) restores `secret_hashes` as a frozenset. -> Task 4 test.
5. **NUL (`\x00`) in text or JSON** raises `DataError` in Postgres and would crash a turn on hostile input; contract helper strips it. -> Task 4 test, store use in plan 02.

---

### Task 1: Remove Braintrust

**Files:**
- Modify: `kbindex/__init__.py` (delete the three lines; leave the file empty or a one-line package comment, like `retrieval/__init__.py`)
- Modify: `pyproject.toml` (drop `braintrust>=0.43.0`), regenerate `uv.lock` with `uv lock`
- Modify: `.env.example` (drop `BRAINTRUST_API_KEY` line)
- Modify: `Dockerfile` pip install list if it names braintrust (grep first; currently only pyproject names it)
- Modify: `docs/architecture/system-architecture-design.md` §1 bullet 6, §3 diagram nodes `Braintrust`, §8 (rewrite as "Postgres trace layer + PydanticAI message history"; delete Braintrust branch and layer 2), mentions around line 82/104
- Modify: `docs/overview/decisions.md` (ADR-008, written in Task 10 of plan 02, records the removal)

**Interfaces:**
- Consumes: nothing.
- Produces: `import kbindex` has no side effects (no logger init, no auto-instrumentation of psycopg / pydantic-ai).

- [ ] **Step 1:** `grep -rn -i braintrust --include=*.py --include=*.toml --include=*.md --include=*.yml --include=Dockerfile . | grep -v kb_ingestion` and list every hit; each must be handled by this task.
- [ ] **Step 2:** Make the edits above. Do not add any replacement tracing hook.
- [ ] **Step 3:** `uv lock` then `uv sync`. Expected: braintrust gone from `uv.lock`, nothing else upgraded unintentionally (inspect `git diff --stat uv.lock`).
- [ ] **Step 4:** Run `uv run pytest tests/kbindex tests/services tests/guardrails -v`. Expected: same pass/fail as before the change (record the baseline run before editing).
- [ ] **Step 5:** Commit `chore: drop braintrust, tracing is postgres + pydantic-ai history`.

---

### Task 2: Migration `20261001_0900_agent-runtime.sql`

**Files:**
- Create: `db/migrations/20261001_0900_agent-runtime.sql`
- Test: `tests/storage/test_schema.py` (new package dir `tests/storage/`, no `__init__.py`, same as sibling test dirs)
- Create: `tests/storage/conftest.py` (fixtures in Task 4; here only the DB URL use via `core.config.settings.database_url`)

**Interfaces:**
- Consumes: `db.init.seed.apply_schema(connection) -> None`.
- Produces: tables below; plan 02 SQL targets these exact names and columns.

Schema (lowercase SQL, `create ... if not exists`, no `%`, a leading comment explaining re-application and that tables are excluded from the dump, in the style of the existing english-search-vector migration):

- `conversations`: `id uuid primary key`, `account_id text null`, `contact_email text null`, `customer_tier text not null`, `active_site_id text null`, `stage text not null`, `guard_history jsonb not null default empty object`, `last_turn int not null default 0`, `last_seq int not null default 0`, `created_at timestamptz not null`, `updated_at timestamptz not null`. Index on `account_id`.
- `messages`: `id uuid primary key`, `conversation_id uuid not null references conversations on delete restrict`, `turn int not null`, `sender text not null`, `content text not null`, `citations jsonb not null default empty array`, `telemetry_evidence jsonb not null default empty array`, `created_at timestamptz not null`. Index `(conversation_id, turn)`.
- `traces`: `id uuid primary key`, `conversation_id uuid not null references conversations restrict`, `message_id uuid null references messages restrict`, `turn int not null`, `seq int not null`, `agent_role text not null`, `parent_trace_id uuid null references traces restrict`, `input jsonb not null`, `output jsonb null`, `model_messages jsonb null`, `status text not null`, `error text null`, `latency_ms int not null`, `prompt_tokens int not null`, `completion_tokens int not null`, `cost_usd numeric null`, `started_at timestamptz not null`, `created_at timestamptz not null`. Unique `(conversation_id, seq)`. Index `(conversation_id, turn)`.
- `tool_calls`: `id uuid primary key`, `trace_id uuid not null references traces restrict`, `conversation_id uuid not null references conversations restrict`, `seq int not null` (position within the trace), `tool_name text not null`, `arguments jsonb not null`, `status text not null`, `result jsonb not null`, `latency_ms int not null`, `created_at timestamptz not null`. Unique `(trace_id, seq)`. Index `(conversation_id, tool_name, status)` (serves "all UNAVAILABLE telemetry calls" and conversation replay).
- `approvals`: `id uuid primary key`, `conversation_id uuid not null references conversations restrict`, `trace_id uuid null references traces restrict`, `action_type text not null`, `payload jsonb not null`, `status text not null`, `idempotency_key text not null`, `reviewer_notes text null`, `edited_payload jsonb null`, `requested_at timestamptz not null`, `resolved_at timestamptz null`. Unique `(conversation_id, idempotency_key)`. Partial index on `status` where status is `PENDING` (values are the `ApprovalStatus` StrEnum values; use the same case as the enum, upper-case).

- [ ] **Step 1: Write failing test** `test_schema.py::test_runtime_tables_exist_and_apply_schema_is_idempotent`: open `psycopg.connect(settings.database_url)`; call `apply_schema` twice; assert via `information_schema.tables` that all five tables exist and that a second call raises nothing. Second test `test_unique_and_fk_constraints`: with a real conversation row inserted via raw SQL, duplicate `(conversation_id, seq)` trace insert raises `psycopg.errors.UniqueViolation`; deleting a conversation that has a message raises `ForeignKeyViolation`; clean up its rows in the test's `finally`.
- [ ] **Step 2:** Run `uv run pytest tests/storage/test_schema.py -v`. Expected FAIL (tables missing).
- [ ] **Step 3:** Write the migration.
- [ ] **Step 4:** Run again. Expected PASS. Also run `uv run pytest tests/db -v` (existing `apply_schema` consumers) to confirm still green.
- [ ] **Step 5:** Commit `feat(db): agent-runtime migration`.

---

### Task 3: Keep runtime tables out of `seed.dump`

**Files:**
- Modify: `db/init/build.py` (`write_dump`): add a module constant naming the five runtime tables, and append one `--exclude-table=<name>` flag per table to BOTH commands (local `pg_dump` and the `docker run ... pg_dump` fallback). Build the flag list once and reuse (DRY), e.g. a small private function returning the list, used in both command lists.
- Test: `tests/db/test_init.py` (append) or new `tests/db/test_dump_excludes_runtime.py`

**Interfaces:**
- Consumes: `db.init.build.write_dump(destination: Path | str) -> Path`.
- Produces: dumps with no runtime schema or data. Do NOT regenerate the committed `db/seed.dump` in this plan (old dump has no runtime tables; `startup` creates them).

- [ ] **Step 1: Write failing test:** insert one conversation row (autocommit connection, fresh uuid) into the live DB; call `write_dump(tmp_path / "x.dump")`; list the archive TOC with `pg_restore --list` (same client binary location logic as `write_dump`: run locally if present, else skip the test with `pytest.skip` when neither `pg_restore` nor docker is available, mirror how `tests/db/test_init.py` shells out for pg_dump if it does); assert no TOC line mentions any runtime table name (TABLE and TABLE DATA both), and that `passages` TABLE DATA is present (sanity). Delete the inserted row in `finally`.
- [ ] **Step 2:** Run it. Expected FAIL (tables present in dump).
- [ ] **Step 3:** Implement the exclusion.
- [ ] **Step 4:** Run it plus `uv run pytest tests/db -v`. Expected PASS.
- [ ] **Step 5:** Commit `feat(db): exclude runtime tables from seed dump`.

---

### Task 4: Contracts `storage/models.py`, `AgentTrace` extension, `ApprovalRecord` deletion

**Files:**
- Create: `storage/__init__.py` (re-exports public names, `__all__`, like `guardrails/__init__.py`)
- Create: `storage/models.py`
- Modify: `agents/models.py` (extend `AgentTrace`; add `ToolCall`)
- Modify: `agents/__init__.py` (export `ToolCall`)
- Modify: `services/models.py`, `services/__init__.py` (delete `ApprovalRecord` and its export; no code uses it, grep confirmed)
- Create: `tests/storage/conftest.py`
- Test: `tests/storage/test_models.py`

**Interfaces (all frozen Pydantic, `AwareDatetime`, StrEnum):**

Enums: `ConversationStage` (`INGESTION_GUARD`, `TRIAGE`, `SCOPE_CHECK`, `DIAGNOSTICS`, `KNOWLEDGE_RETRIEVAL`, `RESOLUTION`, `ACTION_EVALUATION`, `OUTPUT_GUARD`, `IDLE`; no `APPROVAL_PENDING`, approvals are found by querying `approvals`; map 1:1 onto 23's `WorkflowState` names where they overlap, mapping lives in 2.4); `MessageSender` (`CUSTOMER`, `AGENT`, `SYSTEM`); `AgentRole` (`INGESTION_GUARD`, `TRIAGE`, `DIAGNOSTICS`, `KNOWLEDGE`, `RESOLUTION`, `ACTION_GATE`, `OUTPUT_GUARD`, `ORCHESTRATOR`); `TraceStatus` (`OK`, `ERROR`, `RETRIED`); `ApprovalStatus` (`PENDING`, `APPROVED`, `EDITED`, `REJECTED`).

Models (fields as in design §4 minus the deltas above):
- `Conversation`: `id: UUID`, `account_id`, `contact_email`, `customer_tier: AccountTier` (from `core.models`), `active_site_id`, `stage`, `guard_history: SessionGuardHistory` (from `guardrails.models`), `last_turn: int`, `last_seq: int`, `created_at`, `updated_at`.
- `StoredMessage`: `id`, `conversation_id`, `turn`, `sender`, `content`, `citations: tuple[dict[str, str], ...]`, `telemetry_evidence: tuple[TelemetryEvidence, ...]` (from `tools.models`), `created_at`.
- `ToolCallRecord`: `id`, `trace_id`, `conversation_id`, `seq`, `tool_name`, `arguments: dict[str, Any]`, `status: str`, `result: dict[str, Any]`, `latency_ms`, `created_at`. Classmethod `from_tool_call(trace_id, conversation_id, seq, call: agents.models.ToolCall, at) -> ToolCallRecord`.
- `TraceRecord`: `id`, `conversation_id`, `message_id`, `turn`, `seq: int | None` (None before the store assigns it), `agent_role`, `parent_trace_id`, `input: dict[str, Any]`, `output: dict[str, Any] | None`, `model_messages: list[dict[str, Any]] | None`, `status`, `error`, `latency_ms`, `prompt_tokens`, `completion_tokens`, `cost_usd: Decimal | None`, `started_at`, `created_at`. Classmethod `from_agent_trace(agent_trace: AgentTrace, conversation_id, turn, message_id, parent_trace_id, at) -> TraceRecord` (generates `id` via `uuid4` unless the caller passed one; the caller passes a stable id on retry). Guard/orchestrator steps (no `AgentTrace`) build `TraceRecord` directly.
- `Approval`: per design §4, `action_type: ActionType` reused from `guardrails.models`, `payload: dict[str, str]`, `edited_payload: dict[str, str] | None`.
- `ApprovalResolution`: `status: ApprovalStatus`, `reviewer_notes: str | None`, `edited_payload: dict[str, str] | None`, with ONE model validator: status must not be `PENDING`; `edited_payload` present iff status is `EDITED`. This keeps the guard in the type, not in store method ladders.
- `ConversationSnapshot`: `conversation`, `messages: tuple[StoredMessage, ...]`, `pending_approvals: tuple[Approval, ...]`, `open_turn_traces: tuple[TraceRecord, ...]`. **Open turn definition (replaces design's):** highest turn that has a CUSTOMER message and no AGENT/SYSTEM message; `open_turn_traces` is empty when no such turn. Resume rule for the orchestrator (documented in the module docstring-free comment): reuse the `output` of traces with status `OK` per role, redo roles without an `OK` trace.
- `ApprovalStateError(Exception)`: raised when resolving a non-pending or unknown approval.
- Helper `jsonb(value: BaseModel | Mapping | Sequence) -> psycopg.types.json.Jsonb`-wrapper function `to_jsonb(model_dump_result)` in `storage/models.py`'s sibling `storage/jsonb.py` (own tiny module): builds `Jsonb` with a `dumps` that strips `\u0000` escapes. Used by every jsonb write in plan 02. Text values pass through `str.replace("\x00", "")` in the same module (`strip_nul(text: str) -> str`).

`agents/models.py` changes: `ToolCall` (frozen model: `tool_name`, `arguments: dict[str, Any]`, `status: str`, `result: dict[str, Any]`, `latency_ms: int`); `AgentTrace.tool_calls` becomes `list[ToolCall]`; add fields `input: dict[str, Any]`, `output: dict[str, Any] | None`, `model_messages: list[dict[str, Any]] | None`, `status: TraceStatus`, `error: str | None`, `cost_usd: Decimal | None`. Dependency direction: `storage.models` imports `agents.models` (for `AgentTrace`/`ToolCall`); `agents.models` imports `TraceStatus` from... to avoid a cycle define `TraceStatus` in `agents/models.py` and have `storage/models.py` import it (single definition). Note for plan 22: its `AgentTrace` builder must fill these fields; it takes `ToolCall` from tool-return parts of `result.all_messages()` and `ModelMessagesTypeAdapter.dump_python(messages, mode="json")` for `model_messages`.

`tests/storage/conftest.py`: fixtures `conn` (yields `psycopg.connect(settings.database_url, autocommit=True)`), `new_conversation(conn)` factory that records created ids and, at teardown, deletes rows in FK order (`tool_calls`, `approvals`, `traces`, `messages`, `conversations`) for those ids only. No truncation. A `restart()` helper fixture returns a brand-new autocommit connection (used by plan 02 restart tests).

- [ ] **Step 1: Write failing tests** `test_models.py`: (a) `SessionGuardHistory` with an injection verdict and a secret hash round-trips `model_dump(mode="json")` -> `model_validate`, `secret_hashes` is a `frozenset`, `agent_context_note()` equal; (b) `ApprovalResolution` rejects `PENDING`, rejects `EDITED` without payload, rejects `APPROVED` with a payload, accepts valid ones; (c) `TraceRecord.from_agent_trace` copies role/tokens/latency/tool calls and leaves `seq` None; (d) `to_jsonb`/`strip_nul` remove NUL from nested structures (test by `json.loads(jsonb.dumps(obj))` has no NUL). Pure-model tests, no DB (the one logic-heavy bit: the resolution validator).
- [ ] **Step 2:** Run, expect FAIL (imports).
- [ ] **Step 3:** Implement models, `jsonb.py`, `AgentTrace`/`ToolCall`, delete `ApprovalRecord`.
- [ ] **Step 4:** Run `uv run pytest tests/storage tests/services tests/guardrails -v`. Expected PASS; `grep -rn ApprovalRecord . --include=*.py` empty.
- [ ] **Step 5:** Commit `feat(storage): runtime contracts, AgentTrace tool/cost fields`.

---

## Self-review

- Spec coverage: schema (§3) Task 2; dump exclusion (§2.8) Task 3 with a stronger fix; contracts (§4) and cross-package changes (§7, `AgentTrace`, `ApprovalRecord`) Task 4; Braintrust override Task 1. `StateStore`, replay, restart tests, docs, ADR, cleanup in plan 02.
- Types consistent with plan 02: `ToolCallRecord.from_tool_call`, `TraceRecord.from_agent_trace`, `ApprovalResolution`, `to_jsonb`, `strip_nul`, `ConversationSnapshot`.

## Unresolved questions

1. Drop `braintrust` dep + `.env.example` key entirely (assumed yes)?
2. Regenerate committed `db/seed.dump` now (not needed) or leave?
3. Plan 22 `AgentTrace` builder: ok to own filling the new fields incl. `cost_usd` via `ModelResponse.cost()`?
4. `ConversationStatus`/close dropped; ok?
