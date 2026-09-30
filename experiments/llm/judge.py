"""Relevance judge: one LLM call per (query, passage) pair in cache/pools.json.

    uv run --env-file .env python -m experiments.llm.judge [--dry-run] [--limit N] [--ids Q01]
    uv run python -m experiments.llm.judge --sample-audit 20      # no LLM calls

Writes cache/judgments.json {query_id: {passage_id: {grade, reason}}}; per-call model/usage/latency
go to cache/judge_calls.jsonl. The judge sees only the query text and one passage: never a score,
rank or variant name. Pairs already judged are skipped.
"""
import argparse
import asyncio
import json
import random
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator
from pydantic_ai import Agent
from pydantic_ai.models import Model

from experiments.lab.retrieve import BODY_MAX, get_passages_by_ids
from experiments.llm.common import (
    MODEL_SETTINGS,
    Query,
    add_run_args,
    build_model,
    call_meta,
    load_queries,
    model_name,
    progress,
    read_json,
    run_pool,
    select_queries,
    take,
    with_retries,
    write_json,
)
from experiments.llm.prompts import JUDGE_SYSTEM

MODEL_ENV: str = "EXPERIMENT_JUDGE_MODEL"
JUDGE_BODY_MAX: int = 3000
FLUSH_EVERY: int = 25

Pair = tuple[str, str]
Judgments = dict[str, dict[str, dict[str, Any]]]


class Judgment(BaseModel):
    grade: int = Field(description="0 irrelevant, 1 related but does not answer, 2 directly answers")
    reason: str = Field(description="One sentence explaining the grade")

    @field_validator("grade")
    @classmethod
    def _in_range(cls, value: int) -> int:
        if value not in (0, 1, 2):
            raise ValueError("grade must be 0, 1 or 2")
        return value


class PassageText(BaseModel):
    slug: str
    heading: str
    body: str


_AGENT: Agent[None, Judgment] = Agent(
    output_type=Judgment, instructions=JUDGE_SYSTEM, model_settings=MODEL_SETTINGS, retries=2
)


def pending_pairs(pools: dict[str, list[str]], judged: Judgments, ids: set[str], limit: int | None) -> list[Pair]:
    pairs = [
        (qid, pid)
        for qid in sorted(pools) if qid in ids
        for pid in sorted(pools[qid]) if pid not in judged.get(qid, {})
    ]
    return take(pairs, limit)


def load_passage_texts(pids: Sequence[str], passages_path: Path) -> dict[str, PassageText]:
    """Full bodies (capped at JUDGE_BODY_MAX). passages.json bodies are cut at BODY_MAX, so those
    and any passage missing from it are fetched from the DB."""
    cached: dict[str, dict[str, str]] = read_json(passages_path, {})
    texts = {
        pid: PassageText(**cached[pid]) for pid in pids if pid in cached and len(cached[pid]["body"]) < BODY_MAX
    }
    for p in get_passages_by_ids([pid for pid in pids if pid not in texts], full=True):
        texts[p["passage_id"]] = PassageText(slug=p["slug"], heading=p["heading"], body=p["body"])
    return texts


def judge_prompt(query_text: str, passage: PassageText) -> str:
    return (
        f"Customer message:\n{query_text}\n\n"
        f"Passage\nArticle: {passage.slug}\nHeading: {passage.heading}\n\n{passage.body[:JUDGE_BODY_MAX]}"
    )


async def judge_one(model: Model, label: str, prompt: str) -> dict[str, Any]:
    async def call() -> dict[str, Any]:
        started = time.perf_counter()
        result = await _AGENT.run(prompt, model=model)
        return {**result.output.model_dump(), **call_meta(label, result.usage, started)}

    return await with_retries(call)


async def run_judging(
    model: Model,
    label: str,
    pairs: Sequence[Pair],
    query_texts: dict[str, str],
    passages_path: Path,
    judgments_path: Path,
    calls_path: Path,
    concurrency: int,
) -> int:
    """Judge every pair, persisting every FLUSH_EVERY results and at the end. Returns the failure count."""
    texts = load_passage_texts(sorted({pid for _, pid in pairs}), passages_path)
    judgments: Judgments = read_json(judgments_path, {})
    done = 0

    def flush() -> None:
        write_json(judgments_path, judgments)

    def store(pair: Pair, record: dict[str, Any]) -> None:
        nonlocal done
        done += 1
        qid, pid = pair
        judgments.setdefault(qid, {})[pid] = {"grade": record["grade"], "reason": record["reason"]}
        with calls_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"query_id": qid, "passage_id": pid, **record}, ensure_ascii=False) + "\n")
        if done % FLUSH_EVERY == 0:
            flush()
        progress(done, len(pairs), f"{qid} {pid[:8]} grade={record['grade']}", record["latency_s"])

    async def worker(pair: Pair) -> dict[str, Any]:
        qid, pid = pair
        return await judge_one(model, label, judge_prompt(query_texts[qid], texts[pid]))

    try:
        return await run_pool(pairs, worker, store, concurrency)
    finally:
        flush()


def audit(judgments: Judgments, queries: Sequence[Query], passages_path: Path, n: int, seed: int | None) -> None:
    """Print n random judgments with query/passage snippets for human spot-checking."""
    flat = [(qid, pid, j) for qid, by_pid in judgments.items() for pid, j in by_pid.items()]
    sample = random.Random(seed).sample(flat, min(n, len(flat)))
    query_texts = {q["id"]: q["text"] for q in queries}
    texts = load_passage_texts(sorted({pid for _, pid, _ in sample}), passages_path)
    for qid, pid, j in sample:
        p = texts.get(pid)
        snippet = " ".join(p.body.split())[:300] if p else "(passage not found)"
        print(f"--- {qid} / {pid}\nQUERY:   {' '.join(query_texts.get(qid, '?').split())[:200]}")
        print(f"PASSAGE: [{p.slug if p else '?'}] {p.heading if p else '?'}: {snippet}")
        print(f"GRADE {j['grade']}: {j['reason']}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    add_run_args(parser)
    parser.add_argument("--sample-audit", type=int, default=None, metavar="N", help="print N random judgments and exit")
    parser.add_argument("--seed", type=int, default=None, help="seed for --sample-audit")
    args = parser.parse_args(argv)
    cache: Path = args.cache_dir
    queries = load_queries()
    judgments: Judgments = read_json(cache / "judgments.json", {})
    if args.sample_audit is not None:
        audit(judgments, queries, cache / "passages.json", args.sample_audit, args.seed)
        return 0
    pools: dict[str, list[str]] = read_json(cache / "pools.json", {})
    if not pools:
        raise SystemExit("cache/pools.json is missing or empty: run experiments.build_pools first")
    ids = {q["id"] for q in select_queries(queries, args.ids)}
    pairs = pending_pairs(pools, judgments, ids, args.limit)
    label = model_name(MODEL_ENV)
    print(f"model={label} pooled_pairs={sum(len(v) for v in pools.values())} pending={len(pairs)} -> {len(pairs)} calls")
    if args.dry_run:
        return 0
    model = build_model(label)
    query_texts = {q["id"]: q["text"] for q in queries}
    failures = asyncio.run(run_judging(
        model, label, pairs, query_texts, cache / "passages.json",
        cache / "judgments.json", cache / "judge_calls.jsonl", args.concurrency,
    ))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
