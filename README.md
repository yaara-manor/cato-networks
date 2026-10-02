# Cato Networks AI Support Engineer

This repository implements a conversational AI support engineer grounded in Cato Networks' public knowledge base, internal policies, and synthetic telemetry.

## Knowledge Base & Database Seed Dump

- **Database Seed Dump**: `db/seed.dump` is a custom-format PostgreSQL dump holding KB articles, passages, `tsvector` search data, vector embeddings, internal policies, customer accounts (enriched with primary `-01` site country codes), and historical tickets. It sits outside `data/kb_ingestion/` to allow instant startup without crawling or re-embedding. Runtime tables (`conversations`, `messages`, `traces`, `tool_calls`, `approvals`, owned by `storage/`) are intentionally absent from the dump so a restore never wipes live conversations.
- **Model Weights**: The embedding model (`BAAI/bge-small-en-v1.5` at revision `5c38ec7c405ec4b44b94cc5a9bb96e735b38267a`) and reranker model (`cross-encoder/ms-marco-MiniLM-L12-v2` at revision `7b0235231ca2674cb8ca8f022859a6eba2b1c968`) are downloaded during container image build into `/opt/models`. They sit outside `data/kb_ingestion/` and are not committed to the git repository. At runtime, offline mode is enforced via `HF_HUB_OFFLINE=1` and `TRANSFORMERS_OFFLINE=1`.

## Reviewer Quickstart

The reviewer command to initialize and start the system is:

```bash
docker compose up
```

When run:
1. PostgreSQL with `pgvector` starts on port 5432.
2. The application entrypoint checks for `db/seed.dump`, restores the database using `pg_restore`, and runs `python -m db.init.startup`.
3. Startup applies schema migrations, reloads internal policies from `data/policies/` and seed accounts/tickets from `data/tickets/` (preserving any live ticket status updates), validates SHA-256 hashes for all articles and policies, checks embedding dimensions (384), and exits 0.

If `db/seed.dump` is absent, startup exits with an error indicating that the operator must run the build (`python -m db.init.build`).

## Customer Chat UI

`docker compose up ui` serves the customer chat at http://localhost:8501 (needs `OPENAI_API_KEY` in the environment for real agents). Locally: `DATABASE_URL=... uv run streamlit run ui/customer_app.py`.

## Running Tests

To run the test suite against the running database:

```bash
DATABASE_URL="postgresql://kb:kb@localhost:5432/kb" uv run pytest -v
```

## Operator Build (Rebuilding from Scratch)

To re-index an existing crawl or new crawl, seed accounts/tickets/policies, and regenerate the dump:

```bash
DATABASE_URL="postgresql://kb:kb@localhost:5432/kb" python -m db.init.build
```

This ingests the newest crawl directory from `data/kb_ingestion/`, chunks articles, generates embeddings, loads policies, accounts, and tickets into Postgres, and writes the custom dump to `db/seed.dump`.
