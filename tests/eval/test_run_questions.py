from decimal import Decimal

from eval.run_questions import ChunkScore, QuestionRun, to_markdown
from guardrails import MarkerKind
from orchestration import Citation


def _run(question_id: str, citations: tuple[Citation, ...], chunks: tuple[ChunkScore, ...]) -> QuestionRun:
    return QuestionRun(
        question_id=question_id,
        question="What is the MTU?",
        answer="It is 1350 bytes [kb:mtu#dtls].",
        citations=citations,
        chunks=chunks,
        latency_ms=1500,
        prompt_tokens=100,
        completion_tokens=20,
        cost_usd=Decimal("0.001"),
        snapshot_date="2026-09-29T10:35:47+00:00",
    )


def test_chunk_score_reads_a_trace_candidate() -> None:
    candidate = {"slug": "mtu", "heading_anchor": "dtls", "rrf_score": 0.03, "rerank_score": 7.5, "body": "ignored"}
    assert ChunkScore.from_candidate(candidate) == ChunkScore(
        slug="mtu", heading_anchor="dtls", rrf_score=0.03, rerank_score=7.5
    )


def test_answer_entry_carries_every_field_the_brief_lists() -> None:
    citation = Citation(kind=MarkerKind.KB, ref="mtu#dtls", title="MTU", url="https://kb/mtu", heading="DTLS")
    chunk = ChunkScore(slug="mtu", heading_anchor="dtls", rrf_score=0.0328, rerank_score=7.5)
    text = _run("Q01", (citation,), (chunk,)).to_markdown()
    assert "## Q01" in text and "What is the MTU?" in text and "It is 1350 bytes" in text
    assert "MTU › DTLS (`mtu#dtls`) https://kb/mtu" in text
    assert "| 1 | `mtu#dtls` | 0.0328 | 7.50 |" in text
    assert "1500 ms, 100+20 tokens, $0.001000" in text


def test_entry_without_citations_or_chunks_says_so_and_document_names_the_snapshot() -> None:
    text = to_markdown([_run("Q02", (), ())])
    assert "- none" in text and "none retrieved" in text
    assert "KB snapshot date: 2026-09-29T10:35:47+00:00" in text
