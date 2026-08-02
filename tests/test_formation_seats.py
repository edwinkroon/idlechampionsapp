"""Tests for active formation seat detection."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from ic_gamedata.formation_seats import active_formation_seats


class FormationSeatsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        path = Path(__file__).resolve().parent.parent / "webRequestLog_example.json"
        cls.payload = json.loads(path.read_text(encoding="utf-8"))

    def test_example_payload_uses_live_in_seat(self) -> None:
        party_id, seats = active_formation_seats(self.payload)
        self.assertEqual(party_id, 1)
        # Live in_seat heroes (game_instance_id 0 = active roster), not stale formation save
        self.assertEqual(seats, frozenset(range(1, 13)))

    def test_ignores_stale_formation_save_when_in_seat_populated(self) -> None:
        payload = json.loads(json.dumps(self.payload))
        inst = next(
            i
            for i in payload["details"]["game_instances"]
            if int(i["game_instance_id"]) == 1
        )
        on_field = {147, 43}
        for hero in payload["details"]["heroes"]:
            if not isinstance(hero, dict):
                continue
            hid = int(hero["hero_id"])
            hero["in_seat"] = 1 if hid in on_field else 0
        inst["formation_saves_v2"][0]["formation"] = list(range(1, 10))
        party_id, seats = active_formation_seats(payload)
        self.assertEqual(seats, frozenset({1, 3}))

    def test_prefers_live_in_seat_over_formation_grid(self) -> None:
        payload = json.loads(json.dumps(self.payload))
        inst = next(
            i
            for i in payload["details"]["game_instances"]
            if int(i["game_instance_id"]) == 1
        )
        on_field = {147, 43}
        for hero in payload["details"]["heroes"]:
            if not isinstance(hero, dict):
                continue
            hid = int(hero["hero_id"])
            hero["in_seat"] = 1 if hid in on_field else 0
        inst["formation"] = [147, 43, -1, -1, -1, -1, -1, -1, -1]
        party_id, seats = active_formation_seats(payload)
        self.assertEqual(party_id, 1)
        self.assertEqual(seats, frozenset({1, 3}))

    def test_empty_payload(self) -> None:
        party_id, seats = active_formation_seats({})
        self.assertIsNone(party_id)
        self.assertEqual(seats, frozenset())


if __name__ == "__main__":
    unittest.main()
