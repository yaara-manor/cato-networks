"""Shared helpers for the notebooks in `experiments/notebooks/`.

Everything here only READS the caches under `experiments/cache/` (override the directory with the env var
`EXPERIMENT_CACHE_DIR`). Nothing calls an LLM, nothing writes to the DB. Importing this module does not load the
retrieval models or open a DB connection (only `lab.metrics`, which is pure, is imported).

Conventions
- A *run* is one `cache/runs/<name>.json`: `{query_id: {latency_ms, results: [{passage_id, slug, heading, score, rank}]}}`.
- A *label* is True (ANSWERABLE: the judged pool holds at least one grade-2 passage), False (UNANSWERABLE) or
  None (unknown, only before judgments exist and for SCN/TKT queries).
- A *gate* answers iff `value >= threshold`; everything else is refused.
"""
from __future__ import annotations

import json
import math
import os
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any, cast

import numpy as np
import pandas as pd

from . import metrics

EXPERIMENTS_DIR: Path = Path(__file__).resolve().parents[1]
REPO_ROOT: Path = EXPERIMENTS_DIR.parent
QUERIES_PATH: Path = EXPERIMENTS_DIR / "data" / "queries.jsonl"

# Commands a tester runs to produce each cache (shown in "run step X first" messages).
CMD_RUN_VARIANTS = "uv run python -m experiments.run_variants"
CMD_REWRITE = "uv run --env-file .env python -m experiments.llm.rewrite   (then re-run: " + CMD_RUN_VARIANTS + ")"
CMD_AGENT = "uv run --env-file .env python -m experiments.llm.agent_d --variant d_hidden_b3   (repeat for the other variants)"
CMD_POOLS = "uv run python -m experiments.build_pools"
CMD_JUDGE = "uv run --env-file .env python -m experiments.llm.judge"

SETS: tuple[str, ...] = ("ANS", "SCN", "TKT", "OOD", "ADJ")
# Messages that must never be answered from the KB (policy / injection / social engineering / outage triage).
NEVER_KB_IDS: tuple[str, ...] = (
    "SC-03", "SC-04", "SC-05", "SC-07", "SC-10", "TCK-20264223", "TCK-20264246", "TCK-20264209", "TCK-20264210",
)


# ---------------------------------------------------------------- cache access

def cache_dir() -> Path:
    override = os.environ.get("EXPERIMENT_CACHE_DIR")
    return Path(override) if override else EXPERIMENTS_DIR / "cache"


def _read(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    except (OSError, ValueError):
        return None


def need(have: bool, what: str, command: str) -> bool:
    """Return `have`; when False print a clear 'run step X first' message so the calling cell can skip."""
    if not have:
        print(f"SKIPPED - missing cache: {what}\n  Run step first: {command}")
    return have


def load_queries() -> pd.DataFrame:
    with QUERIES_PATH.open(encoding="utf-8") as f:
        rows = [json.loads(line) for line in f if line.strip()]
    return pd.DataFrame(rows).set_index("id", drop=False)


def load_run(name: str) -> dict[str, Any] | None:
    return _read(cache_dir() / "runs" / f"{name}.json")


def load_runs(names: Sequence[str]) -> dict[str, dict[str, Any]]:
    """Only the runs that exist (missing names are simply absent from the result)."""
    out: dict[str, dict[str, Any]] = {}
    for n in names:
        r = load_run(n)
        if r:
            out[n] = r
    return out


def available_runs() -> list[str]:
    return sorted(p.stem for p in (cache_dir() / "runs").glob("*.json"))


def load_rewrites() -> dict[str, Any] | None:
    return _read(cache_dir() / "rewrites.json") or None


def load_judgments() -> dict[str, dict[str, dict[str, Any]]] | None:
    return _read(cache_dir() / "judgments.json") or None


def load_passages() -> dict[str, dict[str, str]]:
    return _read(cache_dir() / "passages.json") or {}


def load_pools() -> dict[str, list[str]] | None:
    return _read(cache_dir() / "pools.json") or None


def d_variants() -> list[str]:
    base = cache_dir() / "d_runs"
    return sorted(p.name for p in base.iterdir() if p.is_dir() and any(p.glob("*.json"))) if base.exists() else []


def load_d_runs(variant: str) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for p in sorted((cache_dir() / "d_runs" / variant).glob("*.json")):
        rec = _read(p)
        if rec:
            out[rec["query_id"]] = rec
    return out


# ---------------------------------------------------------------- labels and qrels

def qrels_from(judgments: Mapping[str, Mapping[str, Mapping[str, Any]]] | None) -> dict[str, dict[str, int]]:
    if not judgments:
        return {}
    return {q: {p: int(j["grade"]) for p, j in d.items()} for q, d in judgments.items()}


def gold_labels(queries: pd.DataFrame, judgments: Mapping[str, Any] | None) -> pd.DataFrame:
    """One row per query: `label` (True/False/None), `n_grade2`, `source`.

    Judged queries: label = at least one grade-2 passage in the pool. Without judgments, fall back to the query
    set: ANS -> True, ADJ/OOD -> False, SCN/TKT -> None (unknown).
    """
    qr = qrels_from(judgments)
    rows: list[dict[str, Any]] = []
    for qid_, row in queries.iterrows():
        qid = str(qid_)
        if qid in qr:
            n2 = sum(1 for g in qr[qid].values() if g >= 2)
            rows.append({"id": qid, "set": row["set"], "label": n2 > 0, "n_grade2": n2, "source": "judged"})
        else:
            prior = {"ANS": True, "ADJ": False, "OOD": False}.get(str(row["set"]))
            rows.append({"id": qid, "set": row["set"], "label": prior, "n_grade2": None,
                         "source": "set-prior" if prior is not None else "unknown"})
    return pd.DataFrame(rows).set_index("id", drop=False)


def label_name(label: bool | None) -> str:
    return "unknown" if label is None or (isinstance(label, float) and math.isnan(label)) else (
        "answerable" if label else "unanswerable")


def never_kb(qid: str) -> bool:
    return any(qid == p or qid.startswith(p + "-") for p in NEVER_KB_IDS)


# ---------------------------------------------------------------- run -> features

def ranked(run: Mapping[str, Any], qid: str) -> list[dict[str, Any]]:
    entry = run.get(qid)
    return sorted(entry["results"], key=lambda r: r["rank"]) if entry else []


def gate_features(run: Mapping[str, Any], lex_run: Mapping[str, Any] | None = None,
                  dense_run: Mapping[str, Any] | None = None) -> pd.DataFrame:
    """Per-query numbers a gate can look at, all derived from the score list of one run (top-20).

    top1, top2, margin (top1-top2), z (top1 vs the list's mean/sd), top1_slug, latency_ms, plus, when the
    lexical/dense runs are given: agree_overlap (|lex10 & dense10| / 10) and agree_top1 (how many of the two
    branches also have this run's top-1 passage in their top-10: 0, 1 or 2).
    """
    rows: list[dict[str, Any]] = []
    for qid in run:
        res = ranked(run, qid)
        s = [float(r["score"]) for r in res]
        row: dict[str, Any] = {"id": qid, "top1": s[0] if s else -math.inf, "top1_slug": res[0]["slug"] if res else "",
                               "top1_pid": res[0]["passage_id"] if res else "",
                               "top2": s[1] if len(s) > 1 else math.nan, "latency_ms": run[qid].get("latency_ms", math.nan)}
        row["margin"] = s[0] - s[1] if len(s) > 1 else math.nan
        if len(s) > 1:
            mu = sum(s) / len(s)
            sd = math.sqrt(sum((x - mu) ** 2 for x in s) / len(s))
            row["z"] = (s[0] - mu) / sd if sd else 0.0
        else:
            row["z"] = math.nan
        if lex_run is not None and dense_run is not None:
            lex10 = {r["passage_id"] for r in ranked(lex_run, qid)[:10]}
            den10 = {r["passage_id"] for r in ranked(dense_run, qid)[:10]}
            row["agree_overlap"] = len(lex10 & den10) / 10
            row["agree_top1"] = int(row["top1_pid"] in lex10) + int(row["top1_pid"] in den10)
        rows.append(row)
    return pd.DataFrame(rows).set_index("id", drop=False)


def per_query_metrics(run: Mapping[str, Any], qrels: Mapping[str, Mapping[str, int]], min_grade: int = 2) -> pd.DataFrame:
    """hit@1/hit@5/recall@20 (= does the top-20 contain an answer), MRR, nDCG@5 per query.

    NaN where the query has no relevant passage (undefined). Unjudged passages count as grade 0.
    """
    rows: list[dict[str, Any]] = []
    for qid in run:
        if qid not in qrels:
            continue
        ids = [r["passage_id"] for r in ranked(run, qid)]
        q = dict(qrels[qid])
        rows.append({
            "id": qid,
            "hit@1": metrics.hit_at_k(ids, q, 1, min_grade), "hit@5": metrics.hit_at_k(ids, q, 5, min_grade),
            "recall@20": metrics.hit_at_k(ids, q, 20, min_grade), "mrr": metrics.mrr(ids, q, min_grade),
            "ndcg@5": metrics.ndcg_at_k(ids, q, 5),
        })
    return pd.DataFrame(rows, columns=["id", "hit@1", "hit@5", "recall@20", "mrr", "ndcg@5"]).set_index("id")


# ---------------------------------------------------------------- decisions and gate sweeps

def decision_metrics(should: Sequence[bool], did: Sequence[bool]) -> dict[str, float]:
    """Answer-class precision/recall/F1 plus false-answer rate (on unanswerable) and false-refusal rate (on answerable)."""
    r = metrics.answer_refuse_prf(list(should), list(did))
    return {"f1": r["answer"]["f1"], "precision": r["answer"]["precision"], "recall": r["answer"]["recall"],
            "false_answer_rate": r["false_answer_rate"], "false_refusal_rate": r["false_refusal_rate"],
            "accuracy": r["accuracy"]}


def sweep_gate(values: pd.Series, should: pd.Series) -> pd.DataFrame:
    """Sweep 'answer iff value >= t' over every observed value; one row per threshold.

    Only queries with a known label are used. NaN values count as -inf (always refused).
    The first row (t = -inf) answers everything; the last (t = +inf) refuses everything.
    """
    idx = should.dropna().index.intersection(values.index)
    v = values.loc[idx].astype(float).fillna(-math.inf).to_numpy()
    y = should.loc[idx].astype(bool).to_numpy()
    cuts = [-math.inf, *sorted({float(x) for x in v if math.isfinite(x)}), math.inf]
    rows: list[dict[str, float]] = []
    for t in cuts:
        did = v >= t
        tp = int((did & y).sum())
        fp = int((did & ~y).sum())
        fn = int((~did & y).sum())
        tn = int((~did & ~y).sum())
        p = tp / (tp + fp) if tp + fp else math.nan
        r = tp / (tp + fn) if tp + fn else math.nan
        f = 2 * p * r / (p + r) if p == p and r == r and (p + r) else (0.0 if tp + fp + fn else math.nan)
        rows.append({"threshold": t, "tp": tp, "fp": fp, "fn": fn, "tn": tn, "precision": p, "recall": r, "f1": f,
                     "false_answer_rate": fp / (fp + tn) if fp + tn else math.nan,
                     "false_refusal_rate": fn / (fn + tp) if fn + tp else math.nan})
    return pd.DataFrame(rows)


def best_threshold(sweep: pd.DataFrame) -> pd.Series:
    """Row with the highest F1; ties go to fewer false answers, then to the higher threshold."""
    s = sweep.dropna(subset=["f1"])
    if s.empty:
        return sweep.iloc[0]
    tied = pd.DataFrame(s[s["f1"] >= s["f1"].max() - 1e-12])
    tied = pd.DataFrame(tied[tied["fp"] == tied["fp"].min()])
    return tied.sort_values(by="threshold").iloc[-1]


def cv_f1(values: pd.Series, should: pd.Series, folds: int = 5, seed: int = 0) -> float:
    """Cross-validated F1: pick the best threshold on the training folds, apply it to the held-out fold."""
    idx = should.dropna().index.intersection(values.index)
    v = values.loc[idx].astype(float).fillna(-math.inf)
    y = should.loc[idx].astype(bool)
    order = np.random.default_rng(seed).permutation(len(idx))
    did = pd.Series(False, index=idx)
    for k in range(folds):
        test = idx[order[k::folds]]
        train = idx.difference(test)
        t = cast(float, best_threshold(sweep_gate(v.loc[train], y.loc[train]))["threshold"])
        did.loc[test] = (v.loc[test] >= t).to_numpy()
    return decision_metrics(y.tolist(), did.tolist())["f1"]


def auc(values: pd.Series, should: pd.Series) -> float:
    """P(answerable query scores higher than unanswerable one); 0.5 = no separation, 1 = perfect."""
    idx = should.dropna().index.intersection(values.index)
    v = values.loc[idx].astype(float).fillna(-math.inf)
    y = should.loc[idx].astype(bool)
    pos, neg = v[y].to_numpy(), v[~y].to_numpy()
    if not len(pos) or not len(neg):
        return math.nan
    gt = (pos[:, None] > neg[None, :]).sum() + 0.5 * (pos[:, None] == neg[None, :]).sum()
    return float(gt / (len(pos) * len(neg)))


def band_table(scores: pd.Series, labels: pd.Series, edges: Sequence[float]) -> pd.DataFrame:
    """Count queries per score band by label (answerable / unanswerable / unknown)."""
    bounds = [-math.inf, *edges, math.inf]
    rows: list[dict[str, Any]] = []
    for lo, hi in zip(bounds[:-1], bounds[1:], strict=True):
        inside = [i for i, v in scores.items() if lo <= v < hi]
        names = [label_name(labels.get(i)) for i in inside]
        name = f"< {hi:g}" if lo == -math.inf else (f">= {lo:g}" if hi == math.inf else f"{lo:g} .. {hi:g}")
        rows.append({"score band": name, "queries": len(inside), "answerable": names.count("answerable"),
                     "unanswerable": names.count("unanswerable"), "unknown": names.count("unknown")})
    return pd.DataFrame(rows)


def safety_floor(scores: pd.Series, should: pd.Series, max_false_refusal: float = 0.05, decimals: int = 2) -> dict[str, Any]:
    """Highest cut-off that refuses at most `max_false_refusal` of the answerable queries.

    `exact` is the lowest answerable score that may still be answered; `rounded_up` is that value rounded UP to
    `decimals` places (what plan 04 asked for). Rounding up can push past the boundary query and refuse one more
    answerable query, so `final` falls back to rounding DOWN in that case (and says so in `note`).
    """
    idx = should.dropna().index.intersection(scores.index)
    v = scores.loc[idx].astype(float).fillna(-math.inf)
    y = should.loc[idx].astype(bool)
    ans = np.sort(v[y].to_numpy())
    if not len(ans):
        return {"exact": math.nan, "rounded_up": math.nan, "final": math.nan, "note": "no answerable queries"}
    allowed = int(math.floor(max_false_refusal * len(ans) + 1e-9))
    exact = float(ans[allowed])
    f = 10 ** decimals
    up, down = math.ceil(exact * f) / f, math.floor(exact * f) / f

    def frr(t: float) -> float:
        return float((ans < t).sum()) / len(ans)

    if frr(up) <= max_false_refusal + 1e-12:
        final, note = up, "rounded up (still within the false-refusal budget)"
    else:
        final, note = down, "rounding up would breach the false-refusal budget, so rounded down"
    return {"exact": exact, "rounded_up": up, "rounded_down": down, "final": final, "note": note,
            "allowed_refusals": allowed, "n_answerable": int(len(ans))}


def label_banner(labels: pd.DataFrame) -> str:
    """One line saying where the gold labels come from (judgments vs the provisional set prior)."""
    known = labels.dropna(subset=["label"])
    n_j = int((known["source"] == "judged").sum())
    if n_j == len(known) and n_j:
        return f"LABELS: judgments.json ({n_j} labelled queries; answerable = has a grade-2 passage)"
    return (f"PROVISIONAL LABELS: {len(known) - n_j} of {len(known)} labelled queries use the query-set prior "
            f"(ANS=answerable, OOD/ADJ=unanswerable; SCN/TKT unlabelled). Run the judge to get real labels: {CMD_POOLS} ; {CMD_JUDGE}")


def gate_study(feats: pd.DataFrame, should: pd.Series, gates: Sequence[str],
               folds: int = 5) -> tuple[pd.DataFrame, dict[str, pd.DataFrame]]:
    """For every gate column: sweep the threshold, keep the best-F1 row, add CV F1 and AUC. Also returns the sweeps."""
    rows: list[dict[str, Any]] = []
    sweeps: dict[str, pd.DataFrame] = {}
    for g in gates:
        if g not in feats or feats[g].dropna().empty:
            continue
        col = cast(pd.Series, feats[g])
        sw = sweep_gate(col, should)
        sweeps[g] = sw
        b = best_threshold(sw)
        rows.append({"gate": g, "best threshold": b["threshold"], "F1": b["f1"], "precision": b["precision"], "recall": b["recall"],
                     "false-answer rate": b["false_answer_rate"], "false-refusal rate": b["false_refusal_rate"],
                     "answered": int(b["tp"] + b["fp"]), "F1 (5-fold CV)": cv_f1(col, should, folds), "AUC": auc(col, should)})
    return pd.DataFrame(rows).set_index("gate") if rows else pd.DataFrame(), sweeps


def plot_sweeps(sweeps: Mapping[str, pd.DataFrame], title: str, ncols: int = 3) -> Any:
    """One panel per gate: answer-F1, false-answer rate and false-refusal rate against the threshold."""
    import matplotlib.pyplot as plt

    n = max(len(sweeps), 1)
    nrows = math.ceil(n / ncols)
    fig, axes = plt.subplots(nrows, min(n, ncols), figsize=(4.6 * min(n, ncols), 3.4 * nrows), squeeze=False)
    for ax in axes.ravel():
        ax.set_visible(False)
    for ax, (g, sw) in zip(axes.ravel(), sweeps.items(), strict=False):
        ax.set_visible(True)
        fin = sw[np.isfinite(sw["threshold"])]
        ax.plot(fin["threshold"], fin["f1"], color="#2a7fbf", label="answer F1")
        ax.plot(fin["threshold"], fin["false_answer_rate"], color="#d9534f", label="false-answer rate")
        ax.plot(fin["threshold"], fin["false_refusal_rate"], color="#e69f00", label="false-refusal rate")
        b = best_threshold(sw)
        ax.axvline(b["threshold"], color="k", ls=":", lw=1)
        ax.set_title(f"gate: {g} (best t={b['threshold']:.2f}, F1={b['f1']:.2f})", fontsize=9)
        ax.set_xlabel("threshold (answer iff value >= t)")
        ax.set_ylabel("rate / F1")
    axes[0][0].legend(fontsize=7)
    fig.suptitle(title)
    fig.tight_layout()
    return fig


def best_config(feats: Mapping[str, pd.DataFrame], should: pd.Series, gates: Sequence[str]) -> dict[str, Any]:
    """Best (run, gate, threshold) by answer-F1 over several runs' feature frames (ties: fewer false answers).

    Returns run, gate, threshold, f1, false_answer_rate, false_refusal_rate, `did` (bool Series over the labelled
    queries) and the full `table` of every run x gate.
    """
    tables: list[pd.DataFrame] = []
    for run, f in feats.items():
        st, _ = gate_study(f, should, gates)
        if len(st):
            tables.append(st.assign(run=run).reset_index())
    if not tables:
        return {}
    table = pd.concat(tables, ignore_index=True)
    table = table.sort_values(["F1", "false-answer rate"], ascending=[False, True]).reset_index(drop=True)
    top = table.iloc[0]
    f = feats[str(top["run"])]
    did = (f.loc[should.index, str(top["gate"])].astype(float).fillna(-math.inf) >= float(top["best threshold"]))
    return {"run": str(top["run"]), "gate": str(top["gate"]), "threshold": float(top["best threshold"]), "f1": float(top["F1"]),
            "false_answer_rate": float(top["false-answer rate"]), "false_refusal_rate": float(top["false-refusal rate"]),
            "did": did, "table": table}


def rewrite_costs(rewrites: Mapping[str, Mapping[str, Any]]) -> pd.DataFrame:
    """Per-query cost of the Direction B rewrite call (latency in ms, tokens, requests)."""
    rows = [{"id": q, "latency_ms": 1000.0 * float(r.get("latency_s", math.nan)),
             "in_tokens": (r.get("usage") or {}).get("input_tokens", 0), "out_tokens": (r.get("usage") or {}).get("output_tokens", 0),
             "requests": (r.get("usage") or {}).get("requests", 1)} for q, r in rewrites.items()]
    return pd.DataFrame(rows, columns=["id", "latency_ms", "in_tokens", "out_tokens", "requests"]).set_index("id")


# ---------------------------------------------------------------- bootstrap

def bootstrap_ci(stat: Callable[[np.ndarray], float], n: int, reps: int = 2000, seed: int = 0) -> tuple[float, float, float]:
    """(point estimate, 2.5%, 97.5%) of `stat(indices)` over resamples of `n` queries. NaN draws are ignored."""
    rng = np.random.default_rng(seed)
    point = stat(np.arange(n))
    draws = np.array([stat(rng.integers(0, n, n)) for _ in range(reps)], dtype=float)
    draws = draws[~np.isnan(draws)]
    if not len(draws):
        return point, math.nan, math.nan
    return point, float(np.percentile(draws, 2.5)), float(np.percentile(draws, 97.5))


def bootstrap_diff(stat_a: Callable[[np.ndarray], float], stat_b: Callable[[np.ndarray], float], n: int,
                   reps: int = 2000, seed: int = 0) -> dict[str, float]:
    """Paired bootstrap of stat_a - stat_b on the same resampled queries: diff, 95% CI and share of draws <= 0."""
    rng = np.random.default_rng(seed)
    diffs: list[float] = []
    for _ in range(reps):
        i = rng.integers(0, n, n)
        d = stat_a(i) - stat_b(i)
        if not math.isnan(d):
            diffs.append(d)
    a = np.array(diffs)
    point = stat_a(np.arange(n)) - stat_b(np.arange(n))
    if not len(a):
        return {"diff": point, "lo": math.nan, "hi": math.nan, "p_le_0": math.nan}
    return {"diff": point, "lo": float(np.percentile(a, 2.5)), "hi": float(np.percentile(a, 97.5)),
            "p_le_0": float((a <= 0).mean())}


def mean_stat(values: Sequence[float] | np.ndarray) -> Callable[[np.ndarray], float]:
    """Stat for `bootstrap_ci`: NaN-ignoring mean of `values` at the resampled indices."""
    arr = np.asarray(values, dtype=float)

    def stat(idx: np.ndarray) -> float:
        x = arr[idx]
        x = x[~np.isnan(x)]
        return float(x.mean()) if len(x) else math.nan

    return stat


def f1_stat(should: Sequence[bool], did: Sequence[bool]) -> Callable[[np.ndarray], float]:
    y, d = np.asarray(should, dtype=bool), np.asarray(did, dtype=bool)

    def stat(idx: np.ndarray) -> float:
        yy, dd = y[idx], d[idx]
        tp, fp, fn = int((yy & dd).sum()), int((~yy & dd).sum()), int((yy & ~dd).sum())
        return 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else math.nan

    return stat


def rate_stat(numer_mask: Sequence[bool], denom_mask: Sequence[bool]) -> Callable[[np.ndarray], float]:
    """Stat: share of the `denom_mask` queries that are also in `numer_mask` (false-answer / false-refusal rates)."""
    a, b = np.asarray(numer_mask, dtype=bool), np.asarray(denom_mask, dtype=bool)

    def stat(idx: np.ndarray) -> float:
        d = int(b[idx].sum())
        return float((a[idx] & b[idx]).sum()) / d if d else math.nan

    return stat


def fmt_ci(ci: tuple[float, float, float], pct: bool = False) -> str:
    p, lo, hi = ci
    if pct:
        return f"{p:.1%} [{lo:.1%}, {hi:.1%}]"
    return f"{p:.3f} [{lo:.3f}, {hi:.3f}]"


# ---------------------------------------------------------------- Direction D

def d_table(records: Mapping[str, Mapping[str, Any]], labels: pd.DataFrame,
            qrels: Mapping[str, Mapping[str, int]] | None = None) -> pd.DataFrame:
    """One row per agent run: decisions, downgrade flag, citation correctness, searches, tokens, latency."""
    rows: list[dict[str, Any]] = []
    for qid, rec in records.items():
        q = (qrels or {}).get(qid)
        cites = list(rec.get("citations") or [])
        grades = [q.get(c, 0) for c in cites] if q is not None else []
        searches = rec.get("searches") or []
        scores = [s for sr in searches for s in sr.get("scores", [])]
        u = rec.get("usage") or {}
        rows.append({
            "id": qid, "set": labels["set"].get(qid), "label": labels["label"].get(qid),
            "decision": rec.get("decision"), "final": rec.get("final_decision"),
            "downgraded": rec.get("decision") == "ANSWER" and rec.get("final_decision") != "ANSWER",
            "invalid_citations": len(rec.get("invalid_citations") or []),
            "n_cites": len(cites),
            "cites_all_grade2": (all(g >= 2 for g in grades) if grades else None) if q is not None else None,
            "cites_any_grade2": (any(g >= 2 for g in grades) if grades else None) if q is not None else None,
            "cite_precision": (sum(g >= 2 for g in grades) / len(grades)) if grades else math.nan,
            "n_searches": rec.get("n_searches", len(searches)),
            "in_tokens": u.get("input_tokens", 0), "out_tokens": u.get("output_tokens", 0),
            "requests": u.get("requests", 0), "latency_s": rec.get("latency_s", math.nan),
            "max_score": max(scores) if scores else math.nan,
            "first_search_ids": searches[0]["passage_ids"] if searches else [],
        })
    return pd.DataFrame(rows).set_index("id", drop=False)


def p50(x: Sequence[float] | pd.Series) -> float:
    a = np.asarray(list(x), dtype=float)
    a = a[~np.isnan(a)]
    return float(np.percentile(a, 50)) if len(a) else math.nan


def recommend(rows: pd.DataFrame, margin: float = 0.03) -> tuple[str, str]:
    """Rule: the top-F1 approach wins only if it leads the runner-up by >= `margin` F1; otherwise the cheaper of the
    two wins. Cost order: LLM calls, then extra tokens, then p50 latency. Needs columns name, f1, llm_calls, tokens, p50_ms."""
    r = rows.dropna(subset=["f1"]).sort_values("f1", ascending=False)
    if len(r) < 2:
        return (str(r.iloc[0]["name"]), "only one approach available") if len(r) else ("", "no approach has a defined F1")
    a, b = r.iloc[0], r.iloc[1]
    gap = float(a["f1"] - b["f1"])
    if gap >= margin:
        return str(a["name"]), f"{a['name']} leads {b['name']} by {gap * 100:.1f} F1 points (>= {margin * 100:.0f})"
    cost = lambda x: (x["llm_calls"], x["tokens"], x["p50_ms"])  # noqa: E731
    cheaper = a if cost(a) <= cost(b) else b
    return str(cheaper["name"]), (f"{a['name']} leads {b['name']} by only {gap * 100:.1f} F1 points (< {margin * 100:.0f}), "
                                  f"so the cheaper one wins: {cheaper['name']}")


# ---------------------------------------------------------------- plotting

def strip(ax: Any, groups: Mapping[str, Sequence[float]], colors: Mapping[str, str] | None = None, seed: int = 0) -> None:
    """Horizontal strip plot (one jittered row per group). Points are the individual queries' scores."""
    rng = np.random.default_rng(seed)
    for i, (name, vals) in enumerate(groups.items()):
        v = np.asarray(list(vals), dtype=float)
        v = v[np.isfinite(v)]
        ax.scatter(v, i + rng.uniform(-0.25, 0.25, len(v)), s=22, alpha=0.75,
                   color=(colors or {}).get(name), edgecolor="none")
    ax.set_yticks(range(len(groups)))
    ax.set_yticklabels([f"{k} (n={len(list(v))})" for k, v in groups.items()])
    ax.grid(axis="x", alpha=0.3)


LABEL_COLORS: dict[str, str] = {"answerable": "#2a7fbf", "unanswerable": "#d9534f", "unknown": "#999999"}


def sigmoid(x: Sequence[float] | np.ndarray | pd.Series) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.asarray(x, dtype=float)))
