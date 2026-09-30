# 02 — Policy Lookup & `RetrievalService` Base — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create `RetrievalService` with in-memory, citable lookup of the 6 internal policies (`POL-CRED`, `POL-CREDIT`, `POL-IDV`, `POL-SEC`, `POL-SEV1`, `POL-SLA`). Lookup keeps working when the DB drops mid-conversation.

**Architecture:** `RetrievalService.__init__` reads the `policies` table once into a read-only mapping keyed by canonical id. `get_policy` and `list_policies` are pure in-memory reads, with no DB roundtrip per call. This plan creates `retrieval/models.py` and `retrieval/service.py`; plan 03 extends both with KB search. It depends on nothing, so it can run in parallel with plan 01.

**Tech Stack:** Python 3.12, psycopg 3 (sync), Pydantic v2, pytest.

**Spec:** [design.md](design.md) §2.2, §2.6, §2.7, §4.1.3, §4.2.1–2 (policy parts), §4.2.4–5, §5.2.

## Global Constraints

- Sync-only. Services take `psycopg.Connection[Any]`.
- Every function and method is fully annotated and passes Pyright `standard`. No bare `list`/`dict`, no implicit `Any`.
- ruff clean. Imports go at the top of the module. f-strings. SQL uses named `%(name)s` parameters where parameters exist.
- New Pydantic models are frozen (`ConfigDict(frozen=True)`).
- No new dependencies.
- Match the surrounding code: short `#` line comments, module-level `_private` helpers.
- Tests are functional against the real seeded PostgreSQL (6 policies present), no mocks. If the compose Postgres is not running, STOP and report.
- Verify with `uv run pytest <path> -v`, `uvx ruff check <paths>` and `uvx pyright <paths>`.

## Branching

- Plan branch: `p-1-4-02_policy-lookup`, created from `p-1-4_kb-retrieval-policy`.
- Task branch: `p-1-4-02-t1_policy-lookup`, created from the plan branch and merged back into it.
- Task 2 runs on the plan branch. Never merge to master, never create a worktree.

## Review Focus

1. **Id spelling variants** callers and the LLM will produce: `" pol-sla "`, `"POL-SLA.md"`, `"pol-sla.MD"`, `"POL-SLA"` all resolve to `POL-SLA`. → Task 1 test.
2. **Ids that must not resolve**: `""`, `"   "`, `"POL-"`, `"POL-SLA-EXTRA"`, `"../POL-SLA"` all return `None` and never raise. → Task 1 test.
3. **Mid-conversation DB outage**: after `connection.close()`, `get_policy` and `list_policies` still return full documents. → Task 1 test.
4. **Callers mutating what they got back**: `list_policies()` returns a fresh `list`, and `PolicyDocument` is frozen, so nothing a caller does can alter service state. → Task 1 test (assigning a field raises `ValidationError`).
5. **Construction against a DB with zero policies**: this is a broken seed. `__init__` raises `RuntimeError` naming the table rather than serving an empty policy set that makes every lookup silently miss. → Task 1 test, using a transaction that deletes the rows and is then rolled back.

---

### Task 1: `PolicyDocument` + `RetrievalService` policy lookup

**Files:**
- Create: `retrieval/models.py`
- Create: `retrieval/service.py`
- Test: `tests/retrieval/test_policy_lookup.py`

**Interfaces:**
- Consumes: the `policies` table (`id`, `title`, `file_path`, `body`). Ids are stored uppercase, for example `POL-SLA`.
- Produces (plan 03 extends these, so keep the names exact):
  - `retrieval.models.PolicyDocument`: frozen, with fields `policy_id: str`, `title: str`, `file_path: str`, `body: str`, and a method `citation_tag() -> str` returning `[policy:{policy_id}]`.
  - `retrieval.service.RetrievalService`, with:
    - `__init__(self, connection: psycopg.Connection[Any]) -> None`. Plan 03 adds `min_score` and the snapshot load.
    - `get_policy(self, policy_id: str) -> PolicyDocument | None`
    - `list_policies(self) -> list[PolicyDocument]`
  - The module-private helper `_normalize_policy_id(policy_id: str) -> str`.
  - The instance attribute `self._conn: psycopg.Connection[Any]`, which plan 03 uses.

- [ ] **Step 1: Write the failing functional tests** in `tests/retrieval/test_policy_lookup.py`. A module fixture opens `psycopg.connect(os.environ["DATABASE_URL"])`, the same pattern as `tests/kbindex/test_startup_rejects_a_hash_or_width_mismatch.py`.
  - `test_every_policy_resolves_with_a_citation_tag`:
    - each of the 6 ids returns a document whose `policy_id` matches
    - it has a non-empty `title` and `body`
    - its `file_path` ends with `f"{policy_id}.md"`
    - `citation_tag()` equals `f"[policy:{policy_id}]"`.
  - `test_policy_id_spelling_variants_normalize`: the Review Focus 1 variants resolve to `POL-SLA`.
  - `test_unknown_or_malformed_ids_return_none`: the Review Focus 2 inputs return `None`.
  - `test_list_policies_is_sorted_and_isolated`:
    - it returns 6 documents in ascending `policy_id` order
    - clearing the returned list leaves the next call at length 6
    - setting `title` on a document raises `pydantic.ValidationError`.
  - `test_lookup_survives_connection_close`: build the service, close the connection, then `get_policy("POL-SEV1")` and `list_policies()` still work.
  - `test_empty_policies_table_fails_fast`:
    - in an open transaction, `delete from policies`
    - assert `RetrievalService(conn)` raises `RuntimeError`
    - `conn.rollback()` in a `finally`.
- [ ] **Step 2: Run to confirm failure.** `uv run pytest tests/retrieval/test_policy_lookup.py -v`. Expected: `ModuleNotFoundError: retrieval.models`.
- [ ] **Step 3: Create `retrieval/models.py`** with `PolicyDocument` exactly as in Interfaces. It is the only model in this plan.
- [ ] **Step 4: Create `retrieval/service.py`.**
  - `_normalize_policy_id`: strip whitespace, uppercase, and remove one trailing `.MD` suffix (`str.removesuffix`). It never raises. Unknown ids simply miss the dict, which covers Review Focus 2 with no pattern matching.
  - `RetrievalService.__init__`:
    - stores `self._conn`
    - runs one query, `select id, title, file_path, body from policies order by id`
    - raises `RuntimeError("policies table is empty")` when zero rows come back
    - stores `self._policies: Mapping[str, PolicyDocument]` as a `types.MappingProxyType` over a dict comprehension keyed by `id`.
    - A `psycopg.Error` propagates (design §4.2.1: startup already requires the DB).
  - `get_policy` returns `self._policies.get(_normalize_policy_id(policy_id))`.
  - `list_policies` returns `list(self._policies.values())`. Insertion order is already `order by id`.
- [ ] **Step 5: Run and confirm pass.** `uv run pytest tests/retrieval/test_policy_lookup.py -v`. Expected: all PASS.
- [ ] **Step 6: Clean-code gate.** `uvx ruff check retrieval tests/retrieval` and `uvx pyright retrieval`. Both clean. No unused imports.
- [ ] **Step 7: Commit** on `p-1-4-02-t1_policy-lookup`: `feat(retrieval): RetrievalService with in-memory policy lookup`.

---

### Task 2: Review & cleanup (plan branch)

- [ ] **Step 1: Merge** `p-1-4-02-t1_policy-lookup` into `p-1-4-02_policy-lookup`.
- [ ] **Step 2: Review the plan diff** with `/ponytail:ponytail-review`, then with `/anthropic-skills:thermo-nuclear-code-quality-review`. Fix accepted findings and re-run `uv run pytest tests/retrieval -v`.
- [ ] **Step 3: Cleanup gate.**
  - ruff and pyright are clean on `retrieval`.
  - No speculative parameters or helpers (for example, no `refresh_policies`).
  - `retrieval/__init__.py` stays a one-line comment (no re-exports; YAGNI).
- [ ] **Step 4: Commit** `chore(plan-02): review fixes`.

## Unresolved Questions

None.
