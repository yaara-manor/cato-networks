import uuid

from eval.run_scenarios import ScenarioScore, parse_conversation_ids, to_markdown
from eval.scenario_checks import RuleResult
from eval.scenario_scorer import Action


def _score(**overrides: object) -> ScenarioScore:
    fields: dict[str, object] = {
        "scenario_id": "SC-X",
        "conversation_id": uuid.uuid4(),
        "replies": ("ok",),
        "expected_cites": 2,
        "missing_cites": (),
        "missing_tools": (),
        "expected_action": "auto_resolve",
        "observed_action": Action.AUTO_RESOLVE,
        "ungrounded": (),
        "guardrail_violations": (),
        "rules": (RuleResult(bullet="b1", passed=True),),
        "unscored": ("needs a human",),
        "kb_searches": 3,
        "kb_refusals": 1,
    }
    return ScenarioScore(**(fields | overrides))


def test_run_passes_only_when_every_dimension_passes() -> None:
    assert _score().passed
    assert not _score(missing_cites=("a",)).passed
    assert not _score(observed_action=Action.NEEDS_INFO).passed
    assert not _score(ungrounded=("9999",)).passed
    assert not _score(guardrail_violations=("leak",)).passed
    assert not _score(rules=(RuleResult(bullet="b1", passed=False),)).passed


def test_report_counts_runs_per_dimension_and_lists_misses_and_unscored_bullets() -> None:
    runs = [[_score()], [_score(missing_cites=("a",), observed_action=Action.NEEDS_INFO)]]
    report = to_markdown(runs)
    assert "| SC-X | 1/2 | 1/2 (75% of required) | 2/2 | 1/2: auto_resolve x1, needs_info x1 (expected" in report
    assert "missing citations: a (1/2)" in report
    assert "### SC-X\n  - needs a human" in report
    assert all(str(sc.conversation_id) in report for run in runs for sc in run)


def test_conversation_ids_round_trip_through_the_report() -> None:
    runs = [[_score(scenario_id="SC-A"), _score(scenario_id="SC-B")], [_score(scenario_id="SC-A"), _score(scenario_id="SC-B")]]
    ids = parse_conversation_ids(to_markdown(runs))
    assert ids == {"SC-A": [runs[0][0].conversation_id, runs[1][0].conversation_id], "SC-B": [runs[0][1].conversation_id, runs[1][1].conversation_id]}


def test_report_notes_how_it_was_produced() -> None:
    assert "- Scored again from run X." in to_markdown([[_score()]], note="Scored again from run X.")
