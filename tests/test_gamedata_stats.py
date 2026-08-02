"""Tests for combined memory + log stats."""

from __future__ import annotations

import time
import unittest

from ic_gamedata.log_parser import GameSnapshot, PartySnapshot
from ic_gamedata.stats import StatsTracker


class StatsTrackerTests(unittest.TestCase):
    def test_memory_only_session(self) -> None:
        tracker = StatsTracker()
        tracker.add_memory_area(10)
        time.sleep(0.01)
        tracker.add_memory_area(15)
        stats = tracker.compute()
        self.assertIsNotNone(stats)
        assert stats is not None
        self.assertEqual(stats.memory_area, 15)
        self.assertEqual(len(stats.parties), 0)
        self.assertEqual(stats.memory_areas_gained, 5.0)
        self.assertIsNotNone(stats.memory_areas_per_quarter)

    def test_combined_session(self) -> None:
        tracker = StatsTracker()
        party = PartySnapshot(
            party_index=0,
            adventure_id=31,
            current_area=100,
            gold=1000.0,
            gold_gained=5000.0,
            gems_this_reset=10,
            boss_kills_this_reset=1,
            monster_kills=100,
            boss_kills=5,
            is_active=True,
        )
        snap = GameSnapshot(
            api_call="getuserdetails",
            active_party_index=0,
            parties=(party,),
            current_area=100,
            gold=1000.0,
            gold_gained=5000.0,
            gems_this_reset=10,
            monster_kills=100,
            boss_kills=5,
        )
        tracker.add_snapshot(snap)
        party2 = PartySnapshot(
            party_index=0,
            adventure_id=31,
            current_area=110,
            gold=1000.0,
            gold_gained=5000.0,
            gems_this_reset=10,
            boss_kills_this_reset=1,
            monster_kills=100,
            boss_kills=5,
            is_active=True,
        )
        snap2 = GameSnapshot(
            api_call="getuserdetails",
            active_party_index=0,
            parties=(party2,),
            current_area=110,
            gold=1000.0,
            gold_gained=5000.0,
            gems_this_reset=10,
            monster_kills=100,
            boss_kills=5,
        )
        tracker.add_snapshot(snap2)
        tracker.add_memory_area(100)
        tracker.add_memory_area(110)
        stats = tracker.compute()
        self.assertIsNotNone(stats)
        assert stats is not None
        self.assertEqual(len(stats.parties), 1)
        self.assertEqual(stats.parties[0].areas_gained, 10.0)
        self.assertGreater(stats.gems_this_reset or 0, 10)
        self.assertTrue(stats.parties[0].gems_estimated)


if __name__ == "__main__":
    unittest.main()
