"""Tests for farm health rules and monitor."""

from __future__ import annotations

import unittest

from ic_gamedata.gem_farm.health_rules import (
    evaluate_farm_health,
    is_gem_farm_monitoring_context,
    median_run_duration_sec,
)
from ic_gamedata.gem_farm.models import FarmHealthThresholds, HealthEvaluationInput
from ic_gamedata.gem_farm.monitor import FarmHealthMonitor
from ic_gamedata.log_parser import PartySnapshot
from ic_gamedata.stats_models import GoalRunRecord, PartySessionStats


def _party(**kwargs) -> PartySnapshot:
    defaults = dict(
        party_index=1,
        adventure_id=31,
        current_area=200,
        gold=1.0,
        gold_gained=1.0,
        gems_this_reset=500,
        boss_kills_this_reset=40,
        monster_kills=200,
        boss_kills=40,
        briv_in_formation=True,
        modron_area_goal=300,
    )
    defaults.update(kwargs)
    return PartySnapshot(**defaults)


def _eval_input(**kwargs) -> HealthEvaluationInput:
    defaults = dict(
        party_index=1,
        is_active=True,
        modron_goal=300,
        briv_in_formation=True,
        current_area=200,
        gems_per_quarter=40.0,
        rate_window_sec=900.0,
        goal_run_history=(),
        area_unchanged_sec=None,
        gem_below_threshold_sec=None,
        now=1000.0,
    )
    defaults.update(kwargs)
    return HealthEvaluationInput(**defaults)


class FarmHealthContextTests(unittest.TestCase):
    def test_requires_active_modron_and_briv(self) -> None:
        self.assertTrue(
            is_gem_farm_monitoring_context(
                is_active=True,
                modron_goal=300,
                briv_in_formation=True,
            )
        )
        self.assertFalse(
            is_gem_farm_monitoring_context(
                is_active=False,
                modron_goal=300,
                briv_in_formation=True,
            )
        )
        self.assertFalse(
            is_gem_farm_monitoring_context(
                is_active=True,
                modron_goal=None,
                briv_in_formation=True,
            )
        )
        self.assertFalse(
            is_gem_farm_monitoring_context(
                is_active=True,
                modron_goal=300,
                briv_in_formation=False,
            )
        )


class FarmHealthRulesTests(unittest.TestCase):
    def test_ok_when_no_alerts(self) -> None:
        status = evaluate_farm_health(
            _eval_input(),
            thresholds=FarmHealthThresholds(),
            gem_baseline=45.0,
        )
        self.assertEqual(status.level, "ok")
        self.assertTrue(status.monitoring)

    def test_run_slowdown_triggers_warning(self) -> None:
        history = (
            GoalRunRecord(duration_sec=1200.0, area_goal=300, peak_area=300, recorded_at=700.0),
            GoalRunRecord(duration_sec=1180.0, area_goal=300, peak_area=299, recorded_at=600.0),
            GoalRunRecord(duration_sec=1160.0, area_goal=300, peak_area=298, recorded_at=500.0),
            GoalRunRecord(duration_sec=600.0, area_goal=300, peak_area=300, recorded_at=400.0),
            GoalRunRecord(duration_sec=580.0, area_goal=300, peak_area=299, recorded_at=300.0),
            GoalRunRecord(duration_sec=560.0, area_goal=300, peak_area=298, recorded_at=200.0),
            GoalRunRecord(duration_sec=550.0, area_goal=300, peak_area=297, recorded_at=100.0),
        )
        self.assertAlmostEqual(median_run_duration_sec(history), 600.0)
        status = evaluate_farm_health(
            _eval_input(goal_run_history=history),
            thresholds=FarmHealthThresholds(run_slowdown_pct=115),
            gem_baseline=45.0,
        )
        rule_ids = {alert.rule_id for alert in status.alerts}
        self.assertIn("run_slowdown", rule_ids)
        self.assertEqual(status.level, "warning")

    def test_gem_drop_after_sustained_low_rate(self) -> None:
        status = evaluate_farm_health(
            _eval_input(gems_per_quarter=30.0, gem_below_threshold_sec=650.0),
            thresholds=FarmHealthThresholds(gem_drop_pct=85, gem_drop_min_sec=600),
            gem_baseline=40.0,
        )
        rule_ids = {alert.rule_id for alert in status.alerts}
        self.assertIn("gem_drop", rule_ids)

    def test_area_stall_is_critical(self) -> None:
        status = evaluate_farm_health(
            _eval_input(area_unchanged_sec=200.0, current_area=250),
            thresholds=FarmHealthThresholds(area_stall_sec=180),
            gem_baseline=40.0,
        )
        rule_ids = {alert.rule_id for alert in status.alerts}
        self.assertIn("area_stall", rule_ids)
        self.assertEqual(status.level, "critical")

    def test_inactive_party_not_monitored(self) -> None:
        status = evaluate_farm_health(
            _eval_input(is_active=False, area_unchanged_sec=500.0),
            thresholds=FarmHealthThresholds(),
            gem_baseline=40.0,
        )
        self.assertFalse(status.monitoring)
        self.assertEqual(status.level, "ok")
        self.assertEqual(status.alerts, ())


class FarmHealthMonitorTests(unittest.TestCase):
    def test_inactive_party_clears_stall_tracking(self) -> None:
        monitor = FarmHealthMonitor()
        party = _party(current_area=250, is_active=True)
        ps = PartySessionStats(
            party_index=1,
            adventure_id=31,
            is_active=True,
            elapsed_sec=100.0,
            segment_elapsed_sec=100.0,
            current_area=250,
            gold=1.0,
            gems_this_reset=100,
            areas_gained=10.0,
            gold_gained=1.0,
            gems_gained=10.0,
            areas_per_quarter=5.0,
            gold_per_quarter=1.0,
            gems_per_quarter=40.0,
            session_areas_gained=10.0,
            session_gems_gained=10.0,
            rate_window_sec=900.0,
            modron_area_goal=300,
        )
        monitor.evaluate_active_party(
            party=party,
            ps=ps,
            is_active=True,
            memory_modron_goal=300,
            goal_run_history=(),
            now=1000.0,
        )
        inactive = _party(current_area=250, is_active=False)
        status = monitor.evaluate_active_party(
            party=inactive,
            ps=ps,
            is_active=False,
            memory_modron_goal=300,
            goal_run_history=(),
            now=1185.0,
        )
        self.assertFalse(status.monitoring)


if __name__ == "__main__":
    unittest.main()
