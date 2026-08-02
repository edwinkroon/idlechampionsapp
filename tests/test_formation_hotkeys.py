"""Tests for Q/W/E formation hotkey resolution."""

from __future__ import annotations

import unittest

from ic_gamedata.gem_farm.formation_hotkeys import (
    format_hotkeys_summary,
    formation_save_names_for_party,
    resolve_formation_hotkeys,
)


class FormationHotkeyTests(unittest.TestCase):
    def _payload(self) -> dict:
        return {
            "details": {
                "modron_saves": {
                    "4": {
                        "formation_saves": {
                            "1": 10,
                            "2": 20,
                            "3": 30,
                        }
                    }
                },
                "game_instances": [
                    {
                        "game_instance_id": 2,
                        "formation_saves_v2_campaign_id": 1,
                        "formation_saves_v2": [
                            {
                                "formation_save_id": 10,
                                "name": "speed progress",
                                "formation": [58, 1, 2],
                            },
                            {
                                "formation_save_id": 20,
                                "name": "stack team",
                                "formation": [58, 3, 4, 5],
                            },
                            {
                                "formation_save_id": 30,
                                "name": "swap team",
                                "formation": [1, 2, 3],
                            },
                        ],
                    },
                    {
                        "game_instance_id": 4,
                        "formation_saves_v2_campaign_id": 1,
                        "formation_saves_v2": [],
                    },
                ],
            }
        }

    def test_resolve_from_campaign_modron(self) -> None:
        payload = {
            "details": {
                "modron_saves": {
                    "1": {"formation_saves": {"1": 10, "2": 99, "3": 30}},
                },
                "game_instances": [
                    {
                        "game_instance_id": 2,
                        "formation_saves_v2_campaign_id": 1,
                        "formation_saves_v2": [
                            {"formation_save_id": 10, "name": "speed progress", "formation": [58, 1]},
                            {"formation_save_id": 30, "name": "swap team", "formation": [1, 2, 3]},
                        ],
                    },
                ],
            }
        }
        hotkeys = resolve_formation_hotkeys(payload, party_index=2)
        assert hotkeys is not None
        self.assertEqual(hotkeys.source, "campaign_1")
        self.assertEqual(hotkeys.slots[0].save_name, "speed progress")
        self.assertEqual(hotkeys.slots[1].save_name, None)
        self.assertEqual(hotkeys.slots[1].save_id, 99)

    def test_resolve_from_fallback_party(self) -> None:
        payload = self._payload()
        payload["details"]["modron_saves"] = {
            "4": {"formation_saves": {"1": 10, "2": 20, "3": 30}},
        }
        hotkeys = resolve_formation_hotkeys(payload, party_index=2)
        self.assertIsNotNone(hotkeys)
        assert hotkeys is not None
        self.assertEqual(hotkeys.slots[0].save_name, "speed progress")
        self.assertEqual(hotkeys.slots[1].save_name, "stack team")

    def test_format_summary(self) -> None:
        hotkeys = resolve_formation_hotkeys(self._payload(), party_index=2)
        text = format_hotkeys_summary(hotkeys)
        self.assertIsNotNone(text)
        assert text is not None
        self.assertIn("Q: speed progress", text)
        self.assertIn("W: stack team", text)

    def test_resolve_from_profile_names(self) -> None:
        payload = self._payload()
        hotkeys = resolve_formation_hotkeys(
            payload,
            party_index=2,
            profile_names=("speed progress", "stack team", "swap team"),
        )
        self.assertIsNotNone(hotkeys)
        assert hotkeys is not None
        self.assertIn("profile", hotkeys.source)
        self.assertEqual(hotkeys.slots[1].save_name, "stack team")

    def test_dropdown_names_fallback_all_parties(self) -> None:
        payload = {
            "details": {
                "game_instances": [
                    {
                        "game_instance_id": 9,
                        "formation_saves_v2_campaign_id": 99,
                        "formation_saves_v2": [],
                    },
                    {
                        "game_instance_id": 2,
                        "formation_saves_v2_campaign_id": 1,
                        "formation_saves_v2": [
                            {"formation_save_id": 10, "name": "speed progress", "formation": [58]},
                        ],
                    },
                ],
            }
        }
        # Unknown/empty party should still list saves from payload.
        names = formation_save_names_for_party(payload, None)
        self.assertIn("speed progress", names)
        names_party = formation_save_names_for_party(payload, 9)
        self.assertIn("speed progress", names_party)

    def test_resolves_save_from_sibling_instance(self) -> None:
        payload = {
            "details": {
                "modron_saves": {
                    "4": {"formation_saves": {"1": 10, "2": 99}},
                },
                "game_instances": [
                    {
                        "game_instance_id": 2,
                        "formation_saves_v2_campaign_id": 1,
                        "formation_saves_v2": [
                            {"formation_save_id": 10, "name": "speed progress", "formation": [58, 1]},
                        ],
                    },
                    {
                        "game_instance_id": 4,
                        "formation_saves_v2_campaign_id": 1,
                        "formation_saves_v2": [
                            {"formation_save_id": 99, "name": "stack team", "formation": [58, 3, 4]},
                        ],
                    },
                ],
            }
        }
        hotkeys = resolve_formation_hotkeys(payload, party_index=2)
        assert hotkeys is not None
        self.assertEqual(hotkeys.slots[0].save_name, "speed progress")
        self.assertEqual(hotkeys.slots[1].save_name, "stack team")


    def test_suggest_formation_names_for_missing_we(self) -> None:
        from ic_gamedata.gem_farm.formation_hotkeys import suggest_formation_names

        names = [
            "speedgemchest2",
            "speedgemnight2-bbeg",
            "speed zonder briv",
            "speed 2.0",
            "push team 2.0",
        ]
        q, w, e = suggest_formation_names(names, known=(None, None, None))
        self.assertEqual(q, "speed 2.0")
        self.assertEqual(w, "speedgemnight2-bbeg")
        self.assertEqual(e, "speed zonder briv")

        q2, w2, e2 = suggest_formation_names(
            names,
            known=("speedgemchest2", None, None),
        )
        self.assertEqual(q2, "speedgemchest2")
        self.assertEqual(w2, "speedgemnight2-bbeg")
        self.assertEqual(e2, "speed zonder briv")


if __name__ == "__main__":
    unittest.main()
