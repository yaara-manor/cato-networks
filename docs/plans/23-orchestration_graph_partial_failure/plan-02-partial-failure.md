# Orchestration Partial Failure Handling Implementation Plan (Plan 2 of 2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The workflow degrades explicitly when telemetry or KB retrieval is down, refuses to guess, recovers on the next healthy turn, and survives an agent raising an exception.

**Architecture:** Degradation is a pure function of the statuses already on issue 7's `DiagnosticEvidence` and `KnowledgeBundle`, evaluated fresh every turn (no sticky flag). Disclosure text is deterministic and prepended by the workflow. "Refuse to guess" is enforced by the existing guardrails through `GroundingContext`, via issue 7's `run_resolution` validators; the workflow adds no second enforcement path.

**Tech Stack:** Same as Plan 1. No new dependencies.

**Spec:** `docs/plans/23-orchestration_graph_partial_failure/design.md` sections 5 and 7, with Plan 1 "Design Decisions" overrides. No brainstruct / Braintrust tracing; failures are recorded as `ERROR` rows in issue 6's `traces` table.

**Depends on:** Plan 1 complete.

## Global Constraints

Same as Plan 1 (typing, no inline imports, frozen models, tuples, f-strings, classmethod conversions, functional tests, no `datetime.now`, files under ~150 lines). Reuse: `tools.models.TelemetryStatus`, `retrieval.models.KBSearchStatus`, `guardrails.models.GroundingContext` / `CitationViolationKind`, issue 7 `DiagnosticEvidence.unavailable` (tuple of `UnavailableTool`) and `KnowledgeBundle.confidence_status`, issue 6 `TraceStatus.ERROR` and `AgentRole.ORCHESTRATOR`.

## Partial-failure semantics (fixed)

| Condition (this turn) | Notice | `escalation_offered` | Reply constraint |
|---|---|---|---|
| `evidence.unavailable` non-empty | telemetry notice | no | no telemetry values for unavailable tools |
| `bundle.confidence_status == UNAVAILABLE` | retrieval notice | yes | refusal grounding: no KB markers or technical claims |
| both | telemetry first, then retrieval | yes | both |
| `LOW_CONFIDENCE_REFUSAL` (SC-09) | none | per `ResolutionPlan.escalate_to_human` | refusal grounding |
| `NOT_FOUND` / `INVALID_ARGUMENT` tool results | none | no | agent reports "no data" itself |
| agent raises | none | no | fixed pause message, state intact |

Which `UnavailableTool.status` values count as an outage: only `TelemetryStatus.UNAVAILABLE`. Other non-OK statuses are listed by the agent but produce no notice. Notice repeats on every degraded turn (stateless, simplest; open question 1).

## Review Focus

1. Evidence from healthy tools kept while one tool is down (true partial result): the healthy tool's evidence is still citable, the down tool's marker is rejected.
2. Fabricated telemetry number (SC-01 `1024/1024`) with telemetry down: rejected by validators, reply is the canned handoff, not the number.
3. Resolution tries a `[kb:...]` marker while retrieval is down: rejected (`REFUSAL_BREACH`); a `[policy:POL-...]` citation (policies served from memory) still passes.
4. Source recovers on turn 2: no notice, KB citation accepted, nothing sticky in stored state.
5. Agent exception mid-turn after the customer message was saved: customer message and error trace persisted, reply is the pause message, stage back to `IDLE`, next turn works.

## File Structure

| File | Responsibility |
|---|---|
| `orchestration/models.py` (modify) | Add `DegradedSource` (`StrEnum`), `DegradationNotice` with `from_telemetry(unavailable: tuple[UnavailableTool, ...])` and `from_retrieval()` classmethods holding the fixed templates (matches architecture section 5 matrix wording); add `degradations` to `TurnResult`. |
| `orchestration/routing.py` (modify) | Add pure `derive_degradations(evidence: DiagnosticEvidence | None, bundle: KnowledgeBundle | None) -> tuple[DegradationNotice, ...]`. |
| `orchestration/workflow.py` (modify) | Call `derive_degradations` after the evidence step, pass notices into `compose_reply`, set `escalation_offered`; wrap the turn body once in the agent-failure handler. |
| `tests/orchestration/test_partial_failure.py` | All scenarios below. |

---

### Task 1: Degradation notices and derivation

**Files:** modify `orchestration/models.py`, `orchestration/routing.py`; test `tests/orchestration/test_partial_failure.py`.

**Interfaces:**
- Consumes: Plan 1 `TurnResult`, `compose_reply`; issue 7 contracts above.
- Produces: `DegradedSource`, `DegradationNotice(source, detail, customer_text)`, `derive_degradations(...)`. `detail` carries tool names and status only. Notice order is always telemetry then retrieval.

- [ ] **Step 1:** Write the failing tests using real `DiagnosticEvidence` / `KnowledgeBundle` objects: telemetry `UNAVAILABLE` -> exactly one telemetry notice with the exact template text; `NOT_FOUND` / `INVALID_ARGUMENT` only -> no notice; retrieval `UNAVAILABLE` -> retrieval notice; `LOW_CONFIDENCE_REFUSAL` -> no notice; both -> telemetry first; both inputs `None` -> empty.
- [ ] **Step 2:** Run `uv run pytest tests/orchestration/test_partial_failure.py -v`. Expected: FAIL.
- [ ] **Step 3:** Implement models and derivation.
- [ ] **Step 4:** Re-run. Expected: PASS.
- [ ] **Step 5:** Commit: `feat(orchestration): degradation notices`.

### Task 2: Wire notices, escalation offer and refusal enforcement into the workflow

**Files:** modify `orchestration/workflow.py`; test `tests/orchestration/test_partial_failure.py`; possibly modify issue 7's `ResolutionInput.grounding_context()` (see Step 3).

**Interfaces:**
- Consumes: Task 1 outputs, Plan 1 `Workflow`.
- Produces: `TurnResult.degradations`, `TurnResult.escalation_offered` set when a retrieval notice exists or the plan escalates. Reply text starts with notice texts.

- [ ] **Step 1:** Write functional tests (real guardrails, real store, real issue 7 `run_resolution` driven by a scripted PydanticAI `FunctionModel` so validators actually run; stubs for Triage / Diagnostics / Knowledge returning degraded contracts; a real `TelemetryService` on a `tmp_path` telemetry dir with no root `sites.json` for the telemetry-down case):
  - Telemetry down: notice present, Knowledge stub still called, scripted model first fabricating `1024/1024` then answering honestly -> final reply honest (one retry); fabricating twice -> canned handoff with `escalate_to_human`.
  - Telemetry partially down: healthy tool evidence quotable, `[telemetry:<down tool>]` rejected.
  - Retrieval down: notice, `escalation_offered`, `[kb:...]` rejected, policy-cited reply passes.
  - Both down: both notices in order.
  - SC-09 low confidence: no outage notice, refusal enforced.
  - `NOT_FOUND` site: no notice.
  - Recovery: turn 1 retrieval down, turn 2 healthy -> turn 2 has no notice and KB citation accepted.
- [ ] **Step 2:** Run the file. Expected: FAIL.
- [ ] **Step 3:** Implement in `workflow.py`. Verify against issue 7 that `ResolutionInput.grounding_context().telemetry_tools` excludes tools in `DiagnosticEvidence.unavailable` (issue 7 builds it from `inspected_tools`, which may include failed calls). If it does not, fix it in issue 7's `agents/models.py` with the one-line subtraction and cover it by the partial-down test; do not add a workflow-side check.
- [ ] **Step 4:** Re-run. Expected: PASS.
- [ ] **Step 5:** Commit: `feat(orchestration): partial failure handling`.

### Task 3: Agent exception boundary

**Files:** modify `orchestration/workflow.py`; test `tests/orchestration/test_partial_failure.py`.

**Interfaces:**
- Consumes: `canned.AGENT_FAILURE_PAUSE`, `TurnRecorder`, `TraceStatus.ERROR`, `AgentRole.ORCHESTRATOR`.
- Produces: `run_turn` catches `Exception` at exactly one site (around steps 2-5), logs via stdlib `logging`, records one error trace with the exception class name only (no message text, may contain customer data), appends the pause message as a system message, returns to `IDLE`, returns a `TurnResult` whose reply is the pause message. The ingestion step stays outside the handler so the redacted customer message and guard history are already saved.

- [ ] **Step 1:** Write tests: Diagnostics stub raises `RuntimeError` -> reply equals the pause constant, customer message persisted, one `ERROR` trace, stage `IDLE`, `guard_history` unchanged; next turn with a healthy stub succeeds on the same conversation.
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement the single handler.
- [ ] **Step 4:** Re-run full `tests/orchestration`. Expected: PASS.
- [ ] **Step 5:** Commit: `feat(orchestration): agent failure boundary`.

### Task 4: Docs, cleanup, lint, type check (final)

- [ ] **Step 1:** Update `docs/architecture/system-architecture-design.md` section 5 diagram and recovery matrix to the table above and the Plan 1 routing (no back-edge, no workflow-level OUTPUT_GUARD re-prompt); remove its Braintrust export mention if present. Add the next free ADR to `docs/overview/decisions.md`: hand-rolled sync workflow over `pydantic_graph`, stateless per-turn degradation, no Braintrust.
- [ ] **Step 2:** Mark `design.md` status "Implemented (see plan-01, plan-02)" and add a one-line pointer that the plans override sections 3, 4.3, 4.5, 5.4, 9.
- [ ] **Step 3:** Read all `orchestration/` files end to end; remove unused code (every `DegradedSource` member, model field and constant used and asserted by a test; every `ConversationStage` the workflow enters appears in some asserted `path`).
- [ ] **Step 4:** Run `uv run ruff check`, `uv run ruff format --check`, `uv run pyright orchestration`, then `uv run pytest tests/orchestration tests/guardrails -q`. Expected: clean and PASS. Grep for `datetime.now`, `braintrust`, inline imports in `orchestration/`.
- [ ] **Step 5:** Commit: `docs(orchestration): architecture, ADR, cleanup`.

## Unresolved Questions

1. Notice every degraded turn (chosen) or once per outage?
2. Retrieval down: offer escalation only (chosen) or auto-create ticket?
3. Does issue 7 already exclude unavailable tools from grounding? If not, we patch it here.
4. Opt-in live-LLM scenario test left to Phase 5 OK?
