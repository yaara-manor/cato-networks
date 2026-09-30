import json
from typing import Any

import pytest

from core.config import settings


def _read_jsonl(relative_path: str) -> list[dict[str, Any]]:
    with (settings.repo_root / "data" / relative_path).open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


@pytest.fixture(scope="session")
def corpus() -> dict[str, str]:
    questions = _read_jsonl("eval/questions.jsonl")
    tickets = _read_jsonl("tickets/tickets.jsonl")
    scenarios = _read_jsonl("eval/scenarios.jsonl")
    assert (len(questions), len(tickets), len(scenarios)) == (35, 54, 12)
    texts = {row["question_id"]: row["question"] for row in questions}
    for ticket in tickets:
        texts[f"{ticket['ticket_id']}.subject"] = ticket["subject"]
        texts[f"{ticket['ticket_id']}.body"] = ticket["body"]
    for scenario in scenarios:
        texts[f"{scenario['scenario_id']}.opening"] = scenario["opening_message"]
        for i, followup in enumerate(scenario["simulated_customer_followups"]):
            texts[f"{scenario['scenario_id']}.followup{i}"] = followup["customer"]
    return texts
