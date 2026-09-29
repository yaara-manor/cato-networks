# Cato Networks AI Support Engineer

This repository implements a conversational AI support engineer grounded in Cato Networks' public knowledge base, internal policies, and synthetic telemetry.

## Knowledge Base & Database Dump

- **Database Dump**: `db/kb.dump` is a custom-format PostgreSQL dump holding articles, passages, tsvector search data, and vector embeddings. It sits outside `data/kb_ingestion/` as an added file to allow instant startup without crawling or re-embedding.
- **Model Weights**: The embedding model (`BAAI/bge-small-en-v1.5` at revision `5c38ec7c405ec4b44b94cc5a9bb96e735b38267a`) and reranker model (`cross-encoder/ms-marco-MiniLM-L12-v2` at revision `7b0235231ca2674cb8ca8f022859a6eba2b1c968`) are downloaded during container image build into `/opt/models`. They sit outside `data/kb_ingestion/` and are not committed to the git repository. At runtime, offline mode is enforced via `HF_HUB_OFFLINE=1` and `TRANSFORMERS_OFFLINE=1`.

## Reviewer Quickstart

The reviewer command to initialize and start the system is:

```bash
docker compose up
```

When run:
1. PostgreSQL with `pgvector` starts on port 5432.
2. The application entrypoint checks for `db/kb.dump`, restores the database using `pg_restore`, and runs `python -m kbindex.startup`.
3. Startup reloads internal policies from `data/policies/`, validates SHA-256 hashes for all articles and policies, checks embedding dimensions (384), and exits 0.

If `db/kb.dump` is absent, startup exits with an error indicating that the operator must run the build.

## Running Tests

To run the test suite against the running database:

```bash
DATABASE_URL="postgresql://kb:kb@localhost:5432/kb" uv run pytest tests/kbindex -v
```

## Operator Build (Rebuilding from Scratch)

To re-index an existing crawl or new crawl and regenerate the dump:

```bash
DATABASE_URL="postgresql://kb:kb@localhost:5432/kb" python -m kbindex.build
```

This ingests the newest crawl directory from `data/kb_ingestion/`, chunks articles, generates embeddings, loads Postgres, and writes the custom dump to `db/kb.dump`.
