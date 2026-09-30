from datetime import datetime, timedelta, timezone

DEFAULT_SIMULATION_TIME: datetime = datetime(2026, 8, 28, 17, 0, 0, tzinfo=timezone.utc)


def _ensure_utc(ts: datetime) -> datetime:
    if ts.tzinfo is None or ts.tzinfo.utcoffset(ts) is None:
        raise ValueError("Timestamp must be timezone-aware")
    return ts.astimezone(timezone.utc)


class SimulationClock:
    """Frozen simulation clock anchored to 2026-08-28T17:00:00Z by default."""

    def __init__(self, anchor: datetime = DEFAULT_SIMULATION_TIME) -> None:
        self._anchor: datetime = _ensure_utc(anchor)

    def now(self) -> datetime:
        """Return the frozen simulation instant in UTC."""
        return self._anchor

    def elapsed(self, since: datetime) -> timedelta:
        """Return the elapsed time from `since` until the simulation anchor."""
        return self._anchor - _ensure_utc(since)

    def is_within(self, ts: datetime, window_hours: int) -> bool:
        """Return True if `ts` falls within `[now - window_hours, now]`."""
        delta = self.elapsed(ts)
        return timedelta(0) <= delta <= timedelta(hours=window_hours)
