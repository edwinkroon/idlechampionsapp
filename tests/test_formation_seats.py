"""Tests for active formation seat detection."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from ic_gamedata.formation_seats import active_formation_seats, formation_layout_fingerprint


class FormationSeatsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        path = Path(__file__).resolve().parent / "fixtures" / "webRequestLog_example.json"
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

    def test_prefers_formation_grid_over_benched_seat_holders(self) -> None:
        """hero_in_seats can list benched champs; F-keys should follow the live grid."""
        payload = {
            "details": {
                "active_game_instance_id": 1,
                "game_instances": [
                    {
                        "game_instance_id": 1,
                        "hero_in_seats": {
                            "1": 139,
                            "2": 91,
                            "5": 58,
                            "7": 113,
                            "12": 59,
                        },
                        "formation": [139, 91, 59, -1, -1],
                    }
                ],
                "heroes": [
                    {"hero_id": 58, "in_seat": 1, "game_instance_id": 0},
                    {"hero_id": 113, "in_seat": 1, "game_instance_id": 0},
                    {"hero_id": 139, "in_seat": 1, "game_instance_id": 1},
                    {"hero_id": 91, "in_seat": 1, "game_instance_id": 1},
                    {"hero_id": 59, "in_seat": 1, "game_instance_id": 1},
                ],
            }
        }
        party_id, seats = active_formation_seats(payload)
        self.assertEqual(party_id, 1)
        self.assertEqual(seats, frozenset({1, 2, 12}))
        self.assertNotIn(5, seats)
        self.assertNotIn(7, seats)

    def test_rich_grid_recovers_seats_when_hero_in_seats_sparse(self) -> None:
        """Regression: sparse hero_in_seats must not collapse a full board to F1 only."""
        payload = {
            "details": {
                "active_game_instance_id": 2,
                "game_instances": [
                    {
                        "game_instance_id": 2,
                        # Only one seat mapped — previously made automation "levelt F1".
                        "hero_in_seats": {"1": 1},
                        "formation": [1, 2, 3, 4, 5, 6, 7, 8, -1],
                    }
                ],
                "heroes": [
                    {
                        "hero_id": hid,
                        "in_seat": 0,
                        "game_instance_id": 2,
                        "level": 50,
                        "owned": 1,
                    }
                    for hid in range(1, 9)
                ],
            }
        }
        party_id, seats = active_formation_seats(payload)
        self.assertEqual(party_id, 2)
        # Champions 1–8 use permanent seat_id 1–8 in cached definitions.
        self.assertEqual(seats, frozenset(range(1, 9)))

        from ic_gamedata.party_advisor_formation import _formation_heroes

        formation = _formation_heroes(payload)
        self.assertEqual(len(formation), 8)
        self.assertTrue(all(hero.seat is not None for hero in formation))
        self.assertEqual({hero.seat for hero in formation}, set(range(1, 9)))

    def test_layout_fingerprint_tracks_live_grid_swaps(self) -> None:
        payload = {
            "details": {
                "active_game_instance_id": 1,
                "game_instances": [
                    {
                        "game_instance_id": 1,
                        "hero_in_seats": {"3": 3, "8": 164, "9": 168},
                        "formation": [3, 164, 168],
                    }
                ],
                "heroes": [],
            }
        }
        before = formation_layout_fingerprint(payload)
        self.assertEqual(before, ((3, 3), (8, 164), (9, 168)))

        # Follow a tip: swap Nayeli (3) with Tess (8)
        inst = payload["details"]["game_instances"][0]
        inst["formation"] = [164, 3, 168]
        inst["hero_in_seats"] = {"3": 164, "8": 3, "9": 168}
        after = formation_layout_fingerprint(payload)
        self.assertEqual(after, ((3, 164), (8, 3), (9, 168)))
        self.assertNotEqual(before, after)

    def test_layout_fingerprint_ignores_benched_seat_holders(self) -> None:
        payload = {
            "details": {
                "active_game_instance_id": 1,
                "game_instances": [
                    {
                        "game_instance_id": 1,
                        "hero_in_seats": {"3": 3, "8": 164, "9": 168},
                        "formation": [164, 168, -1],
                    }
                ],
                "heroes": [],
            }
        }
        fp = formation_layout_fingerprint(payload)
        self.assertEqual(fp, ((8, 164), (9, 168)))
        self.assertNotIn((3, 3), fp)

    def test_layout_fingerprint_empty_payload(self) -> None:
        self.assertIsNone(formation_layout_fingerprint({}))


if __name__ == "__main__":
    unittest.main()
