"""Tests for Modron/adventure reset handling in stats."""

from __future__ import annotations

import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from ic_gamedata.dashboard_tiles import format_goal_run_history
from ic_gamedata.log_parser import GameSnapshot, PartySnapshot
from ic_gamedata.stats import StatsTracker, detect_adventure_reset, rolling_window_span


class _IsolatedGoalRunHistoryTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._history_dir = tempfile.TemporaryDirectory()
        self._history_path = Path(self._history_dir.name) / "goal_run_history.json"
        patcher = patch(
            "ic_gamedata.goal_run_history_store.GOAL_RUN_HISTORY_PATH",
            self._history_path,
        )
        self.addCleanup(patcher.stop)
        patcher.start()

    def tearDown(self) -> None:
        self._history_dir.cleanup()


def _party(
    index: int,
    area: int,
    gems: int,
    *,
    seconds_since_reset: int | None = None,
    adventure_area_goal: int | None = None,
    modron_area_goal: int | None = None,
) -> PartySnapshot:
    goal = modron_area_goal if modron_area_goal is not None else adventure_area_goal
    return PartySnapshot(
        party_index=index,
        adventure_id=31,
        current_area=area,
        gold=100.0,
        gold_gained=100.0,
        gems_this_reset=gems,
        boss_kills_this_reset=1,
        monster_kills=area,
        boss_kills=1,
        seconds_since_reset=seconds_since_reset,
        adventure_area_goal=adventure_area_goal,
        modron_area_goal=goal,
        is_active=index == 0,
    )


def _snap(*parties: PartySnapshot) -> GameSnapshot:
    primary = parties[0]
    return GameSnapshot(
        api_call="getuserdetails",
        active_party_index=0,
        parties=parties,
        current_area=primary.current_area,
        gold=primary.gold,
        gold_gained=primary.gold_gained,
        gems_this_reset=primary.gems_this_reset,
        monster_kills=primary.monster_kills,
        boss_kills=primary.boss_kills,
    )


class ResetDetectionTests(unittest.TestCase):
    def test_area_drop_detects_reset(self) -> None:
        prev = _party(0, 300, 50)
        cur = _party(0, 1, 0)
        self.assertTrue(detect_adventure_reset(prev, cur))

    def test_area_drop_detects_thellora_landing_zone(self) -> None:
        prev = _party(1, 226, 50, modron_area_goal=225)
        cur = _party(1, 45, 0, modron_area_goal=225)
        self.assertTrue(detect_adventure_reset(prev, cur))

    def test_small_area_jitter_is_not_reset(self) -> None:
        prev = _party(0, 300, 50)
        cur = _party(0, 297, 50)
        self.assertFalse(detect_adventure_reset(prev, cur))

    def test_gem_drop_alone_is_not_reset(self) -> None:
        prev = _party(0, 300, 5000)
        cur = _party(0, 305, 100)
        self.assertFalse(detect_adventure_reset(prev, cur))

    def test_estimated_gems_do_not_inflate_reset_count(self) -> None:

        def snap(area: int, gems: int) -> GameSnapshot:
            return _snap(_party(0, area, gems, seconds_since_reset=5000 + area))

        tracker = StatsTracker()
        tracker.add_snapshot(snap(500, 2000))
        tracker.add_snapshot(snap(510, 2000))  # gems stall, area climbs → estimate
        tracker.add_snapshot(snap(520, 2000))
        tracker.add_snapshot(snap(530, 2000))

        stats = tracker.compute()
        self.assertIsNotNone(stats)
        assert stats is not None
        self.assertEqual(stats.parties[0].reset_count, 0)
        self.assertGreater(stats.parties[0].gems_this_reset or 0, 2000)

    def test_stats_continue_after_modron_reset(self) -> None:
        tracker = StatsTracker()
        tracker.add_snapshot(_snap(_party(0, 200, 100, seconds_since_reset=5000)))
        time.sleep(0.01)
        tracker.add_snapshot(_snap(_party(0, 210, 105, seconds_since_reset=5100)))
        tracker.add_snapshot(_snap(_party(0, 1, 0, seconds_since_reset=60)))
        time.sleep(0.01)
        tracker.add_snapshot(_snap(_party(0, 15, 8, seconds_since_reset=200)))

        stats = tracker.compute()
        self.assertIsNotNone(stats)
        assert stats is not None
        self.assertEqual(stats.parties[0].reset_count, 1)
        self.assertEqual(stats.parties[0].areas_gained, 14.0)
        self.assertAlmostEqual(stats.parties[0].session_areas_gained or 0, 24.0)
        self.assertAlmostEqual(stats.areas_gained or 0, 24.0)
        self.assertIsNotNone(stats.parties[0].areas_per_quarter)

    def test_rolling_window_persists_after_modron_reset(self) -> None:
        tracker = StatsTracker()
        base = 1_700_000_000.0
        clock = {"t": base}

        def fake_time() -> float:
            return clock["t"]

        with patch("ic_gamedata.stats.time.time", fake_time):
            tracker.add_snapshot(_snap(_party(0, 100, 0, seconds_since_reset=3600)))
            clock["t"] = base + 600
            tracker.add_snapshot(_snap(_party(0, 200, 6000, seconds_since_reset=4200)))
            clock["t"] = base + 601
            tracker.add_snapshot(_snap(_party(0, 1, 0, seconds_since_reset=60)))
            clock["t"] = base + 900
            tracker.add_snapshot(_snap(_party(0, 50, 3000, seconds_since_reset=300)))

            stats = tracker.compute()

        self.assertIsNotNone(stats)
        assert stats is not None
        ps = stats.parties[0]
        self.assertEqual(ps.reset_count, 1)
        self.assertAlmostEqual(ps.session_gems_gained or 0, 9000.0)
        self.assertIsNotNone(ps.rate_window_sec)
        assert ps.rate_window_sec is not None
        self.assertGreaterEqual(ps.rate_window_sec, 180.0)
        self.assertIsNotNone(ps.gems_per_quarter)
        samples = tracker._party_state[0].samples
        self.assertGreaterEqual(len(samples), 4)
        self.assertIsNotNone(rolling_window_span(samples))


class GoalRunHistoryTests(_IsolatedGoalRunHistoryTestCase):
    def test_records_completed_goal_run_on_reset(self) -> None:
        tracker = StatsTracker()
        tracker.add_snapshot(
            _snap(_party(0, 300, 100, seconds_since_reset=3600, adventure_area_goal=300))
        )
        tracker.add_snapshot(_snap(_party(0, 1, 0, seconds_since_reset=60, adventure_area_goal=300)))

        history = tracker.goal_run_history(0)
        self.assertEqual(len(history), 1)
        self.assertAlmostEqual(history[0].duration_sec, 3600.0)
        self.assertEqual(history[0].area_goal, 300)
        self.assertEqual(history[0].peak_area, 300)

        stats = tracker.compute()
        self.assertIsNotNone(stats)
        assert stats is not None
        self.assertEqual(len(stats.parties[0].goal_run_history), 1)

    def test_skips_reset_when_goal_not_reached(self) -> None:
        tracker = StatsTracker()
        tracker.add_snapshot(
            _snap(_party(0, 250, 100, seconds_since_reset=3600, adventure_area_goal=300))
        )
        tracker.add_snapshot(_snap(_party(0, 1, 0, seconds_since_reset=60, adventure_area_goal=300)))

        self.assertEqual(len(tracker.goal_run_history(0)), 0)

    def test_records_goal_run_when_peak_missed_between_api_polls(self) -> None:
        tracker = StatsTracker()
        tracker.add_snapshot(
            _snap(
                _party(
                    1,
                    220,
                    100,
                    seconds_since_reset=1380,
                    modron_area_goal=225,
                )
            )
        )
        tracker.add_snapshot(
            _snap(_party(1, 1, 0, seconds_since_reset=60, modron_area_goal=225))
        )

        history = tracker.goal_run_history(1)
        self.assertEqual(len(history), 1)
        self.assertAlmostEqual(history[0].duration_sec, 1380.0)
        self.assertEqual(history[0].area_goal, 225)

    def test_records_goal_run_after_thellora_reset_to_area_45(self) -> None:
        tracker = StatsTracker()
        tracker.add_snapshot(
            _snap(
                _party(
                    1,
                    226,
                    100,
                    seconds_since_reset=1380,
                    modron_area_goal=225,
                )
            )
        )
        tracker.add_snapshot(
            _snap(_party(1, 45, 0, seconds_since_reset=60, modron_area_goal=225))
        )

        history = tracker.goal_run_history(1)
        self.assertEqual(len(history), 1)
        self.assertAlmostEqual(history[0].duration_sec, 1380.0)

    def test_records_goal_run_when_goal_area_reached_mid_segment(self) -> None:
        tracker = StatsTracker()
        tracker.add_snapshot(
            _snap(_party(1, 200, 100, seconds_since_reset=1200, modron_area_goal=225))
        )
        tracker.add_memory_area(226, active_party_index=1)

        history = tracker.goal_run_history(1)
        self.assertEqual(len(history), 1)
        self.assertAlmostEqual(history[0].duration_sec, 1200.0)

    def test_keeps_only_last_fifty_goal_runs(self) -> None:
        tracker = StatsTracker()
        for run_index in range(52):
            duration = 1000 + run_index * 100
            tracker.add_snapshot(
                _snap(
                    _party(
                        0,
                        300,
                        100,
                        seconds_since_reset=duration,
                        adventure_area_goal=300,
                    )
                )
            )
            tracker.add_snapshot(
                _snap(_party(0, 1, 0, seconds_since_reset=60, adventure_area_goal=300))
            )

        history = tracker.goal_run_history(0)
        self.assertEqual(len(history), 50)
        self.assertAlmostEqual(history[0].duration_sec, 6100.0)
        self.assertAlmostEqual(history[49].duration_sec, 1200.0)

    def test_goal_run_history_survives_session_reset(self) -> None:
        tracker = StatsTracker()
        tracker.add_snapshot(
            _snap(_party(0, 300, 100, seconds_since_reset=3600, adventure_area_goal=300))
        )
        tracker.add_snapshot(_snap(_party(0, 1, 0, seconds_since_reset=60, adventure_area_goal=300)))
        tracker.reset()
        tracker.add_snapshot(_snap(_party(0, 50, 10, seconds_since_reset=120, adventure_area_goal=300)))

        self.assertEqual(len(tracker.goal_run_history(0)), 1)

    def test_format_goal_run_history(self) -> None:
        from ic_gamedata.stats import GoalRunRecord

        history = (
            GoalRunRecord(duration_sec=754.0, area_goal=300, peak_area=305, recorded_at=0.0),
            GoalRunRecord(duration_sec=812.0, area_goal=300, peak_area=301, recorded_at=0.0),
        )
        summary, extra = format_goal_run_history(
            history,
            area_goal=300,
            format_duration=lambda sec: f"{int(sec // 60)}:{int(sec % 60):02d}",
        )
        self.assertEqual(summary, "Laatste doel-run: 12:34 (Modron-doel 300)")
        self.assertEqual(extra, ("2. 13:32",))

    def test_format_goal_run_history_placeholder_when_empty(self) -> None:
        summary, extra = format_goal_run_history(
            (),
            area_goal=275,
            format_duration=lambda sec: str(sec),
        )
        self.assertIn("275", summary or "")
        self.assertEqual(extra, ())


class GoalRunPersistenceTests(_IsolatedGoalRunHistoryTestCase):
    def test_persists_completed_goal_runs(self) -> None:
        tracker = StatsTracker()
        tracker.add_snapshot(
            _snap(_party(1, 280, 100, seconds_since_reset=3600, adventure_area_goal=275))
        )
        tracker.add_snapshot(
            _snap(_party(1, 1, 0, seconds_since_reset=60, adventure_area_goal=275))
        )
        self.assertEqual(len(tracker.goal_run_history(1)), 1)
        self.assertTrue(self._history_path.is_file())

        tracker2 = StatsTracker()
        self.assertEqual(len(tracker2.goal_run_history(1)), 1)


class GoalRunHistoryExtraTests(_IsolatedGoalRunHistoryTestCase):
    def test_records_goal_run_when_peak_is_highest_area(self) -> None:
        tracker = StatsTracker()
        party = _party(
            0,
            260,
            100,
            seconds_since_reset=3600,
            adventure_area_goal=275,
        )
        party = PartySnapshot(
            party_index=party.party_index,
            adventure_id=party.adventure_id,
            current_area=260,
            gold=party.gold,
            gold_gained=party.gold_gained,
            gems_this_reset=party.gems_this_reset,
            boss_kills_this_reset=party.boss_kills_this_reset,
            monster_kills=party.monster_kills,
            boss_kills=party.boss_kills,
            seconds_since_reset=3600,
            adventure_area_goal=275,
            modron_area_goal=275,
            highest_area=280,
            is_active=True,
        )
        tracker.add_snapshot(_snap(party))
        tracker.add_snapshot(_snap(_party(0, 1, 0, seconds_since_reset=60, adventure_area_goal=275)))

        self.assertEqual(len(tracker.goal_run_history(0)), 1)

    def test_records_goal_run_after_api_log_merge(self) -> None:
        from ic_gamedata.log_parser import merge_party_snapshots

        tracker = StatsTracker()
        api_party = PartySnapshot(
            party_index=1,
            adventure_id=31,
            current_area=280,
            gold=100.0,
            gold_gained=100.0,
            gems_this_reset=100,
            boss_kills_this_reset=10,
            monster_kills=280,
            boss_kills=10,
            seconds_since_reset=3600,
            is_active=True,
            adventure_area_goal=275,
            modron_area_goal=275,
        )
        log_party = _party(1, area=280, gems=130, seconds_since_reset=3600)
        merged = merge_party_snapshots(api_party, log_party)
        self.assertEqual(merged.adventure_area_goal, 275)
        self.assertEqual(merged.modron_area_goal, 275)

        tracker.add_snapshot(_snap(merged))
        reset_party = merge_party_snapshots(
            PartySnapshot(
                party_index=1,
                adventure_id=31,
                current_area=1,
                gold=100.0,
                gold_gained=100.0,
                gems_this_reset=0,
                boss_kills_this_reset=0,
                monster_kills=1,
                boss_kills=0,
                seconds_since_reset=60,
                is_active=True,
                adventure_area_goal=275,
                modron_area_goal=275,
            ),
            _party(1, area=1, gems=0, seconds_since_reset=60),
        )
        tracker.add_snapshot(_snap(reset_party))
        self.assertEqual(len(tracker.goal_run_history(1)), 1)


class GoalRunMemoryResetTests(_IsolatedGoalRunHistoryTestCase):
    def test_records_goal_run_on_memory_area_drop_before_api(self) -> None:
        tracker = StatsTracker()
        tracker.add_snapshot(
            _snap(
                _party(
                    1,
                    226,
                    100,
                    seconds_since_reset=479,
                    adventure_area_goal=275,
                    modron_area_goal=225,
                )
            )
        )
        tracker.add_memory_area(1, active_party_index=1)

        history = tracker.goal_run_history(1)
        self.assertEqual(len(history), 1)
        self.assertAlmostEqual(history[0].duration_sec, 479.0)
        self.assertEqual(history[0].area_goal, 225)

    def test_ignores_garbage_memory_peak_and_reset(self) -> None:
        tracker = StatsTracker()
        tracker.add_snapshot(
            _snap(
                _party(
                    1,
                    220,
                    100,
                    seconds_since_reset=480,
                    modron_area_goal=225,
                )
            )
        )
        tracker.add_memory_area(665, active_party_index=1)
        tracker.add_memory_area(1, active_party_index=1)

        self.assertEqual(len(tracker.goal_run_history(1)), 0)
        self.assertLessEqual(tracker._party_state[1].segment_peak_area or 0, 275)


class GoalRunSanityTests(_IsolatedGoalRunHistoryTestCase):
    def test_rejects_corrupt_history_on_load(self) -> None:
        self._history_path.write_text(
            json.dumps(
                {
                    "parties": {
                        "1": [
                            {
                                "duration_sec": 192091.0,
                                "area_goal": 225,
                                "peak_area": 665,
                                "recorded_at": 1.0,
                            },
                            {
                                "duration_sec": 479.0,
                                "area_goal": 225,
                                "peak_area": 226,
                                "recorded_at": 2.0,
                            },
                        ]
                    }
                }
            ),
            encoding="utf-8",
        )
        from ic_gamedata.goal_run_history_store import load_goal_run_history

        history = load_goal_run_history()
        self.assertEqual(len(history[1]), 1)
        self.assertAlmostEqual(history[1][0].duration_sec, 479.0)


if __name__ == "__main__":
    unittest.main()
