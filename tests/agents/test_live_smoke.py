import os

import pytest

from agents import TriageInput, run_triage
from tests.agents.conftest import MakeDeps


@pytest.mark.skipif(not os.environ.get("OPENAI_API_KEY"), reason="needs OPENAI_API_KEY")
def test_live_triage_returns_valid_result(make_deps: MakeDeps) -> None:
    deps = make_deps()
    run = run_triage(TriageInput(message="How do I add a new site?", identity=deps.identity), deps)
    assert run.output.decision.symptom_summary
