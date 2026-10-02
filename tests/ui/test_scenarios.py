from ui.scenarios import load_scenarios


def test_loads_all_eval_scenarios() -> None:
    scenarios = load_scenarios()
    assert len(scenarios) == 12
    assert all(s.requester_email and s.opening_message for s in scenarios)
