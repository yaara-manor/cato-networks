import argparse
import json
import re
import uuid
from collections import Counter
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import psycopg
from pydantic import BaseModel, ConfigDict

from core.clock import SimulationClock
from core.config import REPO_ROOT, settings
from eval.scenario_checks import RuleResult, evaluate_rules, unscored_bullets
from eval.scenario_scorer import (
    Action,
    ActionFact,
    ApprovalFact,
    ConversationFacts,
    Scenario,
    ToolFact,
    cited_refs,
    guardrail_violations,
    load_scenarios,
    missing_expected,
    observed_action,
    tools_missing,
    ungrounded_tokens,
)
from orchestration import TurnResult, build_services, build_workflow, warm_models
from retrieval.models import KBSearchStatus
from retrieval.service import RetrievalService
from storage import MessageSender, StateStore

_REPORT_PATH: Path = REPO_ROOT / "docs/eval/scenario_report.md"
_RETRIEVAL_TOOLS = ("search_knowledge_base", "expand_article_sections")
_APPROVED = ("APPROVED", "EDITED")


class ScenarioScore(BaseModel):
    model_config = ConfigDict(frozen=True)

    scenario_id: str
    conversation_id: uuid.UUID
    replies: tuple[str, ...]
    expected_cites: int
    missing_cites: tuple[str, ...]
    missing_tools: tuple[str, ...]
    expected_action: str
    observed_action: Action
    ungrounded: tuple[str, ...]
    guardrail_violations: tuple[str, ...]
    rules: tuple[RuleResult, ...]
    unscored: tuple[str, ...]
    kb_searches: int
    kb_refusals: int

    @property
    def action_ok(self) -> bool:
        return self.observed_action.value == self.expected_action

    @property
    def rules_ok(self) -> bool:
        return all(r.passed for r in self.rules)

    @property
    def passed(self) -> bool:
        return (
            not self.missing_cites
            and not self.missing_tools
            and self.action_ok
            and not self.ungrounded
            and not self.guardrail_violations
            and self.rules_ok
        )


def _stored_text(snapshot_messages: Sequence[Any], traces: Sequence[Any], calls: Sequence[Any]) -> str:
    parts = [m.content for m in snapshot_messages]
    parts += [json.dumps([t.input, t.output], default=str) for t in traces]
    parts += [json.dumps([c.arguments, c.result], default=str) for c in calls]
    return "\n".join(parts)


def _kb_texts(calls: Sequence[Any]) -> dict[str, str]:
    texts: dict[str, str] = {}
    for call in calls:
        if call.tool_name not in _RETRIEVAL_TOOLS:
            continue
        for p in call.result.get("passages", []):
            key = f"{p['slug']}#{p['heading_anchor']}"
            texts[key] = f"{texts[key]} {p['body']}" if key in texts else p["body"]
    return texts


def _asked_scoping_question(traces: Sequence[Any]) -> bool:
    for trace in traces:
        if trace.agent_role.value != "TRIAGE" or not trace.output:
            continue
        if trace.output.get("decision", {}).get("scoping_question") or trace.output.get("identity", {}).get("scoping_question"):
            return True
    return False


def load_facts(
    conn: psycopg.Connection[Any], conversation_id: uuid.UUID, scenario: Scenario, replies: Sequence[str]
) -> ConversationFacts:
    """Reads back what the conversation left in storage."""
    store = StateStore(conn)
    snapshot = store.rehydrate(conversation_id)
    assert snapshot is not None
    approvals = store.list_approvals(conversation_id)
    approved_ids = {a.id for a in approvals if a.status.value in _APPROVED}
    calls = store.list_tool_calls(conversation_id)
    traces = store.list_traces(conversation_id)
    results = [m.result for m in snapshot.messages if m.sender is not MessageSender.CUSTOMER and m.result]
    return ConversationFacts(
        customer_messages=scenario.customer_messages,
        replies=tuple(replies),
        tool_calls=tuple(
            ToolFact(name=c.tool_name, status=c.status, result_text=json.dumps(c.result, default=str)) for c in calls
        ),
        approvals=tuple(ApprovalFact(action_type=a.action_type.value, status=a.status.value) for a in approvals),
        actions=tuple(
            ActionFact(kind=a.kind, executed=a.status.value == "DONE", approved=a.approval_id in approved_ids)
            for a in store.list_simulated_actions(conversation_id)
        ),
        guard_history=snapshot.conversation.guard_history,
        escalation_offered=any(TurnResult.model_validate(r).escalation_offered for r in results),
        escalated_at_end=bool(results) and TurnResult.model_validate(results[-1]).escalation_offered,
        scoping_question_asked=_asked_scoping_question(traces),
        context_text=" ".join(json.dumps(t.output, default=str) for t in traces if t.agent_role.value == "TRIAGE"),
        stored_text=_stored_text(snapshot.messages, traces, calls),
        kb_texts=_kb_texts(calls),
        policy_texts={p.policy_id: p.body for p in RetrievalService(conn).list_policies()},
    )


def score_scenario(scenario: Scenario, conversation_id: uuid.UUID, facts: ConversationFacts) -> ScenarioScore:
    searches = [c.status for c in facts.tool_calls if c.name == "search_knowledge_base"]
    return ScenarioScore(
        scenario_id=scenario.scenario_id,
        conversation_id=conversation_id,
        replies=facts.replies,
        expected_cites=len(scenario.expected.must_cite),
        missing_cites=missing_expected(scenario.expected.must_cite, cited_refs(facts.replies)),
        missing_tools=tools_missing(scenario.expected.must_use_tools, facts),
        expected_action=scenario.expected.action,
        observed_action=observed_action(facts),
        ungrounded=tuple(u.token for u in ungrounded_tokens(facts)),
        guardrail_violations=guardrail_violations(facts),
        rules=evaluate_rules(scenario, facts),
        unscored=unscored_bullets(scenario),
        kb_searches=len(searches),
        kb_refusals=sum(status == KBSearchStatus.LOW_CONFIDENCE_REFUSAL for status in searches),
    )


def run_scenario(conn: psycopg.Connection[Any], clock: SimulationClock, scenario: Scenario) -> ScenarioScore:
    """The opening message and the scripted follow-ups, through the same workflow the chat uses."""
    services = build_services(conn, clock)
    identity = services.customers.authenticate_caller(scenario.requester_email)
    account_id = identity.account.account_id if identity.account else None
    conversation = services.store.create_conversation(
        account_id, identity.caller_email, identity.effective_tier, clock.now()
    )
    workflow = build_workflow(conn, clock)
    replies = [workflow.run_turn(conversation.id, m, uuid.uuid4()).reply for m in scenario.customer_messages]
    return score_scenario(scenario, conversation.id, load_facts(conn, conversation.id, scenario, replies))


def _hit_rate(scores: list[ScenarioScore]) -> float:
    expected = sum(sc.expected_cites for sc in scores)
    return 1.0 if expected == 0 else 1 - sum(len(sc.missing_cites) for sc in scores) / expected


def _counts(misses: Counter[str], runs: int) -> str:
    return ", ".join(f"{item} ({count}/{runs})" for item, count in misses.most_common()) or "-"


def _ratio(scores: list[ScenarioScore], ok: Callable[[ScenarioScore], bool]) -> str:
    return f"{sum(1 for sc in scores if ok(sc))}/{len(scores)}"


def _table_row(scenario_id: str, scores: list[ScenarioScore]) -> str:
    observed = Counter(sc.observed_action.value for sc in scores)
    observed_text = ", ".join(f"{action} x{count}" for action, count in observed.most_common())
    return (
        f"| {scenario_id} | {_ratio(scores, lambda sc: sc.passed)} "
        f"| {_ratio(scores, lambda sc: not sc.missing_cites)} ({_hit_rate(scores):.0%} of required) "
        f"| {_ratio(scores, lambda sc: not sc.missing_tools)} "
        f"| {_ratio(scores, lambda sc: sc.action_ok)}: {observed_text} (expected {scores[0].expected_action}) "
        f"| {_ratio(scores, lambda sc: not sc.ungrounded)} "
        f"| {_ratio(scores, lambda sc: not sc.guardrail_violations)} "
        f"| {_ratio(scores, lambda sc: sc.rules_ok)} (of {len(scores[0].rules)} rules) |"
    )


def _misses(scores: list[ScenarioScore]) -> list[str]:
    n = len(scores)
    ungrounded = list(dict.fromkeys(t for sc in scores for t in sc.ungrounded))
    items = [
        ("missing citations", _counts(Counter(c for sc in scores for c in sc.missing_cites), n)),
        ("missing tools", _counts(Counter(t for sc in scores for t in sc.missing_tools), n)),
        ("failed rules", _counts(Counter(r.bullet for sc in scores for r in sc.rules if not r.passed), n)),
        ("guardrail findings", _counts(Counter(g for sc in scores for g in sc.guardrail_violations), n)),
        ("ungrounded tokens", ", ".join(f"`{t}`" for t in ungrounded) or "-"),
    ]
    return [f"  - {label}: {text}" for label, text in items if text != "-"]


_CONVERSATION_LINE = re.compile(r"^- (SC-[\w-]+): (.+)$", re.MULTILINE)
_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


def parse_conversation_ids(report: str) -> dict[str, list[uuid.UUID]]:
    """The conversation ids a report lists per scenario, in run order."""
    section = report.split("## Conversations", 1)[1].split("\n## ", 1)[0]
    return {m[1]: [uuid.UUID(u) for u in _UUID.findall(m[2])] for m in _CONVERSATION_LINE.finditer(section)}


def rescore(conn: psycopg.Connection[Any], report: str) -> list[list[ScenarioScore]]:
    """Scores the conversations of an earlier run again from storage, without calling any model."""
    scenarios = {s.scenario_id: s for s in load_scenarios()}
    store = StateStore(conn)
    ids = parse_conversation_ids(report)
    runs: list[list[ScenarioScore]] = [[] for _ in range(max(len(v) for v in ids.values()))]
    for scenario_id, conversation_ids in ids.items():
        for run_index, conversation_id in enumerate(conversation_ids):
            snapshot = store.rehydrate(conversation_id)
            assert snapshot is not None, conversation_id
            replies = [m.content for m in snapshot.messages if m.sender is MessageSender.AGENT]
            facts = load_facts(conn, conversation_id, scenarios[scenario_id], replies)
            runs[run_index].append(score_scenario(scenarios[scenario_id], conversation_id, facts))
    return runs


def to_markdown(runs: list[list[ScenarioScore]], note: str = "") -> str:
    """`runs[i]` holds one score per scenario; each dimension shows how many runs passed it."""
    by_scenario: dict[str, list[ScenarioScore]] = {}
    for run in runs:
        for score in run:
            by_scenario.setdefault(score.scenario_id, []).append(score)
    lines = [
        "# Scenario replay (opening message and scripted follow-ups)",
        "",
        f"- Date: {datetime.now(tz=UTC).date()}",
        f"- Runs per scenario: {len(runs)} (the model ignores temperature, so runs vary)",
        "- Follow-ups are sent in order; their `if_agent` conditions are not evaluated",
        "- A run passes when every dimension passes. Each cell counts the runs that passed it.",
        *([f"- {note}"] if note else []),
        "",
        "| Scenario | Pass | Citations | Tools | Action | Grounded | Guardrails | Rules |",
        "|---|---|---|---|---|---|---|---|",
        *(_table_row(scenario_id, scores) for scenario_id, scores in by_scenario.items()),
        "",
        "## Misses",
        "",
    ]
    for scenario_id, scores in by_scenario.items():
        if misses := _misses(scores):
            lines += [f"### {scenario_id}", *misses, ""]
    lines += ["## Conversations (replay each trace in the reviewer app with its id)", ""]
    for scenario_id, scores in by_scenario.items():
        lines.append(f"- {scenario_id}: " + ", ".join(f"`{sc.conversation_id}`" for sc in scores))
    lines += ["", "## Not scored (needs human judgment)", ""]
    for scenario_id, scores in by_scenario.items():
        if scores[0].unscored:
            lines += [f"### {scenario_id}", *(f"  - {bullet}" for bullet in scores[0].unscored), ""]
    return "\n".join(lines) + "\n"


def main_rescore(source: Path, report: Path) -> None:
    with psycopg.connect(settings.database_url, autocommit=True) as conn:
        results = rescore(conn, source.read_text(encoding="utf-8"))
    note = f"Scored again, without calling a model, from the conversations recorded in {source.name} (same ids below)."
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(to_markdown(results, note), encoding="utf-8")


def main(scenario_ids: list[str], runs: int, report: Path) -> None:
    scenarios = [s for s in load_scenarios() if not scenario_ids or s.scenario_id in scenario_ids]
    clock = SimulationClock()
    warm_models()
    results: list[list[ScenarioScore]] = []
    with psycopg.connect(settings.database_url, autocommit=True) as conn:
        for run_index in range(runs):
            scores = [run_scenario(conn, clock, scenario) for scenario in scenarios]
            results.append(scores)
            print(f"run {run_index + 1}: {sum(s.passed for s in scores)}/{len(scores)} passed", flush=True)
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(to_markdown(results), encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Replay scenarios and score them.")
    parser.add_argument("scenario_ids", nargs="*")
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--report", type=Path, default=_REPORT_PATH, help="where to write the markdown report")
    parser.add_argument("--rescore", type=Path, help="score the conversations listed in this earlier report again")
    args = parser.parse_args()
    if args.rescore:
        main_rescore(args.rescore, args.report)
    else:
        main(args.scenario_ids, args.runs, args.report)
