from collections.abc import Iterator
import psycopg
import pytest

from core.config import settings
from retrieval.service import RetrievalService



@pytest.fixture(scope="module")
def retrieval() -> Iterator[RetrievalService]:
    with psycopg.connect(settings.database_url) as conn:
        yield RetrievalService(conn)


PLAYBOOK = "xops-network-playbook-socket-offline-after-upgrade"


def test_overview_hit_brings_the_steps_below_it(retrieval: RetrievalService) -> None:
    result = retrieval.search_kb("Socket does not come back after scheduled upgrade what to do")
    overview = next(p for p in result.candidates if p.slug == PLAYBOOK and p.heading_anchor == "overview")

    sections = retrieval.adjacent_sections(overview)

    anchors = [s.heading_anchor for s in sections]
    assert any(a.startswith("step-2") for a in anchors) and any(a.startswith("step-3") for a in anchors)
    assert overview.passage_id not in {s.passage_id for s in sections}
    assert {s.rerank_score for s in sections} == {overview.rerank_score}
    assert [s.position for s in sections] == sorted(s.position for s in sections if s.position is not None)


def test_passage_without_position_has_no_neighbours(retrieval: RetrievalService) -> None:
    result = retrieval.search_kb("Socket does not come back after scheduled upgrade what to do")
    assert retrieval.adjacent_sections(result.candidates[0].model_copy(update={"position": None})) == []
