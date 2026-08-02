"""Tests for gem tracking fixes (party ids, log merge, boss-kill fallback)."""

from __future__ import annotations

import unittest

from ic_gamedata.log_parser import (
    PartySnapshot,
    merge_party_snapshots,
    snapshot_from_payload,
)
from ic_gamedata.stats import StatsTracker, _extrapolate_gems


def _party(
    index: int,
    *,
    area: int = 100,
    gems: int = 0,
    boss_kills: int = 0,
    seconds_since_reset: int | None = None,
) -> PartySnapshot:
    return PartySnapshot(
        party_index=index,
        adventure_id=31,
        current_area=area,
        gold=100.0,
        gold_gained=100.0,
        gems_this_reset=gems,
        boss_kills_this_reset=boss_kills,
        monster_kills=area,
        boss_kills=boss_kills,
        seconds_since_reset=seconds_since_reset,
        is_active=index == 1,
    )


class GameInstanceIdTests(unittest.TestCase):
    def test_uses_game_instance_id_not_array_index(self) -> None:
        snap = snapshot_from_payload(
            {
                "details": {
                    "active_game_instance_id": 1,
                    "game_instances": [
                        {
                            "game_instance_id": 1,
                            "current_adventure_id": 31,
                            "current_area": 250,
                            "gold": "10",
                            "stats": {
                                "this_reset_gems_earned": "42",
                                "this_reset_boss_kills": "6",
                                "gold_gained": "1000",
                            },
                        }
                    ],
                }
            },
            api_call="getuserdetails",
        )
        self.assertIsNotNone(snap)
        assert snap is not None
        self.assertEqual(len(snap.parties), 1)
        party = snap.parties[0]
        self.assertEqual(party.party_index, 1)
        self.assertTrue(party.is_active)
        self.assertEqual(party.gems_this_reset, 42)


class MergeSnapshotTests(unittest.TestCase):
    def test_merge_prefers_higher_gems_from_log(self) -> None:
        api_party = _party(1, gems=100, boss_kills=10)
        log_party = _party(1, gems=130, boss_kills=13)
        merged = merge_party_snapshots(api_party, log_party)
        self.assertEqual(merged.gems_this_reset, 130)
        self.assertEqual(merged.boss_kills_this_reset, 13)

    def test_merge_keeps_api_after_modron_reset(self) -> None:
        api_party = _party(1, area=5, gems=0, boss_kills=0)
        log_party = _party(1, area=400, gems=9000, boss_kills=120)
        merged = merge_party_snapshots(api_party, log_party)
        self.assertEqual(merged.gems_this_reset, 0)

    def test_merge_keeps_api_area_when_log_is_stale(self) -> None:
        api_party = _party(1, area=246, gems=100)
        log_party = _party(1, area=556, gems=275)
        merged = merge_party_snapshots(api_party, log_party)
        self.assertEqual(merged.current_area, 246)
        self.assertEqual(merged.gems_this_reset, 100)

    def test_merge_keeps_primary_is_active_not_log_or(self) -> None:
        api_party = _party(1, area=200, gems=100)
        api_party = PartySnapshot(
            party_index=api_party.party_index,
            adventure_id=api_party.adventure_id,
            current_area=api_party.current_area,
            gold=api_party.gold,
            gold_gained=api_party.gold_gained,
            gems_this_reset=api_party.gems_this_reset,
            boss_kills_this_reset=api_party.boss_kills_this_reset,
            monster_kills=api_party.monster_kills,
            boss_kills=api_party.boss_kills,
            is_active=False,
        )
        log_party = PartySnapshot(
            party_index=1,
            adventure_id=31,
            current_area=200,
            gold=100.0,
            gold_gained=100.0,
            gems_this_reset=100,
            boss_kills_this_reset=10,
            monster_kills=200,
            boss_kills=10,
            is_active=True,
        )
        merged = merge_party_snapshots(api_party, log_party)
        self.assertFalse(merged.is_active)

    def test_merge_preserves_adventure_area_goal(self) -> None:
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
        )
        log_party = _party(1, area=280, gems=130, boss_kills=13)
        merged = merge_party_snapshots(api_party, log_party)
        self.assertEqual(merged.adventure_area_goal, 275)
        self.assertEqual(merged.gems_this_reset, 130)


class BossKillExtrapolationTests(unittest.TestCase):
    def test_extrapolates_when_gems_stall(self) -> None:
        prev = _party(1, gems=100, boss_kills=10)
        cur = _party(1, gems=100, boss_kills=12)
        gems, rate, _, _, _, estimated = _extrapolate_gems(
            prev,
            cur,
            gems_per_boss=10.0,
            gems_per_area=None,
            anchor_gems=100,
            anchor_area=100,
        )
        self.assertEqual(gems, 120)
        self.assertEqual(rate, 10.0)
        self.assertTrue(estimated)

    def test_extrapolates_when_area_advances(self) -> None:
        prev = _party(1, area=528, gems=2614)
        cur = _party(1, area=531, gems=2614)
        gems, _, _, _, _, estimated = _extrapolate_gems(
            prev,
            cur,
            gems_per_boss=None,
            gems_per_area=2614 / 528,
            anchor_gems=2614,
            anchor_area=528,
        )
        self.assertGreater(gems or 0, 2614)
        self.assertTrue(estimated)

    def test_tracker_uses_boss_kill_fallback(self) -> None:
        from ic_gamedata.log_parser import GameSnapshot

        def _snap(party: PartySnapshot) -> GameSnapshot:
            return GameSnapshot(
                api_call="getuserdetails",
                active_party_index=party.party_index,
                parties=(party,),
                current_area=party.current_area,
                gold=party.gold,
                gold_gained=party.gold_gained,
                gems_this_reset=party.gems_this_reset,
                monster_kills=party.monster_kills,
                boss_kills=party.boss_kills,
            )

        tracker = StatsTracker()
        tracker.add_snapshot(_snap(_party(1, gems=100, boss_kills=10)))
        tracker.add_snapshot(_snap(_party(1, gems=100, boss_kills=12)))

        stats = tracker.compute()
        self.assertIsNotNone(stats)
        assert stats is not None
        self.assertAlmostEqual(stats.parties[0].gems_gained or 0, 14.0)

    def test_gem_rate_not_tied_to_area_when_api_gems_stall(self) -> None:
        """Area-based gem estimates must not make gems/kw equal areas/kw."""
        from ic_gamedata.log_parser import GameSnapshot

        def _snap(area: int, gems: int, boss: int = 10) -> GameSnapshot:
            party = _party(1, area=area, gems=gems, boss_kills=boss)
            return GameSnapshot(
                api_call="getuserdetails",
                active_party_index=1,
                parties=(party,),
                current_area=area,
                gold=party.gold,
                gold_gained=party.gold_gained,
                gems_this_reset=gems,
                monster_kills=area,
                boss_kills=boss,
            )

        tracker = StatsTracker()
        tracker.add_snapshot(_snap(100, 100))
        for area in range(103, 130, 3):
            tracker.add_snapshot(_snap(area, 100))

        stats = tracker.compute()
        self.assertIsNotNone(stats)
        assert stats is not None
        ps = stats.parties[0]
        self.assertIsNotNone(ps.areas_per_quarter)
        self.assertIsNotNone(ps.gems_per_quarter)
        assert ps.areas_per_quarter is not None
        assert ps.gems_per_quarter is not None
        self.assertNotAlmostEqual(ps.areas_per_quarter, ps.gems_per_quarter, delta=0.01)
        self.assertLess(ps.gems_per_quarter, ps.areas_per_quarter)

    def test_memory_gems_override_stalled_api(self) -> None:
        from ic_gamedata.log_parser import GameSnapshot

        party = _party(1, area=200, gems=100)
        snap = GameSnapshot(
            api_call="getuserdetails",
            active_party_index=1,
            parties=(party,),
            current_area=200,
            gold=party.gold,
            gold_gained=party.gold_gained,
            gems_this_reset=100,
            monster_kills=200,
            boss_kills=10,
        )
        tracker = StatsTracker()
        tracker.add_snapshot(snap)
        tracker.add_memory_area(220, gems=140)
        stats = tracker.compute()
        self.assertIsNotNone(stats)
        assert stats is not None
        self.assertEqual(stats.parties[0].gems_this_reset, 140)
        self.assertFalse(stats.parties[0].gems_estimated)

    def test_memory_gems_drop_on_modron_reset(self) -> None:
        from ic_gamedata.log_parser import GameSnapshot

        def snap(area: int, gems: int) -> GameSnapshot:
            party = _party(1, area=area, gems=gems)
            return GameSnapshot(
                api_call="getuserdetails",
                active_party_index=1,
                parties=(party,),
                current_area=area,
                gold=party.gold,
                gold_gained=party.gold_gained,
                gems_this_reset=gems,
                monster_kills=area,
                boss_kills=1,
            )

        tracker = StatsTracker()
        tracker.add_snapshot(snap(400, 5000))
        tracker.add_memory_area(400, gems=5000)
        tracker.add_snapshot(snap(5, 0))
        tracker.add_memory_area(5, gems=0)
        stats = tracker.compute()
        self.assertIsNotNone(stats)
        assert stats is not None
        self.assertEqual(stats.parties[0].gems_this_reset, 0)
        self.assertEqual(stats.parties[0].reset_count, 1)


if __name__ == "__main__":
    unittest.main()
