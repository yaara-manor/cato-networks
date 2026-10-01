# experiments/

Purpose: decide how to improve KB retrieval and the answer/refuse decision in this repo, by testing
Direction A (smarter retrieval, relative gates, no LLM), B (LLM query rewrite) and D (agent as tool user)
on a fixed 89-query subset with labelled relevance. Everything here is read-only against the main repo
and the Postgres KB; nothing under `experiments/` is imported by production code.

## Layout
- `data/queries.jsonl` — 89 queries (35 ANS, 12 SCN, 12 ADJ, 10 OOD, 20 TKT); regenerate with `build_queries.py`.
  `data/adj_notes.md` explains why each ADJ query is unanswerable from the KB.
- `lab/retrieve.py` — lexical/dense/fusion/rerank/`clean_query`/`search_current`; `lab/metrics.py` — hit@k, MRR, nDCG@5, answer/refuse P/R/F1.
- `llm/` — LLM runners (default `openai:gpt-5-nano`) via pydantic-ai: `prompts.py`, `rewrite.py` (Direction B), `agent_d.py` (Direction D), `judge.py`, shared `common.py`.
- `run_variants.py` (retrieval variants, no LLM), `build_pools.py` (judging pools), `run_all.sh` (the whole pipeline in order).
- `cache/` — LLM-produced and run outputs (see below).

## Notebooks (`notebooks/`, read top to bottom)
Each notebook states its required caches at the top and ends with a RESULT TABLE. They only read `cache/` (override the
directory with env `EXPERIMENT_CACHE_DIR`) and never call an LLM; a missing cache prints `Run step first: <command>` and the dependent
cells are skipped, so every notebook always executes end-to-end. Shared helpers: `lab/notebook_utils.py`.
- `01_real_tickets_current_pipeline.ipynb` - current pipeline on the 89 queries, confident-but-wrong tickets, "Result boundaries explained" (needs DB; judgments optional).
- `02_fusion_merging.ipynb` - RRF / linear fusion, weight study, lexical-vs-dense overlap (needs `runs/FUS_*`; judgments for metrics).
- `03_direction_a_relative_gates.ipynb` - A_clean and relative gates (margin, z-score, agreement) (runs; judgments for real labels).
- `04_direction_b_rewrite.ipynb` - LLM rewrite, router accuracy, gates on B (`rewrites.json`, `runs/B_*`).
- `05_direction_d_agent_tool_user.ipynb` - agent variants (`d_runs/`, `judgments.json`).
- `06_results_and_threshold.ipynb` - the comparison table, recommendation rule, safety-floor threshold and ADR-007 text.
Order after the LLM steps: `run_all.sh`, then re-execute notebooks 01-06. Without `judgments.json` gate sweeps use a provisional label
(ANS answerable, OOD/ADJ unanswerable) and say so.

## Running notebooks
Postgres must be up (`postgresql://kb:kb@localhost:5432/kb`; `pg_ctlcluster 18 main start` if refused). From the repo root:

    uv run --with nbconvert --with nbformat --with ipykernel --with pandas --with matplotlib \
        jupyter nbconvert --to notebook --execute --inplace experiments/<notebook>.ipynb

Do not edit `pyproject.toml`/`uv.lock`. In notebooks, put `experiments/` and the repo root on `sys.path`, then `from lab.retrieve import ...`.
Override the DB with env `KB_DSN`.

## Running the LLM steps (locally, needs your key)
The runners use an LLM through pydantic-ai (default `openai:gpt-5-nano`; any pydantic-ai model id works via `EXPERIMENT_LLM_MODEL` / `EXPERIMENT_JUDGE_MODEL`); nothing here runs in CI and tests never call a real model.
Put `OPENAI_API_KEY` (or `GEMINI_API_KEY` for google models) in your local `.env`, then from the repo root:

    uv run --env-file .env python -m experiments.llm.rewrite --dry-run     # counts only, no key needed
    uv run --env-file .env python -m experiments.llm.rewrite --limit 3     # try 3 queries first
    uv run --env-file .env python -m experiments.llm.rewrite
    uv run --env-file .env python -m experiments.llm.agent_d --variant d_hidden_b3
    uv run python -m experiments.run_variants
    uv run python -m experiments.build_pools
    uv run --env-file .env python -m experiments.llm.judge
    uv run --env-file .env python -m experiments.llm.judge --sample-audit 20
    bash experiments/run_all.sh [--dry-run]                                  # everything, in order

Common flags (rewrite, agent_d, judge): `--limit N` (at most N not-yet-cached items), `--ids Q01,Q02`, `--concurrency 4`,
`--dry-run`. Runs are resumable: cached results are skipped, so rerunning after a crash or a 429 storm continues where it
stopped; delete a cache file to regenerate it. Calls use temperature 0 and retry 429/5xx/transport errors with exponential
backoff (6 attempts). A query that still fails is reported on stderr and the process exits 1; it is not cached.
Models: `EXPERIMENT_LLM_MODEL` (rewrite + agent, default `settings.llm_model`) and `EXPERIMENT_JUDGE_MODEL` (judge, same default).
Tests: `uv run pytest tests/experiments` (offline: pydantic-ai `TestModel`/`FunctionModel` plus the real local DB).

## Caches (`cache/`)
- `rewrites.json` — `{query_id: {is_kb_question, intent, search_queries (<=3), model, usage, latency_s, ts}}`.
- `d_runs/<variant>/<query_id>.json` — `{query_id, variant, decision, final_decision, citations, invalid_citations, answer_text,
  searches: [{query, passage_ids, scores}], n_searches, usage, latency_s, model, ts}`. `final_decision` is the grounding-checked
  decision: an ANSWER whose citations are empty or not all returned by this run's searches becomes NOT_IN_KB.
  Variants (defined in `llm/agent_d.py`): `d_hidden_b3` (main: scores hidden, 3 searches, top 5), `d_shown_b3`, `d_hidden_b1`,
  `d_hidden_b3_k3`, `d_hidden_b3_k10`. Scores are always logged; `show_scores` only controls what the agent sees.
- `runs/<name>.json` — `{query_id: {latency_ms, results: [top-20 {passage_id, slug, heading, score, rank}]}}`, no bodies.
  Names: `R0_lex`, `R1_dense`, `R2_rrf`, `R3_current` (production), `A_clean`, `B_rewrite_intent`, `B_rewrite_orig` (only if
  `rewrites.json` exists; no sub-queries falls back to the original message), and the fusion study
  `FUS_rrf_wl{0.25,0.5,1,2,4}` / `FUS_lin_wl{0,0.25,0.5,0.75,1}`, each also as `...+rerank` (rerank of the fused top 20).
  Scores are not comparable across variants (RRF, min-max blend, cosine, ts_rank_cd, cross-encoder logits).
- `passages.json` — `{passage_id: {slug, heading, body<=1200}}`, git-ignored (too big to commit; rebuilt by `run_variants`).
- `pools.json` — `{query_id: [passage_id]}`: union of each variant's top 10 and every agent search.
- `judgments.json` — `{query_id: {passage_id: {grade 0|1|2, reason}}}`; `judge_calls.jsonl` (git-ignored) has per-call model/usage/latency.
  The judge sees the query and one passage (full body, <=3000 chars); never scores, ranks or variant names.

## Expected calls and cost (89 queries; approximate, unmeasured)
- rewrite: 89 calls, about 0.3k input / 0.1k output tokens each (~30k tokens total).
- agent_d: per query about 2-4 model requests (one per search plus the final answer); input grows with each search to
  roughly 2-5k tokens per request (5 passages of <=500 chars each; k10 about double). Main run ~300 requests, ~0.5-1M input tokens.
  All five variants together ~1,200 requests, ~3-4M input tokens. `d_hidden_b1` is about 2 requests per query.
- judge: one call per pooled pair. The pool is the union of ~30 variants' top 10, which overlap heavily; I expect roughly
  30-60 pairs per query, so about 3-5k calls at ~0.6-1k input tokens each (~3-5M input tokens). `build_pools` prints the real number;
  `judge --dry-run` prints the pending calls.
- Total order of magnitude: ~5-6k calls, ~7-10M input tokens. On a Flash-class model that is likely single-digit dollars, but
  check the current price of your model; I did not verify it. Wall-clock at concurrency 4 is roughly 1-2 hours, dominated by the judge.

## Committed retrieval runs
`cache/runs/` (non-LLM variants, 89 queries) is committed so notebooks 01-03 work without the ~40 min recompute.
Its `latency_ms` values were measured while other jobs competed for CPU, so they are inflated: rerun
`uv run python -m experiments.run_variants` (after deleting `cache/runs/`) before trusting latency comparisons.
