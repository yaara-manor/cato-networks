"""Read-only retrieval building blocks over the main repo's `passages` table.

Requires the repo root on sys.path (notebooks/CLIs add it; see `ensure_repo_on_path`).
Passage dict: {passage_id, slug, heading, body (<=1200 chars), score, rank}.
"""
from __future__ import annotations

import math
import os
import re
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any, TypedDict

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import psycopg  # noqa: E402
from psycopg.rows import dict_row  # noqa: E402

from encoders.embed import embed_query  # noqa: E402
from encoders.rerank import rerank_pairs  # noqa: E402
from retrieval.service import RetrievalService  # noqa: E402

DSN: str = os.environ.get("KB_DSN", "postgresql://kb:kb@localhost:5432/kb")
BODY_MAX: int = 1200


class Passage(TypedDict, total=False):
    passage_id: str
    slug: str
    heading: str
    body: str
    score: float
    rank: int
    rerank_score: float
    rrf_score: float
    lex_rank: int | None
    vec_rank: int | None


# Same OR-tsquery + ts_rank_cd ordering as the production lexical branch.
_LEX_SQL = """
with q as materialized (
    select string_agg(quote_literal(lexeme), ' | ')::tsquery as tsq
    from unnest(tsvector_to_array(to_tsvector('english', %(query)s))) as lexeme
)
select p.id::text as passage_id, p.article_slug as slug, p.heading, p.body,
       ts_rank_cd(p.search_vector, q.tsq) as score
from passages p, q
where p.search_vector @@ q.tsq
order by score desc, p.id
limit %(k)s
"""

# Same cosine ordering as the production vector branch; score = cosine similarity.
_VEC_SQL = """
select id::text as passage_id, article_slug as slug, heading, body,
       1 - (embedding <=> %(embedding)s::vector) as score
from passages
order by embedding <=> %(embedding)s::vector, id
limit %(k)s
"""

_conn: psycopg.Connection[Any] | None = None
_service: RetrievalService | None = None


def conn() -> psycopg.Connection[Any]:
    """Cached read-only autocommit connection."""
    global _conn
    if _conn is None or _conn.closed:
        c: psycopg.Connection[Any] = psycopg.connect(DSN, autocommit=True, row_factory=dict_row)
        c.read_only = True
        _conn = c
    return _conn


def _service_instance() -> RetrievalService:
    global _service
    if _service is None:
        # The service expects tuple rows, so it gets its own read-only connection.
        c: psycopg.Connection[Any] = psycopg.connect(DSN, autocommit=True)
        c.read_only = True
        _service = RetrievalService(c, min_score=float("-inf"))
    return _service


def _to_passages(rows: Sequence[dict[str, Any]], k: int) -> list[Passage]:
    return [
        Passage(passage_id=r["passage_id"], slug=r["slug"], heading=r["heading"],
                body=r["body"][:BODY_MAX], score=float(r["score"]), rank=i)
        for i, r in enumerate(rows[:k], 1)
    ]


def lexical_top(query: str, k: int = 50) -> list[Passage]:
    """Top-k by the production OR-tsquery / ts_rank_cd ranking. Empty if no lexeme matches."""
    with conn().cursor() as cur:
        cur.execute(_LEX_SQL, {"query": query, "k": k})
        return _to_passages(cur.fetchall(), k)


def dense_top(query: str, k: int = 50, embedding: list[float] | None = None) -> list[Passage]:
    """Top-k by bge cosine similarity (query embedded with the bge query prefix)."""
    emb = embedding if embedding is not None else embed_query(query)
    with conn().cursor() as cur:
        cur.execute(_VEC_SQL, {"embedding": emb, "k": k})
        return _to_passages(cur.fetchall(), k)


def get_passages_by_ids(ids: Sequence[str], full: bool = False) -> list[Passage]:
    """Fetch passages by id, preserving the order of `ids` (unknown ids skipped). score=0.0."""
    if not ids:
        return []
    with conn().cursor() as cur:
        cur.execute(
            "select id::text as passage_id, article_slug as slug, heading, body "
            "from passages where id::text = any(%(ids)s)", {"ids": list(ids)})
        by_id = {r["passage_id"]: r for r in cur.fetchall()}
    out: list[Passage] = []
    for i, pid in enumerate(ids, 1):
        r = by_id.get(pid)
        if r is None:
            continue
        out.append(Passage(passage_id=pid, slug=r["slug"], heading=r["heading"],
                           body=r["body"] if full else r["body"][:BODY_MAX], score=0.0, rank=i))
    return out


# ---------------------------------------------------------------- fusion

def _reranked(items: dict[str, Passage], scores: dict[str, float]) -> list[Passage]:
    order = sorted(scores, key=lambda pid: (-scores[pid], pid))
    out: list[Passage] = []
    for i, pid in enumerate(order, 1):
        p = Passage(**items[pid])  # type: ignore[typeddict-item]
        p["score"] = scores[pid]
        p["rank"] = i
        out.append(p)
    return out


def fuse_rrf(lex: Sequence[Passage], dense: Sequence[Passage], k: int = 60,
             w_lex: float = 1.0, w_vec: float = 1.0, depth: int | None = None) -> list[Passage]:
    """Weighted reciprocal rank fusion: score = w_lex/(k+lex_rank) + w_vec/(k+vec_rank).

    Ranks are list positions (1-based). With weights 1 and depth=20 this reproduces the
    production SQL (ties broken by passage_id). `depth` truncates each branch first.
    """
    lex_l = list(lex)[:depth] if depth else list(lex)
    den_l = list(dense)[:depth] if depth else list(dense)
    items: dict[str, Passage] = {}
    scores: dict[str, float] = {}
    lex_rank = {p["passage_id"]: i for i, p in enumerate(lex_l, 1)}
    vec_rank = {p["passage_id"]: i for i, p in enumerate(den_l, 1)}
    for p in [*lex_l, *den_l]:
        items.setdefault(p["passage_id"], p)
    for pid in items:
        s = 0.0
        if pid in lex_rank:
            s += w_lex / (k + lex_rank[pid])
        if pid in vec_rank:
            s += w_vec / (k + vec_rank[pid])
        scores[pid] = s
    out = _reranked(items, scores)
    for p in out:
        p["lex_rank"] = lex_rank.get(p["passage_id"])
        p["vec_rank"] = vec_rank.get(p["passage_id"])
        p["rrf_score"] = p["score"]
    return out


def _minmax(ps: Sequence[Passage]) -> dict[str, float]:
    if not ps:
        return {}
    vals = [p["score"] for p in ps]
    lo, hi = min(vals), max(vals)
    if hi == lo:
        return {p["passage_id"]: 1.0 for p in ps}
    return {p["passage_id"]: (p["score"] - lo) / (hi - lo) for p in ps}


def fuse_linear(lex: Sequence[Passage], dense: Sequence[Passage],
                w_lex: float, w_vec: float) -> list[Passage]:
    """Min-max normalise each branch's scores over its own list, then weighted sum.
    A passage absent from a branch contributes 0 for that branch."""
    nl, nd = _minmax(lex), _minmax(dense)
    items: dict[str, Passage] = {}
    for p in [*lex, *dense]:
        items.setdefault(p["passage_id"], p)
    scores = {pid: w_lex * nl.get(pid, 0.0) + w_vec * nd.get(pid, 0.0) for pid in items}
    return _reranked(items, scores)


def fuse_dense_only(lex: Sequence[Passage], dense: Sequence[Passage]) -> list[Passage]:
    return [Passage(**p) for p in dense]  # type: ignore[typeddict-item]


def fuse_lexical_only(lex: Sequence[Passage], dense: Sequence[Passage]) -> list[Passage]:
    return [Passage(**p) for p in lex]  # type: ignore[typeddict-item]


# ---------------------------------------------------------------- rerank

def rerank(query: str, passages: Sequence[Passage], top_n: int = 20,
           full_body: bool = True) -> list[Passage]:
    """Cross-encoder rerank of the first `top_n` passages with the main repo's MiniLM.

    Scores the FULL passage body (as production does; `full_body=False` scores the
    <=1200-char body in the dicts). Returns copies with `rerank_score` (also `score`),
    sorted by (-rerank_score, -rrf_score if present, passage_id) and re-ranked.
    """
    cand = list(passages)[:top_n]
    if not cand:
        return []
    if full_body:
        full = {p["passage_id"]: p["body"] for p in get_passages_by_ids([c["passage_id"] for c in cand], full=True)}
        texts = [full.get(c["passage_id"], c["body"]) for c in cand]
    else:
        texts = [c["body"] for c in cand]
    scores = rerank_pairs(query, texts)
    out: list[Passage] = []
    for c, s in zip(cand, scores, strict=True):
        p = Passage(**c)  # type: ignore[typeddict-item]
        p["rerank_score"] = s
        p["score"] = s
        out.append(p)
    out.sort(key=lambda p: (-p["rerank_score"], -p.get("rrf_score", 0.0), p["passage_id"]))
    for i, p in enumerate(out, 1):
        p["rank"] = i
    return out


# ---------------------------------------------------------------- Direction A cleanup

_S = r"(?:^|(?<=[.!?]\s))"  # sentence start
_RULES: list[tuple[re.Pattern[str], str]] = [
    # reply/forward prefixes
    (re.compile(r"^\s*(?:(?:re|fw|fwd)\s*:\s*)+", re.I), ""),
    # greetings at a sentence start: "Hi team,", "Hello Cato support,", "Dear Sir or Madam,"
    (re.compile(_S + r"(?:hi|hello|hey|dear|greetings|good\s+(?:morning|afternoon|evening))\b[^\n,.!?:;]{0,40}[,.!:;]?\s*", re.I), ""),
    # sign-offs at the very end: "Best regards, John Smith"
    (re.compile(r"\b(?i:best regards|kind regards|warm regards|regards|cheers|sincerely|best wishes|br)\b[,.!]?(?:\s+[A-Z][\w.'-]*){0,3}\s*[.!]?\s*$"), ""),
    (re.compile(r"\bsent from my (?:iphone|ipad|android|phone)\b.*$", re.I), ""),
    # thanks
    (re.compile(r"\b(?:many thanks|thanks|thank you|thx|tia)\b(?:\s+(?:so much|in advance|a lot|very much|again|all))*\s*[,.!]*", re.I), ""),
    # urgency / pleading filler
    (re.compile(r"\b(?:urgent(?:ly)?|asap|a\.s\.a\.p\.?|as soon as possible|immediately|right now|this is critical)\b\s*[:!,-]*", re.I), ""),
    (re.compile(r"\b(?:please\s+(?:fix|help)(?:\s+(?:it|this|us|me))?|fix it or we leave|kindly|i would appreciate(?: your help)?)\b[\s,.!]*", re.I), ""),
    (re.compile(r"\bplease\b[,]?", re.I), ""),
    (re.compile(r"\bNOW\b"), ""),
    # repeated punctuation
    (re.compile(r"([!?.])\1{1,}"), r"\1"),
    (re.compile(r"\s+([,.!?;:])"), r"\1"),
    (re.compile(r"(?:^|\s)[,.;:!-]+(?=\s|$)"), " "),
]


def clean_query(text: str) -> str:
    """Deterministic query cleanup for Direction A (no LLM).

    Removes: Re:/Fw: prefixes, greetings at sentence starts (Hi/Hello/Dear/Good morning + <=40
    chars up to punctuation), sign-offs at the end (regards/cheers/sincerely + up to 3
    capitalised name tokens, "Sent from my ..."), thanks, urgency filler (urgent, ASAP,
    immediately, right now, NOW, please fix it, kindly), repeated punctuation, and exact
    duplicate sentences (case-insensitive; subject lines are often repeated in the body).
    Keeps everything else verbatim: product terms, error codes, numbers, site/city names.
    If cleaning would leave < 3 characters, the whitespace-normalised original is returned.
    """
    norm = re.sub(r"\s+", " ", text).strip()
    cur = norm
    for pat, rep in _RULES:
        cur = pat.sub(rep, cur)
    sents = re.split(r"(?<=[.!?])\s+", cur)
    seen: set[str] = set()
    kept: list[str] = []
    for s in sents:
        key = re.sub(r"\W+", " ", s).strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        kept.append(s.strip())
    cur = re.sub(r"\s+", " ", " ".join(kept)).strip(" ,;:-")
    return cur if len(cur) >= 3 else norm


# ---------------------------------------------------------------- current production pipeline

def search_current(query: str, top_k: int = 5) -> list[Passage]:
    """Exact production pipeline: hybrid RRF (20+20) -> MiniLM rerank -> sort -> top_k.

    Calls `RetrievalService(conn, min_score=-inf).search_kb(query, top_k).candidates`, i.e. no
    score gate. Returns passages with score=rerank_score, plus rerank_score, rrf_score,
    lex_rank, vec_rank. Body truncated to 1200 chars.
    """
    res = _service_instance().search_kb(query, top_k)
    return [
        Passage(passage_id=p.passage_id, slug=p.slug, heading=p.heading, body=p.body[:BODY_MAX],
                score=float(p.rerank_score), rank=i, rerank_score=float(p.rerank_score),
                rrf_score=float(p.rrf_score), lex_rank=p.lex_rank, vec_rank=p.vec_rank)
        for i, p in enumerate(res.candidates, 1)
    ]


def gate_stats(passages: Sequence[Passage]) -> dict[str, float]:
    """Helper for relative gates: top1, top2 margin, z-score of top1 among the list."""
    s = [p["score"] for p in passages]
    if len(s) < 2:
        return {"top1": s[0] if s else math.nan, "margin": math.nan, "z": math.nan}
    mean = sum(s) / len(s)
    sd = math.sqrt(sum((x - mean) ** 2 for x in s) / len(s))
    return {"top1": s[0], "margin": s[0] - s[1], "z": (s[0] - mean) / sd if sd else 0.0}
