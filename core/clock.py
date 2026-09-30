import math
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

DEFAULT_ANCHOR: datetime = datetime(2026, 8, 28, 17, 0, 0, tzinfo=UTC)


class SimulationClock:
    def __init__(
        self,
        anchor: datetime = DEFAULT_ANCHOR,
        ticking: bool = True,
        clock_fn: Callable[[], float] = time.monotonic,
    ) -> None:
        self.anchor: datetime = anchor
        self.ticking: bool = ticking
        self._clock_fn: Callable[[], float] = clock_fn
        self._started_at_monotonic: float = clock_fn()

    @classmethod
    def frozen(cls, anchor: datetime = DEFAULT_ANCHOR) -> "SimulationClock":
        return cls(anchor=anchor, ticking=False)

    def now(self) -> datetime:
        if not self.ticking:
            return self.anchor
        return self.anchor + timedelta(seconds=self._clock_fn() - self._started_at_monotonic)

    def elapsed(self, since: datetime) -> timedelta:
        return self.now() - since

    def is_within(self, ts: datetime, window_hours: float) -> bool:
        el = self.elapsed(ts)
        if el < timedelta(0):
            return False
        if math.isinf(window_hours):
            return True
        return el <= timedelta(hours=window_hours)
