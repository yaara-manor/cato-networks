#!/usr/bin/env python
"""Grounding validator for Direction D.

  python experiments/tools/validate_answer.py --run-id R --answer answer.json

answer.json: {decision: ANSWER|ASK_CUSTOMER|NOT_IN_KB, citations: [passage_id], answer_text}.
Every cited id must appear in experiments/cache/d_runs/<R>.searches.jsonl. Writes
<R>.result.json: {decision, citations, invalid_citations, final_decision, answer_text}.
final_decision = NOT_IN_KB when decision is ANSWER with invalid or empty citations (or when the
decision value is not one of the three); otherwise equals decision.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

D_RUNS = Path(__file__).resolve().parents[1] / "cache" / "d_runs"
DECISIONS = {"ANSWER", "ASK_CUSTOMER", "NOT_IN_KB"}


def retrieved_ids(run_id: str) -> set[str]:
    p = D_RUNS / f"{run_id}.searches.jsonl"
    ids: set[str] = set()
    if p.exists():
        for line in p.read_text().splitlines():
            if line.strip():
                ids.update(str(x) for x in json.loads(line)["passage_ids"])
    return ids


def validate(run_id: str, ans: dict) -> dict:
    decision = str(ans.get("decision", "")).strip().upper()
    citations = [str(c) for c in (ans.get("citations") or [])]
    seen = retrieved_ids(run_id)
    invalid = [c for c in citations if c not in seen]
    if decision not in DECISIONS:
        final = "NOT_IN_KB"
    elif decision == "ANSWER" and (invalid or not citations):
        final = "NOT_IN_KB"
    else:
        final = decision
    return {"decision": decision, "citations": citations, "invalid_citations": invalid,
            "final_decision": final, "answer_text": ans.get("answer_text", "")}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--answer", required=True, help="path to the final answer JSON")
    a = ap.parse_args()
    try:
        ans = json.loads(Path(a.answer).read_text())
    except (OSError, json.JSONDecodeError) as e:
        ans = {"decision": "INVALID", "citations": [], "answer_text": f"unreadable answer file: {e}"}
    res = validate(a.run_id, ans)
    D_RUNS.mkdir(parents=True, exist_ok=True)
    (D_RUNS / f"{a.run_id}.result.json").write_text(json.dumps(res, indent=2, ensure_ascii=False))
    print(json.dumps({k: res[k] for k in ("decision", "invalid_citations", "final_decision")}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
