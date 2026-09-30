"""Retrieval and answer/refuse metrics. Pure functions, no I/O.

qrels: {query_id: {passage_id: grade}} with grade 0 irrelevant / 1 partial / 2 answers it.
ranked: list of passage_ids, best first. A passage counts as relevant if grade >= min_grade.
Queries with no relevant passage return nan (undefined); use `mean` to aggregate ignoring nan.
"""
from __future__ import annotations

import math
from collections.abc import Sequence

Qrels = dict[str, dict[str, int]]


def _rel(qrel: dict[str, int], min_grade: int) -> set[str]:
    return {p for p, g in qrel.items() if g >= min_grade}


def hit_at_k(ranked: Sequence[str], qrel: dict[str, int], k: int, min_grade: int = 1) -> float:
    rel = _rel(qrel, min_grade)
    if not rel:
        return math.nan
    return 1.0 if any(p in rel for p in ranked[:k]) else 0.0


def mrr(ranked: Sequence[str], qrel: dict[str, int], min_grade: int = 1) -> float:
    rel = _rel(qrel, min_grade)
    if not rel:
        return math.nan
    for i, p in enumerate(ranked, 1):
        if p in rel:
            return 1.0 / i
    return 0.0


def ndcg_at_k(ranked: Sequence[str], qrel: dict[str, int], k: int = 5) -> float:
    """nDCG with gain 2^grade - 1 and log2(rank+1) discount; ideal from all graded passages."""
    def dcg(grades: Sequence[int]) -> float:
        return sum((2 ** g - 1) / math.log2(i + 2) for i, g in enumerate(grades))
    ideal = sorted((g for g in qrel.values() if g > 0), reverse=True)[:k]
    if not ideal:
        return math.nan
    return dcg([qrel.get(p, 0) for p in ranked[:k]]) / dcg(ideal)


def mean(xs: Sequence[float]) -> float:
    v = [x for x in xs if not math.isnan(x)]
    return sum(v) / len(v) if v else math.nan


def evaluate(rankings: dict[str, Sequence[str]], qrels: Qrels, min_grade: int = 1) -> dict[str, float]:
    """Mean hit@1, hit@5, MRR, nDCG@5 over queries present in both dicts."""
    qs = [q for q in rankings if q in qrels]
    return {
        "hit@1": mean([hit_at_k(rankings[q], qrels[q], 1, min_grade) for q in qs]),
        "hit@5": mean([hit_at_k(rankings[q], qrels[q], 5, min_grade) for q in qs]),
        "mrr": mean([mrr(rankings[q], qrels[q], min_grade) for q in qs]),
        "ndcg@5": mean([ndcg_at_k(rankings[q], qrels[q], 5) for q in qs]),
        "n": float(len(qs)),
    }


def _prf(tp: int, fp: int, fn: int) -> dict[str, float]:
    p = tp / (tp + fp) if tp + fp else math.nan
    r = tp / (tp + fn) if tp + fn else math.nan
    f = 2 * p * r / (p + r) if p == p and r == r and p + r else math.nan
    return {"precision": p, "recall": r, "f1": f}


def answer_refuse_prf(should_answer: Sequence[bool], did_answer: Sequence[bool]) -> dict[str, dict[str, float] | float]:
    """Precision/recall/F1 for the ANSWER class and the REFUSE class, plus accuracy."""
    pairs = list(zip(should_answer, did_answer, strict=True))
    tp = sum(s and d for s, d in pairs)
    fp = sum((not s) and d for s, d in pairs)
    fn = sum(s and (not d) for s, d in pairs)
    tn = sum((not s) and (not d) for s, d in pairs)
    return {
        "answer": _prf(tp, fp, fn),
        "refuse": _prf(tn, fn, fp),
        "accuracy": (tp + tn) / len(pairs) if pairs else math.nan,
        "false_answer_rate": fp / (fp + tn) if fp + tn else math.nan,
        "false_refusal_rate": fn / (fn + tp) if fn + tp else math.nan,
    }


if __name__ == "__main__":
    qrels = {"q1": {"a": 2, "b": 1, "c": 0}, "q2": {"x": 2}, "q3": {}}
    ranked = {"q1": ["c", "b", "a"], "q2": ["x"], "q3": ["a"]}
    assert hit_at_k(ranked["q1"], qrels["q1"], 1) == 0.0
    assert hit_at_k(ranked["q1"], qrels["q1"], 2) == 1.0
    assert mrr(ranked["q1"], qrels["q1"]) == 0.5
    assert mrr(ranked["q1"], qrels["q1"], min_grade=2) == 1 / 3
    assert ndcg_at_k(ranked["q2"], qrels["q2"]) == 1.0
    n = ndcg_at_k(ranked["q1"], qrels["q1"])
    assert abs(n - ((1 / math.log2(3) + 3 / math.log2(4)) / (3 + 1 / math.log2(3)))) < 1e-9, n
    assert math.isnan(mrr(ranked["q3"], qrels["q3"]))
    r = answer_refuse_prf([True, True, False, False], [True, False, False, True])
    assert r["answer"]["precision"] == 0.5 and r["refuse"]["recall"] == 0.5 and r["accuracy"] == 0.5
    print("metrics OK", evaluate(ranked, qrels))
