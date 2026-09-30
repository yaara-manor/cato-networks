import json
import os
import re
from collections.abc import Iterator

import psycopg
import pytest

from core.config import REPO_ROOT
from retrieval.models import KBSearchStatus
from retrieval.service import RetrievalService

_CITATION_TAG_RE = re.compile(r"^\[kb:[^#\]]+#[^\]]+\]$")

_KEY_TERMS: dict[str, str] = {
    "Q01": "mtu",
    "Q05": "bgp",
    "Q10": "no_proposal_chosen",
    "Q15": "azure",
}


def _question_text(question_id: str) -> str:
    # Read the question text from the eval fixture; never copy it inline.
    with (REPO_ROOT / "data/eval/questions.jsonl").open() as f:
        for line in f:
            row = json.loads(line)
            if row["question_id"] == question_id:
                return row["question"]
    raise KeyError(question_id)


@pytest.fixture(scope="module")
def connection() -> Iterator[psycopg.Connection[object]]:
    database_url = os.environ.get("DATABASE_URL", "postgresql://kb:kb@localhost:5432/kb")
    with psycopg.connect(database_url) as conn:
        yield conn


@pytest.fixture(scope="module")
def service(connection: psycopg.Connection[object]) -> RetrievalService:
    return RetrievalService(connection)


@pytest.fixture(scope="module")
def ungated(connection: psycopg.Connection[object]) -> RetrievalService:
    return RetrievalService(connection, min_score=float("-inf"))


@pytest.mark.parametrize("question_id", ["Q01", "Q05", "Q10", "Q15"])
def test_eval_questions_are_answered_confidently(
    service: RetrievalService, question_id: str
) -> None:
    result = service.search_kb(_question_text(question_id))

    assert result.status == KBSearchStatus.CONFIDENT
    assert result.passages != []
    assert result.snapshot_date is not None

    for passage in result.passages:
        assert passage.rerank_score >= service._min_score
        assert passage.rrf_score > 0
        assert _CITATION_TAG_RE.match(passage.citation_tag())

    key_term = _KEY_TERMS[question_id]
    top3_bodies = " ".join(p.body.lower() for p in result.passages[:3])
    assert key_term in top3_bodies, (
        f"{question_id}: top-3 slugs/scores: "
        f"{[(p.slug, p.rerank_score) for p in result.passages[:3]]}"
    )


def test_ungated_ranking_is_consistent_and_deterministic(
    ungated: RetrievalService,
) -> None:
    question = _question_text("Q01")

    first = ungated.search_kb(question, top_k=20)
    second = ungated.search_kb(question, top_k=20)

    assert [p.passage_id for p in first.candidates] == [
        p.passage_id for p in second.candidates
    ]
    assert len(first.candidates) <= 20

    scores = [p.rerank_score for p in first.candidates]
    assert scores == sorted(scores, reverse=True)

    for candidate in first.candidates:
        assert candidate.lex_rank is not None or candidate.vec_rank is not None
        if candidate.lex_rank is not None:
            assert 1 <= candidate.lex_rank <= 20
        if candidate.vec_rank is not None:
            assert 1 <= candidate.vec_rank <= 20

        expected_rrf = 0.0
        if candidate.lex_rank is not None:
            expected_rrf += 1.0 / (60 + candidate.lex_rank)
        if candidate.vec_rank is not None:
            expected_rrf += 1.0 / (60 + candidate.vec_rank)
        assert abs(candidate.rrf_score - expected_rrf) < 1e-9

    assert first.passages == first.candidates


def test_english_stemming_reaches_lexical_branch(ungated: RetrievalService) -> None:
    result = ungated.search_kb(
        "Which priority policy applies when rekeying failed?", top_k=20
    )

    assert any(c.lex_rank is not None for c in result.candidates)
