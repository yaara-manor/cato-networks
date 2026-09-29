### Task 9: Dump, image, and restore

This task packages the filled database so a reviewer can start it without crawling and without embedding. The database is already loaded, and Task 8 already passed.

`write_dump` runs `pg_dump` in custom format against the `kb` database and writes `kb/postgres/kb.dump`. That file is committed. Model weights are not. `python -m kbindex.build` now calls `load_index` and then `write_dump`. A second run on an unchanged crawl leaves passage rows in place, because `upsert_article` sees the same `content_hash`.

The Dockerfile downloads the same two revisions into `/opt/models`: `BAAI/bge-small-en-v1.5` at `5c38ec7c405ec4b44b94cc5a9bb96e735b38267a`, and `cross-encoder/ms-marco-MiniLM-L12-v2` at `7b0235231ca2674cb8ca8f022859a6eba2b1c968`. After that download the image sets `HF_HUB_OFFLINE=1` and `TRANSFORMERS_OFFLINE=1`, so the running container cannot fetch weights. This download is separate from the dev cache filled in Task 1.

`docker compose up` starts Postgres from Task 2. When `kb/postgres/kb.dump` is present, the entrypoint runs `pg_restore` and then `python -m kbindex.startup`. Startup reloads the six policies, checks hashes, checks the width, and exits 0. When the dump is absent, startup exits with a message that the operator must run the build. The README states that the dump and the model weights sit outside `data/kb_ingestion/`, and that the reviewer command is `docker compose up`.

**Files:**
- Create: `Dockerfile`
- Modify: `kbindex/build.py`
- Modify: `docker-compose.yml`
- Modify: `README.md`
- Created by the build, and committed: `kb/postgres/kb.dump`

**Functions:**
- `write_dump(destination)` writes `kb/postgres/kb.dump` in custom `pg_dump` format from the running database. Comment: `Write a custom-format Postgres dump of the filled database.`
- `python -m kbindex.build`, after the load from Task 7, calls `write_dump`. Running it again on an unchanged crawl leaves matching article passages in place because `upsert_article` compares `content_hash`.

- [ ] **Step 1: Write the dump**

The database is already filled and the startup test already passes. There is no new pytest in this task. Run `write_dump` so `kb/postgres/kb.dump` exists.

- [ ] **Step 2: Restore and start**

Run `docker compose up`. Expected: Postgres restores the dump, `python -m kbindex.startup` exits 0, and no crawl runs.

- [ ] **Step 3: Run the suite**

Run: `pytest tests/kbindex -v`

Expected: the tests listed above pass. The model smoke test and the chunk tests use the local cache. The database tests use the restored database.

- [ ] **Step 4: Commit**

Commit the Dockerfile, the dump command, the compose change, the README, and `kb/postgres/kb.dump`. Do not commit model weights.

Commit message: `Restore the knowledge-base dump on startup.`

---

## Spec coverage

The crawl, the manifest, the English path filter, the raw hashes, the public URLs, chunking, overlap, anchors, the policy load, the four tables, the embeddings, the dump, and the startup checks each have a task above.

Fusion, keyword search, cosine search, the rerank cutoff, agents, chat, approvals, and telemetry stay out of this plan. The reranker is installed and smoke-tested here so the later retrieval plan can use the same pinned revision.
