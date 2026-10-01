# 03 — Hybrid `search_kb` — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `RetrievalService.search_kb`, the realtime KB retrieval path:
- lexical top-20 (`'english'` `tsvector`) plus vector top-20 (pgvector cosine), fused with RRF ($k=60$) in one SQL roundtrip
- the RRF top-20 reranked by the MiniLM-L12 cross-encoder
- a gate on `rerank_min_score`
- the answer returned in a `KBSearchResult` envelope that never raises on a DB fault.

**Architecture:** One query runs the whole first stage: a `q` CTE builds the tsquery, then `lexical`, `vector_search`, a `fused` `FULL OUTER JOIN`, and the metadata join. It returns at most `_RERANK_K = 20` rows, already ordered by RRF. Python then:
1. calls `encoders.rerank.rerank_pairs` once over those bodies
2. sorts deterministically
3. gates on `min_score`
4. builds the envelope.

`psycopg.Error` becomes status `UNAVAILABLE`, after a rollback so the shared connection stays usable. The reranker is ~95% of latency (design §2.8), so everything else stays at one roundtrip and no per-row Python work beyond model construction.

**Tech Stack:** Python 3.12, psycopg 3 (sync, `psycopg.rows.class_row`), PostgreSQL 18 + pgvector 0.8.6, sentence-transformers, Pydantic v2, pytest.

**Spec:** [design.md](design.md) §1, §2.4–2.8, §3, §4.1.1–2, §4.2.1–3, §5.1 (except the SC-09 threshold test, which is plan 04).

**Depends on:**
- plan 01: `encoders.embed.embed_query`, `encoders.rerank.rerank_pairs`, the `'english'` `search_vector`
- plan 02: `retrieval/models.py`, `retrieval/service.py`, `RetrievalService.__init__(connection)`, `self._conn`.

Before starting, check that all of these exist on the base branch. If anything is missing, STOP and report.

## Global Constraints

- Sync-only. Services take `psycopg.Connection[Any]`.
- Every function and method is fully annotated and passes Pyright `standard`. No bare `list`/`dict`, no implicit `Any`.
- ruff clean. Imports go at the top of the module. f-strings. SQL is a module-level `LiteralString` constant with named `%(name)s` parameters only: no f-string SQL, and constants are bound as parameters, not interpolated.
- New Pydantic models are frozen (`ConfigDict(frozen=True)`).
- No new dependencies.
- Constants fixed by the spec live as module constants in `retrieval/service.py`: `_RRF_K = 60`, `_CANDIDATE_K = 20`, `_RERANK_K = 20`. They are not constructor parameters.
- No injected model callables. `search_kb` calls `embed_query` and `rerank_pairs` directly (design §4.2.1).
- Match the surrounding code: short `#` line comments, `logger = logging.getLogger(__name__)` as in `services/customer_service.py`.
- Tests are functional against the real seeded PostgreSQL and real local models, no mocks. If the compose Postgres is not running, STOP and report.
- Verify with `uv run pytest <path> -v`, `uvx ruff check <paths>` and `uvx pyright <paths>`.

## Branching

- Plan branch: `p-1-4-03_hybrid-search`, created from `p-1-4_kb-retrieval-policy` after plans 01 and 02 are merged into it.
- Task branches, sequential (Task 2 builds on Task 1): `p-1-4-03-t1_search-kb`, `p-1-4-03-t2_search-kb-faults`. Each merges into the plan branch before the next starts.
- Task 3 runs on the plan branch. Never merge to master, never create a worktree.

## Review Focus

1. **Integer division in RRF.** `1 / (60 + rank)` over SQL integers is `0`. The SQL must divide a float literal (`1.0 / …`). → Task 1 invariant test checks `rrf_score` against the ranks.
2. **Queries whose every word is a stopword** (`"what is the"`): the tsquery is `NULL`, so the lexical branch is empty. The vector branch must still return candidates, with every `lex_rank` `None`, and no SQL error. → Task 2 user-input test.
3. **User text carrying SQL or tsquery syntax** (`O'Brien`, `a & b | !c :*`, `'); drop table passages; --`): lexemes pass through `quote_literal` and bound parameters. The status is not `UNAVAILABLE`, and `passages` still has 14,109 rows afterwards. → Task 2 user-input test.
4. **Rollback on a closed connection raises** (`OperationalError: the connection is closed`, verified). The fault handler rolls back only when `not self._conn.closed`, or the outage path itself crashes. → Task 2 tests (closed connection, and `statement_timeout` cancellation followed by `select 1` on the same connection).
5. **Very long input** (a 5,000-character pasted log): both encoders truncate to 512 tokens, and the search returns a normal envelope without raising. → Task 2 user-input test.

Deliberately not tested (simple guard): `top_k <= 0` raising `ValueError`. The guard stays in the code.

---

### Task 1: Result models + single-roundtrip hybrid search (happy path)

**Files:**
- Modify: `retrieval/models.py` (add `KBSearchStatus`, `RetrievedPassage`, `KBSearchResult`)
- Modify: `retrieval/service.py` (constants, `_FusedRow`, `_HYBRID_SQL`, snapshot load, `min_score`, `_fetch_fused`, `_rank_and_gate`, `search_kb`)
- Modify: `core/models.py` and `core/__init__.py`: delete the unused `Citation` model and its export, which `RetrievedPassage` replaces (design §2.2).
- Modify: `docs/overview/decisions.md` ADR-005 "Package Cohesion" bullet: drop `Citation` from the `core/models.py` list.
- Test: `tests/retrieval/test_search_kb.py`

**Interfaces:**
- Consumes:
  - `encoders.embed.embed_query(text: str) -> list[float]`
  - `encoders.rerank.rerank_pairs(question: str, passages: list[str]) -> list[float]`
  - `RetrievalService.__init__(connection)` and `self._conn` from plan 02
- Produces:
  - `retrieval.models.KBSearchStatus(StrEnum)`: `CONFIDENT = "CONFIDENT"`, `LOW_CONFIDENCE_REFUSAL = "LOW_CONFIDENCE_REFUSAL"`, `UNAVAILABLE = "UNAVAILABLE"`. The values equal the names, as in `tools/models.TelemetryStatus`.
  - `retrieval.models.RetrievedPassage`, frozen, with fields:
    - `passage_id: str`, `slug: str`, `title: str`, `public_url: str`, `site_updated_at: AwareDatetime | None`
    - `heading: str`, `heading_anchor: str`, `body: str`
    - `lex_rank: int | None`, `vec_rank: int | None`
    - `rrf_score: float`, `rerank_score: float`
    - and `citation_tag() -> str`, returning `[kb:{slug}#{heading_anchor}]`.
  - `retrieval.models.KBSearchResult`, frozen, with fields:
    - `status: KBSearchStatus`
    - `query: str`
    - `passages: list[RetrievedPassage] = []` (Pydantic copies defaults)
    - `candidates: list[RetrievedPassage] = []`
    - `snapshot_date: AwareDatetime | None`
    - `error: str | None = None`
  - `RetrievalService.__init__(self, connection: psycopg.Connection[Any], min_score: float = settings.rerank_min_score) -> None`. Plan 04 passes `min_score=float("-inf")`.
  - `RetrievalService.search_kb(self, query: str, top_k: int = 5) -> KBSearchResult`

- [ ] **Step 1: Write the failing functional tests** in `tests/retrieval/test_search_kb.py`.
  - A module-scoped fixture opens the connection and builds one `RetrievalService`, so model load is paid once.
  - A second fixture builds a service with `min_score=float("-inf")`, called `ungated`.
  - `test_eval_questions_are_answered_confidently`, parametrized over Q01, Q05, Q10 and Q15. Question text is read from `data/eval/questions.jsonl` by `question_id`, never copied. Assertions:
    - status is `CONFIDENT` with non-empty `passages`
    - `snapshot_date` is not `None`
    - every passage has `rerank_score >= min_score` and `rrf_score > 0`
    - `citation_tag()` matches the regex `^\[kb:[^#\]]+#[^\]]+\]$`
    - one of the top-3 passage bodies contains, case-insensitively, the question's key term (Q01 `mtu`, Q05 `bgp`, Q10 `no_proposal_chosen`, Q15 `azure`).
  - `test_ungated_ranking_is_consistent_and_deterministic`, using `ungated.search_kb(Q01 text, top_k=20)` run twice:
    - both runs give identical `passage_id` lists
    - `len(candidates) <= 20`
    - candidates are sorted by `rerank_score` descending
    - each candidate has at least one of `lex_rank`/`vec_rank`, each within 1–20
    - `rrf_score` equals the sum of `1 / (60 + rank)` over present ranks, within `1e-9`
    - `passages == candidates` (ungated).
  - `test_english_stemming_reaches_lexical_branch`: `ungated.search_kb("Which priority policy applies when rekeying failed?", top_k=20)` has at least one candidate with a `lex_rank`. Under the old `'simple'` column, `polici`, `prioriti` and `rekey` could never match.
- [ ] **Step 2: Run to confirm failure.** `uv run pytest tests/retrieval/test_search_kb.py -v`. Expected: `ImportError` for `KBSearchResult`, or `AttributeError: search_kb`.
- [ ] **Step 3: Add the three models** to `retrieval/models.py` exactly as in Interfaces. Delete `Citation` from `core/models.py` and `core/__init__.py`, then check `grep -rn "Citation\b" --include=*.py .` (excluding `.venv`) returns nothing.
- [ ] **Step 4: Add the internals to `retrieval/service.py`.**
  - Constants `_RRF_K`, `_CANDIDATE_K`, `_RERANK_K`.
  - `_FusedRow(NamedTuple)`, private, with the 11 fields of `RetrievedPassage` minus `rerank_score`, in SQL select order. `class_row(_FusedRow)` builds it straight from the cursor, so there is no index-based tuple mapping.
  - `_HYBRID_SQL: LiteralString`, whose CTEs follow design §4.2.3:
    - `q AS MATERIALIZED`: `string_agg(quote_literal(lexeme), ' | ')::tsquery` over `unnest(tsvector_to_array(to_tsvector('english', %(query)s)))`. Use the plain cast, not `to_tsquery('english', …)`, which would stem the stems again.
    - `lexical`: `id`, plus `row_number() over (order by ts_rank_cd(search_vector, q.tsq) desc, id)` as `lex_rank`, from `passages, q`, where `search_vector @@ q.tsq`, ordered by the same key, limit `%(candidate_k)s`.
    - `vector_search`: `id`, plus `row_number() over (order by embedding <=> %(embedding)s::vector, id)` as `vec_rank`, limit `%(candidate_k)s`. Binding a `list[float]` with a `::vector` cast is verified to work without `register_vector`, so the shared connection is not mutated.
    - `fused`: `coalesce(l.id, v.id)`, `lex_rank`, `vec_rank`, and `coalesce(1.0 / (%(rrf_k)s + lex_rank), 0) + coalesce(1.0 / (%(rrf_k)s + vec_rank), 0)` as `rrf_score`, from `lexical l full outer join vector_search v using (id)`.
    - Final select: `p.id::text` as `passage_id`, then the article and passage columns, ranks and `rrf_score`. It joins `passages p` and `kb_articles a` (`a.slug = p.article_slug`), orders by `rrf_score desc, passage_id`, and limits to `%(rerank_k)s`.
  - `__init__` gains `min_score`, stored as `self._min_score`, and `self._snapshot_date: datetime | None` from `select max(crawled_at) from snapshots`. That is one extra query at construction, never per search.
  - `_fetch_fused(self, query: str, embedding: list[float]) -> list[_FusedRow]`: one `execute` of `_HYBRID_SQL` with a `class_row(_FusedRow)` cursor, binding `query`, `embedding`, `rrf_k`, `candidate_k` and `rerank_k`.
  - `_rank_and_gate(self, query: str, rows: list[_FusedRow], scores: list[float], top_k: int) -> KBSearchResult`, with no I/O:
    1. build `RetrievedPassage(**row._asdict(), rerank_score=score)` per pair
    2. sort by `(-rerank_score, -rrf_score, passage_id)`
    3. take `candidates = ranked[:top_k]`
    4. `passages` = candidates with `rerank_score >= self._min_score`
    5. status is `CONFIDENT` when the top candidate clears the gate, otherwise `LOW_CONFIDENCE_REFUSAL` with `passages=[]`.
  - `search_kb`, happy path only in this task: `embedding = embed_query(query)` → `rows = self._fetch_fused(query, embedding)` → `scores = rerank_pairs(query, [r.body for r in rows])` → `_rank_and_gate`.
- [ ] **Step 5: Run and confirm pass.** `uv run pytest tests/retrieval -v`. Expected: all PASS.
  - If a Q-test fails its key-term check, STOP and report the top-3 slugs and scores. Do not loosen the test.
- [ ] **Step 6: Clean-code gate.** `uvx ruff check retrieval tests/retrieval` and `uvx pyright retrieval`. Both clean.
- [ ] **Step 7: Commit** on `p-1-4-03-t1_search-kb`: `feat(retrieval): single-roundtrip hybrid search_kb with rerank gate`.

---

### Task 2: Guards, edge inputs, and DB-fault envelope

**Files:**
- Modify: `retrieval/service.py` (`search_kb` guards and fault handling)
- Test: `tests/retrieval/test_search_kb.py`

**Interfaces:**
- Consumes: Task 1's `search_kb`, `_fetch_fused`, `KBSearchStatus`.
- Produces: the final `search_kb` contract. `ValueError` on `top_k <= 0`. Otherwise it always returns a `KBSearchResult`, and never raises on `psycopg.Error`.

- [ ] **Step 1: Write three failing functional tests.** Each outage test gets its own fresh connection.
  - `test_unusual_user_input_never_breaks_search`, one test covering what real chat users type:
    - `""` and `"   \n"` → `LOW_CONFIDENCE_REFUSAL`, empty `candidates`, `snapshot_date` set
    - `ungated.search_kb("what is the", top_k=20)` has non-empty `candidates`, every `lex_rank is None`
    - every string in Review Focus 3, and a 5,000-character query, return a status other than `UNAVAILABLE`
    - afterwards, `select count(*) from passages` is still 14,109 on the same connection.
  - `test_closed_connection_returns_unavailable`:
    - build the service, then `conn.close()`
    - `search_kb(Q01 text)` → `UNAVAILABLE` with a non-empty `error`, `candidates == []` and `snapshot_date` still set
    - no exception escapes.
  - `test_cancelled_query_rolls_back_shared_connection`:
    - on an open connection, `set statement_timeout = 1` (it lives inside the implicit transaction), then `search_kb(Q01 text)` → `UNAVAILABLE`
    - then `conn.execute("select 1")` succeeds, which proves the rollback left the connection out of the aborted state
    - `show statement_timeout` is back to `0`.
- [ ] **Step 2: Run to confirm failure.** `uv run pytest tests/retrieval/test_search_kb.py -v`. Expected:
  - all three FAIL: the blank query reaches the models, and `psycopg` exceptions escape the outage tests.
- [ ] **Step 3: Implement in `search_kb`.**
  - The guard clauses come first:
    - `top_k <= 0` raises `ValueError(f"top_k must be positive, got {top_k}")`
    - a blank `query.strip()` returns the refusal envelope (empty lists, `self._snapshot_date`).
  - Wrap only the `_fetch_fused` call in `try/except psycopg.Error as exc`:
    - `logger.error("KB search failed: %r", exc)`
    - `if not self._conn.closed: self._conn.rollback()`
    - return an `UNAVAILABLE` envelope with `error=str(exc)`.
  - Embedding and reranking stay outside the `try`. A model failure is a bug, not an outage, and must surface.
- [ ] **Step 4: Run and confirm pass.** `uv run pytest tests/retrieval -v`. Expected: all PASS.
- [ ] **Step 5: Clean-code gate.** ruff and pyright are clean on `retrieval`. `search_kb` reads top-down as guards → embed → fetch (try) → rerank → gate, at 25 lines or fewer.
- [ ] **Step 6: Commit** on `p-1-4-03-t2_search-kb-faults`: `feat(retrieval): search_kb guards and unavailable envelope with rollback`.

---

### Task 3: Docs, review, cleanup (plan branch)

**Files:**
- Modify: `docs/overview/decisions.md`. Rewrite the stale parts of ADR-007 (retrieval), keeping its "Threshold Calibration Stop Rule" bullet as-is: it still describes the `'simple'` column with `:*` prefixes, `PolicyLookupResult` and the `snapshots` join. Make it state:
  - the `'english'` column plus plain `::tsquery` cast, with the `polici`/`prioriti`/`proxi` evidence
  - rerank depth 20 at batch 8, with the measured numbers from design §2.8
  - the `KBSearchStatus` `StrEnum`
  - the in-memory policies and snapshot date.
- Modify: `docs/architecture/system-architecture-design.md` §7 "Query Construction" and "Single-Roundtrip" bullets (lines ~365–380): the `'english'` column, no `:*`, no `snapshots` join, and the RRF top 20 reranked.

- [ ] **Step 1: Merge** both task branches into `p-1-4-03_hybrid-search` (sequential, so no conflicts expected). Run `uv run pytest -v`; everything passes.
- [ ] **Step 2: Latency spot-check.** Run the `tests/retrieval` suite with `--durations=10`. Paste the `search_kb` test durations into the plan-branch commit message. Plan 04 produces the real p50/p95.
- [ ] **Step 3: Review the plan diff** with `/ponytail:ponytail-review`, then with `/anthropic-skills:thermo-nuclear-code-quality-review`. Fix accepted findings and re-run the suite.
- [ ] **Step 4: Cleanup gate.**
  - ruff and pyright are clean on `retrieval`.
  - `retrieval/service.py` has no unused constants, helpers or imports.
  - No `'simple'` or `:*` in `retrieval/`.
  - `_FusedRow` is used only inside `service.py`.
- [ ] **Step 5: Apply the doc edits** listed above.
- [ ] **Step 6: Commit** `chore(plan-03): ADR-007 + architecture §7 for english hybrid search, review fixes`.

## Unresolved Questions

None. Decided: models stay lazy-loaded here. The future app entrypoint pre-loads them (`load_embedder()`, `load_reranker()`) to avoid a first-search delay of a few seconds (design §8).
