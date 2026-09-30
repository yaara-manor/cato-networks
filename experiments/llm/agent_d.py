"""Direction D: a Gemini agent that uses `search_kb` (production retrieval, no score gate) to decide
ANSWER / ASK_CUSTOMER / NOT_IN_KB, with a per-run search budget and a citation validator.

    uv run --env-file .env python -m experiments.llm.agent_d [--variant d_hidden_b3] [--dry-run] [--limit N] [--ids Q01]

Writes cache/d_runs/<variant>/<query_id>.json. Queries that already have a file are skipped.
"""
import argparse
import asyncio
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, TypedDict

from pydantic import BaseModel
from pydantic_ai import Agent, RunContext
from pydantic_ai.models import Model
from pydantic_ai.usage import UsageLimits

from experiments.lab.retrieve import Passage, search_current
from experiments.llm.common import (
    MODEL_SETTINGS,
    Query,
    add_run_args,
    build_model,
    call_meta,
    load_queries,
    model_name,
    progress,
    run_pool,
    select_queries,
    take,
    with_retries,
    write_json,
)
from experiments.llm.prompts import render_agent_system

MODEL_ENV: str = "EXPERIMENT_LLM_MODEL"
DEFAULT_VARIANT: str = "d_hidden_b3"
EXHAUSTED: str = "BUDGET EXHAUSTED"
EXCERPT_CHARS: int = 500

Decision = Literal["ANSWER", "ASK_CUSTOMER", "NOT_IN_KB"]


@dataclass(frozen=True)
class Variant:
    budget: int
    top_k: int
    show_scores: bool


VARIANTS: dict[str, Variant] = {
    "d_hidden_b3": Variant(budget=3, top_k=5, show_scores=False),
    "d_shown_b3": Variant(budget=3, top_k=5, show_scores=True),
    "d_hidden_b1": Variant(budget=1, top_k=5, show_scores=False),
    "d_hidden_b3_k3": Variant(budget=3, top_k=3, show_scores=False),
    "d_hidden_b3_k10": Variant(budget=3, top_k=10, show_scores=False),
}


class AgentAnswer(BaseModel):
    decision: Decision
    citations: list[str]
    answer_text: str


class SearchLog(TypedDict):
    query: str
    passage_ids: list[str]
    scores: list[float]


@dataclass
class SearchSession:
    """Per-run state: the variant, the search log, and the budget."""

    variant: Variant
    searches: list[SearchLog] = field(default_factory=list)

    @property
    def seen_ids(self) -> set[str]:
        return {pid for s in self.searches for pid in s["passage_ids"]}

    def search(self, query: str) -> str:
        if len(self.searches) >= self.variant.budget:
            return EXHAUSTED
        passages = search_current(query, top_k=self.variant.top_k)
        self.searches.append(SearchLog(
            query=query,
            passage_ids=[p["passage_id"] for p in passages],
            scores=[round(p["score"], 4) for p in passages],
        ))
        return format_passages(passages, self.variant.show_scores)


def format_passages(passages: Sequence[Passage], show_scores: bool) -> str:
    if not passages:
        return "(no results)"
    blocks: list[str] = []
    for i, p in enumerate(passages, 1):
        score = f" score={p['score']:.2f}" if show_scores else ""
        excerpt = " ".join(p["body"].split())[:EXCERPT_CHARS]
        blocks.append(
            f"[{i}] passage_id={p['passage_id']} slug={p['slug']}{score}\n    heading: {p['heading']}\n    {excerpt}\n"
        )
    return "\n".join(blocks)


_AGENT: Agent[SearchSession, AgentAnswer] = Agent(
    deps_type=SearchSession, output_type=AgentAnswer, model_settings=MODEL_SETTINGS, retries=2
)


@_AGENT.tool
async def search_kb(ctx: RunContext[SearchSession], query: str) -> str:
    """Search the Cato support knowledge base with a short keyword query.

    Args:
        query: Short keyword phrase (product terms, error strings), not the whole customer message.
    """
    return ctx.deps.search(query)


class Validation(TypedDict):
    final_decision: Decision
    invalid_citations: list[str]


def validate(answer: AgentAnswer, seen_ids: set[str]) -> Validation:
    """Grounding check: ANSWER needs citations and every citation must have been retrieved in this run.
    Otherwise ANSWER is downgraded to NOT_IN_KB. Invalid citations are recorded for any decision."""
    invalid = [c for c in answer.citations if c not in seen_ids]
    ungrounded = answer.decision == "ANSWER" and (bool(invalid) or not answer.citations)
    return Validation(final_decision="NOT_IN_KB" if ungrounded else answer.decision, invalid_citations=invalid)


async def run_agent(model: Model, label: str, variant_name: str, query: Query) -> dict[str, Any]:
    variant = VARIANTS[variant_name]
    instructions = render_agent_system(variant.budget, variant.top_k, variant.show_scores)
    limits = UsageLimits(request_limit=2 * variant.budget + 5)

    async def call() -> dict[str, Any]:
        session = SearchSession(variant)  # fresh per attempt so retries never share budget or logs
        started = time.perf_counter()
        result = await _AGENT.run(
            query["text"], model=model, deps=session, instructions=instructions, usage_limits=limits
        )
        answer = result.output
        return {
            "query_id": query["id"],
            "variant": variant_name,
            "decision": answer.decision,
            **validate(answer, session.seen_ids),
            "citations": answer.citations,
            "answer_text": answer.answer_text,
            "searches": session.searches,
            "n_searches": len(session.searches),
            **call_meta(label, result.usage, started),
        }

    return await with_retries(call)


def run_dir(cache_dir: Path, variant_name: str) -> Path:
    return cache_dir / "d_runs" / variant_name


def pending_queries(queries: Sequence[Query], out_dir: Path, limit: int | None) -> list[Query]:
    return take([q for q in queries if not (out_dir / f"{q['id']}.json").exists()], limit)


async def run_variant(
    model: Model, label: str, variant_name: str, pending: Sequence[Query], out_dir: Path, concurrency: int
) -> int:
    """Run the agent on every pending query, one file per query. Returns the failure count."""
    done = 0

    def store(query: Query, record: dict[str, Any]) -> None:
        nonlocal done
        done += 1
        write_json(out_dir / f"{query['id']}.json", record)
        progress(done, len(pending), f"{query['id']} {record['final_decision']}", record["latency_s"])

    async def worker(query: Query) -> dict[str, Any]:
        return await run_agent(model, label, variant_name, query)

    return await run_pool(pending, worker, store, concurrency)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--variant", default=DEFAULT_VARIANT, choices=sorted(VARIANTS))
    add_run_args(parser)
    args = parser.parse_args(argv)
    label = model_name(MODEL_ENV)
    variant = VARIANTS[args.variant]
    out_dir = run_dir(args.cache_dir, args.variant)
    queries = select_queries(load_queries(), args.ids)
    pending = pending_queries(queries, out_dir, args.limit)
    print(
        f"model={label} variant={args.variant} {variant} queries={len(queries)} pending={len(pending)} "
        f"-> about {len(pending) * 2}-{len(pending) * (variant.budget + 1)} model requests "
        f"(1 per search + 1 final answer per query) and up to {len(pending) * variant.budget} local KB searches"
    )
    if args.dry_run:
        return 0
    model = build_model(label)
    failures = asyncio.run(run_variant(model, label, args.variant, pending, out_dir, args.concurrency))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
