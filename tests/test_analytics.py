"""Tests for Modron goal-run analytics helpers."""

from __future__ import annotations

import unittest

from ic_gamedata.analytics import (
    build_goal_run_analytics,
    format_duration_minutes,
    goal_run_csv_rows,
    merge_goal_run_history,
    party_indexes_with_history,
)
from ic_gamedata.stats import GoalRunRecord


class GoalRunAnalyticsTests(unittest.TestCase):
    def test_build_summary_from_newest_first_records(self) -> None:
        records = (
            GoalRunRecord(duration_sec=600.0, area_goal=300, peak_area=301, recorded_at=200.0),
            GoalRunRecord(duration_sec=720.0, area_goal=300, peak_area=299, recorded_at=100.0),
            GoalRunRecord(duration_sec=540.0, area_goal=300, peak_area=300, recorded_at=50.0),
        )
        summary = build_goal_run_analytics(1, records)
        self.assertEqual(summary.run_count, 3)
        self.assertEqual(summary.best_sec, 540.0)
        self.assertEqual(summary.latest_sec, 600.0)
        self.assertAlmostEqual(summary.avg_sec, 620.0)
        self.assertEqual(summary.points[0].run_index, 1)
        self.assertEqual(summary.points[-1].run_index, 3)
        self.assertEqual(summary.points[-1].duration_sec, 600.0)

    def test_excludes_unreliable_runs_from_chart(self) -> None:
        records = (
            GoalRunRecord(
                duration_sec=1200.0,
                area_goal=300,
                peak_area=301,
                recorded_at=200.0,
                duration_unreliable=True,
            ),
            GoalRunRecord(duration_sec=600.0, area_goal=300, peak_area=301, recorded_at=100.0),
            GoalRunRecord(duration_sec=540.0, area_goal=300, peak_area=300, recorded_at=50.0),
        )
        summary = build_goal_run_analytics(1, records)
        self.assertEqual(summary.run_count, 2)
        self.assertEqual(summary.excluded_unreliable_count, 1)
        self.assertEqual(summary.latest_sec, 600.0)
        self.assertEqual(summary.best_sec, 540.0)
        self.assertAlmostEqual(summary.avg_sec, 570.0)

    def test_empty_history(self) -> None:
        summary = build_goal_run_analytics(2, ())
        self.assertEqual(summary.run_count, 0)
        self.assertIsNone(summary.best_sec)

    def test_format_duration_minutes(self) -> None:
        self.assertEqual(format_duration_minutes(754), "12:34")
        self.assertEqual(format_duration_minutes(45), "45s")

    def test_csv_rows_oldest_first(self) -> None:
        records = (
            GoalRunRecord(
                duration_sec=100.0,
                area_goal=200,
                peak_area=201,
                recorded_at=2.0,
                gems_earned=500,
            ),
            GoalRunRecord(duration_sec=200.0, area_goal=200, peak_area=202, recorded_at=1.0),
        )
        rows = goal_run_csv_rows(records)
        self.assertEqual(rows[0][0], "run")
        self.assertIn("gems_earned", rows[0])
        self.assertEqual(rows[1][0], "1")
        self.assertEqual(rows[2][0], "2")
        self.assertEqual(rows[2][1], "100.0")
        self.assertEqual(rows[2][5], "500")
        self.assertEqual(rows[1][5], "")

    def test_merge_deduplicates_live_history(self) -> None:
        record = GoalRunRecord(duration_sec=100.0, area_goal=200, peak_area=201, recorded_at=1.0)
        persisted = {1: [record]}
        merged = merge_goal_run_history(persisted, {1: (record,)})
        self.assertEqual(len(merged[1]), 1)

    def test_party_indexes_with_history(self) -> None:
        record = GoalRunRecord(duration_sec=100.0, area_goal=200, peak_area=201, recorded_at=1.0)
        self.assertEqual(party_indexes_with_history({2: [record], 3: []}), (2,))


if __name__ == "__main__":
    unittest.main()
