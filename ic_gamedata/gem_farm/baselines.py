"""Rolling gem-rate baselines for farm health."""

from __future__ import annotations

import statistics
from collections import defaultdict

from ic_gamedata.stats_rates import ROLLING_MIN_WINDOW_SEC

_GEM_SAMPLE_MAX_AGE_SEC = 1800.0
_MIN_GEM_SAMPLES = 3


class GemRateBaselineStore:
    """Track median gems/kw per party from stable rolling windows."""

    def __init__(self) -> None:
        self._samples: dict[int, list[tuple[float, float]]] = defaultdict(list)

    def clear_party(self, party_index: int) -> None:
        self._samples.pop(party_index, None)

    def observe(
        self,
        party_index: int,
        *,
        gems_per_quarter: float | None,
        rate_window_sec: float | None,
        now: float,
    ) -> None:
        if gems_per_quarter is None or gems_per_quarter <= 0:
            return
        if rate_window_sec is None or rate_window_sec < ROLLING_MIN_WINDOW_SEC:
            return
        samples = self._samples[party_index]
        samples.append((now, gems_per_quarter))
        cutoff = now - _GEM_SAMPLE_MAX_AGE_SEC
        self._samples[party_index] = [(t, v) for t, v in samples if t >= cutoff]

    def baseline_gems_per_quarter(self, party_index: int) -> float | None:
        samples = self._samples.get(party_index, [])
        if len(samples) < _MIN_GEM_SAMPLES:
            return None
        return float(statistics.median(v for _, v in samples))
