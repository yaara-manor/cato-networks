from collections.abc import Iterator
from typing import Any

import psycopg
import pytest

from core.config import REPO_ROOT, settings
from eval.calibrate_threshold import (
    QuestionSet,
    choose_threshold,
    load_questions,
    score_questions,
)
from retrieval.service import RetrievalService


@pytest.fixture(scope="module")
def connection() -> Iterator[psycopg.Connection[Any]]:
    with psycopg.connect(settings.database_url) as conn:
        yield conn


def test_calibration_separates_real_answerable_from_off_domain(
    connection: psycopg.Connection[Any],
) -> None:
    service = RetrievalService(connection, min_score=float("-inf"))
    answerable_all = load_questions(REPO_ROOT / "data/eval/questions.jsonl")
    off_domain_all = load_questions(REPO_ROOT / "data/eval/out_of_coverage.jsonl")
    answerable = score_questions(
        service,
        [q for q in answerable_all if q.question_id in {"Q01", "Q05"}],
        QuestionSet.ANSWERABLE,
    )
    off_domain = score_questions(
        service,
        [q for q in off_domain_all if q.question_id in {"OOD06", "OOD07"}],
        QuestionSet.OFF_DOMAIN,
    )

    decision = choose_threshold(
        {s.question_id: s.top1_score for s in answerable},
        [s.top1_score for s in off_domain],
    )

    assert decision.separated is True
    assert decision.refused_answerable == []
    assert max(s.top1_score for s in off_domain) < decision.threshold
    assert decision.threshold < min(s.top1_score for s in answerable)
    assert all(s.latency_ms > 0 for s in answerable + off_domain)
