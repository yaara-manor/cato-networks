from retrieval.models import RetrievedPassage
from retrieval.service import with_other_articles


def _passage(slug: str, n: int, score: float) -> RetrievedPassage:
    return RetrievedPassage(
        passage_id=f"{slug}-{n}", slug=slug, title=slug, public_url="u", site_updated_at=None, heading="h",
        heading_anchor="h", body="b", lex_rank=1, vec_rank=1, rrf_score=0.1, rerank_score=score,
    )  # fmt: skip


def test_other_article_passages_join_the_top_k_when_they_score_well() -> None:
    ranked = [_passage("a", i, 9.0 - i * 0.1) for i in range(6)] + [
        _passage("b", 0, 6.0),  # 0.6 * 9.0 = 5.4 floor: kept
        _passage("c", 0, 4.0),  # below the relative floor: dropped
        _passage("a", 9, 3.9),  # same article as the head: not an extra
    ]
    selected = with_other_articles(ranked, top_k=5, min_score=2.0)
    assert [p.slug for p in selected] == ["a"] * 5 + ["b"]


def test_extras_are_capped_and_respect_the_absolute_floor() -> None:
    ranked = [_passage("a", 0, 3.0)] + [_passage(f"x{i}", 0, 2.5) for i in range(6)]
    assert len(with_other_articles(ranked, top_k=1, min_score=2.0)) == 1 + 3
    assert with_other_articles(ranked, top_k=1, min_score=2.8) == ranked[:1]
    assert with_other_articles([], top_k=5, min_score=2.0) == []
