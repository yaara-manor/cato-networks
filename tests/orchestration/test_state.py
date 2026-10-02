from typing import Any

import pytest

from orchestration import state as state_module
from orchestration.state import STATE_VERSION, OrchestratorState, StateVersionError
from storage import StateSnapshot


def _rename_counter(data: dict[str, Any]) -> dict[str, Any]:
    return {"clarification_turns": data["turns"]}


@pytest.fixture
def v2(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(state_module, "STATE_VERSION", 2)
    monkeypatch.setattr(state_module, "MIGRATIONS", {1: _rename_counter})


@pytest.mark.parametrize("data", [{}, {"clarification_turns": "many"}, {"notice_shown": 5}])
def test_empty_or_corrupt_data_rebuilds_empty(data: dict[str, Any]) -> None:
    snapshot = StateSnapshot(version=STATE_VERSION, data=data)
    assert OrchestratorState.from_snapshot(snapshot) == OrchestratorState()


def test_current_version_round_trips() -> None:
    state = OrchestratorState(clarification_turns=2, oncall_paged=True)
    assert OrchestratorState.from_snapshot(state.to_snapshot()) == state


def test_older_version_is_migrated(v2: None) -> None:
    state = OrchestratorState.from_snapshot(StateSnapshot(version=1, data={"turns": 2}))
    assert state.clarification_turns == 2
    assert state.to_snapshot().version == 2


def test_failing_migration_rebuilds_empty(v2: None) -> None:
    assert OrchestratorState.from_snapshot(StateSnapshot(version=1, data={"x": 1})) == OrchestratorState()


def test_newer_version_is_refused() -> None:
    with pytest.raises(StateVersionError):
        OrchestratorState.from_snapshot(StateSnapshot(version=STATE_VERSION + 1, data={"a": 1}))
