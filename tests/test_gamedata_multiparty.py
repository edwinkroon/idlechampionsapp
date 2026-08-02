"""Tests for multi-party API parsing."""

from __future__ import annotations

import unittest

from ic_gamedata.log_parser import snapshot_from_payload


class MultiPartyParserTests(unittest.TestCase):
    def test_game_instances_parsed(self) -> None:
        snap = snapshot_from_payload(
            {
                "details": {
                    "active_game_instance_id": 1,
                    "game_instances": [
                        {
                            "current_adventure_id": 1083,
                            "current_area": 326,
                            "gold": "100",
                            "stats": {"this_reset_gems_earned": "10", "gold_gained": "200"},
                        },
                        {
                            "current_adventure_id": 31,
                            "current_area": 186,
                            "gold": "50",
                            "stats": {"this_reset_gems_earned": "5", "gold_gained": "80"},
                        },
                        {
                            "current_adventure_id": -1,
                            "current_area": 1,
                            "gold": "0",
                            "stats": {"this_reset_gems_earned": "0"},
                        },
                    ],
                }
            },
            api_call="getuserdetails",
        )
        self.assertIsNotNone(snap)
        assert snap is not None
        self.assertEqual(len(snap.running_parties), 2)
        self.assertEqual(snap.running_parties[0].current_area, 326)
        self.assertEqual(snap.running_parties[1].current_area, 186)
        self.assertTrue(snap.running_parties[1].is_active)


if __name__ == "__main__":
    unittest.main()
