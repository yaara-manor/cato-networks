# 04 — Rerank Threshold Calibration — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the placeholder `rerank_min_score = 0.0` with a measured threshold. The threshold must refuse off-domain questions while keeping the 35 answerable eval questions answerable, and the evidence goes into a committed report and ADR-005.

**Architecture:** A retrieval-only script, `eval/calibrate_threshold.py`. It builds `RetrievalService(min_score=-inf)`, so nothing is gated, and runs three question sets through `search_kb`, recording top-1 score, top-1 slug and latency:
- the 35 answerable questions
- 10 off-domain questions
- 2 partial-coverage probes.

A pure `choose_threshold` applies the design §4.3 rule to the answerable and off-domain scores only. `CalibrationReport.to_markdown` renders `docs/eval/threshold_calibration.md`. `main` alone does the I/O. The chosen value is then hard-set as the `core/config.py` default.

**Tech Stack:** Python 3.12, stdlib `statistics`/`math`/`time`, Pydantic v2, psycopg 3, pytest.

**Spec:** [design.md](design.md) §4.3 (revised gate scope: off-domain only; SC-09 is a partial-coverage probe), §5.1 refusal bullet, §6.

**Depends on:** plan 03 (`RetrievalService(connection, min_score)`, `search_kb`, `KBSearchResult.candidates`), merged into `p-1-4_kb-retrieval-policy`. If it is missing, STOP and report.

## Global Constraints

- Sync-only. Every function and method is fully annotated and passes Pyright `standard`. ruff clean. Imports go at the top. f-strings.
- New Pydantic models are frozen (`ConfigDict(frozen=True)`).
- No new dependencies. Percentiles use `statistics.quantiles`, the "just above" threshold uses `math.nextafter`, and timing uses `time.perf_counter`.
- Commands, not queries: only `main` reads files, writes the report or prints. Every other function is pure or a pure query.
- Tests are functional against the real DB and models. The single unit test (`choose_threshold`) is allowed as isolated decision math.
- Never read `.env`. If a `RERANK_MIN_SCORE` override is suspected (a test sees a threshold different from the code default), ask the user.
- Verify with `uv run pytest <path> -v`, `uvx ruff check <paths>` and `uvx pyright <paths>`.

## Branching

- Plan branch: `p-1-4-04_threshold-calibration`, created from `p-1-4_kb-retrieval-policy` after plan 03 is merged.
- Task branches: `p-1-4-04-t1_calibration-script`, then `p-1-4-04-t2_apply-threshold` (sequential: t2 needs t1's output). Merge each into the plan branch.
- Task 3 runs on the plan branch. Never merge to master, never create a worktree.

## Review Focus

1. **Off-domain and answerable scores overlap.** `choose_threshold` must still return a threshold that refuses every off-domain query. It reports the answerable questions it sacrifices, and never silently picks a midpoint that lets an off-domain query through. → Task 1 unit test (overlap case).
2. **Empty input sets or a malformed JSONL line** (a blank trailing line, a missing `question` key): blank lines are skipped, and a missing key raises `pydantic.ValidationError` through `model_validate_json`. Calibrating on a partial set must never happen silently. → The loader is too trivial for its own test; `choose_threshold` guards the empty sets (Task 1 test).
3. **An answerable question whose ungated result has no candidates** (all branches empty). Its top-1 score is `-inf` and it is listed in the report rather than crashing `max()`. → handled in `score_questions`; checked in the Task 1 functional smoke test.
4. **The threshold is rounded for `config.py`.** Rounding must go up, to 2 decimals, so every off-domain question is still refused after rounding. → Task 2 test runs every off-domain question through the default-threshold service.
5. **The four plan-03 confident questions (Q01, Q05, Q10, Q15)** must stay `CONFIDENT` under the new default. If one flips, STOP and report instead of lowering the threshold by hand. → Task 2 (re-run plan 03 tests).

---

### Task 1: Off-domain fixture + calibration script

**Files:**
- Create: `data/eval/out_of_coverage.jsonl`
- Create: `eval/__init__.py` (one-line package comment)
- Create: `eval/calibrate_threshold.py`
- Test: `tests/eval/test_calibrate_threshold.py`

**Interfaces:**
- Consumes:
  - `RetrievalService(connection, min_score=float("-inf"))`
  - `search_kb(query, top_k=1)`
  - `KBSearchResult.candidates[0].rerank_score` and `.slug`
- Produces, all in `eval/calibrate_threshold.py`:
  - `EvalQuestion`: frozen, fields `question_id: str`, `question: str`. Extra JSON keys are ignored.
  - `QueryScore`: frozen, fields:
    - `question_id: str`
    - `question_set: QuestionSet`, where `QuestionSet(StrEnum)` is `ANSWERABLE`, `OFF_DOMAIN` or `PARTIAL_COVERAGE`
    - `top1_score: float`, `top1_slug: str | None`, `latency_ms: float`.
  - `ThresholdDecision`: frozen, fields `threshold: float`, `separated: bool`, `refused_answerable: list[str]` (question ids).
  - `CalibrationReport`: frozen, fields `scores: list[QueryScore]`, `decision: ThresholdDecision`, and method `to_markdown() -> str`.
  - `load_questions(path: Path) -> list[EvalQuestion]`
  - `load_scenario_question(path: Path, scenario_id: str) -> EvalQuestion`. It maps `opening_message` to `question`, and raises `KeyError` when the scenario id is absent.
  - `score_questions(service: RetrievalService, questions: list[EvalQuestion], question_set: QuestionSet) -> list[QueryScore]`
  - `choose_threshold(answerable: Mapping[str, float], off_domain: list[float]) -> ThresholdDecision`. Answerable scores are keyed by question id, so refused ids can be reported.
  - `main() -> None`

- [ ] **Step 1: Write the fixture** `data/eval/out_of_coverage.jsonl`. It has 10 lines, each `{"question_id": "OOD01".."OOD10", "question": …}`, and covers:
  1. configuring VLANs on a Cisco Catalyst 9300 switch
  2. resetting a Microsoft 365 mailbox password
  3. setting up a Kubernetes ingress controller on AWS EKS
  4. the per-site list price of Cato licensing in 2027
  5. the discount for renewing a Cato contract for three years
  6. who won the 2026 FIFA World Cup
  7. a sourdough bread recipe
  8. replacing an iPhone battery
  9. Oracle database license audit rules
  10. how to file a US tax return extension
- [ ] **Step 2: Write the failing tests** in `tests/eval/test_calibrate_threshold.py`.
  - `test_choose_threshold_midpoint_when_separated`: answerable `{a: 3.0, b: 5.0}`, off-domain `[-4.0, 1.0]` → threshold `2.0`, `separated=True`, `refused_answerable=[]`.
  - `test_choose_threshold_refuses_all_off_domain_when_overlapping`: answerable `{a: 0.5, b: 5.0}`, off-domain `[-4.0, 1.0]` →
    - `separated=False`
    - `threshold > 1.0`
    - `threshold == math.nextafter(1.0, math.inf)`
    - `refused_answerable == ["a"]`.
  - `test_choose_threshold_rejects_empty_sets`: either set empty → `ValueError`.
  - `test_score_questions_smoke`: a real service with `min_score=-inf`, over Q01 plus OOD06 → two `QueryScore` rows, Q01 scoring higher than OOD06, `latency_ms > 0`.
- [ ] **Step 3: Run to confirm failure.** `uv run pytest tests/eval -v`. Expected: `ModuleNotFoundError: eval.calibrate_threshold`.
- [ ] **Step 4: Implement `eval/calibrate_threshold.py`.**
  - `choose_threshold`:
    - Guard both sets as non-empty (`ValueError`).
    - `gap_low = max(off_domain)`, `gap_high = min(answerable.values())`.
    - If `gap_high > gap_low`: threshold is the midpoint, `separated=True`.
    - Otherwise: threshold is `math.nextafter(gap_low, math.inf)`, `separated=False`.
    - `refused_answerable` = the sorted ids whose score is below the threshold.
  - `score_questions`: per question, time `search_kb(question, top_k=1)` with `perf_counter`. The top-1 score is `candidates[0].rerank_score`, or `float("-inf")` when there are no candidates (Review Focus 3).
  - `load_questions`: read lines, skip blank ones, and `EvalQuestion.model_validate_json` each.
  - `CalibrationReport.to_markdown`:
    - a header with the date and the `settings.reranker_model`/revision
    - the decision (threshold to 3 decimals, separated or overlapping, refused ids)
    - min/max per set
    - p50/p95 latency over all queries, via `statistics.quantiles(n=20)` (indexes 9 and 18)
    - one table sorted by set, then score descending (id, set, top-1 score, top-1 slug, latency ms)
    - a short paragraph restating that partial-coverage rows are informational (design §4.3).
  - `main`:
    - connect with `settings.database_url`
    - load the three sets: questions, the fixture, and the partial-coverage probes (`load_scenario_question(scenarios.jsonl, "SC-09-no-kb-coverage")` plus a literal roadmap probe `EvalQuestion("PC-ROADMAP", "What is on the Cato roadmap for AI features next year?")`)
    - score them and decide on answerable vs off-domain only
    - write `REPO_ROOT / "docs/eval/threshold_calibration.md"` (create the folder)
    - print the threshold.
  - Runs as `uv run python -m eval.calibrate_threshold`.
- [ ] **Step 5: Run and confirm pass.** `uv run pytest tests/eval -v`. Expected: all PASS.
- [ ] **Step 6: Clean-code gate.** `uvx ruff check eval tests/eval` and `uvx pyright eval`. Both clean. No function does both computing and writing.
- [ ] **Step 7: Commit** on `p-1-4-04-t1_calibration-script`: `feat(eval): rerank threshold calibration script + off-domain fixture`.

---

### Task 2: Run calibration, apply threshold, lock it with tests

**Files:**
- Generate: `docs/eval/threshold_calibration.md`
- Modify: `core/config.py` (the `rerank_min_score` default)
- Test: `tests/retrieval/test_search_kb.py`

**Interfaces:**
- Consumes: Task 1's `main` and `load_questions`.
- Produces: `settings.rerank_min_score` set to the calibrated value, which `RetrievalService` picks up by default.

- [ ] **Step 1: Write the failing test** in `tests/retrieval/test_search_kb.py`: `test_off_domain_questions_are_refused`.
  - Parametrized over every line of `data/eval/out_of_coverage.jsonl`, loaded with `eval.calibrate_threshold.load_questions`.
  - It uses the default-threshold service and asserts `LOW_CONFIDENCE_REFUSAL`, `passages == []` and non-empty `candidates`.
- [ ] **Step 2: Run to confirm failure.** `uv run pytest tests/retrieval/test_search_kb.py -k off_domain -v`. Expected: at least one FAIL under the placeholder `0.0` (the pricing probe scored ~0.3 pre-implementation).
- [ ] **Step 3: Run calibration.** `uv run python -m eval.calibrate_threshold`. Read the report. Check each answerable top-1 slug is plausible, and list any that look off-target in the commit message.
  - If `separated=False` and more than 3 answerable questions are refused, STOP and report the table to the user. Do not apply.
- [ ] **Step 4: Apply.** Set the `rerank_min_score` default in `core/config.py` to the threshold rounded **up** to 2 decimals (`math.ceil(x * 100) / 100`, done by hand). Add a trailing comment pointing to `docs/eval/threshold_calibration.md`.
- [ ] **Step 5: Run and confirm pass.** `uv run pytest tests/retrieval tests/eval -v`. Expected: all PASS, including Q01/Q05/Q10/Q15 still `CONFIDENT` (Review Focus 5).
- [ ] **Step 6: Commit** on `p-1-4-04-t2_apply-threshold`: `feat(config): calibrated rerank_min_score + off-domain refusal tests`.

---

### Task 3: ADR, global cleanup, review (plan branch)

**Files:**
- Modify: `docs/overview/decisions.md` ADR-005. Add a "Threshold calibration" bullet covering:
  - the chosen value, whether the sets separated, and the refused answerable count
  - p50/p95 latency
  - the SC-09 finding: partial coverage passes the gate, and refusing roadmap dates is agent grounding.
- Modify: `docs/architecture/system-architecture-design.md` §7, the threshold bullet: the value, plus a link to the report.

- [ ] **Step 1: Merge** both task branches into `p-1-4-04_threshold-calibration`. Run `uv run pytest -v`; everything passes.
- [ ] **Step 2: Apply the doc edits** listed above.
- [ ] **Step 3: Review the plan diff** with `/ponytail:ponytail-review`, then with `/anthropic-skills:thermo-nuclear-code-quality-review`. Fix accepted findings and re-run the suite.
- [ ] **Step 4: Global cleanup (design §6)**, over the whole feature diff `git diff master...HEAD`:
  - Read every touched file end-to-end.
  - `kbindex/embed.py` and `retrieval/rerank.py` are gone.
  - `_STOPWORDS`, `_symptom_stems`, `_shares_keywords` and `import re` are gone from `ticket_service.py`.
  - No `'simple'` tsvector outside `20260929_1500_kb-schema.sql` and the new migration's guard. No `kbindex.embed` or `retrieval.rerank` imports.
  - `uvx ruff check .` and `uvx pyright encoders core services db kbindex retrieval eval` are clean. Every function is fully typed, with no unused imports or helpers.
  - `README.md` and the architecture tree mention `encoders/`, `retrieval/service.py`, `retrieval/models.py` and `eval/calibrate_threshold.py`.
- [ ] **Step 5: Commit** `chore(plan-04): ADR-005 calibration, global cleanup`.

## Unresolved Questions

1. Is the gate scope OK: off-domain refusal only, with SC-09 roadmap-date refusal left to the agent's grounding (design §4.3)?
2. Should the stop condition be "more than 3 answerable refused" (Task 2, Step 3), or a different tolerance?
