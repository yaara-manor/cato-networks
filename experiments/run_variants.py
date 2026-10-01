"""Non-LLM retrieval variants over the 89 queries, written to cache/runs/<name>.json.

    uv run python -m experiments.run_variants [--ids Q01,Q02] [--limit N]

Each file is {query_id: {latency_ms, results: [top-20 {passage_id, slug, heading, score, rank}]}}.
Passage bodies (<=1200 chars) are stored once in cache/passages.json. Variants already cached for a
query are skipped, so reruns are cheap; delete a file to regenerate it. B_* variants need cache/rewrites.json.

Latency: R0/R1/R2/FUS_* include the shared lexical/dense fetch they use; all times are wall-clock on this machine.
"""
import argparse
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from experiments.lab.retrieve import (
    BODY_MAX,
    Passage,
    clean_query,
    dense_top,
    fuse_linear,
    fuse_rrf,
    lexical_top,
    rerank,
    search_current,
)
from experiments.llm.common import CACHE_DIR, Query, load_queries, read_json, select_queries, write_json

DEPTH: int = 20
RRF_K: int = 60
RRF_W_LEX: tuple[float, ...] = (0.25, 0.5, 1, 2, 4)
LIN_W_LEX: tuple[float, ...] = (0, 0.25, 0.5, 0.75, 1)
SCORE_DECIMALS: int = 4
FLUSH_EVERY: int = 10


@dataclass
class Branches:
    """Top-DEPTH lexical and dense lists for the original message, with their fetch times (ms)."""

    lex: list[Passage]
    dense: list[Passage]
    lex_ms: float
    dense_ms: float


@dataclass(frozen=True)
class Context:
    query: Query
    branches: Branches
    rewrite: dict[str, Any] | None


@dataclass(frozen=True)
class Variant:
    name: str
    run: Callable[[Context], list[Passage]]
    uses_lex: bool = False
    uses_dense: bool = False
    needs_rewrite: bool = False


def _timed_ms(fn: Callable[[], list[Passage]]) -> tuple[list[Passage], float]:
    start = time.perf_counter()
    out = fn()
    return out, (time.perf_counter() - start) * 1000


def fetch_branches(text: str) -> Branches:
    lex, lex_ms = _timed_ms(lambda: lexical_top(text, DEPTH))
    dense, dense_ms = _timed_ms(lambda: dense_top(text, DEPTH))
    return Branches(lex, dense, lex_ms, dense_ms)


def merge_rrf(lists: Sequence[Sequence[Passage]], k: int = RRF_K) -> list[Passage]:
    """Reciprocal-rank merge of several ranked lists (used across rewrite sub-queries)."""
    items: dict[str, Passage] = {}
    scores: dict[str, float] = {}
    for ranked in lists:
        for rank, p in enumerate(ranked, 1):
            items.setdefault(p["passage_id"], p)
            scores[p["passage_id"]] = scores.get(p["passage_id"], 0.0) + 1.0 / (k + rank)
    merged: list[Passage] = []
    for i, pid in enumerate(sorted(scores, key=lambda x: (-scores[x], x)), 1):
        p = Passage(**items[pid])  # type: ignore[typeddict-item]
        p["score"] = p["rrf_score"] = scores[pid]
        p["rank"] = i
        merged.append(p)
    return merged


def rewrite_candidates(rewrite: dict[str, Any], text: str) -> list[Passage]:
    """Hybrid (depth 20) retrieval per sub-query, RRF-merged. No sub-queries -> the original message."""
    sub_queries: list[str] = rewrite["search_queries"] or [text]
    hybrids = [fuse_rrf(lexical_top(q, DEPTH), dense_top(q, DEPTH), RRF_K, depth=DEPTH) for q in sub_queries]
    return merge_rrf(hybrids)


def _context_rewrite(ctx: Context) -> dict[str, Any]:
    assert ctx.rewrite is not None
    return ctx.rewrite


def b_intent(ctx: Context) -> list[Passage]:
    rw = _context_rewrite(ctx)
    cands = rewrite_candidates(rw, ctx.query["text"])
    return rerank(rw["intent"] or ctx.query["text"], cands, top_n=DEPTH)


def b_orig(ctx: Context) -> list[Passage]:
    cands = rewrite_candidates(_context_rewrite(ctx), ctx.query["text"])
    return rerank(ctx.query["text"], cands, top_n=DEPTH)


def _fused(kind: str, w_lex: float, ctx: Context) -> list[Passage]:
    b = ctx.branches
    if kind == "rrf":
        return fuse_rrf(b.lex, b.dense, RRF_K, w_lex=w_lex, w_vec=1.0, depth=DEPTH)
    return fuse_linear(b.lex, b.dense, w_lex=w_lex, w_vec=1 - w_lex)


def fusion_variants() -> list[Variant]:
    out: list[Variant] = []
    for kind, weights in (("rrf", RRF_W_LEX), ("lin", LIN_W_LEX)):
        for w in weights:
            name = f"FUS_{kind}_wl{w:g}"
            out.append(Variant(
                name, lambda c, k=kind, w=w: _fused(k, w, c)[:DEPTH], uses_lex=True, uses_dense=True))
            out.append(Variant(
                f"{name}+rerank", lambda c, k=kind, w=w: rerank(c.query["text"], _fused(k, w, c)[:DEPTH], top_n=DEPTH),
                uses_lex=True, uses_dense=True))
    return out


def all_variants() -> list[Variant]:
    return [
        Variant("R0_lex", lambda c: c.branches.lex[:DEPTH], uses_lex=True),
        Variant("R1_dense", lambda c: c.branches.dense[:DEPTH], uses_dense=True),
        Variant("R2_rrf", lambda c: _fused("rrf", 1.0, c)[:DEPTH], uses_lex=True, uses_dense=True),
        Variant("R3_current", lambda c: search_current(c.query["text"], DEPTH)),
        Variant("A_clean", lambda c: search_current(clean_query(c.query["text"]), DEPTH)),
        Variant("B_rewrite_intent", b_intent, needs_rewrite=True),
        Variant("B_rewrite_orig", b_orig, needs_rewrite=True),
        *fusion_variants(),
    ]


def as_rows(passages: Sequence[Passage]) -> list[dict[str, Any]]:
    return [
        {"passage_id": p["passage_id"], "slug": p["slug"], "heading": p["heading"],
         "score": round(p["score"], SCORE_DECIMALS), "rank": i}
        for i, p in enumerate(passages[:DEPTH], 1)
    ]


def run_variant(variant: Variant, ctx: Context) -> tuple[dict[str, Any], list[Passage]]:
    passages, ms = _timed_ms(lambda: variant.run(ctx))
    if variant.uses_lex:
        ms += ctx.branches.lex_ms
    if variant.uses_dense:
        ms += ctx.branches.dense_ms
    return {"latency_ms": round(ms, 1), "results": as_rows(passages)}, passages


def passage_bodies(passages: Sequence[Passage]) -> dict[str, dict[str, str]]:
    return {p["passage_id"]: {"slug": p["slug"], "heading": p["heading"], "body": p["body"][:BODY_MAX]}
            for p in passages}


def flush(runs: dict[str, dict[str, Any]], bodies: dict[str, dict[str, str]], cache_dir: Path) -> None:
    for name, data in runs.items():
        write_json(cache_dir / "runs" / f"{name}.json", data, indent=None)
    write_json(cache_dir / "passages.json", bodies, indent=None)


def run_queries(queries: Sequence[Query], cache_dir: Path, limit: int | None = None) -> None:
    """Compute every variant missing for each query; write runs and passages once at the end."""
    rewrites: dict[str, dict[str, Any]] = read_json(cache_dir / "rewrites.json", {})
    variants = [v for v in all_variants() if rewrites or not v.needs_rewrite]
    runs: dict[str, dict[str, Any]] = {
        v.name: read_json(cache_dir / "runs" / f"{v.name}.json", {}) for v in variants
    }
    bodies: dict[str, dict[str, str]] = read_json(cache_dir / "passages.json", {})
    todo = {q["id"]: [v for v in variants if q["id"] not in runs[v.name] and (q["id"] in rewrites or not v.needs_rewrite)]
            for q in queries}
    work = [q for q in queries if todo[q["id"]]][:limit]
    try:
        for n, query in enumerate(work, 1):
            ctx = Context(query, fetch_branches(query["text"]), rewrites.get(query["id"]))
            for v in todo[query["id"]]:
                entry, passages = run_variant(v, ctx)
                runs[v.name][query["id"]] = entry
                bodies.update(passage_bodies(passages[:DEPTH]))
            print(f"[{n}/{len(work)}] {query['id']}: {len(todo[query['id']])} variants", flush=True)
            if n % FLUSH_EVERY == 0:
                flush(runs, bodies, cache_dir)
    finally:
        flush(runs, bodies, cache_dir)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--ids", default=None, help="comma-separated query ids")
    parser.add_argument("--limit", type=int, default=None, help="compute at most N queries that still have work")
    parser.add_argument("--cache-dir", type=Path, default=CACHE_DIR, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    run_queries(select_queries(load_queries(), args.ids), args.cache_dir, args.limit)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
