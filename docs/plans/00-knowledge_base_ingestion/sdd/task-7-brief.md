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
