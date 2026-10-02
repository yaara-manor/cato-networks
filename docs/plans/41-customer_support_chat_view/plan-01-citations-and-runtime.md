# Citation Persistence & Shared Runtime Implementation Plan (Plan 1 of 2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replies persist structured citations, and one shared function assembles a production `Workflow` so the UI, eval harness and 42 use the same code path.

**Architecture:** Marker parsing moves into one guardrails module reused by the output validator and by orchestration. `_finish` maps markers to the turn's `KnowledgeBundle` and hands the result to the existing `citations` argument of `StateStore.complete_turn` (column already exists, always empty today). `orchestration/runtime.py` replaces the harness-only assembly in `tests/orchestration/conftest.py`.

**Tech Stack:** Python 3.12, pydantic v2 frozen models, PydanticAI (existing agents, no tracing vendor; Braintrust is NOT used), psycopg 3, pytest. No new dependency.

**Spec:** [design.md](design.md) sections 3.3, 4.2, 8.1, 8.2, 8.5. Depends on 21-24 merged. 31/32 later modify `Workflow`/`SupportDeps`; `build_workflow` is the single adaptation point.

## Global Constraints

- Every function fully typed (`-> None` included), Pyright `standard` and ruff clean, imports at module top, f-strings only, `StrEnum` for enums, frozen pydantic models, classmethods instead of `format_x` functions, no `datetime.now` (`SimulationClock`), no inline imports.
- Functional tests on real seeded Postgres with scripted stub agents (`tests/orchestration/conftest.py`); zero LLM calls. If Postgres is down STOP and report.
- Verify: `uv run pytest <path> -v`, `uvx ruff check <paths>`, `uvx pyright <paths>`.
- Branch `design/41-customer-chat-view` worktree; commit per task; never merge, never push. Never read `.env` files.

## Review Focus

1. Replayed turn (same `message_id`) returns the same stored citations, no duplicate writes. -> Task 2.
2. Marker absent from the bundle is dropped, never invented. -> Task 2.
3. Injection refusal / agent-failure pause / clarification-escalation replies store zero citations. -> Task 2.
4. Duplicate `(slug, anchor)` passages yield one citation (best rerank). -> Task 2.
5. `build_workflow` result never shares a connection between services of different calls. -> Task 3.

---

### Task 1: Shared marker parsing in guardrails

**Files:**
- Create: `guardrails/citations.py`
- Modify: `guardrails/validator.py` (use the shared patterns, delete its private copies), `guardrails/__init__.py` (export)
- Test: `tests/guardrails/test_citations.py`

**Interfaces:**
- Consumes: the marker regexes now private in `validator.py` (`_KB_MARKER`, `_POLICY_MARKER`, `_TELEMETRY_MARKER`, `_ANY_MARKER`, `_KB_REF`).
- Produces: `MarkerKind(StrEnum)` (KB, POLICY, TELEMETRY); frozen `CitationMarker` (kind, ref); `extract_markers(message: str) -> tuple[CitationMarker, ...]` in order, deduped; `strip_markers(message: str) -> str` removing all three marker forms and collapsing the left-over double spaces.

- [ ] **Step 1:** Write one parametrized functional-style test in `test_citations.py`: a message with one KB, one policy and one telemetry marker, a repeat, and none; assert extracted kinds/refs and stripped text. Also assert the existing `tests/guardrails` validator suite is the regression net (no new validator tests).
- [ ] **Step 2:** Run it; expect FAIL (module missing).
- [ ] **Step 3:** Move the patterns into `citations.py`, implement the two functions, make `validator.py` import them (single source of truth, DRY).
- [ ] **Step 4:** Run `uv run pytest tests/guardrails -v`; expect all PASS.
- [ ] **Step 5:** Cleanup: ruff, pyright on `guardrails`; confirm no regex duplicated, no unused import/constant left in `validator.py`.
- [ ] **Step 6:** Commit `refactor(guardrails): shared citation marker parsing`.

---

### Task 2: Persist citations at turn end

**Files:**
- Modify: `orchestration/models.py` (add `Citation`), `orchestration/recorder.py` (`complete_turn` gains a `citations` argument forwarded instead of `()`), `orchestration/workflow.py` (`_finish` takes the `KnowledgeBundle | None`; `_answer` passes it)
- Test: `tests/orchestration/test_citation_persistence.py`

**Interfaces:**
- Consumes: Task 1 `extract_markers`; `KnowledgeBundle.retrieved_passages` (`slug`, `heading_anchor`, `heading`, `title`, `public_url`, `rerank_score`) and `referenced_policies` (`policy_id`, `title`); existing `StateStore.complete_turn(... citations: Sequence[dict[str, str]] ...)`.
- Produces: frozen `Citation` with `kind` (KB or POLICY), `ref`, `title`, `url`; classmethod `Citation.from_marker(marker: CitationMarker, bundle: KnowledgeBundle | None) -> Citation | None` (None when not in bundle or telemetry kind) and `to_row() -> dict[str, str]`; a pure helper on `Citation` building the tuple for a reply: `Citation.for_reply(reply: str, bundle: KnowledgeBundle | None) -> tuple[Citation, ...]`. Stored message `citations` rows carry keys `kind`, `ref`, `title`, `url` (url empty string for policies).

- [ ] **Step 1:** Write failing tests with the scripted harness: (a) stub resolution reply with KB and policy markers and a stub `KnowledgeBundle` holding both -> stored reply message has two citation rows with the passage `public_url`; (b) marker not in bundle -> row dropped; (c) two passages same slug+anchor -> one row, best rerank; (d) injection-blocked message, agent failure pause, clarification-exhausted reply -> empty citations; (e) retry with the same `message_id` -> stored reply and citations identical, message row count unchanged.
- [ ] **Step 2:** Run; expect FAIL.
- [ ] **Step 3:** Implement `Citation`, thread the bundle into `_finish` (default None for early returns), forward through `TurnRecorder.complete_turn`; `_replay` untouched (reads stored message).
- [ ] **Step 4:** Run `uv run pytest tests/orchestration tests/storage -v`; expect PASS (existing complete_turn callers updated, default `()` kept for system/pause paths).
- [ ] **Step 5:** Cleanup: ruff + pyright on `orchestration`; no unused parameter, no second dedupe code path.
- [ ] **Step 6:** Commit `feat(orchestration): persist reply citations`.

---

### Task 3: Shared runtime factory

**Files:**
- Create: `orchestration/runtime.py`
- Modify: `orchestration/__init__.py` (export), `tests/orchestration/conftest.py` (harness `workflow` uses `build_workflow` and swaps in scripted ports: DRY with production assembly)
- Test: `tests/orchestration/test_runtime.py`

**Interfaces:**
- Consumes: `settings.llm_model`; `run_triage`, `run_diagnostics`, `run_knowledge`, `run_resolution` (each takes `model: Model | None`); services constructors (`CustomerService(conn, clock)`, `TicketService(conn, clock)`, `TelemetryService(clock=)`, `RetrievalService(conn)`); `encoders.embed.load_embedder`, `encoders.rerank.load_reranker`.
- Produces: frozen dataclass `Services` (`store: StateStore`, `customers: CustomerService`, `tickets: TicketService`, `telemetry: TelemetryService`) and `build_services(connection: psycopg.Connection[Any], clock: SimulationClock) -> Services` (no `RetrievalService`, no encoder/LLM touched; reused by 42's reviewer app); `build_ports(model: str | Model | None = None) -> AgentPorts` binding the model into each callable (stdlib `functools.partial`, resolving the string via PydanticAI's own model inference, no tracing wrapper); `build_workflow(connection: psycopg.Connection[Any], clock: SimulationClock, ports: AgentPorts | None = None) -> Workflow` (composes `build_services`, adds `RetrievalService`, `SupportDeps`, ports; ports override for tests); `warm_models() -> None`.

- [ ] **Step 1:** Failing test: `build_services(conn, clock)` returns the four services with the encoder loaders monkeypatched to raise (proves none is touched); `build_workflow(conn, clock, scripted.ports)` runs one scripted turn end to end and a second call with a different connection works independently; `build_ports()` returns four callables without any network call (assert by constructing with the PydanticAI test model name, no key read).
- [ ] **Step 2:** Run; expect FAIL.
- [ ] **Step 3:** Implement the module; no module-level connection or service instance; `warm_models` only calls the two loaders.
- [ ] **Step 4:** Switch the harness to it; run `uv run pytest tests/orchestration -v`; expect PASS.
- [ ] **Step 5:** Cleanup: ruff + pyright; delete the now-duplicated assembly from conftest; confirm `orchestration/__init__` exports only what is used.
- [ ] **Step 6:** Commit `feat(orchestration): shared runtime factory`.
