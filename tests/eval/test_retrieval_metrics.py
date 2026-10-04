import pytest

from eval.retrieval_metrics import (
    QuestionRetrieval,
    gold_articles,
    recall_at_k,
    reciprocal_rank,
    to_markdown,
)

GOLD = frozenset({"a", "b"})


@pytest.mark.parametrize(
    ("ranked", "k", "expected"),
    [
        (["a", "x", "b"], 1, 0.5),
        (["a", "x", "b"], 3, 1.0),
        (["x", "y", "z"], 3, 0.0),
        (["a", "a", "a"], 3, 0.5),  # repeated passages of one article count once
    ],
)
def test_recall_is_the_share_of_gold_articles_in_the_top_k(ranked: list[str], k: int, expected: float) -> None:
    assert recall_at_k(ranked, GOLD, k) == expected


def test_reciprocal_rank_is_one_over_the_first_gold_rank() -> None:
    assert reciprocal_rank(["x", "b", "a"], GOLD) == 0.5
    assert reciprocal_rank(["x", "y"], GOLD) == 0.0


def test_gold_articles_need_a_passage_graded_two() -> None:
    grades = {"p1": 2, "p2": 1, "p3": 2, "p4": 0, "p5": 2}
    slugs = {"p1": "a", "p2": "b", "p3": "a", "p4": "c"}  # p5 is gone from the index
    assert gold_articles(grades, slugs) == {"a"}


def test_report_states_how_gold_was_built_and_lists_the_misses() -> None:
    hit = QuestionRetrieval(question_id="Q01", question="q1", gold=frozenset({"a"}), ranked=(("a", 8.0),))
    miss = QuestionRetrieval(
        question_id="Q02", question="q2", gold=frozenset({"b"}), ranked=tuple((f"x{i}", 1.0) for i in range(6))
    )
    report = to_markdown([hit, miss], unlabeled=["Q03"])
    assert "LLM judge" in report and "not a human" in report and "Q03" in report
    assert "| Recall@1 | 0.50 |" in report and "| MRR | 0.50 |" in report
    assert "### Q02" in report and "### Q01" not in report
