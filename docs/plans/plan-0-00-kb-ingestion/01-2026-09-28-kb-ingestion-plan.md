# Knowledge-base ingestion implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Crawl the English Cato knowledge base into a timestamped directory, load it and the six policy files into Postgres, and leave a dump a reviewer can restore.

**Architecture:** One crawl writes raw markdown under `data/kb_ingestion/<timestamp>/`. Chunking writes `passages.jsonl` beside those files. A load embeds the passages with the pinned bge-small model and fills Postgres. Reviewer startup restores `db/kb.dump`, reloads the policies, and refuses to run if a file hash or the embedding width does not match.

**Tech Stack:** Python 3.12, pytest, httpx, psycopg, pgvector on Postgres 18 (`pgvector/pgvector:0.8.6-pg18`), sentence-transformers. Embedding model `BAAI/bge-small-en-v1.5` revision `5c38ec7c405ec4b44b94cc5a9bb96e735b38267a`, 384 dimensions. Reranker `cross-encoder/ms-marco-MiniLM-L12-v2` revision `7b0235231ca2674cb8ca8f022859a6eba2b1c968`. The spec name `ms-marco-MiniLM-L-12-v2` is that repo.

**Spec:** `docs/superpowers/01-kb-ingestion/00-2026-09-28-kb-ingestion-design.md`

## Global Constraints

- User agent is `CatoHomeTaskBot/1.0 (educational assignment)`. Wait at least one second between crawl requests.
- Discovery index is only `https://knowledge.catonetworks.com/llms.txt`. Keep a URL only when its path is `/docs/<slug>.md` and the slug has no slash. Drop `/{language}/llms.txt` and `/docs/fr/<slug>.md` before any request.
- Save the raw response bytes. The article hash is SHA-256 of those bytes. The public URL has no `.md`. `site_updated_at` comes from the article `updated` field and is null when that field is missing. The crawl time is never copied into `site_updated_at`.
- Each crawl writes `data/kb_ingestion/<YYYY-MM-DDTHHMMSSZ>/`. Article files are `<slug>.md`. The manifest is `manifest.json` in that same directory. Chunking adds `passages.jsonl` there. Nothing else is written into that directory.
- The dump is `db/kb.dump`. It sits outside the crawl directory.
- Policy ids and files: `POL-CREDIT`, `POL-SEV1`, `POL-IDV`, `POL-SEC`, `POL-CRED`, `POL-SLA`, each `data/policies/<id>.md`.
- A stored passage is at most 400 tokens of the pinned bge-small tokenizer. A sliced section keeps the same heading, takes at most 350 new tokens, plus at most 50 tokens of whole sentences from the previous slice of that same section, and never copies text across headings. A heading with no body produces no passage.
- Passages are embedded as plain text. A question is embedded with the prefix `Represent this sentence for searching relevant passages: `, including the trailing space. The smoke test checks that prefix. Query-time search is not part of this plan.
- Vector search, when it is added later, is an exact cosine scan. This plan creates no HNSW index. The keyword column uses the Postgres `simple` text configuration.
- Model weights are not committed. Task 1 downloads both pinned revisions into the local cache. The image build downloads the same revisions into the image. The running container does not fetch them.
- The crawl command hits the live site once. Tests written after that read the saved files. They do not crawl again.
- Fusion, the search function, and `RERANK_MIN_SCORE` are a later retrieval plan. This plan does not build agents, the chat UI, approvals, or telemetry tools.

## File map

- `pyproject.toml` — package `kbindex`, pytest, runtime dependencies.
- `kbindex/config.py` — the constants in Global Constraints.
- `kbindex/embed.py` — load bge-small, embed passages, embed a question, write the smoke-test files, probe width.
- `kbindex/rerank.py` — load the MiniLM cross-encoder and score question-passage pairs.
- `kbindex/schema.sql` — the four empty tables.
- `kbindex/store.py` — apply the schema, load the crawl and the policies, compare hashes.
- `kbindex/crawl.py` — fetch allowed URLs and write one timestamped directory.
- `kbindex/discover.py` — classify a URL, parse `llms.txt`, apply `robots.txt`.
- `kbindex/hashing.py` — SHA-256 of bytes and of a file, then store those hashes on the manifest.
- `kbindex/chunk.py` — strip the documentation-index banner, split headings, slice, anchors, write `passages.jsonl`.
- `kbindex/policies.py` — read the six policy files into records.
- `kbindex/startup.py` — reload policies, hash check, width check.
- `kbindex/build.py` — operator command: load the crawl into Postgres and write the dump.
- `tests/kbindex/fixtures/article.md` — chunk fixture with a banner, a preamble, a long section, an empty heading, and one sentence over 400 tokens.
- `tests/kbindex/output/` — smoke-test embeddings and rerank scores. Gitignored.
- `docker-compose.yml`, `Dockerfile`, `README.md`.

A passage record has slug, heading, heading_anchor, position, and body. A policy record has id, title, content_hash, file_path, and body.

## Tests

Each test is written first, run, and seen to fail. The implementation step then produces the real files or the real database rows. The test is run again and checks that output.

- `test_embed_and_rerank_prefer_the_relevant_passage` — the pinned models. A BGP passage embeds to 384 numbers with no query prefix. The question embedding matches the prefixed question. The reranker scores the BGP passage above an unrelated SLA-credits passage.
- `test_tables_are_readable` — a connection can read `snapshots`, `kb_articles`, `passages`, and `policies`.
- `test_crawled_article_has_text` — the newest `data/kb_ingestion/<timestamp>/` directory has a manifest and at least one `<slug>.md` whose body is non-empty text. The public URL for that slug has no `.md`. No saved path contains `/docs/fr/`.
- `test_saved_articles_are_english_docs` — every saved file is an English `/docs/<slug>.md` article, and every skipped URL in the manifest was classified as language, robots, or not an article.
- `test_manifest_hash_matches_file` — every saved article's SHA-256 equals its manifest hash. A one-byte copy of one file does not.
- `test_chunk_keeps_every_sentence` — `passages.jsonl` and the fixture. Every sentence that fits the cap appears in a passage. The over-cap sentence appears only as the prefix that was kept. No body is over 400 bge-small tokens.
- `test_chunks_are_whole_sentences` — every passage from the fixture starts and ends on a sentence boundary, except the hard-cut sentence, which ends at the token cap. Overlap text stays inside its own section.
- `test_database_holds_the_crawl_and_policies` — the database has one snapshot, one `kb_articles` row per saved file, passage rows for those articles, and all six policies including `POL-SLA`. One stored embedding has 384 numbers.
- `test_startup_rejects_a_hash_or_width_mismatch` — startup passes on the filled database. A reader that returns different bytes raises `HashMismatch`. A probe width other than 384 raises `StartupError`.

---

### Task 1: Package, constants, and both models

This task creates the Python package, records the constants, downloads both pinned models into the local cache, and proves each one runs.

The embedding model is `BAAI/bge-small-en-v1.5`, revision `5c38ec7c405ec4b44b94cc5a9bb96e735b38267a`, 384 dimensions. The reranker is `cross-encoder/ms-marco-MiniLM-L12-v2`, revision `7b0235231ca2674cb8ca8f022859a6eba2b1c968`. Download those two revisions with the Hugging Face cache and no other revisions. The weight files stay out of git.

`load_embedder` reads that bge-small revision from the cache and does not send a question prefix. `embed_passages` embeds each passage string as its own words. `embed_query` embeds the exact prefix `Represent this sentence for searching relevant passages: `, including the trailing space, and then the question. `embedding_prefix` returns that string so the smoke test can see the prefix without guessing it. `load_reranker` reads the MiniLM revision from the cache. `rerank_pairs` sends the question and one passage through the cross-encoder and keeps the raw score, one number per passage, in the same order as the input.

`write_model_outputs` runs those functions on two fixed passages: one about BGP route limits, one about SLA credits. It writes `passage_embeddings.json`, `query_embedding.json`, and `rerank_scores.json` under `tests/kbindex/output/`. The test reads those files back and checks them against a fresh call: the BGP vector has 384 numbers, it matches the raw passage and differs from the same words with the query prefix, the question file matches `embed_query`, and the BGP rerank score is higher than the SLA-credits score.

**Files:**
- Create: `pyproject.toml`
- Create: `kbindex/__init__.py`
- Create: `kbindex/config.py`
- Create: `kbindex/embed.py`
- Create: `kbindex/rerank.py`
- Modify: `.gitignore`
- Test: `tests/kbindex/test_embed_and_rerank_prefer_the_relevant_passage.py`
- Generated, not committed: `tests/kbindex/output/passage_embeddings.json`, `tests/kbindex/output/query_embedding.json`, `tests/kbindex/output/rerank_scores.json`

**Functions:**
- `load_embedder()` loads the pinned bge-small revision from the local cache and returns it. Comment: `Load the pinned bge-small model from the local cache.`
- `embed_passages(texts) -> list[list[float]]` embeds each string as plain text. Comment: `Embed passage text with no query prefix.`
- `embed_query(text) -> list[float]` embeds `QUERY_PREFIX` plus the text. Comment: `Embed a question with the bge query prefix.`
- `embedding_prefix(question) -> str` returns that exact prefixed string. Comment: `Return the exact string sent to the embedding model for a question.`
- `load_reranker()` loads the pinned MiniLM revision from the local cache. Comment: `Load the pinned MiniLM cross-encoder from the local cache.`
- `rerank_pairs(question, passages) -> list[float]` returns one raw score per passage, in the same order. Comment: `Score each passage against the question and return the raw scores in order.`
- `write_model_outputs(output_dir)` writes the three JSON files for one BGP route-limits passage and one unrelated SLA-credits passage. Comment: `Write the smoke-test embedding and rerank files.`

**Constants in `kbindex/config.py`:** `USER_AGENT`, `RATE_LIMIT_SECONDS` (1), `EMBEDDING_MODEL`, `EMBEDDING_REVISION`, `EMBEDDING_DIMENSIONS` (384), `RERANKER_MODEL`, `RERANKER_REVISION`, `QUERY_PREFIX`, `PASSAGE_TOKEN_CAP` (400), `SLICE_NEW_TOKENS` (350), `SLICE_OVERLAP_TOKENS` (50).

- [ ] **Step 1: Write the failing test**

`test_embed_and_rerank_prefer_the_relevant_passage` reads the three files in `tests/kbindex/output/`. It checks that the BGP embedding has 384 numbers, that this vector matches `embed_passages` on the raw passage and differs from the same words with the query prefix, that the question file matches `embed_query`, and that the rerank file scores the BGP passage above the SLA-credits passage. The files must equal a fresh call of `embed_passages`, `embed_query`, and `rerank_pairs`.

- [ ] **Step 2: Run the test and see it fail**

Run: `pytest tests/kbindex/test_embed_and_rerank_prefer_the_relevant_passage.py -v`

Expected: fail because the output files are absent.

- [ ] **Step 3: Download both models and generate the files**

Create the package for Python 3.12 with pytest, httpx, psycopg (binary), pgvector, and sentence-transformers. `kbindex/__init__.py` is empty. Assign the constants above.

Download `BAAI/bge-small-en-v1.5` revision `5c38ec7c405ec4b44b94cc5a9bb96e735b38267a` and `cross-encoder/ms-marco-MiniLM-L12-v2` revision `7b0235231ca2674cb8ca8f022859a6eba2b1c968` into the local cache. Implement the loaders and `write_model_outputs`, then run `write_model_outputs` so the three JSON files exist. Add `tests/kbindex/output/` and the Hugging Face weight cache to `.gitignore`.

- [ ] **Step 4: Run the test and see it pass**

Run: `pytest tests/kbindex/test_embed_and_rerank_prefer_the_relevant_passage.py -v`

Expected: pass. The files match a fresh run of the same two models.

- [ ] **Step 5: Commit**

Commit the package, the loaders, the test, and the gitignore entries. Do not commit the weights or `tests/kbindex/output/`.

Commit message: `Install kbindex and the pinned embedding and reranker models.`

---

### Task 2: Empty database

This task starts Postgres and creates the four tables with no rows. Later tasks insert into them. Nothing in this task crawls, chunks, or embeds.

`docker-compose.yml` starts image `pgvector/pgvector:0.8.6-pg18`, creates database `kb`, and publishes port 5432. The data volume is mounted at `/var/lib/postgresql`. Postgres 18 keeps the cluster at `/var/lib/postgresql/18/docker`, so a mount at `/var/lib/postgresql/data` does not start.

`apply_schema` runs `kbindex/schema.sql` once. The script creates the tables below if they are missing. It does not insert a snapshot, an article, a passage, or a policy. After it runs, a count of each table is 0.

`snapshots` will later hold one row for this crawl: when it was crawled, which embedding model was used, the width 384, and which reranker was used. `kb_articles` will later hold one row per saved English article, keyed by slug. `passages` will later hold the chunked text, a `simple` full-text column, and a `vector(384)` embedding. The full-text column is generated from `body` so tokens such as `IKEv2` are not stemmed. The GIN index is on that column. There is no HNSW index, because nearest-neighbor search will be an exact cosine scan. `policies` will later hold the six policy files whole, with no embedding and no snapshot id.

**Files:**
- Create: `docker-compose.yml`
- Create: `kbindex/schema.sql`
- Create: `kbindex/store.py`
- Test: `tests/kbindex/test_tables_are_readable.py`

**Function:**
- `apply_schema(connection)` runs `schema.sql`. Comment: `Create the four knowledge-base tables when they are missing.`

**Schema:**

`snapshots` has `id` uuid primary key, `crawled_at` timestamptz, `embedding_model` text, `embedding_dimensions` int, `reranker_model` text.

`kb_articles` has `slug` text primary key, `snapshot_id` uuid referencing `snapshots`, `title` text, `public_url` text, `site_updated_at` timestamptz null, `content_hash` text, `file_path` text.

`passages` has `id` uuid primary key, `article_slug` text referencing `kb_articles`, `heading` text, `heading_anchor` text, `position` int, `body` text, `content_hash` text, `search_vector` tsvector generated as `to_tsvector('simple', body)`, and `embedding vector(384)`. Unique key on `(article_slug, position)`. A GIN index on `search_vector`. No HNSW index.

`policies` has `id` text primary key, `title` text, `content_hash` text, `file_path` text, `body` text. No embedding and no snapshot row.

- [ ] **Step 1: Write the failing test**

`test_tables_are_readable` connects with `DATABASE_URL` and selects from `snapshots`, `kb_articles`, `passages`, and `policies`.

- [ ] **Step 2: Run the test and see it fail**

Run: `pytest tests/kbindex/test_tables_are_readable.py -v`

Expected: fail because the tables do not exist.

- [ ] **Step 3: Create the database and the tables**

`docker compose up -d` starts Postgres. `apply_schema` creates the four tables. At the end of this step each table has zero rows.

- [ ] **Step 4: Run the test and see it pass**

Run: `pytest tests/kbindex/test_tables_are_readable.py -v`

Expected: pass. Each select returns a count of 0.

- [ ] **Step 5: Commit**

Commit message: `Create the empty knowledge-base tables.`

---

### Task 3: Crawl the English articles

This task fetches the live English knowledge base once and saves the raw markdown. A later test only reads those files. About 1,470 articles at one request per second takes on the order of half an hour. The English filter is applied in this task, before any article request. Task 4 moves the same rules into `discover.py` without fetching again and without changing which files were saved.

English is a path rule, not a guess about the language of the page text. The only discovery page is `https://knowledge.catonetworks.com/llms.txt`. The crawl does not open `https://knowledge.catonetworks.com/fr/llms.txt` or any other `https://knowledge.catonetworks.com/<language>/llms.txt`. Those indexes are the lists of translated articles. It also ignores the sitemap named in `robots.txt`, because that sitemap failed during design and is not a source of URLs.

`crawl` does the following, in order:

1. Fetch `https://knowledge.catonetworks.com/robots.txt` with `User-Agent: CatoHomeTaskBot/1.0 (educational assignment)`. Remember the robots decision. Wait one second.
2. Fetch `https://knowledge.catonetworks.com/llms.txt` with the same user agent. Wait one second. Read the markdown link targets. Do not fetch any other index.
3. For each link, decide before `fetch` is called:
   - Keep `https://knowledge.catonetworks.com/docs/<slug>.md` when `<slug>` contains no slash. `https://knowledge.catonetworks.com/docs/viewing-translated-knowledge-base-articles.md` is kept, because that page is English and its path has no language segment.
   - Skip `/docs/<language>/<slug>.md`, including `/docs/fr/<slug>.md`, with reason `language`. Do not send the request.
   - Skip `/<language>/llms.txt`, including `/fr/llms.txt`, with reason `language`. Do not send the request.
   - Skip any other URL, including another host, an HTML page, a partners page, or an image, with reason `not an article`. Do not send the request. Image files linked from a saved article are not downloaded either.
   - Skip a URL that the path rule would keep when `robots.txt` disallows it for this user agent, with reason `robots`. Do not send the request.
4. For each kept URL, wait one second, then fetch. Status 200 writes the response body bytes, unchanged, to `data/kb_ingestion/<YYYY-MM-DDTHHMMSSZ>/<slug>.md`. The directory name is `now()` in UTC. Any other status or a connection error is recorded under `failed` with the status or the error text, and no file is written. The crawl does not invent a body.
5. Read `title` and `updated` from the YAML front matter, the block between the first pair of `---` lines. A missing `updated` becomes a null `site_updated_at`. The crawl clock is stored as `crawled_at` and is never copied into `site_updated_at`. The public URL stored for the article is `https://knowledge.catonetworks.com/docs/<slug>` with the `.md` suffix removed.

The manifest in that directory records `crawled_at`, `user_agent`, `rate_limit_seconds`, `robots_decision`, `discovery_source` of `llms.txt`, one entry per saved article (slug, file path relative to the repo, title, public URL, site updated time), every skipped URL and its reason, and every failed URL. Article hashes are added in Task 5, so these entries have no `content_hash` yet.

**Files:**
- Create: `kbindex/crawl.py`
- Test: `tests/kbindex/test_crawled_article_has_text.py`
- Created by the crawl, and committed: `data/kb_ingestion/<YYYY-MM-DDTHHMMSSZ>/<slug>.md` and `manifest.json`

**Function:**
- `crawl(snapshot_root, fetch, sleep, now) -> path` writes one new directory under `snapshot_root` and returns that path. The directory name comes from `now()` in UTC, formatted `YYYY-MM-DDTHHMMSSZ`. `fetch(url) -> (status, body_bytes)`. `sleep(seconds)` waits between requests. The command `python -m kbindex.crawl` uses httpx, `time.sleep`, and the current UTC time, with `snapshot_root` of `data/kb_ingestion`. Comment: `Fetch the English knowledge-base articles and write one timestamped directory of raw markdown.`

- [ ] **Step 1: Write the failing test**

`test_crawled_article_has_text` opens the newest directory under `data/kb_ingestion/`. It reads `manifest.json` and one saved `<slug>.md`. The file's text is non-empty. The manifest public URL for that slug has no `.md`. No saved relative path contains `/docs/fr/` or a language index.

- [ ] **Step 2: Run the test and see it fail**

Run: `pytest tests/kbindex/test_crawled_article_has_text.py -v`

Expected: fail because `data/kb_ingestion/` has no crawl directory.

- [ ] **Step 3: Crawl**

Implement `crawl` and run `python -m kbindex.crawl`. Expect a new timestamp directory, a manifest whose `discovery_source` is `llms.txt`, and raw markdown files.

- [ ] **Step 4: Run the test and see it pass**

Run: `pytest tests/kbindex/test_crawled_article_has_text.py tests/kbindex/test_embed_and_rerank_prefer_the_relevant_passage.py -v`

Expected: the crawl test passes by reading the saved article. The model smoke test still passes.

- [ ] **Step 5: Commit**

Commit the crawler and the timestamp directory, including every saved article and the manifest.

Commit message: `Save the English knowledge-base crawl.`

---

### Task 4: URL discovery

This task moves the URL rules out of the body of `crawl` into three functions in `discover.py`. The saved crawl does not change, and the live site is not fetched again. After this task, `crawl` calls these functions for the same decisions it already made inline.

`parse_llms_links` reads the `llms.txt` markdown and returns every link target, the URL inside each `](url)`. It does not fetch.

`classify_url` looks only at the URL string. It returns `keep` for `https://knowledge.catonetworks.com/docs/<slug>.md` when the slug has no slash, including `viewing-translated-knowledge-base-articles`. It returns `skip_language` for `/docs/fr/<slug>.md`, for any other `/docs/<language>/<slug>.md`, and for `/fr/llms.txt` or any `/<language>/llms.txt`. It returns `skip_not_article` for every remaining URL. It does not fetch.

`robots_allows` parses the robots text with `urllib.robotparser` and returns whether `CatoHomeTaskBot/1.0 (educational assignment)` may fetch that URL. A false result is the `robots` skip. It does not fetch.

`crawl` then uses them in this order: parse the English `llms.txt` body, `classify_url` on each link, and `robots_allows` on the ones classified `keep`. Only a `keep` that robots allows is passed to `fetch`. The inline copies of these rules are deleted in this same task.

**Files:**
- Create: `kbindex/discover.py`
- Modify: `kbindex/crawl.py`
- Test: `tests/kbindex/test_saved_articles_are_english_docs.py`

**Functions:**
- `classify_url(url) -> str` returns `keep`, `skip_language`, or `skip_not_article`. Comment: `Decide whether a URL is an English article, a translation, or something else.` `keep` is only `https://knowledge.catonetworks.com/docs/<slug>.md` with a single slug segment. `skip_language` is a `/{language}/llms.txt` index or a `/docs/<language>/<slug>.md` path. Everything else is `skip_not_article`.
- `parse_llms_links(markdown) -> list[str]` returns the markdown link targets. Comment: `Collect the markdown link targets from an llms.txt page.` Use a standard-library pattern for `](url)`.
- `robots_allows(robots_text, url, user_agent) -> bool` uses `urllib.robotparser`. Comment: `Return whether robots.txt allows this user agent to fetch this URL.`

- [ ] **Step 1: Write the failing test**

`test_saved_articles_are_english_docs` reads the newest crawl. Every saved file's manifest URL classifies as `keep`. Every skipped URL classifies as `skip_language` or `skip_not_article`, or the manifest reason is `robots` and `robots_allows` is false for the saved robots text. No saved file's path has a slash in the slug.

- [ ] **Step 2: Run the test and see it fail**

Run: `pytest tests/kbindex/test_saved_articles_are_english_docs.py -v`

Expected: fail because `classify_url` is missing.

- [ ] **Step 3: Move the filter into `discover.py`**

Implement the three functions. Change `crawl` so it calls them and deletes the inline copies of the same rules. Do not crawl again.

- [ ] **Step 4: Run the test and see it pass**

Run: `pytest tests/kbindex/test_saved_articles_are_english_docs.py tests/kbindex/test_crawled_article_has_text.py -v`

Expected: both pass against the directory saved in Task 3.

- [ ] **Step 5: Commit**

Commit message: `Classify knowledge-base URLs before they are fetched.`

---

### Task 5: Hash the saved articles

This task hashes the raw article files and writes each digest onto that article's manifest entry. It does not fetch, and it does not rewrite the markdown.

`sha256_bytes` takes the response bytes and returns the SHA-256 digest as lowercase hex. `sha256_file` opens the saved `<slug>.md` in binary mode and passes those bytes to `sha256_bytes`. The hash covers the file as it was saved, including the documentation-index banner and the front matter. It does not cover a cleaned or re-encoded copy. If it did, a reviewer could not tell that the file is the page that was fetched.

`write_manifest_hashes` opens the newest crawl's `manifest.json`, and for each article entry sets `content_hash` to `sha256_file` of that entry's `file_path`. Skipped and failed URLs get no hash and no file. The test checks every saved article, then appends one byte to a temporary copy of one file and checks that the new digest differs. The saved file stays as it was.

**Files:**
- Create: `kbindex/hashing.py`
- Modify: the newest `data/kb_ingestion/<timestamp>/manifest.json`
- Test: `tests/kbindex/test_manifest_hash_matches_file.py`

**Functions:**
- `sha256_bytes(data) -> str` hashes a byte string. Comment: `Return the lowercase hex SHA-256 of these bytes.`
- `sha256_file(path) -> str` reads the file in binary mode and hashes those bytes. Comment: `Return the lowercase hex SHA-256 of a file's raw bytes.`
- `write_manifest_hashes(crawl_dir)` sets `content_hash` on every article entry in `manifest.json` from `sha256_file` of that entry's file. Comment: `Store each saved article's SHA-256 on its manifest entry.`

- [ ] **Step 1: Write the failing test**

`test_manifest_hash_matches_file` reads the newest crawl. For every article entry, `sha256_file` of the saved markdown equals `content_hash`. It also hashes a temporary copy of one file after appending one byte, and that digest differs from the manifest hash. The saved file is left unchanged.

- [ ] **Step 2: Run the test and see it fail**

Run: `pytest tests/kbindex/test_manifest_hash_matches_file.py -v`

Expected: fail because `content_hash` is missing.

- [ ] **Step 3: Write the hashes**

Implement the three functions. Run `write_manifest_hashes` on the Task 3 directory.

- [ ] **Step 4: Run the test and see it pass**

Run: `pytest tests/kbindex/test_manifest_hash_matches_file.py -v`

Expected: pass.

- [ ] **Step 5: Commit**

Commit the hashing module and the updated manifest.

Commit message: `Hash each saved article with SHA-256.`

---

### Task 6: Chunk the saved articles

This task splits each saved article into passages a citation can name, and writes `passages.jsonl` in the crawl directory. Token counts come from the pinned bge-small tokenizer loaded by `load_embedder`. The model is already in the cache from Task 1. There is no word counter, and this task does not embed.

`write_passages` reads the manifest and each raw `<slug>.md`. For each file it calls `chunk_article` with the manifest title. `chunk_article` does the following:

1. `strip_doc_banner` removes the repeated documentation-index banner from the text used to build passages. The `<slug>.md` file on disk is not rewritten.
2. Split the remaining markdown on headings. Text before the first heading becomes one passage whose heading is the article title from the manifest. A heading with no body produces no passage.
3. Count tokens with the bge-small tokenizer. A section of at most 400 tokens is one passage, with no copied neighbor text.
4. A longer section is cut on sentence boundaries. A sentence ends at `.`, `?`, or `!` followed by whitespace. The first slice has no copied prefix and may use the full 400 tokens. Each later slice takes at most 350 new tokens, then copies at most 50 tokens of whole sentences from the tail of the previous slice of that same section. The copy never includes the next heading, because the citation would name the wrong section. Every slice keeps that section's heading.
5. A single sentence longer than 400 tokens is cut by dropping trailing words until the tokenizer reports at most 400. That passage is the one case that ends mid-sentence.
6. `heading_anchor` lowercases the heading, turns spaces into hyphens, and removes punctuation. `position` is the passage order inside the article, starting at 0, and is what distinguishes slices that share a heading. When two headings in one article produce the same anchor, the later one appends `-` and its position.

Each `passages.jsonl` line has the article slug, heading, heading_anchor, position, and body. The fixture `tests/kbindex/fixtures/article.md` is what forces a banner, a preamble, a sliced section, an empty heading, and one over-cap sentence, in case the saved crawl does not contain all of those shapes.

**Files:**
- Create: `kbindex/chunk.py`
- Create: `tests/kbindex/fixtures/article.md`
- Modify: the crawl directory, adding `passages.jsonl`
- Test: `tests/kbindex/test_chunk_keeps_every_sentence.py`
- Test: `tests/kbindex/test_chunks_are_whole_sentences.py`

**Functions:**
- `strip_doc_banner(markdown) -> str` removes the documentation-index banner from the text used for passages. Comment: `Remove the documentation-index banner from passage text only.` The saved article file stays raw.
- `chunk_article(markdown, title) -> list` returns passage records. Comment: `Split one article into citable passages using the pinned bge-small tokenizer.` The preamble before the first heading uses `title` as its heading. Sentence boundaries are `.`, `?`, or `!` followed by whitespace. A section that fits in 400 tokens is one passage. A longer section is sliced at 350 new tokens on a sentence boundary. Each later slice starts with at most 50 tokens of whole sentences copied from the tail of the previous slice of that same section. Text is never copied across headings. A heading with no body produces no passage. One sentence longer than 400 tokens is cut by dropping trailing words until the tokenizer reports at most 400.
- `heading_anchor(heading, position, used) -> str` builds the anchor. Comment: `Build a unique heading anchor for one article.` Lowercase, spaces become hyphens, punctuation is removed. `used` is the set of anchors already emitted. A collision appends `-` plus `position`.
- `write_passages(crawl_dir)` reads the manifest and each raw file, calls `chunk_article` with the manifest title, and writes `passages.jsonl`. Comment: `Write one passage record per line for the saved crawl.` Each line has slug, heading, heading_anchor, position, and body.

The fixture `tests/kbindex/fixtures/article.md` has a documentation-index banner, a preamble, several headings, one section long enough for this tokenizer to slice, one heading with no body, and one sentence longer than 400 tokens.

- [ ] **Step 1: Write the failing tests**

`test_chunk_keeps_every_sentence` reads `passages.jsonl` for the newest crawl and checks one saved article against `chunk_article`: every sentence that fits the cap appears in at least one passage, a boundary sentence may appear twice because of overlap, and the over-cap case is covered by the fixture. Every body in the fixture output is at most 400 tokens by the pinned tokenizer.

`test_chunks_are_whole_sentences` checks the fixture passages. Each passage starts at a sentence start and ends at a sentence end, except the passage that holds the hard-cut sentence, which ends at the token cap. Overlap text does not include the next heading. The preamble heading is the article title. The empty heading produces no passage.

- [ ] **Step 2: Run the tests and see them fail**

Run: `pytest tests/kbindex/test_chunk_keeps_every_sentence.py tests/kbindex/test_chunks_are_whole_sentences.py -v`

Expected: fail because `passages.jsonl` is absent.

- [ ] **Step 3: Generate the passage file**

The models from Task 1 are already in the cache. Implement the chunk functions and run `write_passages` on the crawl directory.

- [ ] **Step 4: Run the tests and see them pass**

Run: `pytest tests/kbindex/test_chunk_keeps_every_sentence.py tests/kbindex/test_chunks_are_whole_sentences.py -v`

Expected: pass. The fixture checks use the real tokenizer. One saved article in `passages.jsonl` matches `chunk_article`.

- [ ] **Step 5: Commit**

Commit the chunker, the fixture, the tests, and `passages.jsonl`. Do not commit `tests/kbindex/output/`.

Commit message: `Split the saved articles into citable passages.`

---

### Task 7: Fill the database

This task reads the newest crawl directory and the six policy files and inserts them into the empty tables from Task 2. `python -m kbindex.build` calls `load_index` on that directory. This is the step that embeds. It embeds passage bodies only.

`load_policies` reads `data/policies/POL-CREDIT.md`, `POL-SEV1.md`, `POL-IDV.md`, `POL-SEC.md`, `POL-CRED.md`, and `POL-SLA.md`. It does not crawl and it does not embed. For each file the id is the filename without `.md`, the title is the text of the first markdown heading, `body` is the whole file, `content_hash` is `sha256_file` of those bytes, and `file_path` is the path relative to the repository root, such as `data/policies/POL-SLA.md`.

`load_index` then writes rows in this order:

1. One `snapshots` row. `crawled_at` is the manifest value. `embedding_model` is `BAAI/bge-small-en-v1.5`. `embedding_dimensions` is 384. `reranker_model` is `cross-encoder/ms-marco-MiniLM-L12-v2`.
2. One `kb_articles` row per manifest article. The slug, title, public URL, `site_updated_at`, and `content_hash` come from the manifest. `file_path` is the repo-relative path of `<slug>.md`. `site_updated_at` stays null when the manifest says null.
3. One `passages` row per `passages.jsonl` line. `content_hash` is SHA-256 of `body`. `embedding` is `embed_passages` of that body, so the query prefix is not applied. The database fills `search_vector` from `body`.
4. The six policy rows, through `upsert_policies`.

`upsert_article` inserts the article and its passages. If the same slug is loaded again and `content_hash` is unchanged, the existing passage rows stay, including their embeddings. If the hash differs, those passage rows are deleted and the new passages are inserted. Policies have no embedding column, so a policy cannot be mixed into a passage search.

**Files:**
- Create: `kbindex/policies.py`
- Create: `kbindex/build.py`
- Modify: `kbindex/store.py`
- Test: `tests/kbindex/test_database_holds_the_crawl_and_policies.py`

**Functions:**
- `load_policies(policies_dir) -> list` reads every `POL-*.md` in `data/policies`. The id is the filename without `.md`. The title is the first markdown heading. `file_path` is relative to the repository root. `body` is the full file text. `content_hash` is `sha256_file`. Comment: `Read the six policy files into records, including POL-SLA.`
- `upsert_policies(connection, policies)` inserts or replaces each policy row. Comment: `Insert or replace each policy row from its file record.`
- `upsert_article(connection, snapshot_id, article, passages)` inserts the article. When an article with the same slug already has the same `content_hash`, its passage rows are left in place. When the hash differs, those passage rows are deleted and replaced. Comment: `Replace an article's passages only when its content hash changes.`
- `load_index(connection, crawl_dir, policies_dir)` inserts one `snapshots` row (`crawled_at` from the manifest, `embedding_model`, `embedding_dimensions` 384, `reranker_model`), then the articles and passages, then the policies. Passage `content_hash` is SHA-256 of `body`. Passage `embedding` is `embed_passages` of `body`. `file_path` values are relative to the repository root. Comment: `Insert the snapshot, the articles, the embedded passages, and the policies.`
- `python -m kbindex.build` calls `load_index` for the newest crawl directory. The dump is added in Task 9.

- [ ] **Step 1: Write the failing test**

`test_database_holds_the_crawl_and_policies` reads the newest crawl and the database. It expects one snapshot row, one `kb_articles` row per manifest article, passage rows whose bodies match `passages.jsonl` for one slug, all six policy ids, and a `POL-SLA` body equal to `data/policies/POL-SLA.md`. One passage embedding has 384 numbers. Article `content_hash` matches the manifest. `site_updated_at` matches the manifest and is null where the manifest has null.

- [ ] **Step 2: Run the test and see it fail**

Run: `pytest tests/kbindex/test_database_holds_the_crawl_and_policies.py -v`

Expected: fail because the tables are still empty.

- [ ] **Step 3: Load the database**

Implement the functions. Run `python -m kbindex.build` with Postgres up. This embeds every passage, so it is a one-time load, not part of the test.

- [ ] **Step 4: Run the test and see it pass**

Run: `pytest tests/kbindex/test_database_holds_the_crawl_and_policies.py -v`

Expected: pass. The test reads the database. It does not embed the corpus again.

- [ ] **Step 5: Commit**

Commit message: `Load the crawl and the six policies into Postgres.`

---

### Task 8: Startup checks

This task checks that the filled database still matches the files on disk and the embedding model that built the vectors. It does not crawl, and it does not embed the articles again. `python -m kbindex.startup` runs the checks and exits 0 only when all of them pass. A failure raises before any later caller can answer from this database.

`run_startup` does three checks, in this order:

1. Read the six files in `data/policies/` again and `upsert_policies`, so a policy edit on disk is loaded before the hash check.
2. `verify_hashes` reads every `kb_articles.file_path` and every `policies.file_path`, computes `sha256_file` of those bytes, and compares it to the stored `content_hash`. One mismatch raises `HashMismatch` and startup stops. The test covers that path by passing a reader that returns one different byte, so the saved crawl is not edited.
3. `probe_width` embeds the fixed string `width-check` with the pinned bge-small model and returns how many numbers came back. `run_startup` compares that length to `snapshots.embedding_dimensions`. The expected length is 384. A different length raises `StartupError`. The individual numbers in the probe vector are not compared.

The real model must return 384, and that 384 must equal the snapshot row written in Task 7.

**Files:**
- Create: `kbindex/startup.py`
- Modify: `kbindex/embed.py`
- Modify: `kbindex/store.py`
- Test: `tests/kbindex/test_startup_rejects_a_hash_or_width_mismatch.py`

**Functions:**
- `verify_hashes(connection, read_file)` hashes each `kb_articles.file_path` and each `policies.file_path` with `sha256_file` and compares it to `content_hash`. Comment: `Raise HashMismatch when a stored hash differs from the file at file_path.` `read_file` is the normal file read, except the test passes a reader that returns different bytes.
- `probe_width(embed) -> int` embeds the fixed string `width-check` and returns the vector length. Comment: `Embed the fixed string width-check and return the vector length.` The probe's numeric values are not compared.
- `run_startup(connection, embed, policies_dir)` calls `upsert_policies` on the six files, then `verify_hashes`, then checks `probe_width` equals `snapshots.embedding_dimensions`. Comment: `Reload policies, check file hashes, check the embedding width, and stop on a mismatch.` A hash failure raises `HashMismatch`. A width failure raises `StartupError`. The command `python -m kbindex.startup` calls this and exits 0 when both checks pass.

- [ ] **Step 1: Write the failing test**

`test_startup_rejects_a_hash_or_width_mismatch` calls `run_startup` against the filled database and expects success. It calls `verify_hashes` with a reader that changes one byte and expects `HashMismatch`. It calls the width check with a stand-in embedder that returns a vector whose length is not 384 and expects `StartupError`. The real `probe_width(load_embedder())` equals 384 and equals the snapshot row.

- [ ] **Step 2: Run the test and see it fail**

Run: `pytest tests/kbindex/test_startup_rejects_a_hash_or_width_mismatch.py -v`

Expected: fail because `run_startup` is missing.

- [ ] **Step 3: Implement the checks**

Add `probe_width` to `embed.py`. Add `verify_hashes` to `store.py`. Add `run_startup`.

- [ ] **Step 4: Run the test and see it pass**

Run: `pytest tests/kbindex/test_startup_rejects_a_hash_or_width_mismatch.py -v`

Expected: pass. Also run `python -m kbindex.startup` and expect exit code 0.

- [ ] **Step 5: Commit**

Commit message: `Stop startup when a file hash or the embedding width is wrong.`

---

### Task 9: Dump, image, and restore

This task packages the filled database so a reviewer can start it without crawling and without embedding. The database is already loaded, and Task 8 already passed.

`write_dump` runs `pg_dump` in custom format against the `kb` database and writes `db/kb.dump`. That file is committed. Model weights are not. `python -m kbindex.build` now calls `load_index` and then `write_dump`. A second run on an unchanged crawl leaves passage rows in place, because `upsert_article` sees the same `content_hash`.

The Dockerfile downloads the same two revisions into `/opt/models`: `BAAI/bge-small-en-v1.5` at `5c38ec7c405ec4b44b94cc5a9bb96e735b38267a`, and `cross-encoder/ms-marco-MiniLM-L12-v2` at `7b0235231ca2674cb8ca8f022859a6eba2b1c968`. After that download the image sets `HF_HUB_OFFLINE=1` and `TRANSFORMERS_OFFLINE=1`, so the running container cannot fetch weights. This download is separate from the dev cache filled in Task 1.

`docker compose up` starts Postgres from Task 2. When `db/kb.dump` is present, the entrypoint runs `pg_restore` and then `python -m kbindex.startup`. Startup reloads the six policies, checks hashes, checks the width, and exits 0. When the dump is absent, startup exits with a message that the operator must run the build. The README states that the dump and the model weights sit outside `data/kb_ingestion/`, and that the reviewer command is `docker compose up`.

**Files:**
- Create: `Dockerfile`
- Modify: `kbindex/build.py`
- Modify: `docker-compose.yml`
- Modify: `README.md`
- Created by the build, and committed: `db/kb.dump`

**Functions:**
- `write_dump(destination)` writes `db/kb.dump` in custom `pg_dump` format from the running database. Comment: `Write a custom-format Postgres dump of the filled database.`
- `python -m kbindex.build`, after the load from Task 7, calls `write_dump`. Running it again on an unchanged crawl leaves matching article passages in place because `upsert_article` compares `content_hash`.

- [ ] **Step 1: Write the dump**

The database is already filled and the startup test already passes. There is no new pytest in this task. Run `write_dump` so `db/kb.dump` exists.

- [ ] **Step 2: Restore and start**

Run `docker compose up`. Expected: Postgres restores the dump, `python -m kbindex.startup` exits 0, and no crawl runs.

- [ ] **Step 3: Run the suite**

Run: `pytest tests/kbindex -v`

Expected: the tests listed above pass. The model smoke test and the chunk tests use the local cache. The database tests use the restored database.

- [ ] **Step 4: Commit**

Commit the Dockerfile, the dump command, the compose change, the README, and `db/kb.dump`. Do not commit model weights.

Commit message: `Restore the knowledge-base dump on startup.`

---

## Spec coverage

The crawl, the manifest, the English path filter, the raw hashes, the public URLs, chunking, overlap, anchors, the policy load, the four tables, the embeddings, the dump, and the startup checks each have a task above.

Fusion, keyword search, cosine search, the rerank cutoff, agents, chat, approvals, and telemetry stay out of this plan. The reranker is installed and smoke-tested here so the later retrieval plan can use the same pinned revision.
