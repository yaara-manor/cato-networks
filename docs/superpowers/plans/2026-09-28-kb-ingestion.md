# Knowledge-base ingestion implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Crawl the English Cato knowledge base into a pinned snapshot, load it and the six policy files into Postgres, and answer a question with the top passages or a refusal.

**Architecture:** Raw markdown in `kb/snapshot/` is the source of truth. A one-time build chunks it, embeds it, and writes `kb/postgres/kb.dump`. Reviewer startup restores that dump, reloads policies from disk, and refuses to run if a file hash or the embedding width does not match. Search reads Postgres only: keyword list, exact cosine list, reciprocal rank fusion, then a local cross-encoder.

**Tech Stack:** Python 3.12, pytest, httpx, psycopg, pgvector on Postgres 16, sentence-transformers. Embedding model `BAAI/bge-small-en-v1.5` revision `5c38ec7c405ec4b44b94cc5a9bb96e735b38267a`. Reranker `cross-encoder/ms-marco-MiniLM-L12-v2` revision `7b0235231ca2674cb8ca8f022859a6eba2b1c968` (the spec name `ms-marco-MiniLM-L-12-v2` is this repo).

## Global Constraints

- User agent is `CatoHomeTaskBot/1.0 (educational assignment)`. Wait at least one second between crawl requests.
- Discovery index is only `https://knowledge.catonetworks.com/llms.txt`. Drop any URL whose path is not `/docs/<slug>.md` with a single slug segment. Drop `/{language}/llms.txt` and `/docs/fr/<slug>.md`.
- Save the raw response bytes. Article hash is SHA-256 of those bytes. Public URL has no `.md`. `site_updated_at` comes from the article `updated` field and is null when that field is missing.
- Snapshot files live only in `kb/snapshot/articles/<slug>.md` plus `kb/snapshot/manifest.json`. The dump is `kb/postgres/kb.dump`.
- Policy ids and files: `POL-CREDIT`, `POL-SEV1`, `POL-IDV`, `POL-SEC`, `POL-CRED`, `POL-SLA`, each `data/policies/<id>.md`.
- Passage cap is 400 tokens of the bge tokenizer. A sliced section keeps the same heading, uses at most 350 new tokens plus at most 50 tokens of whole sentences from the previous slice of that same section, and never copies text across headings. A heading with no body produces no passage.
- Passages are embedded as plain text. Questions use the prefix `Represent this sentence for searching relevant passages: `.
- Keyword search and vector search each return 20. Fusion score is the sum of `1 / (60 + rank)` with rank starting at 1. The reranker returns at most 5 passages at or above `RERANK_MIN_SCORE`.
- Vector search is an exact cosine scan. No HNSW index. Keyword search uses the Postgres `simple` text configuration.
- Model weights are not committed. The image build downloads the pinned revisions. The running container does not fetch them.
- A live crawl is not part of the test suite. Tests use fixtures and fakes.
- This plan does not build agents, the chat UI, approvals, or telemetry tools.

## File map

- `pyproject.toml` — package `kbindex`, pytest, runtime dependencies.
- `kbindex/config.py` — the constants in Global Constraints, including the two revision ids and `RERANK_MIN_SCORE`.
- `kbindex/hashing.py` — SHA-256 of bytes and of a file.
- `kbindex/discover.py` — classify a URL, parse `llms.txt`, apply `robots.txt`.
- `kbindex/chunk.py` — strip the documentation-index banner, split headings, slice, anchors.
- `kbindex/policies.py` — read the six policy files into records.
- `kbindex/crawl.py` — fetch allowed URLs and write the snapshot and manifest.
- `kbindex/schema.sql` — the four tables from the spec.
- `kbindex/store.py` — apply schema, upsert articles and passages, skip unchanged article hashes, write and restore the dump.
- `kbindex/embed.py` — load the pinned embedding model, embed passages, embed a question, probe width.
- `kbindex/rerank.py` — load the pinned cross-encoder and score question-passage pairs.
- `kbindex/search.py` — keyword query, cosine query, fusion, rerank, threshold.
- `kbindex/startup.py` — restore, reload policies, hash check, width check.
- `kbindex/build.py` — operator command: chunk the snapshot, embed, load, dump.
- `tests/test_hashing.py`, `tests/test_discover.py`, `tests/test_chunk.py`, `tests/test_policies.py`, `tests/test_crawl.py`, `tests/test_fusion.py`, `tests/test_search.py`, `tests/test_store.py`, `tests/test_startup.py`.
- `Dockerfile`, `docker-compose.yml`, `README.md`.

A passage record has heading, heading_anchor, position, and body. A policy record has id, title, content_hash, file_path, and body. A search hit has slug, heading, heading_anchor, public_url, fusion_score, and rerank_score.

---

### Task 1: Package and constants

**Files:**
- Create: `pyproject.toml`
- Create: `kbindex/__init__.py`
- Create: `kbindex/config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Consumes: nothing
- Produces: `kbindex.config` attributes `USER_AGENT`, `RATE_LIMIT_SECONDS` (1), `EMBEDDING_MODEL`, `EMBEDDING_REVISION`, `EMBEDDING_DIMENSIONS` (384), `RERANKER_MODEL`, `RERANKER_REVISION`, `QUERY_PREFIX`, `FUSION_K` (60), `KEYWORD_K` (20), `VECTOR_K` (20), `RERANK_K` (5), `PASSAGE_TOKEN_CAP` (400), `SLICE_NEW_TOKENS` (350), `SLICE_OVERLAP_TOKENS` (50), `RERANK_MIN_SCORE` (None until Task 12)

- [ ] **Step 1: Write the failing test**

`tests/test_config.py` imports those attributes and asserts the literal values above. It asserts `RERANK_MIN_SCORE` is None.

- [ ] **Step 2: Run the test and see it fail**

Run: `pytest tests/test_config.py -v`

Expected: fail because `kbindex.config` does not exist.

- [ ] **Step 3: Write the minimal implementation**

Create the package metadata for Python 3.12 with pytest, httpx, psycopg (binary), pgvector, and sentence-transformers. `kbindex/__init__.py` is empty. `kbindex/config.py` assigns the values above.

- [ ] **Step 4: Run the test and see it pass**

Run: `pytest tests/test_config.py -v`

Expected: pass.

- [ ] **Step 5: Commit**

Commit message: `Add kbindex package and ingestion constants.`

---

### Task 2: Content hashes

**Files:**
- Create: `kbindex/hashing.py`
- Test: `tests/test_hashing.py`

**Interfaces:**
- Consumes: nothing
- Produces: `sha256_bytes(data) -> str` of lowercase hex. `sha256_file(path) -> str` of the file bytes.

- [ ] **Step 1: Write the failing test**

Write a temp file whose contents are the bytes `abc`. Assert `sha256_file` equals the known SHA-256 of `abc`. Change one byte and assert the hash changes. Assert `sha256_bytes` of the same bytes matches.

- [ ] **Step 2: Run the test and see it fail**

Run: `pytest tests/test_hashing.py -v`

Expected: fail because `sha256_file` is missing.

- [ ] **Step 3: Write the minimal implementation**

Hash with SHA-256 and return lowercase hex. Read the file in binary mode.

- [ ] **Step 4: Run the test and see it pass**

Run: `pytest tests/test_hashing.py -v`

Expected: pass.

- [ ] **Step 5: Commit**

Commit message: `Hash snapshot files with SHA-256.`

---

### Task 3: URL discovery

**Files:**
- Create: `kbindex/discover.py`
- Test: `tests/test_discover.py`

**Interfaces:**
- Consumes: nothing
- Produces: `classify_url(url) -> str` returning `keep`, `skip_language`, or `skip_not_article`. `parse_llms_links(markdown) -> list[str]`. `robots_allows(robots_text, url, user_agent) -> bool`.

- [ ] **Step 1: Write the failing test**

Assert `classify_url` keeps `https://knowledge.catonetworks.com/docs/what-is-cato-sd-wan.md` and `https://knowledge.catonetworks.com/docs/viewing-translated-knowledge-base-articles.md`. Assert it returns `skip_language` for `https://knowledge.catonetworks.com/docs/fr/what-is-cato-sd-wan.md` and for `https://knowledge.catonetworks.com/fr/llms.txt`. Assert it returns `skip_not_article` for `https://knowledge.catonetworks.com/partners/docs/partner-onboarding` and for a URL ending in `.png`. Assert `parse_llms_links` on a two-item markdown list returns those two URLs in order. Assert `robots_allows` is false when the robots text disallows `/docs/` for the configured user agent, and true when the text allows `/`.

- [ ] **Step 2: Run the test and see it fail**

Run: `pytest tests/test_discover.py -v`

Expected: fail because `classify_url` is missing.

- [ ] **Step 3: Write the minimal implementation**

`keep` only for `https://knowledge.catonetworks.com/docs/<slug>.md` where the slug has no slash. A language index is any host path with two segments whose second segment is `llms.txt` and whose first is not empty, or any `/docs/<segment>/<rest>` path. Everything else that is not `keep` is `skip_not_article`, except the language cases which are `skip_language`. Parse markdown links with a standard-library pattern for `](url)`. Use `urllib.robotparser` for robots.

- [ ] **Step 4: Run the test and see it pass**

Run: `pytest tests/test_discover.py -v`

Expected: pass.

- [ ] **Step 5: Commit**

Commit message: `Filter the crawl to English article URLs.`

---

### Task 4: Chunking

**Files:**
- Create: `kbindex/chunk.py`
- Test: `tests/test_chunk.py`

**Interfaces:**
- Consumes: `PASSAGE_TOKEN_CAP`, `SLICE_NEW_TOKENS`, `SLICE_OVERLAP_TOKENS` from `kbindex.config`
- Produces: `strip_doc_banner(markdown) -> str`. `chunk_article(markdown, title, count_tokens) -> list` of passage records. `count_tokens` is a function from text to int supplied by the caller. `heading_anchor(heading, position, used) -> str`, where `used` is the set of anchors already emitted for the article.

- [ ] **Step 1: Write the failing test**

Use a counter that returns the number of words, so the test does not download a model. Cover these cases:

- A fixture that starts with the documentation-index blockquote (the heading `Documentation Index` and the sentence `Use this file to discover all available pages before exploring further.`) loses that block from passage bodies and keeps the rest.
- Front matter and a title, then two headings. The text before the first heading is one passage whose heading is the title argument. Each later heading is its own passage. A heading with no text before the next heading produces no passage.
- A section long enough to need three slices keeps one heading on every slice. The second slice's body starts with the last words of the first slice. No slice contains the next heading's text.
- With a counter that reports every string as 10 tokens except one sentence reported as 500, that sentence is hard-cut so the passage is still within the cap the chunker was given. The test passes a cap of 400 into the chunker by using the config constants, and asserts no body has a count over 400.
- `heading_anchor` of `Hold Timer` is `hold-timer`. A second heading `Hold Timer` at position 4 becomes `hold-timer-4`.

- [ ] **Step 2: Run the test and see it fail**

Run: `pytest tests/test_chunk.py -v`

Expected: fail because `chunk_article` is missing.

- [ ] **Step 3: Write the minimal implementation**

Strip the banner only from the text passed to the chunker. The crawler still stores raw bytes. Split on markdown headings. Build the preamble from the text before the first heading, with the supplied title. Sentence boundaries are `.`, `?`, or `!` followed by whitespace. Fill a slice up to 350 new tokens on a sentence boundary, then start the next slice with up to 50 tokens of whole sentences from the end of the previous slice. If one sentence alone exceeds the cap, cut it by dropping trailing words until `count_tokens` is at most 400. Anchors are lowercase, spaces become hyphens, punctuation is removed, and a collision appends `-` plus position.

- [ ] **Step 4: Run the test and see it pass**

Run: `pytest tests/test_chunk.py -v`

Expected: pass.

- [ ] **Step 5: Commit**

Commit message: `Split articles into citable passages.`

---

### Task 5: Policy loader

**Files:**
- Create: `kbindex/policies.py`
- Test: `tests/test_policies.py`

**Interfaces:**
- Consumes: `sha256_file` from `kbindex.hashing`
- Produces: `load_policies(policies_dir) -> list` of policy records. The id is the filename without `.md`. The title is the text of the first markdown heading. `file_path` is relative to the repository root. `body` is the file text.

- [ ] **Step 1: Write the failing test**

Point the loader at `data/policies`. Assert the ids are exactly `POL-CREDIT`, `POL-SEV1`, `POL-IDV`, `POL-SEC`, `POL-CRED`, and `POL-SLA`. Assert `POL-SLA` has file path `data/policies/POL-SLA.md`, a title taken from its first heading, a body equal to the file text, and a content hash equal to `sha256_file` of that path.

- [ ] **Step 2: Run the test and see it fail**

Run: `pytest tests/test_policies.py -v`

Expected: fail because `load_policies` is missing.

- [ ] **Step 3: Write the minimal implementation**

Read every `POL-*.md` in the directory. Do not crawl. Do not embed.

- [ ] **Step 4: Run the test and see it pass**

Run: `pytest tests/test_policies.py -v`

Expected: pass.

- [ ] **Step 5: Commit**

Commit message: `Load policy files, including POL-SLA.`

---

### Task 6: Crawl writer

**Files:**
- Create: `kbindex/crawl.py`
- Test: `tests/test_crawl.py`

**Interfaces:**
- Consumes: `classify_url`, `parse_llms_links`, `robots_allows`, `sha256_bytes`, config `USER_AGENT` and `RATE_LIMIT_SECONDS`
- Produces: `crawl(fetch, sleep, now, snapshot_dir) -> dict`. `fetch(url) -> (status, body_bytes)` is injected. `sleep(seconds)` and `now() -> datetime` are injected. The return value is the manifest dict that was also written to `snapshot_dir/manifest.json`. Article bodies are written to `snapshot_dir/articles/<slug>.md` only when `classify_url` returns `keep` and the status is 200.

- [ ] **Step 1: Write the failing test**

Pass a fake `fetch` whose clock records call times. The llms body contains one English article URL, one `/docs/fr/` URL, and one partners URL. Robots allows `/`. Assert the French and partners URLs are in `skipped` with reasons `language` and `not_article`, and that `fetch` was never called for them. Assert the English article file bytes equal the fake body, the manifest hash matches those bytes, `public_url` has no `.md`, and `site_updated_at` is the fixture's `updated` value. A second fixture with no `updated` field yields null `site_updated_at`. A third URL that returns status 500 is listed under `failed` with that status and is not written. Assert the gap between article fetches is at least one second. Assert the saved article file is the raw body, banner included.

- [ ] **Step 2: Run the test and see it fail**

Run: `pytest tests/test_crawl.py -v`

Expected: fail because `crawl` is missing.

- [ ] **Step 3: Write the minimal implementation**

Fetch robots first, then the English llms index. Skip disallowed URLs with reason `robots`. Read `title` and `updated` from the YAML front matter of a raw article. Write the manifest fields from the spec: crawled_at, user_agent, rate_limit_seconds, robots_decision, discovery_source `llms.txt`, articles, skipped, failed. `crawled_at` comes from the injected clock in UTC. Do not copy `crawled_at` into `site_updated_at`.

- [ ] **Step 4: Run the test and see it pass**

Run: `pytest tests/test_crawl.py -v`

Expected: pass.

- [ ] **Step 5: Commit**

Commit message: `Write the pinned crawl snapshot and manifest.`

---

### Task 7: Fusion

**Files:**
- Create: `kbindex/fusion.py`
- Test: `tests/test_fusion.py`

**Interfaces:**
- Consumes: `FUSION_K` from config
- Produces: `fuse(keyword_ids, vector_ids) -> list` of pairs `(id, score)` sorted by score descending. Rank of the first id in a list is 1. An id missing from a list contributes no term for that list.

- [ ] **Step 1: Write the failing test**

Keyword order A, B, C. Vector order B, D, A. Assert the rounded scores are A = 1/61 + 1/63, B = 1/62 + 1/61, D = 1/62, C = 1/63, and the order is B, A, D, C.

- [ ] **Step 2: Run the test and see it fail**

Run: `pytest tests/test_fusion.py -v`

Expected: fail because `fuse` is missing.

- [ ] **Step 3: Write the minimal implementation**

Sum `1 / (60 + rank)` per list. Sort descending. Do not read cosine distances or keyword scores.

- [ ] **Step 4: Run the test and see it pass**

Run: `pytest tests/test_fusion.py -v`

Expected: pass.

- [ ] **Step 5: Commit**

Commit message: `Merge keyword and vector ranks with reciprocal rank fusion.`

---

### Task 8: Search over fakes

**Files:**
- Create: `kbindex/search.py`
- Test: `tests/test_search.py`

**Interfaces:**
- Consumes: `fuse`, config `KEYWORD_K`, `VECTOR_K`, `RERANK_K`
- Produces: `search(question, keyword_search, vector_search, rerank, min_score) -> list` of hits. `keyword_search(question, limit)` and `vector_search(question, limit)` return passage records that already include slug, heading, heading_anchor, public_url, and id. `rerank(question, passages) -> list` of `(passage_id, score)` using the cross-encoder's raw score. Hits are those at or above `min_score`, capped at 5, each carrying fusion_score and rerank_score.

- [ ] **Step 1: Write the failing test**

Fake keyword and vector searches return overlapping passages. The fake reranker gives passage B a higher score than A, and passage C a score below `min_score`. Assert the result is only the passages at or above the threshold, ordered by rerank score, with at most 5 items, and that B's fusion_score matches `fuse`. Assert a question whose best rerank score is below `min_score` returns an empty list. Assert each search is called with limit 20.

- [ ] **Step 2: Run the test and see it fail**

Run: `pytest tests/test_search.py -v`

Expected: fail because `search` is missing.

- [ ] **Step 3: Write the minimal implementation**

Call the two searches, fuse by passage id, rerank the unique fused passages, drop scores below `min_score`, and return at most `RERANK_K`. Do not open the network or Postgres in this module's unit test.

- [ ] **Step 4: Run the test and see it pass**

Run: `pytest tests/test_search.py -v`

Expected: pass.

- [ ] **Step 5: Commit**

Commit message: `Rerank fused passages and refuse below the score threshold.`

---

### Task 9: Postgres schema and loader

**Files:**
- Create: `kbindex/schema.sql`
- Create: `kbindex/store.py`
- Create: `docker-compose.yml`
- Test: `tests/test_store.py`

**Interfaces:**
- Consumes: passage records from `chunk_article`, policy records from `load_policies`, `sha256_bytes`
- Produces: `apply_schema(connection)`. `upsert_article(connection, snapshot_id, article, passages)` which deletes and replaces passages only when the stored article hash differs. `upsert_policies(connection, policies)`. `verify_hashes(connection, read_file)` which raises `HashMismatch` when a `kb_articles` or `policies` hash differs from `sha256` of the file at `file_path`.

- [ ] **Step 1: Write the failing test**

`docker-compose.yml` starts `pgvector/pgvector:pg16` with a database `kb` and publishes port 5432. The test skips if `DATABASE_URL` is unset. With the database up, assert the four tables exist with the columns in the spec and with a unique key on `(article_slug, position)`. Insert an article and two passages. Call upsert again with the same article hash and a different passage body, and assert the old body remains. Call upsert with a new article hash and assert the passages are replaced. Assert `verify_hashes` raises `HashMismatch` when the file bytes change. Assert the embedding column is `vector(384)` and that no HNSW index exists. Assert a full-text index exists on `search_vector`.

- [ ] **Step 2: Run the test and see it fail**

Start Postgres with `docker compose up -d postgres`. Run: `DATABASE_URL=postgresql://kb:kb@localhost:5432/kb pytest tests/test_store.py -v`

Expected: fail because `apply_schema` is missing.

- [ ] **Step 3: Write the minimal implementation**

`schema.sql` creates `snapshots`, `kb_articles`, `passages`, and `policies` as in the spec. `search_vector` is a generated column using `to_tsvector('simple', body)`. Cosine search is a later query, not an index. `upsert_article` compares `content_hash` and leaves passages in place when it matches. `file_path` values are relative to the repo root.

- [ ] **Step 4: Run the test and see it pass**

Run: `DATABASE_URL=postgresql://kb:kb@localhost:5432/kb pytest tests/test_store.py -v`

Expected: pass.

- [ ] **Step 5: Commit**

Commit message: `Store articles, passages, and policies in Postgres.`

---

### Task 10: Startup checks

**Files:**
- Create: `kbindex/startup.py`
- Create: `kbindex/embed.py`
- Test: `tests/test_startup.py`

**Interfaces:**
- Consumes: `verify_hashes`, `upsert_policies`, `load_policies`, `EMBEDDING_DIMENSIONS`, `QUERY_PREFIX`
- Produces: `embed_query(text) -> list[float]` which prefixes `QUERY_PREFIX`. `embed_passages(texts) -> list[list[float]]` which does not prefix. `probe_width(embed) -> int` using the string `width-check`. `run_startup(connection, embed, policies_dir)` which upserts policies, calls `verify_hashes`, checks `probe_width` equals `snapshots.embedding_dimensions`, and raises `StartupError` on mismatch. `embedding_prefix(question) -> str` returns the exact string sent to the model.

- [ ] **Step 1: Write the failing test**

Assert `embedding_prefix("MTU")` equals `Represent this sentence for searching relevant passages: MTU`. Use a fake embedder. Assert `run_startup` raises `StartupError` when the fake probe returns length 8. Assert it raises `StartupError` when `verify_hashes` would fail. Assert a matching width and matching hashes return without error. These tests do not download a model.

- [ ] **Step 2: Run the test and see it fail**

Run: `pytest tests/test_startup.py -v`

Expected: fail because `run_startup` is missing.

- [ ] **Step 3: Write the minimal implementation**

`embed.py` loads `BAAI/bge-small-en-v1.5` from the local pinned directory when a real call is made, and exposes `embedding_prefix` with no model load. `run_startup` does not compare probe vector numbers, only the width. It reads `embedding_dimensions` from the single snapshots row.

- [ ] **Step 4: Run the test and see it pass**

Run: `pytest tests/test_startup.py -v`

Expected: pass.

- [ ] **Step 5: Commit**

Commit message: `Stop startup when the snapshot hash or embedding width is wrong.`

---

### Task 11: Image, restore, and build command

**Files:**
- Create: `Dockerfile`
- Create: `kbindex/build.py`
- Create: `kbindex/rerank.py`
- Modify: `docker-compose.yml`
- Modify: `README.md`
- Test: `tests/test_build.py`

**Interfaces:**
- Consumes: `crawl` is not called here. `chunk_article`, `embed_passages`, `upsert_article`, `apply_schema`
- Produces: `build_index(connection, snapshot_dir, count_tokens, embed_passages)` reads the manifest, chunks each raw file, embeds passage bodies with no prefix, and upserts. `write_dump(destination)` writes `kb/postgres/kb.dump` in custom pg_dump format. The image sets `HF_HUB_OFFLINE=1` and `TRANSFORMERS_OFFLINE=1` after the build has downloaded the two pinned revisions into `/opt/models`.

- [ ] **Step 1: Write the failing test**

`tests/test_build.py` uses the compose database and a tiny fixture snapshot of one article. It skips without `DATABASE_URL`. Assert `build_index` writes one `kb_articles` row whose `public_url` has no `.md`, and passage rows whose bodies do not contain `Documentation Index`. Assert a second call with the same article hash does not change passage ids. Assert `count_tokens` used for the build is the bge tokenizer only when `/opt/models` or the local Hugging Face cache contains revision `5c38ec7c405ec4b44b94cc5a9bb96e735b38267a`; otherwise the test uses the word counter and does not claim a token-cap result.

- [ ] **Step 2: Run the test and see it fail**

Run: `DATABASE_URL=postgresql://kb:kb@localhost:5432/kb pytest tests/test_build.py -v`

Expected: fail because `build_index` is missing.

- [ ] **Step 3: Write the minimal implementation**

`build_index` takes each article's title and `site_updated_at` from the manifest entry, not from a rewritten file. The Dockerfile downloads only those two revisions during `docker build`. Compose runs Postgres and a one-shot `kbindex.startup` after `pg_restore` of `kb/postgres/kb.dump` when that file exists. When the dump does not exist yet, startup exits with a message that the operator must run the build. README states the dump and the model weights are additions outside `kb/snapshot/`, and lists the reviewer command: `docker compose up`, which restores the dump and runs startup, with no crawl.

- [ ] **Step 4: Run the test and see it pass**

Run: `DATABASE_URL=postgresql://kb:kb@localhost:5432/kb pytest tests/test_build.py -v`

Expected: pass. Then run `pytest -v` and expect every test that does not need `DATABASE_URL` to pass with no network.

- [ ] **Step 5: Commit**

Commit message: `Build the index image and restore a committed dump.`

---

### Task 12: Operator crawl, dump, and refusal threshold

**Files:**
- Modify: `kbindex/config.py`
- Modify: `README.md`
- Create: `kb/snapshot/` and `kb/postgres/kb.dump` by running the tools, not by hand

**Interfaces:**
- Consumes: `crawl`, `build_index`, `search`, the real keyword and cosine queries added in `kbindex/search.py` as `keyword_search_db` and `vector_search_db`, and `rerank` loaded from `/opt/models`
- Produces: a committed snapshot and dump. `RERANK_MIN_SCORE` set to the smallest value that still returns no passages for the IPv6 roadmap question.

- [ ] **Step 1: Write the failing test**

`tests/test_threshold.py` skips unless `RERANK_MIN_SCORE` is a float and `DATABASE_URL` is set. It runs the real search for the question `Our network architect is asking whether Cato supports IPv6-only branch sites and what's on the roadmap next year. Can you share dates?` and asserts the result list is empty.

- [ ] **Step 2: Run the test and see it fail**

Run the crawl once: `python -m kbindex.crawl`. Expect a manifest whose `discovery_source` is `llms.txt` and whose article files are raw markdown. Then `python -m kbindex.build`. Then run `pytest tests/test_threshold.py -v` before editing the constant.

Expected: fail because `RERANK_MIN_SCORE` is still None, so the test skips or the search refuses to run. If it skips, that skip is the failure this task closes.

- [ ] **Step 3: Write the minimal implementation**

Add `keyword_search_db` using `plainto_tsquery('simple', question)` and `vector_search_db` using cosine distance on `embedding` with an exact scan, each limited to 20. Run the IPv6 question once with a temporary threshold low enough to see the top rerank score. Set `RERANK_MIN_SCORE` in `kbindex/config.py` to just above that score so this question returns no passages. Record the chosen number and the question text in the README. Write `kb/postgres/kb.dump` from the loaded database. Do not put model weights in git.

- [ ] **Step 4: Run the test and see it pass**

Run: `DATABASE_URL=postgresql://kb:kb@localhost:5432/kb pytest tests/test_threshold.py -v`

Expected: pass, and the result list is empty. Run `python -m kbindex.startup` and expect exit code 0 against the dump and the snapshot files.

- [ ] **Step 5: Commit**

Commit the snapshot, the manifest, the dump, the config value, and the README note. Commit message: `Pin the knowledge-base snapshot and the refusal threshold.`

---

### Task 13: Cleanup

**Files:**
- Modify: whatever Task 1 through Task 12 left unused

- [ ] **Step 1: Write the failing test**

No new behavior. Run `pytest -v` and confirm the suite is the behavior lock.

- [ ] **Step 2: Remove unused code**

Delete any module, dependency, fixture, or config key that no test and no command imports. Delete a word-counter code path if the real tokenizer is now what `build_index` uses and the tests inject their own counter. Do not add a second retrieval algorithm.

- [ ] **Step 3: Run the tests and see them pass**

Run: `pytest -v`

Expected: pass. The database tests still skip when `DATABASE_URL` is unset, and pass when it is set.

- [ ] **Step 4: Commit**

Commit message: `Remove unused ingestion code.`

---

## Spec coverage

The crawl, manifest, English path filter, raw hashes, public URLs, chunking, overlap, anchors, policy load, tables, exact cosine scan, fusion, rerank, threshold, dump, and startup checks each have a task above. Agents, chat, approvals, and telemetry stay out of this plan.
