import argparse
import uuid
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import psycopg
from pydantic import BaseModel, ConfigDict

from core.clock import SimulationClock
from core.config import REPO_ROOT, settings
from guardrails import MarkerKind, extract_markers
from orchestration import build_services, build_workflow, warm_models
from retrieval.models import KBSearchStatus

_SCENARIOS_PATH: Path = REPO_ROOT / "data/eval/scenarios.jsonl"
_REPORT_PATH: Path = REPO_ROOT / "docs/eval/scenario_report.md"
_TELEMETRY_TOOL_PREFIXES: tuple[str, ...] = ("get_", "list_")  # other expected tools are actions, not scored here


class Expected(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    must_cite: tuple[str, ...] = ()
    must_use_tools: tuple[str, ...] = ()


class Scenario(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    scenario_id: str
    requester_email: str
    opening_message: str
    expected: Expected


class ScenarioScore(BaseModel):
    model_config = ConfigDict(frozen=True)

    scenario_id: str
    conversation_id: uuid.UUID
    reply: str
    cited: tuple[str, ...]
    expected_cites: int
    missing_cites: tuple[str, ...]
    tools_used: tuple[str, ...]
    missing_tools: tuple[str, ...]
    kb_searches: int
    kb_refusals: int

    @property
    def passed(self) -> bool:
        return not self.missing_cites and not self.missing_tools


def load_scenarios(path: Path = _SCENARIOS_PATH) -> tuple[Scenario, ...]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return tuple(Scenario.model_validate_json(line) for line in lines if line.strip())


def cited_refs(reply: str) -> tuple[str, ...]:
    """Reply markers in the vocabulary of `must_cite`: KB slug, policy id, `telemetry:<tool without get_>`."""
    refs: list[str] = []
    for marker in extract_markers(reply):
        match marker.kind:
            case MarkerKind.KB:
                refs.append(marker.ref.split("#", 1)[0])
            case MarkerKind.POLICY:
                refs.append(marker.ref)
            case MarkerKind.TELEMETRY:
                refs.append(f"telemetry:{marker.ref.removeprefix('get_')}")
            case _:
                raise AssertionError(marker.kind)
    return tuple(dict.fromkeys(refs))


def missing_expected(expected: tuple[str, ...], actual: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(item for item in expected if item not in actual)


def score_scenario(
    scenario: Scenario, conversation_id: uuid.UUID, reply: str, tool_calls: list[tuple[str, str]]
) -> ScenarioScore:
    """`tool_calls` are (tool_name, status) rows of the conversation."""
    cited = cited_refs(reply)
    tools_used = tuple(dict.fromkeys(name for name, _ in tool_calls))
    expected_tools = tuple(t for t in scenario.expected.must_use_tools if t.startswith(_TELEMETRY_TOOL_PREFIXES))
    searches = [status for name, status in tool_calls if name == "search_knowledge_base"]
    return ScenarioScore(
        scenario_id=scenario.scenario_id,
        conversation_id=conversation_id,
        reply=reply,
        cited=cited,
        expected_cites=len(scenario.expected.must_cite),
        missing_cites=missing_expected(scenario.expected.must_cite, cited),
        tools_used=tools_used,
        missing_tools=missing_expected(expected_tools, tools_used),
        kb_searches=len(searches),
        kb_refusals=sum(status == KBSearchStatus.LOW_CONFIDENCE_REFUSAL for status in searches),
    )


def run_scenario(conn: psycopg.Connection[Any], clock: SimulationClock, scenario: Scenario) -> ScenarioScore:
    """Opening turn only, through the same workflow the chat uses."""
    services = build_services(conn, clock)
    identity = services.customers.authenticate_caller(scenario.requester_email)
    account_id = identity.account.account_id if identity.account else None
    conversation = services.store.create_conversation(account_id, identity.caller_email, identity.effective_tier, clock.now())
    result = build_workflow(conn, clock).run_turn(conversation.id, scenario.opening_message, uuid.uuid4())
    rows = conn.execute(
        "select tool_name, status from tool_calls where conversation_id = %s order by created_at, seq",
        (conversation.id,),
    ).fetchall()
    return score_scenario(scenario, conversation.id, result.reply, [(name, status) for name, status in rows])


def _hit_rate(scores: list[ScenarioScore]) -> float:
    expected = sum(sc.expected_cites for sc in scores)
    return 1.0 if expected == 0 else 1 - sum(len(sc.missing_cites) for sc in scores) / expected


def _counts(misses: Counter[str], runs: int) -> str:
    return ", ".join(f"{item} ({count}/{runs})" for item, count in misses.most_common()) or "-"


def to_markdown(runs: list[list[ScenarioScore]]) -> str:
    """`runs[i]` holds one score per scenario; the table reports pass rate and per-run misses."""
    by_scenario: dict[str, list[ScenarioScore]] = {}
    for run in runs:
        for score in run:
            by_scenario.setdefault(score.scenario_id, []).append(score)
    lines = [
        "# Scenario replay (opening turn)",
        "",
        f"- Date: {datetime.now(tz=UTC).date()}",
        f"- Runs per scenario: {len(runs)} (the model ignores temperature, so runs vary)",
        "- Pass: all `must_cite` markers present and all telemetry tools called",
        "",
        "| Scenario | Pass rate | Cite hit rate | Missing cites (runs) | Missing tools (runs) | KB searches / refused (avg) |",
        "|---|---|---|---|---|---|",
    ]
    for scenario_id, scores in by_scenario.items():
        n = len(scores)
        misses = Counter(c for sc in scores for c in sc.missing_cites)
        tool_misses = Counter(t for sc in scores for t in sc.missing_tools)
        lines.append(
            f"| {scenario_id} | {sum(sc.passed for sc in scores)}/{n} | "
            f"{_hit_rate(scores):.0%} | {_counts(misses, n)} | {_counts(tool_misses, n)} | "
            f"{sum(sc.kb_searches for sc in scores) / n:.1f} / {sum(sc.kb_refusals for sc in scores) / n:.1f} |"
        )
    return "\n".join(lines) + "\n"


def main(scenario_ids: list[str], runs: int) -> None:
    scenarios = [s for s in load_scenarios() if not scenario_ids or s.scenario_id in scenario_ids]
    clock = SimulationClock()
    warm_models()
    results: list[list[ScenarioScore]] = []
    with psycopg.connect(settings.database_url, autocommit=True) as conn:
        for run_index in range(runs):
            scores = [run_scenario(conn, clock, scenario) for scenario in scenarios]
            results.append(scores)
            print(f"run {run_index + 1}: {sum(s.passed for s in scores)}/{len(scores)} passed", flush=True)
    _REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    _REPORT_PATH.write_text(to_markdown(results), encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Replay scenario opening turns and score them.")
    parser.add_argument("scenario_ids", nargs="*")
    parser.add_argument("--runs", type=int, default=3)
    args = parser.parse_args()
    main(args.scenario_ids, args.runs)
