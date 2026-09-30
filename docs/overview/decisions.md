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

---

## ADR-003: Unbounded Repeat-Contact Detection Window (The Chicago Site Rule)

- **Context / Problem**: An early draft of §4.2 in `system-architecture-design.md` described `is_repeat_contact` as checking whether a site had a ticket in the last 7 days. However, in the synthetic ticket dataset (`data/tickets/tickets.jsonl`) anchored at `2026-08-28T17:00:00Z`, the canonical repeat-contact scenario (`SC-06` — Solstice Media Chicago site `S-1008-01`) consists of three tickets on the same site: `TCK-20264200` (`2026-08-11`, closed), `TCK-20264201` (`2026-08-19`, closed), and `TCK-20264216` (`2026-08-25`, open). A strict 7-day cutoff from `2026-08-28` (`>= 2026-08-21`) would exclude both prior closed tickets (`Aug 11` and `Aug 19`), leaving only the single open ticket (`Aug 25`) and failing to detect the repeat contact. Conversely, sites with two unrelated open tickets on the same site (`S-1003-01` firmware vs IPS; `S-1010-02` cloud/IPsec vs routing/BGP) must not be falsely flagged as repeat contacts.
- **Options Evaluated**:
  1. Enforce a strict 7-day lookback window (`created_at >= clock.now() - 7 days`).
  2. Use an unbounded historical lookback on `tickets` for the account/site, flagging `is_repeat_contact = True` when there is `>= 1` prior `closed` ticket on the same site/symptom or `>= 2` tickets sharing both `site_id` and (`product_area` or recurring symptom stems).
- **Chosen Approach**: Option 2 (`TicketService.detect_repeat_contact` in `services/ticket_service.py`).
- **Reasoning**: Captures multi-week recurring site churn (`SC-06` Chicago site across Aug 11, Aug 19, and Aug 25) while avoiding false positives on single-incident open sites (`SC-01`, `SC-11`, `SC-12`) and on sites with two unrelated open tickets (`S-1003-01`, `S-1010-02`).

---

## ADR-004: Dynamic `zoneinfo` Resolution from Account `country` Code & PydanticAI Gemini Fallback Agent

- **Context / Problem**: `POL-SLA.md` specifies that `P2`–`P4` SLA clocks run in business hours (`Mon–Fri 08:00–18:00` in the customer's primary region), while `P1` runs `24x7`. Account records store a 2-letter ISO country code (`country`), which may occasionally be `NULL` or require interactive clarification from a free-text customer reply (e.g., `"I'm in Israel"`).
- **Options Evaluated**:
  1. Hardcode a static Python dictionary of country codes and regex rules for free-text country extraction.
  2. Resolve any ISO 3166-1 alpha-2 country code dynamically via Python's stdlib IANA timezone table (`/usr/share/zoneinfo/zone1970.tab`, cached once in memory via `@lru_cache(maxsize=1)`), and when `country` is missing or unrecognized, log an error, prompt the user for their country, and extract the ISO code from the user's free-text reply via a PydanticAI `Agent` (`settings.llm_model = "google-gla:gemini-3.8-flash"` with structured `CountryCodeOutput`) before persisting it to `accounts.country`.
- **Chosen Approach**: Option 2 (`CustomerService` in `services/customer_service.py`).
- **Reasoning**: Parsing `/usr/share/zoneinfo/zone1970.tab` once with primary-country precedence supports all ISO 3166-1 alpha-2 codes (`US -> America/New_York`, `DE -> Europe/Berlin`, `IL -> Asia/Jerusalem`, `NL -> Europe/Brussels`, etc.) with zero external dependencies or per-call disk I/O, while PydanticAI + Gemini Flash cleanly normalizes arbitrary natural-language country replies and persists the resolved code to PostgreSQL.

---

## ADR-005: File-Backed `TelemetryService`, Unified `TelemetryToolResult[T]` Envelope, and Single-Module Evidence Extraction (`tools/telemetry.py`)

- **Context / Problem**: Phase 1.3 (Issue #3) requires 7 typed telemetry tools (`list_sites`, `get_site_status`, `get_link_quality`, `get_events`, `get_bgp_status`, `get_ipsec_status`, `get_client_diagnostics`) over `data/telemetry/`. In real production at Cato, telemetry lives in the external CMA GraphQL API and time-series backend rather than the agent's Postgres database. Furthermore:
  1. Each `link_quality/<site_id>.csv` contains ~580 rows (24h of 5-minute intervals across WAN links), which would bloat LLM context if returned raw.
  2. Conversely, each `events/<site_id>.jsonl` contains `<20` rows, and in scenario `SC-02-vague-slow` (`S-1008-03`), the critical `"Last-Mile Quality"` alert occurred at `2026-08-24T17:00:00Z` (4 days before the `2026-08-28T17:00:00Z` anchor), which would be dropped if an LLM passed `window="24h"` to a strict filter.
  3. The system architecture initially listed a separate `tools/formatters.py` module alongside `tools/telemetry.py`.
- **Options Evaluated**:
  1. Ingest `data/telemetry/` into PostgreSQL tables alongside `accounts` and `tickets`.
  2. Return raw `dict[str, Any]` payloads from `tools/telemetry.py` and format strings in a separate `tools/formatters.py` wrapper module.
  3. Read `data/telemetry/` directly from disk in a single module (`tools/telemetry.py`) using stdlib (`pathlib`, `json`, `csv`) + `@lru_cache` keyed on `(resolved_path, mtime_ns)`, returning a generic `TelemetryToolResult[T]` envelope that pairs typed Pydantic domain models (`data: T | None`) with deterministically extracted `evidence: list[TelemetryEvidence]`, aggregating 580-row `link_quality` CSVs per link while preserving all `<20` rows in `get_events`.
- **Chosen Approach**: Option 3 (`TelemetryService` in `tools/telemetry.py`).
- **Reasoning**:
  - **Production Alignment & YAGNI**: Unlike `tickets` (which are mutated during conversations and require persistence across restarts), telemetry is 100% read-only point-in-time CMA data. Reading directly from `data/telemetry/` accurately models querying an external read-only CMA API per `site_id` / `user_email` without unnecessary SQL tables, migrations, or seed steps, while making missing/corrupt file simulation (`status="unavailable"`) trivial in tests.
  - **Code-Judo Layer Deletion**: Embedding deterministic `TelemetryEvidence` extraction directly into `TelemetryToolResult[T]` inside `tools/telemetry.py` eliminates `tools/formatters.py`, removes per-tool error branching in `DiagnosticsAgent`, and guarantees verbatim metric quoting (`routes_count 1024/1024`, `NO_PROPOSAL_CHOSEN`, `AUTHENTICATION_FAILED`, `TUNNEL_TIMEOUT (408)`).
  - **Context-Aware Windowing**: Slicing and aggregating `link_quality/<site_id>.csv` by `window` reduces 580 CSV rows to compact per-link statistical summaries + anomaly evidence, whereas ignoring the time cutoff in `get_events` (while still validating `window` and filtering by `event_type`) ensures multi-day historical alerts in tiny `<20`-line JSONL logs (`S-1008-03`) are never lost.

