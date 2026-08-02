"""Tests for adaptive rolling-window rate calculation (per kwartier)."""

from __future__ import annotations

import time
import unittest

from ic_gamedata.stats import (
    RATE_PERIOD_SEC,
    ROLLING_MAX_WINDOW_SEC,
    ROLLING_MIN_WINDOW_SEC,
    _MetricSample,
    rolling_rate,
    rolling_window_span,
)


class RollingRateTests(unittest.TestCase):
    def test_warmup_returns_none_under_min_window(self) -> None:
        start = time.time() - 120
        samples = [
            _MetricSample(timestamp=start, gems=0, area=1, gold=0.0),
            _MetricSample(timestamp=start + 120, gems=5000, area=10, gold=0.0),
        ]
        self.assertIsNone(rolling_rate(samples, field_name="gems"))
        self.assertIsNone(rolling_window_span(samples))

    def test_stable_gem_rate_at_min_window(self) -> None:
        start = time.time() - ROLLING_MIN_WINDOW_SEC
        samples = [
            _MetricSample(timestamp=start, gems=0, area=1, gold=0.0),
            _MetricSample(timestamp=start + ROLLING_MIN_WINDOW_SEC / 2, gems=5000, area=50, gold=0.0),
            _MetricSample(timestamp=start + ROLLING_MIN_WINDOW_SEC, gems=10000, area=100, gold=0.0),
        ]
        rate = rolling_rate(samples, field_name="gems")
        span = rolling_window_span(samples)
        self.assertIsNotNone(rate)
        self.assertIsNotNone(span)
        assert rate is not None
        assert span is not None
        self.assertAlmostEqual(span, ROLLING_MIN_WINDOW_SEC, delta=1.0)
        expected = 10000.0 * RATE_PERIOD_SEC / ROLLING_MIN_WINDOW_SEC
        self.assertAlmostEqual(rate, expected, delta=500.0)

    def test_window_expands_with_available_history(self) -> None:
        start = time.time() - 600
        samples = [
            _MetricSample(timestamp=start, gems=0, area=1, gold=0.0),
            _MetricSample(timestamp=start + 300, gems=1500, area=50, gold=0.0),
            _MetricSample(timestamp=start + 600, gems=3000, area=100, gold=0.0),
        ]
        span = rolling_window_span(samples)
        rate = rolling_rate(samples, field_name="gems")
        self.assertIsNotNone(span)
        assert span is not None
        self.assertAlmostEqual(span, 600.0, delta=1.0)
        self.assertIsNotNone(rate)
        assert rate is not None
        self.assertAlmostEqual(rate, 3000.0 * RATE_PERIOD_SEC / 600.0, delta=50.0)

    def test_window_caps_at_quarter_hour(self) -> None:
        start = time.time() - 1800
        samples = [
            _MetricSample(timestamp=start, gems=0, area=1, gold=0.0),
            _MetricSample(timestamp=start + 900, gems=5000, area=50, gold=0.0),
            _MetricSample(timestamp=start + 1800, gems=15000, area=100, gold=0.0),
        ]
        span = rolling_window_span(samples)
        rate = rolling_rate(samples, field_name="gems")
        self.assertIsNotNone(span)
        assert span is not None
        self.assertAlmostEqual(span, ROLLING_MAX_WINDOW_SEC, delta=1.0)
        self.assertLessEqual(span, ROLLING_MAX_WINDOW_SEC)
        self.assertGreaterEqual(span, ROLLING_MIN_WINDOW_SEC)
        self.assertIsNotNone(rate)
        assert rate is not None
        # Last 15 min: 5000 → 15000 over 900s → 10000 per kwartier
        self.assertAlmostEqual(rate, 10000.0, delta=50.0)

    def test_cumulative_samples_span_full_session_after_reset(self) -> None:
        start = time.time() - 900
        samples = [
            _MetricSample(timestamp=start, gems=0, area=0, gold=0.0),
            _MetricSample(timestamp=start + 600, gems=5000, area=100, gold=0.0),
            _MetricSample(timestamp=start + 601, gems=5000, area=100, gold=0.0),
            _MetricSample(timestamp=start + 900, gems=8000, area=150, gold=0.0),
        ]
        span = rolling_window_span(samples)
        rate = rolling_rate(samples, field_name="gems")
        self.assertIsNotNone(span)
        self.assertIsNotNone(rate)
        assert span is not None
        assert rate is not None
        self.assertAlmostEqual(span, 900.0, delta=1.0)
        self.assertAlmostEqual(rate, 8000 * RATE_PERIOD_SEC / 900.0, delta=50.0)


if __name__ == "__main__":
    unittest.main()
