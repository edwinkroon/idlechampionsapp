"""Tests for familiar seat detection (skip F-key leveling)."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from ic_gamedata.familiar_seats import familiar_level_seats, familiar_party_count


class FamiliarSeatsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        path = Path(__file__).resolve().parent / "fixtures" / "webRequestLog_example.json"
        cls.payload = json.loads(path.read_text(encoding="utf-8"))

    def test_example_payload_has_no_familiar_seats(self) -> None:
        seats = familiar_level_seats(self.payload)
        self.assertEqual(seats, frozenset())

    def test_live_dict_assignment_for_active_party(self) -> None:
        payload = {
            "details": {
                "active_game_instance_id": 2,
                "game_instances": [{"game_instance_id": 2}],
                "familiars": [
                    {"familiar_id": "32", "assignment": {"Seat": 1, "game_instance_id": 2}},
                    {"familiar_id": "3", "assignment": {"Seat": 2, "game_instance_id": 2}},
                    {"familiar_id": "2", "assignment": {"Seat": 3, "game_instance_id": 2}},
                    {"familiar_id": "1", "assignment": {"Seat": 4, "game_instance_id": 2}},
                ],
            }
        }
        self.assertEqual(familiar_level_seats(payload), frozenset({1, 2, 3, 4}))

    def test_ignores_other_party_and_clicks(self) -> None:
        payload = {
            "details": {
                "active_game_instance_id": 1,
                "game_instances": [{"game_instance_id": 1}],
                "familiars": [
                    {"familiar_id": "32", "assignment": {"Seat": 1, "game_instance_id": 2}},
                    {"familiar_id": "27", "assignment": {"Clicks": 0, "game_instance_id": 1}},
                    {"familiar_id": "58", "assignment": {"Seat": 99, "game_instance_id": 1}},
                ],
            }
        }
        self.assertEqual(familiar_level_seats(payload), frozenset())

    def test_legacy_list_assignment(self) -> None:
        payload = {
            "details": {
                "active_game_instance_id": 1,
                "game_instances": [{"game_instance_id": 1}],
                "familiars": [
                    {"familiar_id": "113", "assignment": ["Seat", 3]},
                    {"familiar_id": "1", "assignment": ["Clicks", 0]},
                ],
            }
        }
        self.assertEqual(familiar_level_seats(payload), frozenset({3}))

    def test_level_up_slots_do_not_map_to_f_keys(self) -> None:
        payload = {
            "details": {
                "active_game_instance_id": 1,
                "game_instances": [{"game_instance_id": 1}],
                "familiars": [
                    {"assignment": ["level_up_1", 1]},
                ],
            }
        }
        self.assertEqual(familiar_level_seats(payload), frozenset())

    def test_party_count_includes_clicks_and_seat_assignments(self) -> None:
        payload = {
            "details": {
                "active_game_instance_id": 1,
                "game_instances": [{"game_instance_id": 1}],
                "familiars": [
                    {"familiar_id": "32", "assignment": {"Seat": 1, "game_instance_id": 1}},
                    {"familiar_id": "27", "assignment": {"Clicks": 0, "game_instance_id": 1}},
                    {"familiar_id": "58", "assignment": {"Seat": 99, "game_instance_id": 1}},
                    {"familiar_id": "2", "assignment": {"Seat": 1, "game_instance_id": 2}},
                ],
            }
        }
        self.assertEqual(familiar_party_count(payload), 2)

    def test_empty_payload(self) -> None:
        self.assertEqual(familiar_level_seats({}), frozenset())


if __name__ == "__main__":
    unittest.main()
