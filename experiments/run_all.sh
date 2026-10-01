#!/usr/bin/env bash
# Full experiment pipeline. Run from the repo root with a local .env holding OPENAI_API_KEY:
#
#     bash experiments/run_all.sh            # dry-run the LLM steps, then run everything
#     bash experiments/run_all.sh --dry-run  # only print call counts, make no calls
#
# Cost (89 queries, approximate; the judge step dominates and its exact count is printed by build_pools):
#   rewrite          89 calls
#   agent_d          5 variants, about 2-4 model requests per query each (main run d_hidden_b3: ~300 requests)
#   judge            one call per (query, passage) pair in the pools: expect a few thousand calls
# Every step is resumable (cached results are skipped), so an interrupted run can simply be restarted.
# Point EXPERIMENT_LLM_MODEL / EXPERIMENT_JUDGE_MODEL at another model id to override settings.llm_model.
set -euo pipefail
cd "$(dirname "$0")/.."

RUN="uv run --env-file .env python -m"
VARIANTS=(d_hidden_b3 d_shown_b3 d_hidden_b1 d_hidden_b3_k3 d_hidden_b3_k10)
DRY="${1:-}"

echo "== call counts (dry run) =="
$RUN experiments.llm.rewrite --dry-run
for v in "${VARIANTS[@]}"; do $RUN experiments.llm.agent_d --variant "$v" --dry-run; done
[ "$DRY" = "--dry-run" ] && exit 0

$RUN experiments.llm.rewrite                      # 1. Direction B rewrites -> cache/rewrites.json
$RUN experiments.run_variants                     # 2. retrieval variants (incl. B_* now that rewrites exist)
for v in "${VARIANTS[@]}"; do                     # 3. Direction D agent runs -> cache/d_runs/<variant>/
  $RUN experiments.llm.agent_d --variant "$v"
done
$RUN experiments.build_pools                      # 4. judging pools from runs + agent searches (prints #pairs)
$RUN experiments.run_variants                     # 5. fills anything still missing (no-op for cached variants)
$RUN experiments.build_pools                      #    rebuild pools in case step 5 added runs
$RUN experiments.llm.judge --dry-run              # 6. judge call count
$RUN experiments.llm.judge                        #    -> cache/judgments.json
$RUN experiments.llm.judge --sample-audit 20      # 7. spot-check 20 judgments by eye
