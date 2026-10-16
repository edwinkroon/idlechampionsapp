"""Tests for dashboard party display helpers."""

from __future__ import annotations

import unittest

from ic_gamedata.log_parser import GameSnapshot, PartySnapshot
from ic_gamedata.party_display import (
    format_area_line,
    format_buff_remaining,
    party_tile_title,
    refresh_snapshot_from_payload,
    summarize_active_buffs,
)


class PartyDisplayTests(unittest.TestCase):
    def test_area_line_shows_wall(self) -> None:
        self.assertEqual(format_area_line(450, 520), "Area: 450 (wall 520)")

    def test_area_line_without_wall(self) -> None:
        self.assertEqual(format_area_line(450, 450), "Area: 450")

    def test_party_title_with_custom_name(self) -> None:
        title = party_tile_title(
            party_index=2,
            custom_name="Mimic Farm",
            adventure_name="Rime of the Frostmaiden",
            is_active=False,
        )
        self.assertEqual(title, "Party 2 · Mimic Farm, Rime of the Frostmaiden")

    def test_buff_remaining_minutes(self) -> None:
        self.assertEqual(format_buff_remaining(41509), "6m")

    def test_summarize_active_buffs(self) -> None:
        instance = {
            "active_buff_ids": [2271],
            "buffs": [
                {"buff_id": 2271, "remaining_time": 41509},
                {"buff_id": 99, "remaining_time": 0},
            ],
        }
        payload = {
            "details": {
                "event_details": [
                    {
                        "name": "Renown Weekend",
                        "details": {
                            "buff_id": 2271,
                            "promo_buff_title": "Renown Weekend",
                        },
                    }
                ]
            }
        }
        text = summarize_active_buffs(instance, payload)
        self.assertIsNotNone(text)
        assert text is not None
        self.assertIn("Renown Weekend", text)
        self.assertNotIn("2271", text)
        self.assertIn("rest", text)

    def test_summarize_multiple_buffs_on_separate_lines(self) -> None:
        instance = {
            "active_buff_ids": [1, 2, 3],
            "buffs": [
                {"buff_id": 1, "remaining_time": 5000},
                {"buff_id": 2, "remaining_time": 6000},
                {"buff_id": 3, "remaining_time": 7000},
            ],
        }
        payload = {
            "defines": {
                "boon_buff_defines": [
                    {"id": 1, "effect_key": "time_scale"},
                    {"id": 2, "effect_key": "gold_multiplier_mult"},
                    {"id": 3, "effect_key": "global_dps_multiplier_mult"},
                ]
            }
        }
        text = summarize_active_buffs(instance, payload)
        self.assertIsNotNone(text)
        assert text is not None
        self.assertTrue(text.startswith("Buffs:\n"))
        lines = text.split("\n")
        self.assertEqual(len(lines), 4)
        self.assertTrue(all(line.startswith("· ") for line in lines[1:]))
        self.assertTrue(all("rest" in line for line in lines[1:]))

    def test_refresh_snapshot_updates_active_adventure(self) -> None:
        """Caption/dashboard must follow live adventure after a party swap."""
        stale = GameSnapshot(
            api_call="getuserdetails",
            active_party_index=1,
            parties=(
                PartySnapshot(
                    party_index=1,
                    adventure_id=100,
                    current_area=50,
                    gold=1.0,
                    gold_gained=1.0,
                    gems_this_reset=0,
                    boss_kills_this_reset=0,
                    monster_kills=0,
                    boss_kills=0,
                    is_active=True,
                ),
                PartySnapshot(
                    party_index=2,
                    adventure_id=200,
                    current_area=10,
                    gold=1.0,
                    gold_gained=1.0,
                    gems_this_reset=0,
                    boss_kills_this_reset=0,
                    monster_kills=0,
                    boss_kills=0,
                    is_active=False,
                ),
            ),
            current_area=50,
            gold=1.0,
            gold_gained=1.0,
            gems_this_reset=0,
            monster_kills=0,
            boss_kills=0,
        )
        payload = {
            "details": {
                "active_game_instance_id": 2,
                "current_adventure_id": 999,
                "game_instances": [
                    {
                        "game_instance_id": 1,
                        "current_adventure_id": 100,
                        "current_area": 50,
                        "stats": {},
                    },
                    {
                        "game_instance_id": 2,
                        "current_adventure_id": 321,
                        "current_area": 12,
                        "stats": {},
                    },
                ],
            }
        }
        refreshed = refresh_snapshot_from_payload(stale, payload)
        self.assertEqual(refreshed.active_party_index, 2)
        by_id = {p.party_index: p for p in refreshed.parties}
        self.assertFalse(by_id[1].is_active)
        self.assertTrue(by_id[2].is_active)
        self.assertEqual(by_id[2].adventure_id, 321)
        self.assertEqual(by_id[2].current_area, 12)


if __name__ == "__main__":
    unittest.main()
