from pathlib import Path

from pydantic import BaseModel, ConfigDict

from core.config import REPO_ROOT

SCENARIOS_PATH: Path = REPO_ROOT / "data" / "eval" / "scenarios.jsonl"


class Scenario(BaseModel):
    """The slice of an eval scenario the chat sidebar needs; other keys are ignored."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    scenario_id: str
    customer_id: str
    requester_email: str
    persona: str
    opening_message: str


def load_scenarios(path: Path = SCENARIOS_PATH) -> tuple[Scenario, ...]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return tuple(Scenario.model_validate_json(line) for line in lines if line.strip())
