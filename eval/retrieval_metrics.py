import argparse
import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import psycopg
from pydantic import BaseModel, ConfigDict

from core.config import REPO_ROOT, settings
from eval.calibrate_threshold import EvalQuestion, load_questions
from retrieval.service import RetrievalService

_QUESTIONS_PATH: Path = REPO_ROOT / "data/eval/questions.jsonl"
_JUDGMENTS_PATH: Path = REPO_ROOT / "experiments/cache/judgments.json"
_REPORT_PATH: Path = REPO_ROOT / "docs/eval/retrieval_report.md"
_GOLD_GRADE = 2  # the experiments' judge: 2 means the passage answers the question
_DEPTH = 10  # passages ranked per question
_KS: tuple[int, ...] = (1, 3, 5)

# {question id: {passage id: judge's grade 0..2}}
Judgments = Mapping[str, Mapping[str, int]]


def recall_at_k(ranked_slugs: Sequence[str], gold: frozenset[str], k: int) -> float:
    """Share of the gold articles that have a passage among the first k ranked passages."""
    return len(gold & set(ranked_slugs[:k])) / len(gold)


def reciprocal_rank(ranked_slugs: Sequence[str], gold: frozenset[str]) -> float:
    """1 / rank of the first passage from a gold article; 0 when none is ranked."""
    return next((1 / rank for rank, slug in enumerate(ranked_slugs, start=1) if slug in gold), 0.0)


def gold_articles(grades: Mapping[str, int], passage_slugs: Mapping[str, str]) -> frozenset[str]:
    """Articles holding at least one passage graded as answering the question."""
    return frozenset(passage_slugs[p] for p, grade in grades.items() if grade >= _GOLD_GRADE and p in passage_slugs)


class QuestionRetrieval(BaseModel):
    model_config = ConfigDict(frozen=True)

    question_id: str
    question: str
    gold: frozenset[str]
    ranked: tuple[tuple[str, float], ...]  # (slug, rerank score), best first

    @property
    def slugs(self) -> list[str]:
        return [slug for slug, _ in self.ranked]

    def recall(self, k: int) -> float:
        return recall_at_k(self.slugs, self.gold, k)

    @property
    def mrr(self) -> float:
        return reciprocal_rank(self.slugs, self.gold)


def load_judgments(path: Path = _JUDGMENTS_PATH) -> Judgments:
    raw: dict[str, dict[str, dict[str, Any]]] = json.loads(path.read_text(encoding="utf-8"))
    return {qid: {pid: int(v["grade"]) for pid, v in passages.items()} for qid, passages in raw.items()}


def passage_slugs(conn: psycopg.Connection[Any], judgments: Judgments, question_ids: Sequence[str]) -> dict[str, str]:
    ids = sorted({pid for qid in question_ids for pid in judgments.get(qid, {})})
    rows = conn.execute("select id::text, article_slug from passages where id::text = any(%s)", (ids,)).fetchall()
    return {pid: slug for pid, slug in rows}


def measure(
    service: RetrievalService, question: EvalQuestion, gold: frozenset[str]
) -> QuestionRetrieval:
    """The pipeline's own ranking for the raw question text, as the agent's search tool would return it."""
    candidates = service.search_kb(question.question, top_k=_DEPTH).candidates
    return QuestionRetrieval(
        question_id=question.question_id,
        question=question.question,
        gold=gold,
        ranked=tuple((p.slug, p.rerank_score) for p in candidates),
    )


def to_markdown(measured: list[QuestionRetrieval], unlabeled: list[str]) -> str:
    n = len(measured)
    recalls = {k: sum(m.recall(k) for m in measured) / n for k in _KS}
    mrr = sum(m.mrr for m in measured) / n
    misses = [m for m in measured if m.recall(max(_KS)) < 1]
    lines = [
        "# Retrieval quality on the 35 benchmark questions",
        "",
        f"- Generated: {datetime.now(tz=UTC).isoformat(timespec='seconds')} by `python -m eval.retrieval_metrics`",
        f"- Questions scored: {n} of {n + len(unlabeled)}. Not scored (no passage graded as answering them): "
        f"{', '.join(unlabeled) or 'none'}",
        f"- Ranking measured: `RetrievalService.search_kb(question text, top_k={_DEPTH})` (hybrid fusion, then "
        "the cross-encoder reranker). It is the retrieval stage alone, not the agent's own LLM-written queries.",
        "",
        "## How the gold answers were obtained",
        "",
        "The brief keeps the answer keys with the reviewers, so these numbers rest on our own labels:",
        "",
        "- Gold articles come from `experiments/cache/judgments.json`: an **LLM judge** graded passages 0, 1 or 2 "
        "per question. A gold article is one with at least one passage graded 2.",
        "- Only passages that the experiments' retrieval variants surfaced were graded (a pool, about 34 per "
        "question), so a relevant article that no variant surfaced is missing from the gold set. "
        "Unjudged articles count as non-relevant.",
        "- The judge is not a human, so the figures measure agreement with it, not with the reviewers' keys.",
        "- Recall and MRR are per **article**: a hit is any passage of a gold article.",
        f"- The judge is generous: {sum(len(m.gold) for m in measured) / n:.1f} gold articles per question on average, "
        "against the one or two the brief describes. That makes recall conservative; MRR (first relevant "
        "article) is the steadier figure.",
        "",
        "## Results",
        "",
        "| Metric | Value |",
        "|---|---|",
        *(f"| Recall@{k} | {recalls[k]:.2f} |" for k in _KS),
        f"| MRR | {mrr:.2f} |",
        "",
        "## Failure analysis",
        "",
        f"Questions whose gold articles are not all in the top {max(_KS)}: {len(misses)} of {n}.",
        "",
    ]
    for m in misses:
        found = [slug for slug in dict.fromkeys(m.slugs) if slug in m.gold]
        lines += [
            f"### {m.question_id}",
            "",
            f"- Question: {m.question}",
            f"- Gold: {', '.join(sorted(m.gold))}",
            f"- Gold found in the top {_DEPTH}: {', '.join(found) or 'none'}",
            f"- Top 3 returned: {', '.join(f'{slug} ({score:.1f})' for slug, score in m.ranked[:3])}",
            "",
        ]
    return "\n".join(lines)


def main(report: Path) -> None:
    questions = load_questions(_QUESTIONS_PATH)
    judgments = load_judgments()
    measured: list[QuestionRetrieval] = []
    unlabeled: list[str] = []
    with psycopg.connect(settings.database_url) as conn:
        slugs = passage_slugs(conn, judgments, [q.question_id for q in questions])
        service = RetrievalService(conn)
        for question in questions:
            gold = gold_articles(judgments.get(question.question_id, {}), slugs)
            if gold:
                measured.append(measure(service, question, gold))
            else:
                unlabeled.append(question.question_id)
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(to_markdown(measured, unlabeled), encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Recall@k and MRR of the retrieval stage on the benchmark.")
    parser.add_argument("--report", type=Path, default=_REPORT_PATH)
    main(parser.parse_args().report)
