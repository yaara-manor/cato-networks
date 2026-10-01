"""Direction B: one LLM call per customer message -> {is_kb_question, intent, search_queries}.

    uv run --env-file .env python -m experiments.llm.rewrite [--dry-run] [--limit N] [--ids Q01,Q02]

Writes cache/rewrites.json {query_id: {is_kb_question, intent, search_queries, model, usage,
latency_s, ts}}. Queries already in the file are skipped.
"""
import argparse
import asyncio
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from pydantic import BaseModel, field_validator
from pydantic_ai import Agent
from pydantic_ai.models import Model

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
from experiments.llm.prompts import REWRITE_SYSTEM

MODEL_ENV: str = "EXPERIMENT_LLM_MODEL"
MAX_SEARCH_QUERIES: int = 3


class Rewrite(BaseModel):
    is_kb_question: bool
    intent: str
    search_queries: list[str]

    @field_validator("search_queries")
    @classmethod
    def _cap_queries(cls, value: list[str]) -> list[str]:
        return [q.strip() for q in value if q.strip()][:MAX_SEARCH_QUERIES]


_AGENT: Agent[None, Rewrite] = Agent(
    output_type=Rewrite, instructions=REWRITE_SYSTEM, model_settings=MODEL_SETTINGS, retries=2
)


async def rewrite_one(model: Model, label: str, query: Query) -> dict[str, Any]:
    async def call() -> dict[str, Any]:
        started = time.perf_counter()
        result = await _AGENT.run(query["text"], model=model)
        return {**result.output.model_dump(), **call_meta(label, result.usage, started)}

    return await with_retries(call)


def pending_queries(queries: Sequence[Query], cache: dict[str, Any], limit: int | None) -> list[Query]:
    return take([q for q in queries if q["id"] not in cache], limit)


async def run_rewrites(
    model: Model, label: str, pending: Sequence[Query], cache_path: Path, concurrency: int
) -> int:
    """Rewrite every pending query, persisting after each one. Returns the failure count."""
    cache: dict[str, Any] = read_json(cache_path, {})
    done = 0

    def store(query: Query, record: dict[str, Any]) -> None:
        nonlocal done
        done += 1
        cache[query["id"]] = record
        write_json(cache_path, cache)
        progress(done, len(pending), query["id"], record["latency_s"])

    async def worker(query: Query) -> dict[str, Any]:
        return await rewrite_one(model, label, query)

    return await run_pool(pending, worker, store, concurrency)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    add_run_args(parser)
    args = parser.parse_args(argv)
    label = model_name(MODEL_ENV)
    cache_path: Path = args.cache_dir / "rewrites.json"
    queries = select_queries(load_queries(), args.ids)
    pending = pending_queries(queries, read_json(cache_path, {}), args.limit)
    print(f"model={label} queries={len(queries)} pending={len(pending)} -> {len(pending)} calls")
    if args.dry_run:
        return 0
    model = build_model(label)
    failures = asyncio.run(run_rewrites(model, label, pending, cache_path, args.concurrency))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
