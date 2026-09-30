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

## ADR-005: Single-Module `RetrievalService` (`retrieval/service.py`), Native PostgreSQL Snowball Stemming, and `KBSearchResult` Envelope

- **Context / Problem**: Phase 1.4 (Issue #4) requires online hybrid KB retrieval (lexical top-20 + vector top-20 + RRF $k=60$ + `ms-marco-MiniLM-L12-v2` cross-encoder reranking + `RERANK_MIN_SCORE` confidence gate) and lookup of the 6 internal governance policies (`POL-*`). Early architecture drafts split this across 4–5 small files (`retrieval/search.py`, `retrieval/threshold.py`, `retrieval/policies.py`, `services/retrieval_service.py`, `services/policy_service.py`). Additionally:
  1. `passages.search_vector` is indexed with PostgreSQL's `'simple'` configuration (`to_tsvector('simple', body)`). Using `plainto_tsquery('simple', query)` (`AND` across all tokens, including English filler words like `"what"`, `"does"`, `"why"`) returns 0 lexical rows on multi-clause natural-language questions (`data/eval/questions.jsonl`), while naive `OR` without stopword removal matches every passage on `"the"` / `"is"`. Meanwhile, `services/ticket_service.py` maintained a hardcoded 30-word `_STOPWORDS` set and a naive 5-character prefix slicer (`tok[:5]`) in Python.
  2. Deliverable C (`answers.md`) and the `traces` table require the top retrieved chunks with scores and the `snapshots.crawled_at` timestamp from the same code path even when a query is refused below `RERANK_MIN_SCORE`.
- **Options Evaluated**:
  1. Split search, thresholding, and policy lookup across 4–5 modules, use literal `plainto_tsquery('simple', query)`, keep Python `_STOPWORDS` in `ticket_service.py`, and raise exceptions on DB outages or low-confidence refusals.
  2. Add an external Python stemmer dependency (`snowballstemmer` / `nltk`) and run 3 sequential SQL queries per search.
  3. Consolidate KB hybrid retrieval and policy lookup into `RetrievalService` inside a single module (`retrieval/service.py` alongside `retrieval/rerank.py`), execute lexical + vector + `FULL OUTER JOIN` RRF + `snapshots` join in a single SQL CTE using PostgreSQL's built-in `'english'` Snowball stemmer (`tsvector_to_array(to_tsvector('english', query))` with `:*` prefix OR-matching against the `'simple'` GIN index), delete `_STOPWORDS` from `services/ticket_service.py` in favor of PostgreSQL `'english'` stemming, and return typed `KBSearchResult` / `PolicyLookupResult` envelopes.
- **Chosen Approach**: Option 3 (`RetrievalService` in `retrieval/service.py`).
- **Reasoning**:
  - **Code-Judo Layer Deletion**: Putting `search_kb`, `get_policy`, and `list_policies` on `RetrievalService` in `retrieval/service.py` eliminates four pass-through files and removes the redundant `policy_store` field from `SupportDeps`.
  - **Native PostgreSQL Snowball Stemmer (Zero New Dependencies)**: PostgreSQL's `'english'` dictionary natively strips English stopwords and computes Porter2/Snowball stems in C. Appending `:*` to those stems (`rekey:* | fail:* | azur:*`) matches morphological variants and exact technical identifiers (`no_proposal_chosen:*`, `1383:*`) directly against the existing `'simple'` GIN index in a single CTE roundtrip, while allowing us to delete `_STOPWORDS` and `_symptom_stems` from `services/ticket_service.py`.
  - **Unified Eval & Chat Contract**: Returning `KBSearchResult` (`status`, threshold-filtered `passages` for the agent, unfiltered `candidates` for traces/`answers.md`, `snapshot_date`, and `error` on `psycopg.Error`) satisfies both interactive chat safety and `answers.md` auditability from a single method call.

