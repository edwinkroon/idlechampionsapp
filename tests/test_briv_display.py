"""Tests for Briv / party instance display helpers."""

from __future__ import annotations

import unittest

from ic_gamedata.party_display import parse_instance_extras


class BrivDisplayTests(unittest.TestCase):
    def test_briv_detected_via_live_heroes_for_party(self) -> None:
        instance = {
            "game_instance_id": 2,
            "formation": [-1, -1, -1, -1, -1, -1, -1, -1, -1],
            "hero_in_seats": {},
            "stats": {"briv_sprint_stacks": "4200"},
        }
        payload = {
            "details": {
                "heroes": [
                    {
                        "hero_id": 58,
                        "game_instance_id": 2,
                        "in_seat": 1,
                    }
                ]
            }
        }
        extras = parse_instance_extras(instance, payload, party_index=2)
        self.assertTrue(extras["briv_in_formation"])
        self.assertEqual(extras["briv_sprint_stacks"], 4200)

    def test_briv_stacks_default_zero_when_in_formation(self) -> None:
        instance = {
            "game_instance_id": 2,
            "formation": [58, -1, -1, -1, -1, -1, -1, -1, -1],
            "hero_in_seats": {"1": 58},
            "stats": {},
        }
        extras = parse_instance_extras(instance, None, party_index=2)
        self.assertTrue(extras["briv_in_formation"])
        self.assertIsNone(extras["briv_sprint_stacks"])

    def test_briv_stacks_fallback_to_account_stats_for_active_party(self) -> None:
        instance = {
            "game_instance_id": 2,
            "formation": [58],
            "hero_in_seats": {"1": 58},
            "stats": {},
        }
        payload = {
            "details": {
                "active_game_instance_id": 2,
                "stats": {"briv_sprint_stacks": "9001"},
            }
        }
        extras = parse_instance_extras(instance, payload, party_index=2)
        self.assertEqual(extras["briv_sprint_stacks"], 9001)

    def test_briv_stacks_prefers_live_account_stats_when_instance_lags(self) -> None:
        instance = {
            "game_instance_id": 2,
            "formation": [58],
            "hero_in_seats": {"1": 58},
            "stats": {"briv_sprint_stacks": "49"},
        }
        payload = {
            "details": {
                "active_game_instance_id": 2,
                "stats": {"briv_sprint_stacks": "512"},
            }
        }
        extras = parse_instance_extras(instance, payload, party_index=2)
        self.assertEqual(extras["briv_sprint_stacks"], 512)


if __name__ == "__main__":
    unittest.main()
