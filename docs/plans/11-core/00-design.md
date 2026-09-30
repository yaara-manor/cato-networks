# [Phase 1] 1.1: System Clock, Configuration & Pydantic Data Models — Implementation Plan

## Goal Description

Create the `core/` package (`core/clock.py`, `core/config.py`, and `core/models.py`) providing the ticking `SimulationClock` anchored to `2026-08-28T17:00:00Z`, centralized `pydantic-settings` `Settings` (absorbing constants from `kbindex/config.py`), and the typed Pydantic v2 domain schemas consumed by downstream services and agents.

---

## Global Constraints

- **No Inline Imports**: All imports must sit at the top of each module.
- **Strict Type Annotations**: Every function and method must explicitly annotate all parameter types and return types (including `-> None`), adhering to Pyright standard mode.
- **Functional over Unit Testing**: Skip unit tests for declarative Pydantic models and settings (`core/models.py`, `core/config.py`); only test non-trivial clock window/ticking math.

---

## Proposed Changes

### Core Package (`core/`)

#### [NEW] `core/__init__.py`
- **One-liner**: Package marker exporting `SimulationClock`, `Settings`, and the core Pydantic domain schemas.

#### [NEW] `core/clock.py`
- **One-liner**: Implement `SimulationClock` anchored to `2026-08-28T17:00:00Z` that ticks forward using `time.monotonic()` in live mode so conversations have progressing timestamps while remaining inside the 24-hour telemetry window.
- **Functions & Methods**:
  - `SimulationClock.__init__(self, anchor: datetime = DEFAULT_ANCHOR, ticking: bool = True, clock_fn: Callable[[], float] = time.monotonic) -> None`: Stores `anchor` (`2026-08-28T17:00:00Z`), `ticking`, `clock_fn`, and `started_at_monotonic = clock_fn()`.
  - `SimulationClock.frozen(cls, anchor: datetime = DEFAULT_ANCHOR) -> SimulationClock`: Classmethod returning a non-ticking (`ticking=False`) clock for deterministic test assertions.
  - `SimulationClock.now(self) -> datetime`: Returns `anchor + timedelta(seconds=clock_fn() - started_at_monotonic)` when `ticking=True`, or `anchor` when `ticking=False`.
  - `SimulationClock.elapsed(self, since: datetime) -> timedelta`: Returns `self.now() - since`.
  - `SimulationClock.is_within(self, ts: datetime, window_hours: int) -> bool`: Returns whether `ts` falls within `[self.now() - timedelta(hours=window_hours), self.now()]`.

#### [NEW] `core/config.py` & [DELETE] [kbindex/config.py](file:///home/yaara/Documents/Assignments/cato%20networks/kbindex/config.py)
- **One-liner**: Centralize all application and ingestion settings into `core/config.py` using `pydantic-settings` `BaseSettings`, update `kbindex/` modules to import from `core.config`, and delete `kbindex/config.py`.
- **Fields on `Settings`**:
  - `repo_root: Path`
  - `database_url: str` (default `"postgresql://kb:kb@localhost:5432/kb"`)
  - `simulation_time: AwareDatetime` (default `2026-08-28T17:00:00Z`)
  - `user_agent: str`, `rate_limit_seconds: float`
  - `embedding_model: str`, `embedding_revision: str`, `embedding_dimensions: int`
  - `reranker_model: str`, `reranker_revision: str`, `rerank_min_score: float`
  - `query_prefix: str`, `passage_token_cap: int`, `slice_new_tokens: int`, `slice_overlap_tokens: int`
  - `llm_model: str`, `country_resolver_model: str`

#### [NEW] `core/models.py`
- **One-liner**: Define the Pydantic v2 domain models shared across `services/` and `agents/`.
- **Models & Fields**:
  - `AccountTier`: Type alias for `Literal["Premium", "Standard", "Unknown"]`.
  - `TicketPriority`: Type alias for `Literal["P1", "P2", "P3", "P4"]`.
  - `TicketStatus`: Type alias for `Literal["open", "closed", "pending_customer", "pending_approval"]`.
  - `CustomerAccount`: Fields `account_id: str`, `company: str`, `tier: AccountTier`, `email_domain: str`, `registered_admin_contact: str`, `country: str | None = None`.
  - `CallerIdentity`: Fields `account: CustomerAccount | None`, `caller_email: str | None`, `effective_tier: AccountTier`, `is_verified_account_member: bool`, `is_registered_admin: bool`, `claimed_tier_rejected: bool`, `needs_country_clarification: bool`, `scoping_question: str | None = None`.
  - `SLADeadlines`: Fields `priority: TicketPriority`, `tier: AccountTier`, `timezone_name: str`, `product_area: str | None`, `started_at: AwareDatetime`, `first_response_due: AwareDatetime`, `resolution_due: AwareDatetime`, `update_cadence: str`, `is_24x7: bool`, `resolution_paused: bool`.
  - `Ticket`: Fields `ticket_id: str`, `created_at: AwareDatetime`, `channel: str`, `customer_id: str`, `customer_name: str`, `requester_email: str`, `company: str`, `tier: AccountTier`, `site_id: str | None`, `product_area: str`, `priority: TicketPriority`, `subject: str`, `body: str`, `status: TicketStatus`.
  - `RepeatContactResult`: Fields `is_repeat_contact: bool`, `matching_tickets: list[Ticket]`, `prior_closed_tickets: list[Ticket]`, `reason: str | None`.
  - `TelemetryEvidence`, `Citation`, `ApprovalRecord`, `AgentTrace`: Schemas matching §4.2 of [system-architecture-design.md](file:///home/yaara/Documents/Assignments/cato%20networks/docs/architecture/system-architecture-design.md).

---

## Execution Plan

### Task 1: Implement `core/config.py` and `core/models.py` and Migrate `kbindex/` Imports
- **Files**:
  - Create: `core/__init__.py`, `core/config.py`, `core/models.py`
  - Modify: `kbindex/build.py`, `kbindex/chunk.py`, `kbindex/crawl.py`, `kbindex/embed.py`, `kbindex/policies.py`, `kbindex/startup.py`, `kbindex/store.py`
  - Delete: `kbindex/config.py`
- **Steps** (declarative schemas and config migration — no new unit tests needed):
  - [ ] **Step 1**: Implement `core/config.py` and `core/models.py`, update `kbindex/` imports to reference `core.config`, and remove `kbindex/config.py`.
  - [ ] **Step 2**: Run existing `uv run pytest tests/kbindex -v` to verify `kbindex` still passes.
  - [ ] **Step 3**: Commit `core/config.py`, `core/models.py`, and `kbindex/` import updates.

### Task 2: Implement Ticking `SimulationClock` (`core/clock.py`)
- **Files**:
  - Create: `core/clock.py`
  - Create: `tests/core/test_clock.py`
- **Steps**:
  - [ ] **Step 1 (Write Failing Test)**: Create `tests/core/test_clock.py` testing monotonic clock advancement (`ticking=True`), frozen mode (`ticking=False`), and `is_within` 24-hour window boundary checks.
  - [ ] **Step 2 (Verify Failure)**: Run `uv run pytest tests/core/test_clock.py -v` and confirm failure.
  - [ ] **Step 3 (Implement)**: Implement `SimulationClock` in `core/clock.py` and export in `core/__init__.py`.
  - [ ] **Step 4 (Verify Pass)**: Run `uv run pytest tests/core/test_clock.py -v` and confirm pass.
  - [ ] **Step 5 (Commit)**: Commit `core/clock.py` and `tests/core/test_clock.py`.

### Task 3: Cleanup
- **Steps**:
  - [ ] **Step 1**: Verify `kbindex/config.py` is deleted, no unused imports or dead code exist in `core/` or `kbindex/`, and all functions have strict type annotations (`-> None` included).
