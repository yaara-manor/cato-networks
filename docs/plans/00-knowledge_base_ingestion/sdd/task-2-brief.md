### Task 2: Empty database

This task starts Postgres and creates the four tables with no rows. Later tasks insert into them. Nothing in this task crawls, chunks, or embeds.

`docker-compose.yml` starts image `pgvector/pgvector:0.8.6-pg18`, creates database `kb`, and publishes port 5432. The data volume is mounted at `/var/lib/postgresql`. Postgres 18 keeps the cluster at `/var/lib/postgresql/18/docker`, so a mount at `/var/lib/postgresql/data` does not start.

`apply_schema` runs `db/migrations/20260929_1500_kb-schema.sql` once. The script creates the tables below if they are missing. It does not insert a snapshot, an article, a passage, or a policy. After it runs, a count of each table is 0.

`snapshots` will later hold one row for this crawl: when it was crawled, which embedding model was used, the width 384, and which reranker was used. `kb_articles` will later hold one row per saved English article, keyed by slug. `passages` will later hold the chunked text, a `simple` full-text column, and a `vector(384)` embedding. The full-text column is generated from `body` so tokens such as `IKEv2` are not stemmed. The GIN index is on that column. There is no HNSW index, because nearest-neighbor search will be an exact cosine scan. `policies` will later hold the six policy files whole, with no embedding and no snapshot id.

**Files:**
- Create: `docker-compose.yml`
- Create: `db/migrations/20260929_1500_kb-schema.sql`
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
