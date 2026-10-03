from datetime import UTC, datetime, timedelta

import pytest

from ui.reviewer_panels import SlaCountdown, SlaState

START = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)
DUE = START + timedelta(hours=4)  # 25% of the window = 1h


@pytest.mark.parametrize(
    ("elapsed", "paused", "expected"),
    [
        (timedelta(hours=2), False, SlaState.OK),
        (timedelta(hours=2, minutes=59), False, SlaState.OK),
        (timedelta(hours=3), False, SlaState.AT_RISK),
        (timedelta(hours=4), False, SlaState.AT_RISK),
        (timedelta(hours=4, seconds=1), False, SlaState.BREACHED),
        (timedelta(hours=9), True, SlaState.PAUSED),
    ],
)
def test_sla_state_thresholds(elapsed: timedelta, paused: bool, expected: SlaState) -> None:
    countdown = SlaCountdown.from_deadline("Resolution", START, DUE, START + elapsed, paused)
    assert countdown.state is expected
