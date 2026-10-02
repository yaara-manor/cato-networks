# Agent Contracts, SupportDeps & Shared Runner Implementation Plan (22 / plan 1 of 4)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. User rule: this plan has no code lines; write code from the words, signatures and I/O below.

**Goal:** Land every agent contract, `SupportDeps`, prompt loader, agent factory, message-history extractors and one shared failure-safe runner, so plans 2-4 only add per-role tools, prompts and assembly.

**Architecture:** Frozen Pydantic contracts in `agents/models.py` (LLM-facing output vs code-assembled output; assembly = classmethods on the target class). `agents/base.py` holds deps + factory + prompt loader; `agents/runner.py` holds the single `run_role` (sync `run_sync`, latency, usage, `UnexpectedModelBehavior` to fallback). No DB writes, no tracing library.

**Tech Stack:** pydantic-ai 2.51 (already in `pyproject.toml`), pydantic v2, psycopg (existing services), pytest. No new dependencies.

**Spec:** `docs/plans/22-specialized_agent_contracts/design.md` (issue #7). Siblings: `21-agent_state_machine/design.md`, `23-orchestration_graph_partial_failure/design.md`.

## Design Decisions (up front; they override the design where they differ)

1. **No brainstruct anywhere.** Design/architecture text mentioning it is superseded. Tracing = PydanticAI's own data: `result.all_messages()` (tool calls/returns) + `result.usage()` (`input_tokens`, `output_tokens`, verified present on 2.51 `RunUsage`) + `time.perf_counter`. No OpenTelemetry/Logfire `instrument` call. Persistence of traces is plan 21's `StateStore` (`TraceRecord.from_agent_trace`, `ToolCallRecord`); agents write nothing to the DB.
2. **`AgentTrace` ownership.** Issue 21 (§7) owns *new fields* on `AgentTrace` (input, output, status, error, retrieval_scores, cost_usd, parent_trace_id). Issue 22 only adds one classmethod `AgentTrace.from_run` that fills the five existing fields (`agent_role`, `tool_calls`, `latency_ms`, `prompt_tokens`, `completion_tokens`) plus `cost_usd`, computed with the already-installed `genai_prices` (transitive dep of pydantic-ai, no new dependency); `cost_usd` is `None` when the model is unknown. 21's fields must have defaults. Merge order: 21 -> 22 -> 23. `tool_calls` stays `list[dict[str, Any]]` with keys `tool_name`, `arguments`, `status`, `result` (envelope dump) so 21's `ToolCallRecord.from_envelope` can consume it. Retrieval scores for traces: orchestrator reads `KnowledgeBundle.candidates`.
3. **`SupportDeps` is owned by 22** (`agents/base.py`); 21 does not define it, 23 only constructs and passes it. Signature of every runner: `run_<role>(Input, SupportDeps)`. No builder function (YAGNI): the orchestrator constructs it per turn; tests use one conftest fixture.
4. **Sync vs async.** 22 ships sync `run_<role>()` (`agent.run_sync`, sync tools, matches sync psycopg services). 23's agent ports are async `Protocol`s: 23 adapts with `asyncio.to_thread` at the boundary (21 §1 already prescribes this). 22 contains no async code. Caveat: one psycopg connection must not be used by two threads at once; turns are sequential so this holds.
5. **Contract seams with 23.** Triage returns `TriageResult` (superset of 23's `TriageDecision`; 23 stores `result.decision`). `DiagnosticEvidence` has the field `unavailable_tools: tuple[UnavailableTool, ...]` (every non-`OK` result) for 23's partial-failure handling. `KnowledgeBundle` has `needs_more_telemetry: bool` (LLM judgement in `KnowledgeFindings`, copied into the bundle) for 23's Diagnostics <-> Knowledge back-edge capped at 2 rounds. Resolution's extra inputs from 23 (degradation notices, prior violations) are not added: output-validator retry inside the agent replaces the orchestrator re-prompt (design §4.4).
6. **LLM decides, code records** exactly as design §1. Only judgement fields are `output_type`; evidence, passages, policies, SLA, repeat contact, identity are assembled from message history in code.
7. **Retry exhaustion reason is a fixed string** ("output validation retries exhausted" / "model failure"), not violation kinds: `UnexpectedModelBehavior` carries no structured violations. Smaller than the design; violation details stay visible in the retry prompts inside the message history.
8. **Layout hygiene.** `agents/models.py` holds shared types + all contracts (est. under 300 lines; split into an `agents/contracts/` package only if it passes ~350). Prompts under `prompts/` (new dir at repo root).

## Global Constraints

- Python fully typed: every parameter and return, `-> None` included; Pyright `standard` clean; no bare `list`/`dict`.
- No inline imports; imports at module top.
- Enums are `StrEnum` (matches `tools/models.py`, `guardrails/models.py`); reuse `TicketPriority` / `AccountTier` Literals from `core/models.py`. All contract models subclass one frozen `_AgentModel`; collections are tuples. (User's `AtiIntEnum`/`AtiBaseModel` do not exist in this repo; design §2 documents this.)
- f-strings or named placeholders only for string building.
- One responsibility per function; conversions are classmethods on the target class, not `format_x` functions.
- Tests are functional/integration with scripted models (`FunctionModel`/`TestModel` from `pydantic_ai.models`); real Postgres seed and real services where a service is involved; unit tests only for the status truth table.
- Zero LLM cost in CI; no network.
- `settings.llm_model` is the one model; factories accept an optional `Model` override.

## Review Focus

- Empty message history (model answered without any tool call): extractors return empty tuples, no exception; tested in Task 3.
- `UnexpectedModelBehavior` from the model: `run_role` returns a fallback outcome, never raises; transport errors (`ModelAPIError`) propagate; tested in Task 3.
- Duplicate passages across two searches (same `passage_id`): deduplicated, highest `rerank_score` kept; tested in plan 3.
- `identity.account is None`: contracts allow `None` SLA/repeat contact; tested in Task 1.
- Prompt file missing/blank: `load_prompt` raises a clear error at build time, not at first request; tested in Task 2.

---

## File Structure

- `agents/models.py` (modify): keep `AgentTrace`; add `from_run` classmethod; add `_AgentModel`, `TurnSender`, `ConversationTurn`, `AgentRun[T]`, and all role contracts from design §3 (inputs, LLM outputs, assembled outputs, `Intent`, `SupportActionKind`, `SupportAction`, `ResolutionPlan`, `UnavailableTool`).
- `agents/base.py` (create): `SupportDeps` (22 owns it), `load_prompt`, `build_agent`.
- `agents/messages.py` (create): `tool_returns`, `tool_call_dicts` (message-history extractors).
- `agents/runner.py` (create): `RoleOutcome`, `run_role`.
- `agents/__init__.py` (modify, plan 4): re-exports only.
- `prompts/` (create dir; files arrive in plans 2-4).
- `tests/agents/conftest.py` (create): DB connection, real services, `make_deps` fixture, a `scripted_model` helper (FunctionModel replaying scripted tool calls then a final output; adapt the shape of `tests/experiments/exp_helpers.scripted_model`, do not import from `experiments`).
- `tests/agents/test_contracts.py`, `tests/agents/test_runner.py` (create).

## Tasks

### Task 1: Shared contracts and `AgentTrace.from_run` declaration

**Files:** modify `agents/models.py`; create `tests/agents/test_contracts.py`.

**Interfaces:**
- Produces: all types named in design §3 with these decisions: `AgentRun[T]` generic frozen model (`output: T`, `trace: AgentTrace`); `TriageResult.scoping_question` property (identity's deterministic question wins over the model's); `DiagnosticEvidence.has_anomaly` property and `unavailable_tools` field; `KnowledgeBundle.needs_more_telemetry` field; `TriageInput` carries `identity: CallerIdentity` (no email / session account id); `ResolutionInput.grounding_context() -> GroundingContext` built only from successful tool results (telemetry tools exclude `unavailable_tools`); `SupportAction.to_proposed_action(target_account_id: str) -> ProposedAction | None` driven by one module-level mapping from `SupportActionKind` to `guardrails.ActionType` (absent kinds map to `None`).
- `DiagnosticEvidence.from_tool_results` and `KnowledgeBundle.from_tool_results` are classmethods; only fields/properties here, bodies in plans 3.

- [ ] **Step 1: Failing test** `grounding_context()`: build a `ResolutionInput` per knowledge status (CONFIDENT with one passage and one policy, LOW_CONFIDENCE_REFUSAL, UNAVAILABLE, `knowledge=None`) using real `RetrievedPassage` / `PolicyDocument` objects from the seeded DB (reuse the `connection` fixture pattern in `tests/retrieval/test_search_kb.py`); assert `kb_refs` (slug, `heading_anchor`), `policy_ids`, `telemetry_tools`, and `is_refusal` true only for the two non-confident statuses.
- [ ] **Step 2: Failing test** `to_proposed_action` per `SupportActionKind`: CREDIT / MFA_RESET / VERDICT_OVERRIDE / CLOSE_TICKET / PAGE_ON_CALL map to the same-named `ActionType` with the passed `target_account_id` and payload; CREATE_TICKET / UPDATE_TICKET return `None`; feed the CREDIT result into `guardrails.check_action` with a verified-admin identity and assert `GateOutcome.REQUIRE_APPROVAL`.
- [ ] **Step 3a: Failing test** `grounding_context()` with a tool listed in `unavailable_tools`: absent from `telemetry_tools`.
- [ ] **Step 3: Failing test**: models frozen (assignment raises); `TriageResult` with `identity.account=None` accepts `sla=None`, `repeat_contact=None`; `scoping_question` precedence.
- [ ] **Step 4:** Run `uv run pytest tests/agents/test_contracts.py -v`; expect FAIL (imports missing).
- [ ] **Step 5: Implement** in `agents/models.py`, reusing `services.models` (`CallerIdentity`, `SLADeadlines`, `RepeatContactResult`), `tools.models` (`TelemetryEvidence`, `TelemetryStatus`), `retrieval.models` (`RetrievedPassage`, `PolicyDocument`, `KBSearchStatus`), `guardrails` (`GroundingContext`, `ProposedAction`, `ActionType`), `core.models`. Redefine none of them.
- [ ] **Step 6:** Run the file; expect PASS.
- [ ] **Step 7: Commit** `feat(agents): role contracts`.

### Task 2: `SupportDeps`, `load_prompt`, `build_agent`, test fixtures

**Files:** create `agents/base.py`, `tests/agents/conftest.py`, start `tests/agents/test_runner.py`.

**Interfaces:**
- `SupportDeps` frozen dataclass per design §3.1 (clock `core.clock.SimulationClock`, customers `CustomerService`, tickets `TicketService`, telemetry `TelemetryService`, retrieval `RetrievalService`, identity `CallerIdentity`, guard_history `SessionGuardHistory`, approved_actions `frozenset[ActionType]`, grounding `GroundingContext | None = None`).
- `load_prompt(name: str) -> str`: `functools.cache` read of `settings.repo_root / "prompts" / f"{name}.md"`; `FileNotFoundError` if absent, `ValueError` if blank.
- `build_agent(role_prompt: str, output_type: type[O], model: Model | None = None) -> Agent[SupportDeps, O]`: model defaults to `settings.llm_model`; instructions = prompt text plus a dynamic callback returning `deps.guard_history.agent_context_note()`. Before writing, introspect the 2.51 API once (`uv run python -c`) for: instructions accepting a callable, retry arguments (`retries`, output retry budget), `Agent.output_validator`; do not guess names.

- [ ] **Step 1: Failing test** `load_prompt`: monkeypatch `settings.repo_root` to a tmp dir; missing and blank files raise; present returns text.
- [ ] **Step 2: Failing test** guard note: agent over a recording `FunctionModel`; with a `SessionGuardHistory` holding a blocked injection verdict the note text reaches the model; with empty history it does not.
- [ ] **Step 3:** Run `uv run pytest tests/agents/test_runner.py -v`; FAIL. Implement `agents/base.py`; PASS.
- [ ] **Step 4: conftest**: session-scoped psycopg connection (pattern from `tests/retrieval/test_search_kb.py`); real `CustomerService`, `TicketService`, `TelemetryService`, `RetrievalService` built from it (read their constructors in `services/*.py`, `tools/telemetry.py`, `retrieval/service.py` first) with one frozen `SimulationClock`; function-scoped `make_deps(email, account_id, **overrides) -> SupportDeps` calling `customers.authenticate_caller`; `scripted_model(calls, final)` helper.
- [ ] **Step 5: Commit** `feat(agents): SupportDeps, prompt loader, agent factory`.

### Task 3: Message extractors and `run_role`

**Files:** create `agents/messages.py`, `agents/runner.py`; add `AgentTrace.from_run` body in `agents/models.py`; extend `tests/agents/test_runner.py`.

**Interfaces:**
- `tool_returns(messages: list[ModelMessage], tool_name: str) -> tuple[Any, ...]`: `ToolReturnPart.content` of that tool in order (PydanticAI keeps the raw returned object; Step 1 proves it for a Pydantic return).
- `tool_call_dicts(messages: list[ModelMessage]) -> list[dict[str, Any]]`: pairs each `ToolCallPart` with its `ToolReturnPart` by `tool_call_id` into `{tool_name, arguments, status, result}` (status from the envelope's `status` attribute when present, else `"OK"`; result `model_dump(mode="json")`).
- `AgentTrace.from_run(role: str, messages: list[ModelMessage], usage: RunUsage, latency_ms: int, model_name: str | None) -> AgentTrace`; `cost_usd` via `genai_prices` (read its API once with `uv run python -c` before use), `None` when the model is unknown.
- `RoleOutcome[O]` frozen dataclass: `output: O | None`, `messages: tuple[ModelMessage, ...]`, `trace: AgentTrace`.
- `run_role(agent, prompt: str, deps: SupportDeps, role: str) -> RoleOutcome[O]`: times with `perf_counter`, calls `run_sync`, builds the trace; catches only `UnexpectedModelBehavior`; transport errors (`ModelAPIError`, `ModelHTTPError`) propagate (backoff/fallback model belong to 23 per design §4).

- [ ] **Step 1: Failing test**: scripted model calls a real tool returning a real `KBSearchResult` (real `RetrievalService.search_kb` on the Q10 question, text read from `data/eval/questions.jsonl` like `tests/retrieval/test_search_kb.py`) then a final output; `tool_returns` yields the typed `KBSearchResult` instance (not dict/str); `tool_call_dicts` has one entry with `status == "CONFIDENT"`.
- [ ] **Step 2: Failing tests**: invalid output beyond the retry budget gives `output is None` and a trace with role set, no exception; `ModelHTTPError` propagates; no-tool-call run gives empty tuples; `latency_ms >= 0`; token counts equal the `FunctionModel` usage; `cost_usd` is `None` for the unknown scripted model and set for a known model name.
- [ ] **Step 3:** Run; FAIL. Implement; PASS.
- [ ] **Step 4: Commit** `feat(agents): message extractors and shared runner`.

### Task 4: Cleanup, lint, type check

- [ ] Run the repo's ruff and pyright configs from `pyproject.toml` over `agents` and `tests/agents`; fix all findings.
- [ ] Grep for unused imports, functions, contract fields; every model and every `SupportActionKind` / `Intent` member must be used by a later plan or test; delete leftovers (final re-check after plan 4).
- [ ] Grep: no `brainstruct`, no inline imports, no `datetime.now` in `agents/`.
- [ ] Commit `chore(agents): lint and types`.

## Unresolved Questions

None.

Decisions recorded:
- Failure-path messages: `run_role` wraps `run_sync` in PydanticAI `capture_run_messages()`, which keeps the message list even when `UnexpectedModelBehavior` is raised; fallbacks (design §4.2, §4.3) use it. Task 3 test proves it with a scripted tool call followed by invalid output; if the installed 2.51 API differs, fall back to `messages=()` and weaken only those fallbacks.
- Single `settings.llm_model` for all roles; per-role split not added.
- Opt-in live-LLM smoke test is owned by plan 04 Task 3.
