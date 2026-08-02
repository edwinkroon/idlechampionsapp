"""Tests for buff name resolution."""

from __future__ import annotations

import unittest

from ic_gamedata.buff_names import buff_name_map_from_payload, build_buff_name_map


class BuffNamesTests(unittest.TestCase):
    def test_event_promo_buff_title_from_payload(self) -> None:
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
            },
            "defines": {
                "boon_buff_defines": [
                    {"id": 5, "effect_key": "time_scale"},
                ]
            },
        }
        names = buff_name_map_from_payload(payload)
        self.assertEqual(names.get(2271), "Renown Weekend")
        self.assertEqual(names.get(5), "Speed potion")

    def test_build_map_never_uses_raw_id(self) -> None:
        from ic_gamedata.buff_names import buff_display_name

        payload = {
            "details": {
                "event_details": [
                    {
                        "name": "Test Event",
                        "details": {"buff_id": 9999, "promo_buff_title": "Test Event Buff"},
                    }
                ]
            }
        }
        self.assertEqual(buff_display_name(9999, payload), "Test Event Buff")
        self.assertEqual(buff_display_name(8888, payload), "Onbekende buff")
        self.assertNotIn("8888", build_buff_name_map(payload).get(8888, ""))


if __name__ == "__main__":
    unittest.main()
