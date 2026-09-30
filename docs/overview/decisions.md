# Architectural & Technical Decisions

## ADR-001: Central Simulation Clock (`core/clock.py`)

- **Context / Problem**: All synthetic telemetry files, historical tickets, and evaluation scenarios are anchored at `2026-08-28T17:00:00Z`. Using system wall-clock time (`datetime.now()`) would break SLA calculations, ticket recency windows, and telemetry lookbacks, while a purely static timestamp would prevent measuring elapsed time during multi-turn live sessions.
- **Options Evaluated**:
  1. Hardcode `2026-08-28T17:00:00Z` everywhere (breaks live session elapsed time).
  2. Monkeypatch `datetime.now` globally (fragile and interferes with third-party libraries and DB drivers).
  3. Inject a `SimulationClock` anchored at `2026-08-28T17:00:00Z` that advances via `time.monotonic()` in live sessions and supports `.frozen()` for deterministic tests and batch evaluations.
- **Chosen Approach**: Option 3 (`SimulationClock` in `core/clock.py`).
- **Reasoning**: Provides deterministic reproducibility for evaluations and unit tests via `SimulationClock.frozen()` while naturally advancing elapsed seconds during interactive customer conversations without external library side effects.

---

## ADR-002: PostgreSQL Ingestion of `accounts` and `tickets`, Unified `db/seed.dump`, and `db/init/` Separation

- **Context / Problem**: The support engineer needs to authenticate callers against customer accounts (`data/tickets/accounts.csv`), resolve each account's headquarters country for business-hours SLA calculations (`data/telemetry/sites.json`), query historical tickets (`data/tickets/tickets.jsonl`) for repeat-contact detection, and update ticket statuses during live conversations. Additionally, database build, startup checks, and non-KB seeding previously lived inside `kbindex/`, conflating offline KB indexing with system-wide database initialization.
- **Options Evaluated**:
  1. Read `accounts.csv` and `tickets.jsonl` into memory on every service call and keep `kbindex/` as the catch-all build/startup package.
  2. Ingest `accounts` (enriched with the primary `-01` site's `country` code from `sites.json`) and `tickets` into PostgreSQL, bundle all 6 seeded tables into `db/seed.dump`, and extract cross-domain database initialization into `db/init/` (`seed.py`, `startup.py`, `build.py`).
- **Chosen Approach**: Option 2.
- **Reasoning**:
  - Storing `accounts` and `tickets` in PostgreSQL allows indexed SQL queries (`tickets_customer_created_idx`, `tickets_customer_site_idx`) for repeat-contact detection and persistent ticket status updates across sessions.
  - Using `on conflict (ticket_id) do nothing` (`preserve_existing=True`) during `db.init.startup` ensures live ticket updates are preserved across container restarts while `db.init.build` (`preserve_existing=False`) resets the canonical `db/seed.dump`.
  - Moving `seed.py`, `startup.py`, and `build.py` into `db/init/` keeps `kbindex/` strictly focused on KB crawling, chunking, and embedding.
