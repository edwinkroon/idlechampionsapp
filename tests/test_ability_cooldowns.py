"""Tests for ultimate ability cooldown hotkeys."""



from __future__ import annotations

import json
import unittest
from pathlib import Path

from ic_gamedata.ability_cooldowns import ability_status, ready_ability_keys


class AbilityCooldownTests(unittest.TestCase):

    @classmethod

    def setUpClass(cls) -> None:

        path = Path(__file__).resolve().parent.parent / "webRequestLog_example.json"

        cls.payload = json.loads(path.read_text(encoding="utf-8"))



    def test_ready_keys_skip_on_cooldown(self) -> None:

        keys = ready_ability_keys(self.payload)

        # Gale (seat 1, ult 745) and Raistlin (seat 2, ult 941) are on cooldown in example

        self.assertNotIn("1", keys)

        self.assertNotIn("2", keys)

        # Spurt ready

        self.assertIn("3", keys)

        self.assertIsInstance(keys, list)



    def test_unmapped_hero_is_not_ready(self) -> None:

        payload = json.loads(json.dumps(self.payload))

        inst = next(i for i in payload["details"]["game_instances"] if int(i["game_instance_id"]) == 1)

        inst["hero_in_seats"]["4"] = 9999

        keys, status = ability_status(payload)

        self.assertNotIn("4", keys)

        self.assertIn("4: onbekend", status)



    def test_unmapped_hero_not_ready_without_events(self) -> None:

        payload = json.loads(json.dumps(self.payload))

        payload["details"]["events_details"] = {"champion_details": []}

        # Remove seed entries for Gale/Raistlin to simulate unknown mapping

        inst = next(i for i in payload["details"]["game_instances"] if int(i["game_instance_id"]) == 1)

        inst["hero_in_seats"]["1"] = 9998

        inst["hero_in_seats"]["2"] = 9997

        keys, status = ability_status(payload)

        self.assertNotIn("1", keys)

        self.assertNotIn("2", keys)

        self.assertIn("1: onbekend", status)

        self.assertIn("2: onbekend", status)



    def test_status_shows_cooldown_seconds(self) -> None:

        keys, status = ability_status(self.payload)

        self.assertIn("1: 26s", status)

        self.assertIn("2: 35s", status)

        self.assertIn("3: klaar", status)

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





if __name__ == "__main__":

    unittest.main()

