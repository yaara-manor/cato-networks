# Cato Networks AI Support Engineer

This repository implements a conversational AI support engineer grounded in Cato Networks' public knowledge base, internal policies, and synthetic telemetry.

## Knowledge Base & Database Seed Dump

**Seed dump** (`db/seed.dump`): PostgreSQL custom-format dump that lets the app start instantly, with no crawling or re-embedding. It contains:
- KB articles and passages (with `tsvector` search data and vector embeddings)
- Internal policies
- Customer accounts (with primary `-01` site country codes)
- Historical tickets

Runtime tables (`conversations`, `messages`, `traces`, `tool_calls`, `approvals`; owned by `storage/`) are not in the dump, so a restore never wipes live conversations.

**Model weights**: downloaded at Docker image build into `/opt/models` (not committed to git). Offline mode is enforced at runtime (`HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1`).

| Model | Name | Revision |
|-------|------|----------|
| Embedding | `BAAI/bge-small-en-v1.5` | `5c38ec7c405ec4b44b94cc5a9bb96e735b38267a` |
| Reranker | `cross-encoder/ms-marco-MiniLM-L12-v2` | `7b0235231ca2674cb8ca8f022859a6eba2b1c968` |

## Run the Customer Chat UI (`ui/customer_app.py`)

Prerequisites: Docker with Compose v2, an OpenAI API key, and `db/seed.dump` present (committed to the repo). Run everything from the repo root.

### 1. Configure the API key

```bash
cp .env.example .env
```

Edit `.env` and set `OPENAI_API_KEY=sk-...`. Docker Compose reads `.env` automatically and passes the key to the `ui` container.

### 2. Start PostgreSQL

```bash
docker compose up -d postgres
```

Starts PostgreSQL + `pgvector` on port 5432 (volume `pgdata` persists data).

### 3. Consume the seed dump and run startup checks

```bash
docker compose run --rm app
```

This builds the image (first run downloads the embedding/reranker models, takes a few minutes) and runs the entrypoint, which:
1. Waits for Postgres.
2. Restores `db/seed.dump` via `pg_restore --clean --if-exists` (KB articles, passages, embeddings, policies, accounts, tickets). Runtime tables (`conversations`, `messages`, `traces`, `tool_calls`, `approvals`) are not in the dump, so live conversations are never wiped.
3. Runs `python -m db.init.startup`: applies schema migrations, reloads policies and seed accounts/tickets (preserving live ticket status), validates SHA-256 hashes, checks embedding dimension (384).

Success ends with `Startup finished successfully.` and exit code 0. If `db/seed.dump` is missing it exits with an error; see "Operator Build" below.

### 4. Start the customer UI

```bash
docker compose up ui
```

Open **http://localhost:8501**. The `ui` container re-runs step 3's restore on boot, which is safe and idempotent.

Add `-d` to run in the background; follow logs with `docker compose logs -f ui`.

### 5. Use it

1. Pick a **Scenario** in the sidebar (or `Custom` + any email).
2. Click **Send opening message** for a scenario, or type in the chat box ("Describe your issue").
3. The **Trace** tab shows agent steps. Approval-gated actions appear as banners and wait for a reviewer (next section).
4. **New conversation** resets the thread. The conversation id is kept in the URL (`?conversation_id=...`).

### Run the customer UI locally (without the `ui` container)

Needs Python 3.12+ and [uv](https://docs.astral.sh/uv/). Do steps 1-3 above first (Postgres on `localhost:5432` is exposed by compose), then:

```bash
uv sync
uv run python -m streamlit run ui/customer_app.py
```

`DATABASE_URL` and `OPENAI_API_KEY` come from `.env` (`DATABASE_URL` defaults to `postgresql://kb:kb@localhost:5432/kb`). Opens on http://localhost:8501.

### Stop / reset

```bash
docker compose down        # stop, keep data
docker compose down -v     # stop and wipe the database volume (redo step 2-3 after)
```

## Run the Reviewer Board (optional, `ui/reviewer_app.py`)

Handles pending approvals raised in customer conversations. Needs steps 1-3 above (no API key required for the reviewer itself).

```bash
docker compose up reviewer
```

Open **http://localhost:8502**. Select a conversation from the sidebar board (Pending / Escalated tabs), review evidence, live trace and model messages, then approve / edit / reject.

Typical flow: run the customer UI and reviewer together in one command:

```bash
docker compose up ui reviewer
```

Locally:

```bash
uv run python -m streamlit run ui/reviewer_app.py --server.port=8502
```

## Running Tests

Needs Postgres up and seeded (steps 2-3 above) and `uv sync` done.

```bash
DATABASE_URL="postgresql://kb:kb@localhost:5432/kb" uv run pytest -v
```

## Operator Build (Rebuilding from Scratch)

To re-index an existing crawl or new crawl, seed accounts/tickets/policies, and regenerate the dump:

```bash
DATABASE_URL="postgresql://kb:kb@localhost:5432/kb" python -m db.init.build
```

This ingests the newest crawl directory from `data/kb_ingestion/`, chunks articles, generates embeddings, loads policies, accounts, and tickets into Postgres, and writes the custom dump to `db/seed.dump`.
