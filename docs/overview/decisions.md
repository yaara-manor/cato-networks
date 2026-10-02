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
  2. Resolve any ISO 3166-1 alpha-2 country code dynamically via Python's stdlib IANA timezone table (`/usr/share/zoneinfo/zone1970.tab`, cached once in memory via `@lru_cache(maxsize=1)`), and when `country` is missing or unrecognized, log an error, prompt the user for their country, and extract the ISO code from the user's free-text reply via a PydanticAI `Agent` (`settings.llm_model = "openai:gpt-5-nano"` with structured `CountryCodeOutput`) before persisting it to `accounts.country`.
- **Chosen Approach**: Option 2 (`CustomerService` in `services/customer_service.py`).
- **Reasoning**: Parsing `/usr/share/zoneinfo/zone1970.tab` once with primary-country precedence supports all ISO 3166-1 alpha-2 codes (`US -> America/New_York`, `DE -> Europe/Berlin`, `IL -> Asia/Jerusalem`, `NL -> Europe/Brussels`, etc.) with zero external dependencies or per-call disk I/O, while PydanticAI + Gemini Flash cleanly normalizes arbitrary natural-language country replies and persists the resolved code to PostgreSQL.

---

## ADR-005: File-Backed `TelemetryService`, Package-Scoped `tools/models.py`, and Bounded Generic `TelemetryToolResult[T]`

- **Context / Problem**: Phase 1.3 (Issue #3) requires 7 typed telemetry tools (`list_sites`, `get_site_status`, `get_link_quality`, `get_events`, `get_bgp_status`, `get_ipsec_status`, `get_client_diagnostics`) over `data/telemetry/`. In real production at Cato, telemetry lives in the external CMA GraphQL API and time-series backend rather than the agent's Postgres database. Furthermore:
  1. Placing ~12 telemetry-specific Pydantic models into `core/models.py` would turn `core/models.py` into a cross-domain "god schema" coupling magnet.
  2. Each `link_quality/<site_id>.csv` contains ~580 rows (24h of 5-minute intervals across WAN links), which would bloat LLM context if returned raw.
  3. Conversely, each `events/<site_id>.jsonl` contains `<20` rows, and in scenario `SC-02-vague-slow` (`S-1008-03`), the critical `"Last-Mile Quality"` alert occurred at `2026-08-24T17:00:00Z` (4 days before the `2026-08-28T17:00:00Z` anchor), which would be dropped if an LLM passed `window="24h"` to a strict filter.
  4. Tool results need a uniform envelope (`status: TelemetryStatus`, `data`, `evidence`, `error`) that supports both narrow per-tool type safety at direct call sites and heterogeneous collection across tools.
- **Options Evaluated**:
  1. Ingest `data/telemetry/` into PostgreSQL tables alongside `accounts` and `tickets`, and store all telemetry schemas in `core/models.py`.
  2. Use a bare `Union` for `TelemetryToolResult.data: TelemetryPayload | None` (non-generic) or return raw `dict[str, Any]` payloads with a separate `tools/formatters.py` module.
  3. Read `data/telemetry/` directly from disk in `tools/telemetry.py` using stdlib (`pathlib`, `json`, `csv`) + `@lru_cache` keyed on `(resolved_path, mtime_ns)`; colocate all telemetry contracts (`TelemetryStatus(StrEnum)` with `"OK"`, `"NOT_FOUND"`, `"UNAVAILABLE"`, `"INVALID_ARGUMENT"`, `TelemetryEvidence`, `TelemetryPayload` union alias, and bounded generic `TelemetryToolResult[T: TelemetryPayload]`) in `tools/models.py` (removing `TelemetryEvidence` from `core/models.py`); aggregate 580-row `link_quality` CSVs per link while preserving all `<20` rows in `get_events`.
- **Chosen Approach**: Option 3 (`tools/models.py` + `tools/telemetry.py`).
- **Reasoning**:
  - **Package Cohesion (`core/models.py`, `services/models.py`, `tools/models.py`, `agents/models.py`)**: Keeping `core/models.py` strictly limited to shared cross-cutting primitives (`CustomerAccount`, `Ticket` and their literal type aliases) while colocating domain-specific schemas in `services/models.py` (`CallerIdentity`, `SLADeadlines`, `RepeatContactResult`, `CountryCodeOutput`; the early `ApprovalRecord` was deleted in favour of `storage.Approval`), `tools/models.py` (`TelemetryEvidence`, `TelemetryStatus`, `TelemetryToolResult[T]`, payload schemas), and `agents/models.py` (`AgentTrace`) enforces Single Responsibility and prevents `core/models.py` from coupling unrelated packages.
  - **Bounded Generic `TelemetryToolResult[T: TelemetryPayload]` vs. Bare `Union`**: If `.data` were typed only as a 7-way `Union` (`TelemetryPayload | None`), Pyright (`typeCheckingMode: "standard"`) would reject direct attribute access such as `res.data.neighbors` on `get_bgp_status()` because the other 6 union members lack `.neighbors`, forcing `isinstance` assertions or `cast()` boilerplate at every call site and test. Defining `TelemetryPayload` as the union alias and bounding `T` to `TelemetryPayload` gives narrow compile-time types per tool (`TelemetryToolResult[BgpStatusPayload]`) while still allowing heterogeneous collections to use `TelemetryToolResult[TelemetryPayload]`.
  - **Production Alignment & YAGNI**: Reading directly from `data/telemetry/` accurately models querying an external read-only CMA API per `site_id` / `user_email` without unnecessary SQL tables, migrations, or `tools/formatters.py` indirection.
  - **Context-Aware Windowing**: Slicing and aggregating `link_quality/<site_id>.csv` by `window` reduces 580 CSV rows to compact per-link statistical summaries + anomaly evidence, whereas ignoring the time cutoff in `get_events` ensures multi-day historical alerts in tiny `<20`-line JSONL logs (`S-1008-03`) are never lost.

## ADR-006: Telemetry Hardening: Identity Validation, Granular Reachability, Asynchronous Timeouts, and Shared State Enums

- **Context / Problem**: Initial telemetry loading allowed potential foreign payload returns if embedded identities (`site_id`, `user_email`) did not match the query, collapsed UDP and TCP 443 reachability into a single text-formatted evidence item, lacked positive deadline enforcement during synchronous read/parsing operations, used unconstrained `str` for finite-state fields (`SiteRecord.status`, `CmaEvent.action`, `BgpNeighbor.state`, `IpsecTunnelEndpoint.status`), permitted `SimulationClock` to raise unhandled `OverflowError` on massive finite windows (e.g. `1000000000d`), evaluated IPsec note anomalies using only the primary tunnel, and defaulted missing BGP timer fields to `0` (emitting misleading `0s` evidence on idle sessions).
- **Options Evaluated**:
  1. Rely on filename validation alone, ignore positive timeout enforcement, and parse reachability strings downstream.
  2. Implement strict identity validation on all loaded objects and JSONL lines (returning `TelemetryStatus.UNAVAILABLE` on mismatch), emit discrete `udp_443_reachable` and `tcp_443_reachable` evidence entries with raw booleans alongside optional `ssid` evidence, enforce positive timeouts via non-blocking worker pool cancellation (`_load_with_timeout`), constrain finite states with `Literal` types and preprocessing normalization (`@field_validator(mode="before")`), normalize oversized finite windows (`>= MAX_WINDOW_HOURS`) to `float("inf")`, link IPsec note anomalies to aggregate tunnel health (`primary_unhealthy or secondary_unhealthy`), and define BGP negotiated timers as `int | None = None` while suppressing timer evidence for inactive sessions.
- **Chosen Approach**: Option 2.
- **Reasoning**:
  - **Zero Trust File Parsing**: Path resolution protects directory boundaries, but validating embedded IDs prevents foreign data leakage if files are misplaced or corrupted.
  - **Granular Evidence Citations**: Consumers and evaluation metrics require structured evaluation of UDP vs TCP port 443 connectivity without regex parsing of composite reachability strings.
  - **Bounded Execution**: Bounding both I/O and deserialization under `_load_with_timeout` guarantees the TAC agent will not freeze if disk or parser operations hang, returning `TelemetryStatus.UNAVAILABLE` consistently.
  - **Explicit Modeling of BGP & Tunnel States**: An idle BGP session has no negotiated timers; reporting `0s` without an anomaly was factually misleading. Making timers optional accurately reflects protocol reality and cleanly suppresses timer evidence until a session reaches `Established`.

---

## ADR-007: Single-Module `RetrievalService` (`retrieval/service.py`), Native PostgreSQL Snowball Stemming, and `KBSearchResult` Envelope

- **Context / Problem**: Phase 1.4 (Issue #4) requires online hybrid KB retrieval (lexical top-20 + vector top-20 + RRF $k=60$ + `ms-marco-MiniLM-L12-v2` cross-encoder reranking + `RERANK_MIN_SCORE` confidence gate) and lookup of the 6 internal governance policies (`POL-*`). Early architecture drafts split this across 4–5 small files (`retrieval/search.py`, `retrieval/threshold.py`, `retrieval/policies.py`, `services/retrieval_service.py`, `services/policy_service.py`). Additionally:
  1. `passages.search_vector` was indexed with PostgreSQL's `'simple'` configuration. Using `plainto_tsquery('simple', query)` (`AND` across all tokens, including English filler words like `"what"`, `"does"`, `"why"`) returns 0 lexical rows on multi-clause natural-language questions (`data/eval/questions.jsonl`), while naive `OR` without stopword removal matches every passage on `"the"` / `"is"`. A tried fallback — keep `'simple'`, stem the query in Python, and OR-match stems as `:*` prefixes — was verified broken on the live DB: Snowball stems are not always prefixes of the surface word (`policy`→`polici`, `priority`→`prioriti`, `proxy`→`proxi` each fail to match themselves against a `'simple'` index). Meanwhile, `services/ticket_service.py` maintained a hardcoded 30-word `_STOPWORDS` set and a naive 5-character prefix slicer (`tok[:5]`) in Python.
  2. Deliverable C (`answers.md`) and the `traces` table require the top retrieved chunks with scores and the `snapshots.crawled_at` timestamp from the same code path even when a query is refused below `RERANK_MIN_SCORE`.
- **Options Evaluated**:
  1. Split search, thresholding, and policy lookup across 4–5 modules, use literal `plainto_tsquery('simple', query)`, keep Python `_STOPWORDS` in `ticket_service.py`, and raise exceptions on DB outages or low-confidence refusals.
  2. Add an external Python stemmer dependency (`snowballstemmer` / `nltk`) and run 3 sequential SQL queries per search.
  3. Consolidate KB hybrid retrieval and policy lookup into `RetrievalService` inside a single module (`retrieval/service.py` alongside `encoders/rerank.py`), execute lexical + vector + `FULL OUTER JOIN` RRF in a single SQL CTE against a `passages.search_vector` generated column re-indexed with PostgreSQL's built-in `'english'` Snowball stemmer (`tsvector_to_array(to_tsvector('english', query))` folded into a plain `::tsquery` cast, no `:*` prefix matching), delete `_STOPWORDS` from `services/ticket_service.py` in favor of PostgreSQL `'english'` stemming, load the 6 policies and the pinned `snapshots.crawled_at` once at `RetrievalService.__init__` instead of per-call, and return a typed `KBSearchResult` envelope (`PolicyDocument` lookups return plain values — they cannot fail at runtime).
- **Chosen Approach**: Option 3 (`RetrievalService` in `retrieval/service.py`).
- **Reasoning**:
  - **Code-Judo Layer Deletion**: Putting `search_kb`, `get_policy`, and `list_policies` on `RetrievalService` in `retrieval/service.py` eliminates four pass-through files and removes the redundant `policy_store` field from `SupportDeps`.
  - **Native PostgreSQL Snowball Stemmer (Zero New Dependencies)**: PostgreSQL's `'english'` dictionary natively strips English stopwords and computes Porter2/Snowball stems in C on both the indexed column and the query, so stem equality alone matches morphological variants and exact technical identifiers (`no_proposal_chosen`, `1383`) — no `:*` prefix trick needed, and it lets us delete `_STOPWORDS` and `_symptom_stems` from `services/ticket_service.py`.
  - **Rerank Depth 20, Batch Size 8 (Realtime Budget)**: measured on-machine (CPU, under load, median of 5): cross-encoder over 40 pairs ≈ 2.0s, over the RRF top-20 ≈ 0.9s; `batch_size=8` beats 32 (40 pairs: 2.0s vs 3.4s). Vector scan over 14,109 rows ≈ 25ms, query embedding ≈ 30ms. The reranker is the whole latency budget, so `search_kb` reranks only the RRF top `_RERANK_K = 20` (design §2.8).
  - **`KBSearchStatus` `StrEnum` + In-Memory Policies/Snapshot**: `KBSearchResult.status` is a `KBSearchStatus` `StrEnum` (`CONFIDENT`, `LOW_CONFIDENCE_REFUSAL`, `UNAVAILABLE`) mirroring `TelemetryStatus`. The 6 policies and the snapshot `crawled_at` are immutable for a given `seed.dump`, so `__init__` loads them once into an in-memory mapping — no per-call policy DB roundtrip, no per-row `snapshots` join, no empty-result snapshot fallback.
  - **Unified Eval & Chat Contract**: Returning `KBSearchResult` (`status`, threshold-filtered `passages` for the agent, unfiltered `candidates` for traces/`answers.md`, `snapshot_date`, and `error` on `psycopg.Error`) satisfies both interactive chat safety and `answers.md` auditability from a single method call.
  - **Threshold Calibration Stop Rule (> 3 answerable refused)**: `RERANK_MIN_SCORE` is calibrated (`eval/calibrate_threshold.py`) to refuse off-domain questions only. Partially covered questions such as SC-09 (IPv6 roadmap) pass the gate, and refusing their uncovered part (roadmap dates) is the Knowledge Agent's grounding duty. If answerable and off-domain scores overlap, the threshold is the lowest value that refuses every off-domain question. If that refuses **more than 3** of the 35 answerable questions (~9%), calibration stops and the threshold is not applied without an explicit product decision: accept the loss, drop a borderline off-domain probe, or fix retrieval for the low scorers. At 3 or fewer, it is applied automatically. (The applied value deviates from this rule, see the next bullet.)
  - **Threshold Calibration Result (`rerank_min_score = 2.00`, safety floor)**: report in `docs/eval/threshold_calibration.md`. The top-1 rerank score does not separate right from wrong (AUC 0.90 on 57 labelled queries, 54 of them LLM-judged and 3 on the query-set prior (evidence: `experiments/README.md`, notebook `06_results_and_threshold`); real tickets show confident-but-wrong and relevant-but-low cases), so the value is a floor that drops hopeless matches, not a correctness test. Two original off-domain probes (Cisco VLANs, M365 password) matched real Cato articles (scores 4.89, 3.99) and were replaced. On the final fixture the plan rule gives 0.77, which would round up to 0.78; 2.00 was applied instead. It is the highest 2-decimal value that keeps Q05 (2.007) and the other three plan-03 confident questions (Q01, Q10, Q15) `CONFIDENT`, and it refuses 1 of the 35 answerable questions (Q14, top-1 is release notes) and all 10 off-domain probes. A higher floor (2.75 from the 5% rule) was rejected because it flips Q15 (2.735). Partial coverage (SC-09 IPv6 roadmap 4.24, roadmap probe 4.74) passes the gate; refusing the uncovered part is agent grounding. Latency p50 1.5 s, p95 1.8 s. Alternatives measured in `experiments/` (LLM query rewrite, relative gates, search-tool agent with 1-3 searches) did not beat the fixed cut by the required 3 F1 points (0.857 vs best 0.875, paired CI includes 0) at 10x latency and 1-2.4 extra LLM calls per query, so the fixed cut stays. Caveats: judge labels are partial (54 of 89 queries; scenarios and real tickets unjudged), the 2.00 floor sits only 0.007 under Q05 so a reranker or revision change must re-run calibration, the cut is in-sample, and SC-01/11/12 gold articles are not in the top 5, so retrieval quality, not the gate, is the open problem.

---

## ADR-008: Conversation State as Postgres Rows (`storage/StateStore`), Append-Only Traces, No Braintrust

- **Context / Problem**: Phase 2.1 (Issue #6) must survive process restarts and replay a conversation from stored data alone, while several writers (customer turn, reviewer resolving an approval, background retry) touch one conversation.
- **Chosen Approach**: Every runtime fact is a row: `conversations` (stage, guard history, versioned `state`, `last_turn`/`last_seq` counters), `messages`, append-only `traces` plus a `tool_calls` child table, and `approvals`. One sync `StateStore` over an autocommit connection; each write is one transaction that first locks the conversation row (`SELECT ... FOR UPDATE`), which makes turn/seq counters gapless and "exists? then insert" idempotency race-free. Approval resolution is a compare-and-set from `PENDING`. `rehydrate`/`replay_trace` read under `REPEATABLE READ`.
- **Tracing**: PydanticAI message history is stored in `traces.model_messages`, next to redacted inputs, tool envelopes and cost; this replaces Braintrust (dropped).
- **Seed dump**: runtime tables are excluded from `db/seed.dump` via `--exclude-table`, because `pg_restore --clean` on every boot would wipe live conversations.
- **Cost if wrong**: cross-worker turn locking and `ConversationState` rebuild are not solved here (issue #34).

---

## ADR-009: Specialized Agent Contracts: LLM Decides, Code Records

- **Context / Problem**: Phase 2.2 needs four PydanticAI role agents (Triage, Diagnostics, Knowledge, Resolution) whose outputs feed the 2.3 orchestrator without trusting the model for facts code can derive.
- **Chosen Approach**: Each role's LLM output is a small `*Decision`/`*Findings` model; code assembles the final result (`TriageResult`, `DiagnosticEvidence`, `KnowledgeBundle`) from tool returns, identity and services. Resolution has no tools; its `ResolutionPlan` passes two PydanticAI output validators wrapping `guardrails.check_citations` / `check_outgoing_message` (native `ModelRetry`, budget 1), else a canned holding plan with `escalate_to_human=True`.
- **Hard gates in code**: approvals come from `check_action`, not a model field. `ActionType.PAGE_ON_CALL` is ALLOWed only for P1 + code-derived `sev1_corroborated` + not already paged (`POL-SEV1`).
- **Tracing**: PydanticAI messages, usage and latency (`AgentTrace.from_run`); no brainstruct. Persistence stays in `StateStore` (ADR-008).
- **Cost if wrong**: a single `settings.llm_model` serves all roles; the fallback escalation reason is one fixed string (cannot distinguish validator exhaustion from transport-level model failure).

---

## ADR-010: Hand-Rolled Sync Orchestration Workflow, Stateless Per-Turn Degradation

- **Context / Problem**: Phase 2.3 must route one customer turn through guards and four agents, degrade explicitly when telemetry or KB is down, and survive an agent exception.
- **Chosen Approach**: A plain synchronous `orchestration.Workflow.run_turn` over `StateStore` instead of `pydantic_graph`. Degradation is a pure function of statuses on `DiagnosticEvidence` / `KnowledgeBundle`, recomputed every turn; only `OrchestratorState.notice_shown` (in the versioned state snapshot) dedupes the customer notice, cleared when the source is healthy. Refusal is enforced by `run_resolution` validators, not a second workflow path. One `except Exception` boundary returns a canned pause message and an `ERROR` trace (class name only). No Braintrust.
- **Cost if wrong**: no graph visualisation or resumable node state; a crash mid-turn is recovered by replaying the idempotent `message_id`.

