"""Tests for Modron reset area goal resolution."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ic_gamedata.log_parser import PartySnapshot
from ic_gamedata.modron_area_goal import _load_gamedata, resolve_modron_area_goal
from ic_gamedata.stats import StatsTracker


class ModronAreaGoalTests(unittest.TestCase):
    def test_config_override_wins_over_api_milestone(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "gamedata.json"
            config_path.write_text(
                json.dumps({"party_modron_goals": {"1": 225}}),
                encoding="utf-8",
            )
            with patch("ic_gamedata.modron_area_goal.GAMEDATA_CONFIG_PATH", config_path):
                _load_gamedata.cache_clear()
                goal = resolve_modron_area_goal(
                    {"stats": {"adventure_area_goal": 275}},
                    {"details": {"stats": {"adventure_area_goal": 275}}},
                    party_index=1,
                )
        self.assertEqual(goal, 225)

    def test_does_not_use_adventure_area_goal_as_modron_goal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "gamedata.json"
            config_path.write_text("{}", encoding="utf-8")
            with patch("ic_gamedata.modron_area_goal.GAMEDATA_CONFIG_PATH", config_path):
                _load_gamedata.cache_clear()
                goal = resolve_modron_area_goal(
                    {"stats": {"adventure_area_goal": 275}},
                    None,
                    party_index=1,
                )
        self.assertIsNone(goal)

    def test_records_run_at_modron_goal_not_milestone(self) -> None:
        party_high = PartySnapshot(
            party_index=1,
            adventure_id=31,
            current_area=228,
            gold=1.0,
            gold_gained=1.0,
            gems_this_reset=10,
            boss_kills_this_reset=1,
            monster_kills=228,
            boss_kills=1,
            seconds_since_reset=3600,
            is_active=True,
            adventure_area_goal=275,
            modron_area_goal=225,
            highest_area=228,
        )
        party_reset = PartySnapshot(
            party_index=1,
            adventure_id=31,
            current_area=1,
            gold=1.0,
            gold_gained=1.0,
            gems_this_reset=0,
            boss_kills_this_reset=0,
            monster_kills=1,
            boss_kills=0,
            seconds_since_reset=60,
            is_active=True,
            adventure_area_goal=275,
            modron_area_goal=225,
        )
        from ic_gamedata.log_parser import GameSnapshot

        def snap(party: PartySnapshot) -> GameSnapshot:
            return GameSnapshot(
                api_call="t",
                active_party_index=1,
                parties=(party,),
                current_area=party.current_area,
                gold=party.gold,
                gold_gained=party.gold_gained,
                gems_this_reset=party.gems_this_reset,
                monster_kills=party.monster_kills,
                boss_kills=party.boss_kills,
            )

        with tempfile.TemporaryDirectory() as tmp:
            history_path = Path(tmp) / "goal_run_history.json"
            with patch("ic_gamedata.goal_run_history_store.GOAL_RUN_HISTORY_PATH", history_path):
                tracker = StatsTracker()
                tracker.add_snapshot(snap(party_high))
                tracker.add_snapshot(snap(party_reset))
                self.assertEqual(len(tracker.goal_run_history(1)), 1)
                self.assertEqual(tracker.goal_run_history(1)[0].area_goal, 225)


if __name__ == "__main__":
    unittest.main()
