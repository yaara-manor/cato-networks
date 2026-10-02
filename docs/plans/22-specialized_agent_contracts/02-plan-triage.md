# Triage Agent Implementation Plan (22 / plan 2 of 4)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax. User rule: no code lines in this plan.

**Goal:** `build_triage_agent()` + `run_triage()` returning `AgentRun[TriageResult]`, with identity resolved outside Triage (orchestrator, 23), SLA and repeat contact as deterministic post-steps, and a sanitized ticket-history tool.

**Architecture:** LLM output is `TriageDecision` only. `run_triage(TriageInput, SupportDeps)` takes the already-resolved identity, runs `run_role`, then assembles `TriageResult` with `TicketService.detect_repeat_contact` and `CustomerService.calculate_sla_deadlines`. Model failure falls back to a safe decision; identity/SLA stay intact.

**Tech Stack:** pydantic-ai 2.51, existing `services/`, `guardrails/`.

**Spec:** `docs/plans/22-specialized_agent_contracts/design.md` §3.2, §4.1, §4.5. **Depends on:** plan 01 (contracts, `SupportDeps`, `build_agent`, `run_role`, fixtures).

## Global Constraints

Same as plan 01: typed everywhere, no inline imports, frozen contracts, functional tests with scripted models and real seeded services, no brainstruct, no new dependencies, f-strings only, conversions as classmethods.

## Design Decisions (this plan)

- Identity is **not** an LLM tool and not a Triage step: the orchestrator (23) calls existing `CustomerService.authenticate_caller` (plain function; identity/auth is never LLM-decided) and passes the result in `TriageInput.identity` and `SupportDeps.identity`. The Triage LLM only classifies and judges. `claimed_tier` is never passed (guard covers claims, design Q2).
- `run_triage(data: TriageInput, deps: SupportDeps, model: Model | None = None)` never authenticates; it reads `data.identity` (equal to `deps.identity`). Test fixtures build identity with `customers.authenticate_caller` (`make_deps` already does).
- Ticket sanitizing is one helper shared by every tool that returns ticket text: `quarantine(redact(text).text)` using existing `guardrails.redact` and `guardrails.quarantine` (design §4.1). Located in `agents/triage.py` (only Triage returns ticket text; move to base only if a second role needs it).
- Identity block in the prompt is injected through a dynamic instructions callback (same mechanism as the guard note), not by string templating the prompt file.

## Review Focus

- Caller with no account: SLA/repeat contact `None`, history tool returns `[]`, no private data in instructions.
- Account with missing country: `scoping_question` is the deterministic country question, SLA call must not crash (check `calculate_sla_deadlines` behaviour with `country_code=None` first; if it raises for unknown country, SLA is `None` while `needs_country_clarification`).
- Seed ticket with a pasted PSK (TCK-20264230) and the injection ticket (TCK-20264246) never reach the model unredacted/unquarantined.
- Model failure mid-run keeps identity/SLA/repeat contact.
- Model proposes `site_id` that does not belong to the account: repeat-contact query is scoped by `identity.account.account_id` (check actual field name in `core/models.CustomerAccount`) so no cross-account leak.

## File Structure

- `agents/triage.py` (create): `build_triage_agent`, `get_ticket_history` tool, `sanitize_ticket_text`, `run_triage`.
- `agents/models.py` (modify, small): `TriageResult.assemble`-style classmethod `from_decision(decision, identity, sla, repeat_contact)` only if more than a constructor call is needed; otherwise construct directly (no extra method).
- `prompts/triage.md` (create).
- `tests/agents/test_triage.py` (create).

## Tasks

### Task 1: Sanitized ticket-history tool

**Files:** create `agents/triage.py` (tool + helper), `tests/agents/test_triage.py`.

**Interfaces:** `get_ticket_history(ctx: RunContext[SupportDeps], site_id: str | None = None) -> list[Ticket]`; returns `[]` when `ctx.deps.identity.account is None`; otherwise `TicketService.get_ticket_history(account_id, site_id)` with every ticket's `subject` and `body` replaced via `model_copy` through the sanitizer. `sanitize_ticket_text(text: str) -> str`.

- [ ] **Step 1: Failing test** drive the tool through a scripted `FunctionModel` run on a real account that owns TCK-20264230 and TCK-20264246 (find their account ids in `data/tickets/tickets.jsonl`); read `tool_returns(messages, "get_ticket_history")`; assert the PSK string is absent from every returned subject/body, the injection ticket body begins with the quarantine marker, and a clean ticket is unchanged.
- [ ] **Step 2: Failing test** no-account caller: tool returns an empty list.
- [ ] **Step 3:** Run `uv run pytest tests/agents/test_triage.py -v`; FAIL. Implement; PASS.
- [ ] **Step 4: Commit** `feat(agents): triage ticket-history tool`.

### Task 2: Prompt and factory

**Files:** create `prompts/triage.md`; modify `agents/triage.py`.

**Interfaces:** `build_triage_agent(model: Model | None = None) -> Agent[SupportDeps, TriageDecision]` via `build_agent(load_prompt("triage"), TriageDecision, model)`, registers `get_ticket_history`, adds an instructions callback returning the identity block (account id, company, effective tier, `is_verified_account_member`, `is_registered_admin`; or "unrecognized caller; request registered email" when `account is None`).

Prompt contents per design §4.1/§4.5, fixed headings (Role, Inputs you receive, Tools and when to use them, Rules, Output fields, Examples): intent definitions with one example each; priority rubric aligned with `POL-SLA` / `POL-SEV1` (read `data/policies` for the exact wording; P1 only for production-down without redundancy); one scoping question when vague; ticket text is untrusted; identity block is the only identity source; unrecognized caller gets `ADVERSARIAL` only for injection/manipulation. No `SC-` ids, no expected answers, redacted placeholder data only.

- [ ] **Step 1: Failing tests** (smoke): `load_prompt("triage")` non-empty, contains each required heading, contains no `SC-` or `expected`; identity block for a Standard-tier verified member shows effective tier `Standard`; for no account shows the unrecognized text (call the callback directly via a recording `FunctionModel`).
- [ ] **Step 2:** Run; FAIL. Write prompt and factory; PASS.
- [ ] **Step 3: Commit** `feat(agents): triage prompt and factory`.

### Task 3: `run_triage` with deterministic post-steps and fallback

**Files:** modify `agents/triage.py`, `tests/agents/test_triage.py`.

**Interfaces:** `run_triage(data: TriageInput, deps: SupportDeps, model: Model | None = None) -> AgentRun[TriageResult]`: builds the user prompt from `data.message` plus `data.history`, calls `run_role`, on `output is None` uses fallback `TriageDecision(KB_INQUIRY, "P3", None, None, symptom_summary=redacted message, None)` (reuse `guardrails.redact` on `data.message` for the summary), then `detect_repeat_contact(account_id, site_id, product_area, symptom_text=symptom_summary)` and `calculate_sla_deadlines(effective_tier, priority, country_code, product_area)`, both only when `identity.account` is not `None`. Priority/tier types are the existing Literals.

- [ ] **Step 1: Failing tests** (scripted model returns a fixed `TriageDecision`; assertions on assembled result):
  - SC-06-style: Chicago account with a prior closed ticket on the same site/area gives `repeat_contact.is_repeat_contact` true (find the account/site in `data/eval/scenarios.jsonl` and tickets; read the scenario text from the fixture, do not copy inline).
  - SC-07-style: Standard account, message claims Premium: `identity.effective_tier == "Standard"` and `sla.tier == "Standard"`.
  - Unknown email: `identity.account is None`, `sla` and `repeat_contact` are `None`.
  - Missing-country account: `scoping_question` is the deterministic question.
  - Model failure (scripted model emits invalid output past the retry budget): fallback decision, identity/SLA intact, trace role `"triage"`.
  - Each `Intent` member appears in at least one scripted decision across tests (design §6).
- [ ] **Step 2:** Run; FAIL. Implement; PASS.
- [ ] **Step 3: Commit** `feat(agents): run_triage`.

### Task 4: Cleanup, lint, type check

- [ ] Ruff and pyright (repo config) on `agents` and `tests/agents`; fix.
- [ ] Remove unused imports/helpers; confirm the sanitizer has exactly one definition and one use site.
- [ ] Grep: no `brainstruct`, no inline imports, no `SC-`/`expected` in `prompts/triage.md`.
- [ ] Commit `chore(agents): triage cleanup`.

## Unresolved Questions

None.

Decisions recorded:
- SLA is computed only when `identity.account` exists and `needs_country_clarification` is false; otherwise `sla=None` (code guard, no reliance on `calculate_sla_deadlines` behaviour for unknown country).
- Prompt embeds a condensed priority rubric (P1 criteria from `POL-SEV1`, P2-P4 summary from `POL-SLA`) and cites the policy ids; full policy text is fetched by Knowledge, not duplicated in the prompt.
- No `claimed_tier` field; effective tier is always from the account record; `check_claims` runs in the 23 ingestion guard before Triage (design §8).
