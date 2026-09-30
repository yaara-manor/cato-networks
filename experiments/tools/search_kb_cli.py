#!/usr/bin/env python
"""search_kb tool for Direction-D agent subagents.

  python experiments/tools/search_kb_cli.py --run-id R --query "text" [--top-k 5] [--show-scores]

Runs the current production pipeline (no gate), prints compact passages and appends a JSON line
to experiments/cache/d_runs/<run_id>.searches.jsonl. Budget: env SEARCH_BUDGET (default 3) calls
per run-id; beyond that prints "BUDGET EXHAUSTED" and exits 2 (the call is not logged).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

EXP = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(EXP), str(EXP.parent)]

D_RUNS = EXP / "cache" / "d_runs"


def count_searches(run_id: str) -> int:
    p = D_RUNS / f"{run_id}.searches.jsonl"
    if not p.exists():
        return 0
    return sum(1 for line in p.read_text().splitlines() if line.strip())


def main() -> int:
    ap = argparse.ArgumentParser(description="Search the support KB.")
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--query", required=True)
    ap.add_argument("--top-k", type=int, default=5)
    ap.add_argument("--show-scores", action="store_true")
    a = ap.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9._-]+", a.run_id):
        print("invalid run-id (use [A-Za-z0-9._-])", file=sys.stderr)
        return 1
    if a.top_k <= 0:
        print("--top-k must be positive", file=sys.stderr)
        return 1
    budget = int(os.environ.get("SEARCH_BUDGET", "3"))
    if count_searches(a.run_id) >= budget:
        print("BUDGET EXHAUSTED")
        return 2
    from lab.retrieve import search_current

    res = search_current(a.query, a.top_k)
    D_RUNS.mkdir(parents=True, exist_ok=True)
    rec = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "run_id": a.run_id, "query": a.query,
           "top_k": a.top_k, "passage_ids": [p["passage_id"] for p in res],
           "scores": [p["rerank_score"] for p in res]}
    with open(D_RUNS / f"{a.run_id}.searches.jsonl", "a") as f:
        f.write(json.dumps(rec) + "\n")
    if not res:
        print("(no results)")
    for i, p in enumerate(res, 1):
        body = " ".join(p["body"].split())[:500]
        score = f" score={p['rerank_score']:.2f}" if a.show_scores else ""
        print(f"[{i}] passage_id={p['passage_id']} slug={p['slug']}{score}\n    heading: {p['heading']}\n    {body}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
