import json
import math
import statistics
import time
from collections.abc import Mapping
from datetime import date
from enum import StrEnum
from pathlib import Path

import psycopg
from pydantic import BaseModel, ConfigDict

from core.config import REPO_ROOT, settings
from retrieval.service import RetrievalService

_REPORT_PATH: Path = REPO_ROOT / "docs/eval/threshold_calibration.md"
_SC09_ID = "SC-09-no-kb-coverage"
_ROADMAP_PROBE = "What is on the Cato roadmap for AI features next year?"


class QuestionSet(StrEnum):
    ANSWERABLE = "answerable"
    OFF_DOMAIN = "off-domain"
    PARTIAL_COVERAGE = "partial-coverage"


class EvalQuestion(BaseModel):
    model_config = ConfigDict(frozen=True)

    question_id: str
    question: str


class QueryScore(BaseModel):
    model_config = ConfigDict(frozen=True)

    question_id: str
    question_set: QuestionSet
    top1_score: float
    top1_slug: str | None
    latency_ms: float


class ThresholdDecision(BaseModel):
    model_config = ConfigDict(frozen=True)

    threshold: float
    separated: bool
    refused_answerable: list[str]


class CalibrationReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    generated_on: date
    scores: list[QueryScore]
    decision: ThresholdDecision

    def _scores_in(self, question_set: QuestionSet) -> list[QueryScore]:
        return [s for s in self.scores if s.question_set == question_set]

    def to_markdown(self) -> str:
        decision = self.decision
        outcome = "separated" if decision.separated else "overlapping"
        refused = ", ".join(decision.refused_answerable) or "none"
        latencies = [s.latency_ms for s in self.scores]
        cuts = statistics.quantiles(latencies, n=20)
        lines = [
            "# Rerank Threshold Calibration",
            "",
            f"- Date: {self.generated_on.isoformat()}",
            f"- Reranker: `{settings.reranker_model}` @ `{settings.reranker_revision}`",
            "",
            "## Decision",
            "",
            f"- Threshold: **{decision.threshold:.3f}** (answerable vs off-domain: {outcome})",
            f"- Answerable questions refused: {len(decision.refused_answerable)} ({refused})",
            "",
            "## Score ranges (top-1 rerank score)",
            "",
            "| Set | Count | Min | Max |",
            "|---|---|---|---|",
        ]
        for question_set in QuestionSet:
            values = [s.top1_score for s in self._scores_in(question_set)]
            if values:
                lines.append(
                    f"| {question_set.value} | {len(values)} "
                    f"| {min(values):.3f} | {max(values):.3f} |"
                )
        lines += [
            "",
            f"## Latency (all {len(latencies)} queries)",
            "",
            f"- p50: {cuts[9]:.0f} ms",
            f"- p95: {cuts[18]:.0f} ms",
            "",
            "## Per-query scores",
            "",
            "| Id | Set | Top-1 score | Top-1 slug | Latency ms |",
            "|---|---|---|---|---|",
        ]
        set_order = list(QuestionSet)
        ordered = sorted(
            self.scores,
            key=lambda s: (set_order.index(s.question_set), -s.top1_score),
        )
        lines += [
            f"| {s.question_id} | {s.question_set.value} | {s.top1_score:.3f} "
            f"| {s.top1_slug or '-'} | {s.latency_ms:.0f} |"
            for s in ordered
        ]
        lines += [
            "",
            "Partial-coverage rows are informational only (design section 4.3): "
            "they pass the gate because the KB covers part of the question, and "
            "declining the uncovered part (roadmap dates) is the agent's "
            "grounding duty, not the threshold's.",
            "",
        ]
        return "\n".join(lines)


def load_questions(path: Path) -> list[EvalQuestion]:
    return [
        EvalQuestion.model_validate_json(line)
        for line in path.read_text().splitlines()
        if line.strip()
    ]


def load_scenario_question(path: Path, scenario_id: str) -> EvalQuestion:
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row["scenario_id"] == scenario_id:
            return EvalQuestion(
                question_id=scenario_id, question=row["opening_message"]
            )
    raise KeyError(scenario_id)


def score_questions(
    service: RetrievalService,
    questions: list[EvalQuestion],
    question_set: QuestionSet,
) -> list[QueryScore]:
    scores: list[QueryScore] = []
    for question in questions:
        started = time.perf_counter()
        result = service.search_kb(question.question, top_k=1)
        latency_ms = (time.perf_counter() - started) * 1000
        top = result.candidates[0] if result.candidates else None
        scores.append(
            QueryScore(
                question_id=question.question_id,
                question_set=question_set,
                top1_score=top.rerank_score if top else float("-inf"),
                top1_slug=top.slug if top else None,
                latency_ms=latency_ms,
            )
        )
    return scores


def choose_threshold(
    answerable: Mapping[str, float], off_domain: list[float]
) -> ThresholdDecision:
    if not answerable or not off_domain:
        raise ValueError("answerable and off-domain score sets must be non-empty")
    gap_low = max(off_domain)
    gap_high = min(answerable.values())
    separated = gap_high > gap_low
    threshold = (
        (gap_low + gap_high) / 2 if separated else math.nextafter(gap_low, math.inf)
    )
    return ThresholdDecision(
        threshold=threshold,
        separated=separated,
        refused_answerable=sorted(
            question_id for question_id, score in answerable.items() if score < threshold
        ),
    )


def main() -> None:
    eval_dir = REPO_ROOT / "data/eval"
    answerable_questions = load_questions(eval_dir / "questions.jsonl")
    off_domain_questions = load_questions(eval_dir / "out_of_coverage.jsonl")
    partial_questions = [
        load_scenario_question(eval_dir / "scenarios.jsonl", _SC09_ID),
        EvalQuestion(question_id="PC-ROADMAP", question=_ROADMAP_PROBE),
    ]
    with psycopg.connect(settings.database_url) as connection:
        service = RetrievalService(connection, min_score=float("-inf"))
        answerable = score_questions(
            service, answerable_questions, QuestionSet.ANSWERABLE
        )
        off_domain = score_questions(
            service, off_domain_questions, QuestionSet.OFF_DOMAIN
        )
        partial = score_questions(
            service, partial_questions, QuestionSet.PARTIAL_COVERAGE
        )
    decision = choose_threshold(
        {s.question_id: s.top1_score for s in answerable},
        [s.top1_score for s in off_domain],
    )
    report = CalibrationReport(
        generated_on=date.today(),
        scores=answerable + off_domain + partial,
        decision=decision,
    )
    _REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    _REPORT_PATH.write_text(report.to_markdown())
    print(f"Chosen rerank_min_score threshold: {decision.threshold:.3f}")


if __name__ == "__main__":
    main()
