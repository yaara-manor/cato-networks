# experiments/

Purpose: decide how to improve KB retrieval and the answer/refuse decision in this repo, by testing
Direction A (smarter retrieval, relative gates, no LLM), B (LLM query rewrite) and D (agent as tool user)
on a fixed 89-query subset with labelled relevance. Everything here is read-only against the main repo
and the Postgres KB; nothing under `experiments/` is imported by production code.

## Layout
- `data/queries.jsonl` — 89 queries (35 ANS, 12 SCN, 12 ADJ, 10 OOD, 20 TKT); regenerate with `build_queries.py`.
  `data/adj_notes.md` explains why each ADJ query is unanswerable from the KB.
- `lab/retrieve.py` — lexical/dense/fusion/rerank/`clean_query`/`search_current`; `lab/metrics.py` — hit@k, MRR, nDCG@5, answer/refuse P/R/F1.
- `tools/search_kb_cli.py`, `tools/validate_answer.py` — tool and grounding check used by Direction-D agent subagents.
- `cache/` — LLM-produced and run outputs (see below).

## Running notebooks
Postgres must be up (`postgresql://kb:kb@localhost:5432/kb`; `pg_ctlcluster 18 main start` if refused). From the repo root:

    uv run --with nbconvert --with nbformat --with ipykernel --with pandas --with matplotlib \
        jupyter nbconvert --to notebook --execute --inplace experiments/<notebook>.ipynb

Do not edit `pyproject.toml`/`uv.lock`. In notebooks, put `experiments/` and the repo root on `sys.path`, then `from lab.retrieve import ...`.
Override the DB with env `KB_DSN`.

## LLM-produced caches
Sonnet subagents (never called from library code) write JSON under `cache/` so reruns are free:
query rewrites (Direction B), relevance judgments, and Direction-D runs in `cache/d_runs/<run_id>.{searches,result}.json(l)`
(searches are logged by `search_kb_cli.py`, budget via env `SEARCH_BUDGET`, default 3). Delete a cache file to regenerate it.
