from typing import Any

import pytest

from orchestration import state as state_module
from orchestration.state import STATE_VERSION, OrchestratorState, StateVersionError
from storage import StateSnapshot


def _rename_counter(data: dict[str, Any]) -> dict[str, Any]:
    return {"clarification_turns": data["turns"]}


@pytest.fixture
def next_version(monkeypatch: pytest.MonkeyPatch) -> int:
    monkeypatch.setattr(state_module, "STATE_VERSION", STATE_VERSION + 1)
    monkeypatch.setattr(state_module, "MIGRATIONS", {STATE_VERSION: _rename_counter})
    return STATE_VERSION + 1


@pytest.mark.parametrize("data", [{}, {"clarification_turns": "many"}, {"notice_shown": 5}])
def test_empty_or_corrupt_data_rebuilds_empty(data: dict[str, Any]) -> None:
    snapshot = StateSnapshot(version=STATE_VERSION, data=data)
    assert OrchestratorState.from_snapshot(snapshot) == OrchestratorState()


def test_current_version_round_trips() -> None:
    state = OrchestratorState(clarification_turns=2, oncall_paged=True, active_ticket_id="TCK-1")
    assert OrchestratorState.from_snapshot(state.to_snapshot()) == state


def test_older_version_is_migrated(next_version: int) -> None:
    state = OrchestratorState.from_snapshot(StateSnapshot(version=STATE_VERSION, data={"turns": 2}))
    assert state.clarification_turns == 2
    assert state.to_snapshot().version == next_version


def test_failing_migration_rebuilds_empty(next_version: int) -> None:
    snapshot = StateSnapshot(version=STATE_VERSION, data={"x": 1})
    assert OrchestratorState.from_snapshot(snapshot) == OrchestratorState()


def test_v1_snapshot_loads_with_no_active_ticket() -> None:
    state = OrchestratorState.from_snapshot(StateSnapshot(version=1, data={"oncall_paged": True}))
    assert (state.oncall_paged, state.active_ticket_id) == (True, None)


def test_active_ticket_round_trips() -> None:
    state = OrchestratorState().with_active_ticket("TCK-1")
    assert OrchestratorState.from_snapshot(state.to_snapshot()).active_ticket_id == "TCK-1"


def test_newer_version_is_refused() -> None:
    with pytest.raises(StateVersionError):
        OrchestratorState.from_snapshot(StateSnapshot(version=STATE_VERSION + 1, data={"a": 1}))
