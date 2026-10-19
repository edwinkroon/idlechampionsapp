"""Tests for ultimate ability cooldown hotkeys."""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from typing import Any

from ic_gamedata.ability_cooldowns import (
    ability_hotkey_labels,
    ability_status,
    formation_ability_keys,
    formation_ultimate_assignments,
    formation_ultimate_seat_hotkeys,
    ready_ability_keys,
)


def _board_from_seats(payload: dict[str, Any], seats: list[int] | None = None) -> dict[str, Any]:
    """Put hero_in_seats champions onto the live formation in seat order."""
    payload = json.loads(json.dumps(payload))
    inst = next(
        i for i in payload["details"]["game_instances"] if int(i["game_instance_id"]) == 1
    )
    seat_map = {int(k): int(v) for k, v in inst["hero_in_seats"].items() if int(v) > 0}
    order = seats if seats is not None else sorted(s for s in seat_map if 1 <= s <= 12)[:10]
    inst["formation"] = [seat_map[s] for s in order if s in seat_map]
    return payload


class AbilityCooldownTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        path = Path(__file__).resolve().parent / "fixtures" / "webRequestLog_example.json"
        cls.raw_payload = json.loads(path.read_text(encoding="utf-8"))
        # Fixture formation is sparse; put seats 1–10 on the board in seat order
        # so hotkeys 1–0 match Gale, Raistlin, Spurt, …
        cls.payload = _board_from_seats(cls.raw_payload, list(range(1, 11)))

    def test_ready_keys_skip_on_cooldown(self) -> None:
        keys = ready_ability_keys(self.payload)
        # Gale (seat 1, ult 745) and Raistlin (seat 2, ult 941) are on cooldown in example
        self.assertNotIn("1", keys)
        self.assertNotIn("2", keys)
        # Spurt ready
        self.assertIn("3", keys)
        self.assertIsInstance(keys, list)

    def test_unmapped_hero_is_not_ready(self) -> None:
        payload = _board_from_seats(self.raw_payload, list(range(1, 11)))
        inst = next(i for i in payload["details"]["game_instances"] if int(i["game_instance_id"]) == 1)
        inst["hero_in_seats"]["4"] = 9999
        inst["formation"] = [
            int(inst["hero_in_seats"][str(s)]) for s in range(1, 11)
        ]
        keys, status = ability_status(payload)
        self.assertNotIn("4", keys)
        self.assertIn("4: unknown", status)

    def test_unmapped_hero_not_ready_without_events(self) -> None:
        payload = _board_from_seats(self.raw_payload, list(range(1, 11)))
        payload["details"]["events_details"] = {"champion_details": []}
        # Remove seed entries for Gale/Raistlin to simulate unknown mapping
        inst = next(i for i in payload["details"]["game_instances"] if int(i["game_instance_id"]) == 1)
        inst["hero_in_seats"]["1"] = 9998
        inst["hero_in_seats"]["2"] = 9997
        inst["formation"] = [
            int(inst["hero_in_seats"][str(s)]) for s in range(1, 11)
        ]
        keys, status = ability_status(payload)
        self.assertNotIn("1", keys)
        self.assertNotIn("2", keys)
        self.assertIn("1: unknown", status)
        self.assertIn("2: unknown", status)

    def test_status_shows_cooldown_seconds(self) -> None:
        keys, status = ability_status(self.payload)
        self.assertIn("1: 26s", status)
        self.assertIn("2: 35s", status)
        self.assertIn("3: ready", status)
        self.assertNotIn("1", keys)

    def test_no_cooldown_data_fires_party_keys(self) -> None:
        payload = json.loads(json.dumps(self.payload))
        payload["details"]["attack_cooldowns"] = []
        keys = ready_ability_keys(payload)
        self.assertGreaterEqual(len(keys), 1)
        self.assertTrue(set(keys) <= set("1234567890"))

    def test_all_ready_when_cooldowns_zero(self) -> None:
        payload = json.loads(json.dumps(self.payload))
        for entry in payload["details"]["attack_cooldowns"]:
            entry["cooldown_remaining"] = 0
        keys = ready_ability_keys(payload)
        self.assertIn("1", keys)
        self.assertIn("2", keys)
        self.assertTrue(set(keys) <= set("1234567890"))

    def test_empty_payload(self) -> None:
        self.assertEqual(ready_ability_keys({}), [])
        self.assertEqual(ability_status({})[0], [])

    def test_hotkey_labels_include_champion_and_ultimate(self) -> None:
        labels = ability_hotkey_labels(self.payload)
        self.assertIn("1", labels)
        self.assertIn("2", labels)
        self.assertTrue(labels["1"].startswith("Gale - "))
        self.assertIn("Gale", labels["1"].split(" - ", 1)[-1])
        self.assertTrue(labels["2"].startswith("Raistlin - "))

    def test_fallbacks_hotkey_label_uses_call_uggie(self) -> None:
        payload = json.loads(json.dumps(self.payload))
        inst = next(
            i for i in payload["details"]["game_instances"] if int(i["game_instance_id"]) == 1
        )
        # Tess permanent seat is 8; put her first on the board → hotkey 1.
        inst["hero_in_seats"]["8"] = 164
        inst["formation"] = [164]
        labels = ability_hotkey_labels(payload)
        self.assertEqual(labels.get("1"), "Tess - Call Uggie")

    def test_hotkeys_follow_live_formation_order_not_permanent_seats(self) -> None:
        """Hotkeys follow board order so seat 11/12 champions also get a number key."""
        payload = {
            "details": {
                "active_game_instance_id": 1,
                "game_instances": [
                    {
                        "game_instance_id": 1,
                        "hero_in_seats": {
                            "1": 171,  # Anson, benched
                            "2": 34,  # Donaar, benched
                            "3": 179,  # Caramon, benched
                            "4": 169,  # Skylla, benched
                            "5": 172,  # Kyre, benched
                            "6": 6,  # Asharra, benched
                            "7": 151,  # Umberto, benched
                            "8": 164,  # Tess, on the board
                            "9": 178,  # Flint, benched
                            "10": 166,  # Cazrin, benched
                            "12": 165,  # Baldric, on the board (no permanent number key)
                        },
                        # Board order: Gale, Briv, Tess, Baldric → keys 1,2,3,4
                        "formation": [147, 58, 164, 165, -1],
                    }
                ],
                "heroes": [],
            }
        }
        labels = ability_hotkey_labels(payload)
        self.assertEqual(set(labels), {"1", "2", "3", "4"})
        self.assertTrue(labels["1"].startswith("Gale - "))
        self.assertTrue(labels["2"].startswith("Briv - "))
        self.assertTrue(labels["3"].startswith("Tess - "))
        self.assertTrue(labels["4"].startswith("Baldric - "))
        self.assertEqual(formation_ability_keys(payload), ["1", "2", "3", "4"])
        seat_keys = formation_ultimate_seat_hotkeys(payload)
        self.assertEqual(seat_keys.get(1), "1")  # Gale's permanent seat
        self.assertEqual(seat_keys.get(5), "2")  # Briv
        self.assertEqual(seat_keys.get(8), "3")  # Tess
        self.assertEqual(seat_keys.get(12), "4")  # Baldric seat 12 → hotkey 4
        self.assertEqual(set(ready_ability_keys(payload)), {"1", "2", "3", "4"})
        rows = formation_ultimate_assignments(payload)
        self.assertEqual([r["seat"] for r in rows], [1, 5, 8, 12])


if __name__ == "__main__":
    unittest.main()
