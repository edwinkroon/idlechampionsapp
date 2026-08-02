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

    def test_briv_not_detected_from_stale_hero_in_seats(self) -> None:
        instance = {
            "game_instance_id": 1,
            "formation": [52, 91, 125, 83, 75, 47, 59, 139, 148],
            "hero_in_seats": {"5": 58, "4": 52},
            "formation_saves_v2": [{"name": "gemfarm", "formation": [58, 1, 2]}],
            "stats": {"briv_sprint_stacks": "1699"},
        }
        extras = parse_instance_extras(instance, None, party_index=1)
        self.assertFalse(extras["briv_in_formation"])
        self.assertIsNone(extras["briv_sprint_stacks"])

    def test_briv_not_detected_from_shared_roster_game_instance_zero(self) -> None:
        instance = {
            "game_instance_id": 1,
            "formation": [-1, -1, -1],
            "hero_in_seats": {},
            "stats": {},
        }
        payload = {
            "details": {
                "heroes": [
                    {
                        "hero_id": 58,
                        "game_instance_id": 0,
                        "in_seat": 1,
                    }
                ]
            }
        }
        extras = parse_instance_extras(instance, payload, party_index=1)
        self.assertFalse(extras["briv_in_formation"])

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
                "game_instances": [instance],
            }
        }
        extras = parse_instance_extras(instance, payload, party_index=2)
        self.assertEqual(extras["briv_sprint_stacks"], 512)

    def test_briv_steelbones_from_api(self) -> None:
        instance = {
            "game_instance_id": 2,
            "formation": [58],
            "hero_in_seats": {"1": 58},
            "stats": {"briv_steelbones_stacks": "125000"},
        }
        payload = {
            "details": {
                "active_game_instance_id": 2,
                "stats": {"briv_steelbones_stacks": "125000"},
                "game_instances": [instance],
            }
        }
        extras = parse_instance_extras(instance, payload, party_index=2)
        self.assertEqual(extras["briv_steelbones_stacks"], 125000)

    def test_briv_stacks_ignores_stale_account_from_other_party(self) -> None:
        instance = {
            "game_instance_id": 2,
            "formation": [58],
            "hero_in_seats": {"1": 58},
            "stats": {},
        }
        payload = {
            "details": {
                "active_game_instance_id": 2,
                "stats": {"briv_sprint_stacks": "48"},
                "game_instances": [
                    {
                        "game_instance_id": 1,
                        "stats": {"briv_sprint_stacks": "48"},
                    },
                    instance,
                ],
                "heroes": [{"hero_id": 58, "game_instance_id": 2, "in_seat": 1}],
            }
        }
        extras = parse_instance_extras(instance, payload, party_index=2)
        self.assertIsNone(extras["briv_sprint_stacks"])


if __name__ == "__main__":
    unittest.main()
