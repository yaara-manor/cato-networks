from datetime import datetime, timedelta, timezone

from core.clock import DEFAULT_ANCHOR, SimulationClock


def test_simulation_clock_ticking_frozen_and_window() -> None:
    fake_now = 100.0
    clock = SimulationClock(clock_fn=lambda: fake_now)
    assert clock.now() == DEFAULT_ANCHOR

    fake_now = 145.0
    assert clock.now() == datetime(2026, 8, 28, 17, 0, 45, tzinfo=timezone.utc)
    assert clock.elapsed(DEFAULT_ANCHOR) == timedelta(seconds=45)

    frozen = SimulationClock.frozen()
    assert frozen.now() == DEFAULT_ANCHOR
    assert frozen.is_within(DEFAULT_ANCHOR, 24)
    assert frozen.is_within(DEFAULT_ANCHOR - timedelta(hours=24), 24)
    assert not frozen.is_within(DEFAULT_ANCHOR - timedelta(hours=24, seconds=1), 24)
    assert not frozen.is_within(DEFAULT_ANCHOR + timedelta(seconds=1), 24)
    assert frozen.is_within(DEFAULT_ANCHOR - timedelta(days=100), float("inf"))
    assert not frozen.is_within(DEFAULT_ANCHOR + timedelta(seconds=1), float("inf"))
    assert frozen.is_within(DEFAULT_ANCHOR - timedelta(hours=1, minutes=30), 1.5)
    assert not frozen.is_within(DEFAULT_ANCHOR - timedelta(hours=1, minutes=31), 1.5)
