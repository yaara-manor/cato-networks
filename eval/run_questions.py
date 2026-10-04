import argparse
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Self

import psycopg
from pydantic import BaseModel, ConfigDict

from core.clock import SimulationClock
from core.config import REPO_ROOT, settings
from eval.calibrate_threshold import EvalQuestion, load_questions
from orchestration import Citation, TurnResult, build_services, build_workflow, warm_models
from storage import AgentRole, StateStore, TraceReplay

_QUESTIONS_PATH: Path = REPO_ROOT / "data/eval/questions.jsonl"
_ANSWERS_PATH: Path = REPO_ROOT / "answers.md"
# Premium tier, so no SLA wording colours an answer; its registered admin is a verified caller.
_ACCOUNT_ID = "ACC-1001"
_CALLER_EMAIL = "netops@northwind-logistics.com"
_TOP_CHUNKS = 5


class ChunkScore(BaseModel):
    model_config = ConfigDict(frozen=True)

    slug: str
    heading_anchor: str
    rrf_score: float
    rerank_score: float

    @classmethod
    def from_candidate(cls, candidate: dict[str, Any]) -> Self:
        return cls(
            slug=candidate["slug"],
            heading_anchor=candidate["heading_anchor"],
            rrf_score=candidate["rrf_score"],
            rerank_score=candidate["rerank_score"],
        )


class QuestionRun(BaseModel):
    model_config = ConfigDict(frozen=True)

    question_id: str
    question: str
    answer: str
    citations: tuple[Citation, ...]
    chunks: tuple[ChunkScore, ...]
    latency_ms: int
    prompt_tokens: int
    completion_tokens: int
    cost_usd: Decimal
    snapshot_date: str

    @classmethod
    def from_turn(cls, question: EvalQuestion, result: TurnResult, replay: TraceReplay) -> Self:
        """Totals cover every agent step of the conversation, which holds this one question only."""
        steps = [step.trace for turn in replay.turns for step in turn.steps]
        knowledge = next((t.output for t in steps if t.agent_role is AgentRole.KNOWLEDGE and t.output), {})
        candidates = knowledge.get("candidates", [])[:_TOP_CHUNKS]
        return cls(
            question_id=question.question_id,
            question=question.question,
            answer=result.reply,
            citations=result.citations,
            chunks=tuple(ChunkScore.from_candidate(c) for c in candidates),
            latency_ms=sum(t.latency_ms for t in steps),
            prompt_tokens=sum(t.prompt_tokens for t in steps),
            completion_tokens=sum(t.completion_tokens for t in steps),
            cost_usd=sum((t.cost_usd or Decimal(0) for t in steps), Decimal(0)),
            snapshot_date=str(knowledge.get("snapshot_date") or "unknown"),
        )

    def to_markdown(self) -> str:
        lines = [f"## {self.question_id}", "", f"**Question:** {self.question}", "", "**Answer:**", "", self.answer, ""]
        lines.append("**Citations:**")
        lines += [
            f"- {c.title}{' › ' + c.heading if c.heading else ''} (`{c.ref}`){' ' + c.url if c.url else ''}"
            for c in self.citations
        ] or ["- none"]
        lines += ["", "**Top retrieved chunks:**", "", "| Rank | Passage | RRF | Rerank |", "|---|---|---|---|"]
        lines += [
            f"| {rank} | `{c.slug}#{c.heading_anchor}` | {c.rrf_score:.4f} | {c.rerank_score:.2f} |"
            for rank, c in enumerate(self.chunks, start=1)
        ] or ["| - | none retrieved | - | - |"]
        tokens = f"{self.prompt_tokens}+{self.completion_tokens} tokens"
        lines += ["", f"**Latency / cost:** {self.latency_ms} ms, {tokens}, ${self.cost_usd:.6f}", ""]
        return "\n".join(lines)


def run_question(conn: psycopg.Connection[Any], clock: SimulationClock, question: EvalQuestion) -> QuestionRun:
    """One new conversation per question, through the same workflow the chat uses."""
    services = build_services(conn, clock)
    identity = services.customers.authenticate_caller(_CALLER_EMAIL)
    conversation = services.store.create_conversation(
        _ACCOUNT_ID, identity.caller_email, identity.effective_tier, clock.now()
    )
    result = build_workflow(conn, clock).run_turn(conversation.id, question.question, uuid.uuid4())
    replay = StateStore(conn).replay_trace(conversation.id)
    assert replay is not None
    return QuestionRun.from_turn(question, result, replay)


def to_markdown(runs: list[QuestionRun]) -> str:
    snapshots = ", ".join(sorted({r.snapshot_date for r in runs}))
    header = [
        "# answers.md: the agent on the 35 benchmark questions",
        "",
        f"- Generated: {datetime.now(tz=UTC).isoformat(timespec='seconds')} by `python -m eval.run_questions`",
        f"- Code path: the chat workflow (`build_workflow(...).run_turn`), one new conversation per question, "
        f"caller {_CALLER_EMAIL} ({_ACCOUNT_ID}, Premium)",
        f"- KB snapshot date: {snapshots}",
        f"- Totals: {sum(r.latency_ms for r in runs) / 1000:.0f} s, "
        f"{sum(r.prompt_tokens + r.completion_tokens for r in runs)} tokens, "
        f"${sum((r.cost_usd for r in runs), Decimal(0)):.4f}",
        "",
    ]
    return "\n".join([*header, *(r.to_markdown() for r in runs)])


def main(out: Path) -> None:
    questions = load_questions(_QUESTIONS_PATH)
    clock = SimulationClock()
    warm_models()
    runs: list[QuestionRun] = []
    with psycopg.connect(settings.database_url, autocommit=True) as conn:
        for question in questions:
            runs.append(run_question(conn, clock, question))
            print(f"{question.question_id} done", flush=True)
    out.write_text(to_markdown(runs), encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the benchmark questions and write answers.md.")
    parser.add_argument("--out", type=Path, default=_ANSWERS_PATH)
    main(parser.parse_args().out)
