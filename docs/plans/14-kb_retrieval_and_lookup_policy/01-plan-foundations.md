# 01 — Foundations: `encoders/`, English Search Vector, Ticket Stemming — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prepare the three independent building blocks that `search_kb` (plan 03) needs, and move ticket matching onto the same stemmer: a torch-only `encoders/` package, an `'english'` `passages.search_vector`, and PostgreSQL-stemmed repeat-contact matching.

**Architecture:** Three tasks with no file overlap, run in parallel on separate task branches, then merged into the plan branch. The first moves the embedder and reranker into `encoders/`, so `kbindex/`, `db/init/` and `retrieval/` depend downward on it. The second adds a migration runner and an idempotent `SET EXPRESSION` migration. The third replaces the regex tokenizer in `TicketService` with one batched `to_tsvector('english', …)` query plus a data-only stopword module in `core/`.

**Tech Stack:** Python 3.12, psycopg 3 (sync), PostgreSQL 18 + pgvector 0.8.6, sentence-transformers (bge-small-en-v1.5, ms-marco-MiniLM-L12-v2), pytest.

**Spec:** [design.md](design.md) §2.1, §2.4, §4.4, §4.5, §4.6, §5.3–5.5.

## Global Constraints

- Sync-only. Services take `psycopg.Connection[Any]`.
- Every function and method is fully annotated and passes Pyright `standard`. No bare `list`/`dict`, no implicit `Any`.
- ruff clean. Imports go at the top of the module (no inline imports). f-strings for interpolation. SQL uses named `%(name)s` parameters.
- No new dependencies in `pyproject.toml`.
- Match the surrounding code: short `#` line comments, module-level `_private` helpers, no docstring blocks where neighbors have none.
- Tests are functional: real seeded PostgreSQL and real local models, no mocks.
- Prerequisite: the compose Postgres is running (`docker compose up -d`) with `db/seed.dump` restored. If it isn't, STOP and report.
- Verify with `uv run pytest <path> -v`, `uvx ruff check <paths>` and `uvx pyright <paths>`.

## Branching

- Plan branch: `p-1-4-01_foundations`, created from `p-1-4_kb-retrieval-policy`.
- Task branches, each from the plan branch, worked in parallel:
  - `p-1-4-01-t1_encoders`
  - `p-1-4-01-t2_english-search-vector`
  - `p-1-4-01-t3_ticket-stemming`
- Merge each task branch into the plan branch. Task 4 runs on the plan branch. Never merge to master, never create a worktree.

## Review Focus

1. **Restoring the old `'simple'` dump:** startup's `apply_schema` must convert the column. Restoring the new dump must be a no-op (no table rewrite on every start). → Task 2, idempotency test.
2. **`embed_passages([])`** must return `[]` without error. The batched `encode` path changes how empty input behaves. → Task 1 test.
3. **Symptom text of only stopwords or noise words** (`"please, still the same issue today"`) must yield no keyword match and no error. → Task 3 test.
4. **Short technical tokens and inflections** (`VPN`, `DNS`, `tunnels dropping` vs `tunnel drops`) now match. That's the intended behavior change, and it must not break ADR-003's two negative cases (`S-1003-01`, `S-1010-02`). → Task 3 tests.
5. **Ticket text containing quotes, apostrophes, or tsquery operators** (`O'Brien`, `a & b | !c`): stemming goes through a bound `text[]` parameter, never string-built SQL. → Task 3 test.

---

### Task 1: `encoders/` package

**Files:**
- Create: `encoders/__init__.py` (one-line package comment, like `retrieval/__init__.py`)
- Move (use `git mv`): `kbindex/embed.py` → `encoders/embed.py`
- Move (use `git mv`): `retrieval/rerank.py` → `encoders/rerank.py`
- Modify imports: `kbindex/chunk.py:9`, `kbindex/store.py:18`, `db/init/startup.py:10`
- Modify tests: `tests/kbindex/test_embed_and_rerank_prefer_the_relevant_passage.py`, `tests/kbindex/test_startup_rejects_a_hash_or_width_mismatch.py`, `tests/kbindex/test_chunks_are_whole_sentences.py`, `tests/kbindex/test_chunk_keeps_every_sentence.py`

**Interfaces:**
- Consumes: nothing new.
- Produces (plan 03 relies on these exact names):
  - `encoders.embed.embed_query(text: str) -> list[float]`
  - `encoders.embed.embed_passages(texts: list[str]) -> list[list[float]]`
  - `encoders.embed.load_embedder() -> SentenceTransformer`
  - `encoders.embed.embedding_prefix(question: str) -> str`
  - `encoders.embed.probe_width(embed: Callable[[list[str]], list[list[float]]] = embed_passages) -> int`
  - `encoders.rerank.rerank_pairs(question: str, passages: list[str]) -> list[float]`
  - `encoders.rerank.load_reranker() -> CrossEncoder`

- [ ] **Step 1: Update tests to the target API first.**
  - Switch every `kbindex.embed` / `retrieval.rerank` import in the four test files to `encoders.embed` / `encoders.rerank`.
  - In the embed/rerank test, define `BGP_PASSAGE`, `SLA_PASSAGE` and `SMOKE_QUESTION` as module constants (same strings as `kbindex/embed.py:7-9`) and stop importing them.
  - Add two assertions to that test: `embed_passages([]) == []` and `rerank_pairs(SMOKE_QUESTION, []) == []`.
  - In the startup test, delete the `probe_width(load_embedder())` line (the `SentenceTransformer` duck-typing goes away) and drop the now-unused `load_embedder` import.
- [ ] **Step 2: Run to confirm failure.** `uv run pytest tests/kbindex -v`. Expected: `ModuleNotFoundError: encoders`.
- [ ] **Step 3: Move the two modules** with `git mv`, add `encoders/__init__.py`, and fix the three production imports listed above.
- [ ] **Step 4: Edit `encoders/embed.py`.**
  - Delete the three test constants.
  - `embed_passages`: return `[]` for empty input, otherwise one `model.encode(texts, prompt="", show_progress_bar=False)` call, converting each row to `list[float]`.
  - `embed_query` stays `embed_passages([embedding_prefix(text)])[0]`.
  - `probe_width`: new signature from Interfaces; its body is the length of `embed(["width-check"])[0]`.
  - Drop `from typing import Any`. Add `from collections.abc import Callable`.
- [ ] **Step 5: Edit `encoders/rerank.py`.** `rerank_pairs` returns `[]` when `passages` is empty. Otherwise it calls `predict` with `batch_size=8` (design §2.8: measured faster than 32 on CPU), `convert_to_numpy=True`, `show_progress_bar=False`.
- [ ] **Step 6: Run and confirm pass.** `uv run pytest tests/kbindex tests/db -v`. Expected: all PASS, including the exact-float equality against `tests/kbindex/output/*.json`.
  - If batching shifts floats, do not regenerate the fixtures silently. STOP and report the max absolute diff.
- [ ] **Step 7: Clean-code gate.** `uvx ruff check encoders kbindex db tests/kbindex` and `uvx pyright encoders kbindex/chunk.py kbindex/store.py db/init/startup.py`. Both clean.
  - `grep -rn "kbindex.embed\|retrieval.rerank" --include=*.py .` (excluding `.venv`) returns nothing.
- [ ] **Step 8: Commit** on `p-1-4-01-t1_encoders`: `refactor(encoders): move embed/rerank into encoders pkg, batch embedding`.

---

### Task 2: English `search_vector` migration + seed dump

**Files:**
- Modify: `db/init/seed.py:47-52` (`apply_schema`)
- Create: `db/migrations/20260930_1200-english-search-vector.sql`
- Regenerate: `db/seed.dump`
- Test: `tests/db/test_init.py`

**Interfaces:**
- Consumes: nothing new.
- Produces:
  - `db.init.seed.apply_schema(connection: psycopg.Connection) -> None` (same signature). It now runs every `db/migrations/*.sql` in sorted filename order, in one transaction, and commits once.
  - After it runs, `passages.search_vector` is `to_tsvector('english', body)`. Plan 03's SQL relies on this.

- [ ] **Step 1: Write the failing tests** in `tests/db/test_init.py`:
  - Add a module helper `_search_vector_expression(connection: psycopg.Connection) -> str`. It returns `pg_get_expr(adbin, adrelid)` from `pg_attrdef` joined to `pg_attribute`, filtered on `passages` / `search_vector`.
  - `test_seed_dump_contains_all_six_tables_and_restores_cleanly`: after the restore, assert the expression contains `'english'` and not `'simple'`.
  - New `test_apply_schema_is_idempotent_and_stems_search_vector`:
    - run `apply_schema` twice
    - the expression contains `'english'`
    - the `passages` row count is unchanged
    - `search_vector @@ 'polici'::tsquery` matches at least one row. That's the stem the `'simple'` column could never match.
- [ ] **Step 2: Run to confirm failure.** `uv run pytest tests/db/test_init.py -v`. Expected: FAIL on the `'english'` assertions.
- [ ] **Step 3: Write the migration** `db/migrations/20260930_1200-english-search-vector.sql`.
  - A single `DO $$ … $$` block. When the stored `search_vector` expression contains `'simple'`, it runs `ALTER TABLE passages ALTER COLUMN search_vector SET EXPRESSION AS (to_tsvector('english', body))`. Otherwise it does nothing.
  - One header comment explains the guard: startup re-applies every migration after each `pg_restore`, so an unguarded `SET EXPRESSION` would rewrite 14k rows on every start.
- [ ] **Step 4: Change `apply_schema`.** Iterate `sorted((REPO_ROOT / "db" / "migrations").glob("*.sql"))`, executing each file's text in one cursor, then commit once.
  - Keep the existing `LiteralString` cast.
- [ ] **Step 5: Regenerate `db/seed.dump`.** Do not use the live DB state: tests may have left rows in it.
  - Restore the committed dump with the exact `pg_restore --clean --if-exists --no-owner …` command from `Dockerfile:72`.
  - Run `uv run python -m db.init.startup` (it calls `seed_all` → `apply_schema`).
  - Run `uv run python -c "from db.init.build import write_dump; write_dump()"`.
- [ ] **Step 6: Run and confirm pass.** `uv run pytest tests/db tests/kbindex -v`. Expected: all PASS.
- [ ] **Step 7: Clean-code gate.** `uvx ruff check db tests/db` and `uvx pyright db/init/seed.py`. Both clean.
- [ ] **Step 8: Commit** on `p-1-4-01-t2_english-search-vector`: `feat(db): migration runner + english search_vector, regen seed.dump`.

---

### Task 3: Ticket stemming via PostgreSQL `'english'`

**Files:**
- Create: `core/stopwords.py`
- Modify: `services/ticket_service.py` (lines 1–106 helpers, `detect_repeat_contact`; `__init__` unchanged)
- Test: `tests/services/test_support_intake_functional.py`

**Interfaces:**
- Consumes: nothing new.
- Produces:
  - `core.stopwords.ENGLISH_STOP_WORDS: frozenset[str]` — 318 words.
  - `core.stopwords.SUPPORT_NOISE_WORDS: frozenset[str]` — 10 words.
  - `core.stopwords.EXCLUDED_WORDS: frozenset[str]` — the union of the two.
  - `TicketService.detect_repeat_contact`: signature and `RepeatContactResult` shape unchanged. `TicketService.__init__` unchanged (no constructor I/O).

- [ ] **Step 1: Write the failing tests.** Add them to `tests/services/test_support_intake_functional.py`. Each uses the existing `db_conn` fixture, which deletes created tickets. Each creates two open tickets with `create_ticket` on a site with no seeded tickets, `S-1001-99` under `ACC-1001`, with different `product_area` values and `body=""`, so only the subjects carry words. Each calls `detect_repeat_contact(account_id="ACC-1001", site_id="S-1001-99")`.
  - `test_short_technical_terms_and_inflections_mark_repeat_contact`:
    - Subjects `"VPN DNS failing"` and `"DNS over VPN broken"` → `is_repeat_contact is True`.
    - In a second pair on `S-1001-98`: `"tunnels dropping hourly"` vs `"tunnel drops again"` → `True`.
  - `test_noise_words_alone_do_not_mark_repeat_contact`: texts that share only `please`, `issue`, `today`, `site`, `still` → `False`.
    - Same test, one more check: `symptom_text="please, still the same issue today"` → `False`.
  - `test_symptom_text_with_sql_and_tsquery_characters_is_safe`: `symptom_text="O'Brien a & b | !c :*"` returns a result without raising.
- [ ] **Step 2: Run to confirm failure.** `uv run pytest tests/services -v`. Expected: the short-term/inflection test FAILS, because the old code drops tokens under 5 characters and slices prefixes to 5.
  - The other two pass on old code too; they stay as regression guards.
- [ ] **Step 3: Create `core/stopwords.py`.**
  - A comment cites the source: scikit-learn `ENGLISH_STOP_WORDS`, from the Glasgow IR group list, copied as data to avoid the dependency and the import cost.
  - `ENGLISH_STOP_WORDS`: produce the sorted literal once with `uv run python -c "from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS as s; print(sorted(s))"` (sklearn is present transitively) and paste it as a `frozenset`. Assert `len == 318` while pasting.
  - `SUPPORT_NOISE_WORDS`: the 10 words from design §4.5, with a one-line comment saying they come from `ts_stat` over the 54 seeded tickets.
  - `EXCLUDED_WORDS`: the union.
  - No imports. Do not re-export from `core/__init__.py`, which is YAGNI.
- [ ] **Step 4: Rewrite the helpers in `services/ticket_service.py`.**
  - Delete `import re`, `_STOPWORDS`, `_symptom_stems` and `_shares_keywords`.
  - Add `_shares_stems(stems_a: frozenset[str], stems_b: frozenset[str]) -> bool`, true when at least 2 stems are shared.
  - Change `_matches_area_or_symptom` to `(candidate: Ticket, product_area: str | None, symptom_stems: frozenset[str] | None, stems_by_ticket: Mapping[str, frozenset[str]], peer_tickets: list[Ticket]) -> bool`.
    - Same branch structure as today. Every text comparison becomes `_shares_stems` over precomputed sets.
    - `symptom_stems is None` keeps the old "symptom_text not given" meaning. An empty set can never match.
- [ ] **Step 5: Add `TicketService._stem_texts(self, texts: list[str]) -> list[frozenset[str]]`.** Exclusion happens inside PostgreSQL, so there is no constructor query, no cached-stems state and no second helper.
  - Add a module constant `_EXCLUDED_TEXT: str`, the space-joined `sorted(EXCLUDED_WORDS)`. It's built once at import.
  - The SQL:
    - selects `tsvector_to_array(ts_delete(to_tsvector('english', t), tsvector_to_array(to_tsvector('english', %(excluded)s))))` from `unnest(%(texts)s::text[]) with ordinality as x(t, ord)`, ordered by `ord`
    - binds `{"texts": texts, "excluded": _EXCLUDED_TEXT}`
    - maps each row to a `frozenset[str]`.
  - Return `[]` immediately for empty input, with no roundtrip.
  - The `ts_delete` form was verified on the live DB at about 2 ms per call. It stems the exclusion list with the same stemmer every call, so exclusion can never drift from the stemmer's output.
- [ ] **Step 6: Wire `detect_repeat_contact`.**
  - After `candidates` is built, run one `_stem_texts` call over `[f"{t.subject} {t.body}" for t in candidates]`, plus `symptom_text` appended when it is not `None`.
  - Zip the results into `stems_by_ticket: dict[str, frozenset[str]]` keyed by `ticket_id`, plus `symptom_stems`.
  - Pass both to `_matches_area_or_symptom`. Nothing else changes.
- [ ] **Step 7: Run and confirm pass.** `uv run pytest tests/services -v`. Expected: all PASS, including the ADR-003 cases (SC-06 Chicago, `S-1003-01`, `S-1010-02`, SC-01/11/12).
  - If an ADR-003 negative case now flags, STOP and report the shared stems. Do not tune the lists silently.
- [ ] **Step 8: Clean-code gate.** `uvx ruff check core services tests/services` and `uvx pyright core/stopwords.py services/ticket_service.py`. Both clean.
  - `grep -n "import re\|_STOPWORDS\|_symptom_stems\|_shares_keywords" services/ticket_service.py` returns nothing.
- [ ] **Step 9: Commit** on `p-1-4-01-t3_ticket-stemming`: `refactor(services): stem ticket text with postgres english, stopwords to core`.

---

### Task 4: Merge, review, cleanup (plan branch)

**Files:**
- Modify: `docs/architecture/system-architecture-design.md`:
  - §5 `passages` line 353: change `simple` to `english`.
  - §7 line 368: change `kbindex.embed.embed_query` to `encoders.embed.embed_query`.
  - Directory tree (lines ~495–505): add `encoders/` with `embed.py` and `rerank.py`; remove `embed.py` from `kbindex/` and `rerank.py` from `retrieval/`.
- Modify: `README.md`, only where it names the moved modules or the `'simple'` config.

- [ ] **Step 1: Merge** the three task branches into `p-1-4-01_foundations`. Expect no conflicts (disjoint files).
- [ ] **Step 2: Full suite.** `uv run pytest -v`. Everything passes.
- [ ] **Step 3: Review the plan diff** (`git diff p-1-4_kb-retrieval-policy...HEAD`) with `/ponytail:ponytail-review`, then with `/anthropic-skills:thermo-nuclear-code-quality-review`. Fix every accepted finding and re-run the suite.
- [ ] **Step 4: Cleanup gate.**
  - `uvx ruff check .` and `uvx pyright encoders core services db kbindex` are clean.
  - No unused imports or helpers.
  - No `'simple'` tsvector reference outside `20260929_1500_kb-schema.sql` and the new migration's guard.
  - `kbindex/embed.py` and `retrieval/rerank.py` no longer exist.
- [ ] **Step 5: Docs.** Apply the architecture/README edits listed above.
- [ ] **Step 6: Commit** `chore(plan-01): review fixes and docs for encoders/english stemming`.

## Unresolved Questions

None.
