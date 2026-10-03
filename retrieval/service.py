import logging
from collections.abc import Mapping
from datetime import datetime
from typing import Any, LiteralString, NamedTuple

import psycopg
from psycopg.rows import class_row, dict_row

from core.config import settings
from encoders.embed import embed_query
from encoders.rerank import rerank_pairs
from retrieval.models import (
    KBSearchResult,
    KBSearchStatus,
    PolicyDocument,
    RetrievedPassage,
)

logger = logging.getLogger(__name__)

# RRF constant and branch/rerank depths are fixed by spec, never tuned per call.
_RRF_K = 60
_CANDIDATE_K = 20
_RERANK_K = 20
# Beyond the top_k, keep passages of articles absent from it when they also score well, so one article
# cannot crowd out a second relevant one.
_EXTRA_PASSAGES = 3
_EXTRA_SCORE_RATIO = 0.6
# Sections around a retrieved passage: the one before it and the next few, where steps usually follow.
_SECTIONS_BEFORE = 1
_SECTIONS_AFTER = 4


_SECTIONS_SQL: LiteralString = """
select
    p.id::text as passage_id,
    a.slug as slug,
    a.title as title,
    a.public_url as public_url,
    a.site_updated_at as site_updated_at,
    p.heading as heading,
    p.heading_anchor as heading_anchor,
    p.body as body,
    p.position as position
from passages p
join kb_articles a on a.slug = p.article_slug
where p.article_slug = %(slug)s and p.position between %(low)s and %(high)s and p.position <> %(position)s
order by p.position
"""


def with_other_articles(ranked: list[RetrievedPassage], top_k: int, min_score: float) -> list[RetrievedPassage]:
    """The top_k, plus well-scoring passages of articles the top_k lacks (best first, capped)."""
    head = ranked[:top_k]
    if not head:
        return head
    head_slugs = {p.slug for p in head}
    floor = max(min_score, _EXTRA_SCORE_RATIO * head[0].rerank_score)
    extras = [p for p in ranked[top_k:] if p.slug not in head_slugs and p.rerank_score >= floor]
    return head + extras[:_EXTRA_PASSAGES]


def _normalize_policy_id(policy_id: str) -> str:
    return policy_id.strip().upper().removesuffix(".MD")


class _FusedRow(NamedTuple):
    # One row of the hybrid SQL result, before rerank scoring is attached.
    passage_id: str
    slug: str
    title: str
    public_url: str
    site_updated_at: datetime | None
    heading: str
    heading_anchor: str
    body: str
    position: int
    lex_rank: int | None
    vec_rank: int | None
    rrf_score: float


_HYBRID_SQL: LiteralString = """
with q as materialized (
    select string_agg(quote_literal(lexeme), ' | ')::tsquery as tsq
    from unnest(tsvector_to_array(to_tsvector('english', %(query)s))) as lexeme
),
lexical as (
    select
        id,
        row_number() over (
            order by ts_rank_cd(search_vector, q.tsq) desc, id
        ) as lex_rank
    from passages, q
    where search_vector @@ q.tsq
    order by ts_rank_cd(search_vector, q.tsq) desc, id
    limit %(candidate_k)s
),
vector_search as (
    select
        id,
        row_number() over (
            order by embedding <=> %(embedding)s::vector, id
        ) as vec_rank
    from passages
    order by embedding <=> %(embedding)s::vector, id
    limit %(candidate_k)s
),
fused as (
    select
        coalesce(l.id, v.id) as id,
        l.lex_rank,
        v.vec_rank,
        coalesce(1.0 / (%(rrf_k)s + l.lex_rank), 0)
            + coalesce(1.0 / (%(rrf_k)s + v.vec_rank), 0) as rrf_score
    from lexical l
    full outer join vector_search v using (id)
)
select
    p.id::text as passage_id,
    a.slug as slug,
    a.title as title,
    a.public_url as public_url,
    a.site_updated_at as site_updated_at,
    p.heading as heading,
    p.heading_anchor as heading_anchor,
    p.body as body,
    p.position as position,
    f.lex_rank as lex_rank,
    f.vec_rank as vec_rank,
    f.rrf_score as rrf_score
from fused f
join passages p on p.id = f.id
join kb_articles a on a.slug = p.article_slug
order by f.rrf_score desc, passage_id
limit %(rerank_k)s
"""


class RetrievalService:
    def __init__(
        self,
        connection: psycopg.Connection[Any],
        min_score: float = settings.rerank_min_score,
    ) -> None:
        self._conn: psycopg.Connection[Any] = connection
        self._min_score: float = min_score
        with self._conn.cursor(row_factory=class_row(PolicyDocument)) as cur:
            cur.execute(
                "select id as policy_id, title, file_path, body "
                "from policies order by id"
            )
            self._policies: Mapping[str, PolicyDocument] = {
                p.policy_id: p for p in cur.fetchall()
            }
        with self._conn.cursor() as cur:
            cur.execute("select max(crawled_at) from snapshots")
            row = cur.fetchone()
            self._snapshot_date: datetime | None = row[0] if row else None

    def get_policy(self, policy_id: str) -> PolicyDocument | None:
        return self._policies.get(_normalize_policy_id(policy_id))

    def list_policies(self) -> list[PolicyDocument]:
        return list(self._policies.values())

    def adjacent_sections(self, passage: RetrievedPassage) -> list[RetrievedPassage]:
        """Sections around `passage` in its article, carrying its scores: context to answer from, not ranking."""
        if passage.position is None:
            return []
        params = {
            "slug": passage.slug,
            "position": passage.position,
            "low": passage.position - _SECTIONS_BEFORE,
            "high": passage.position + _SECTIONS_AFTER,
        }
        try:
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(_SECTIONS_SQL, params)
                rows = cur.fetchall()
        except psycopg.Error as exc:
            logger.error("Adjacent sections failed: %r", exc)
            if not self._conn.closed:
                self._conn.rollback()
            return []
        return [
            RetrievedPassage(
                **row, lex_rank=None, vec_rank=None, rrf_score=0.0, rerank_score=passage.rerank_score
            )
            for row in rows
        ]

    def _fetch_fused(self, query: str, embedding: list[float]) -> list[_FusedRow]:
        with self._conn.cursor(row_factory=class_row(_FusedRow)) as cur:
            cur.execute(
                _HYBRID_SQL,
                {
                    "query": query,
                    "embedding": embedding,
                    "rrf_k": _RRF_K,
                    "candidate_k": _CANDIDATE_K,
                    "rerank_k": _RERANK_K,
                },
            )
            return cur.fetchall()

    def _rank_and_gate(
        self,
        query: str,
        rows: list[_FusedRow],
        scores: list[float],
        top_k: int,
    ) -> KBSearchResult:
        scored = [
            RetrievedPassage(**row._asdict(), rerank_score=score)
            for row, score in zip(rows, scores, strict=True)
        ]
        ranked = sorted(
            scored, key=lambda p: (-p.rerank_score, -p.rrf_score, p.passage_id)
        )
        candidates = with_other_articles(ranked, top_k, self._min_score)
        confident = bool(candidates) and candidates[0].rerank_score >= self._min_score
        passages = [p for p in candidates if p.rerank_score >= self._min_score]
        status = (
            KBSearchStatus.CONFIDENT if confident else KBSearchStatus.LOW_CONFIDENCE_REFUSAL
        )
        return KBSearchResult(
            status=status,
            query=query,
            passages=passages,
            candidates=candidates,
            snapshot_date=self._snapshot_date,
        )

    def search_kb(self, query: str, top_k: int = 5) -> KBSearchResult:
        if top_k <= 0:
            raise ValueError(f"top_k must be positive, got {top_k}")
        if not query.strip():
            return KBSearchResult(
                status=KBSearchStatus.LOW_CONFIDENCE_REFUSAL,
                query=query,
                snapshot_date=self._snapshot_date,
            )
        embedding = embed_query(query)
        try:
            rows = self._fetch_fused(query, embedding)
        except psycopg.Error as exc:
            logger.error("KB search failed: %r", exc)
            if not self._conn.closed:
                self._conn.rollback()
            return KBSearchResult(
                status=KBSearchStatus.UNAVAILABLE,
                query=query,
                snapshot_date=self._snapshot_date,
                error=str(exc),
            )
        scores = rerank_pairs(query, [row.body for row in rows])
        return self._rank_and_gate(query, rows, scores, top_k)
