"""Liar's Night 2026 rebalance coverage for Avren, Brig, and Dob."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from ic_gamedata.champion_role_advice import get_role_advice
from ic_gamedata.specialization_engine import dynamic_default_ids
from ic_gamedata.specializations import SpecializationOption, load_specialization_rules


class LiarsNightRebalanceTests(unittest.TestCase):
    def test_avren_specs_replaced(self) -> None:
        rules = load_specialization_rules()
        hero = (rules.get("heroes") or {})["51"]
        ids = {int(o["upgrade_id"]) for o in hero["options"]}
        self.assertEqual(ids, {20700, 20701, 20702, 20703, 20704, 20705})
        self.assertTrue({3095, 3098, 3099}.isdisjoint(ids))
        advice = get_role_advice(51, "support")
        assert advice is not None
        self.assertIn(20700, advice.specialization_ids)

    def test_brig_new_upgrade_ids(self) -> None:
        rules = load_specialization_rules()
        hero = (rules.get("heroes") or {})["90"]
        ids = {int(o["upgrade_id"]) for o in hero["options"]}
        self.assertEqual(ids, {20713, 20714})
        advice = get_role_advice(90, "support")
        assert advice is not None
        self.assertIn(20713, advice.specialization_ids)

    def test_dob_three_specs_and_handler(self) -> None:
        rules = load_specialization_rules()
        hero = (rules.get("heroes") or {})["105"]
        names = [o["name"] for o in hero["options"]]
        self.assertEqual(
            names,
            ["Befriend the Magical", "Befriend the Friendly", "Befriend the Quick"],
        )
        self.assertNotIn("Befriend Everybody!", names)

        options = [
            SpecializationOption(20926, "Befriend the Magical", 160, 0),
            SpecializationOption(20927, "Befriend the Friendly", 160, 0),
            SpecializationOption(20928, "Befriend the Quick", 160, 0),
        ]
        with patch(
            "ic_gamedata.specialization_engine.dob_qualified_counts",
            return_value=(2, 5, 1, 0),
        ):
            ids, reason = dynamic_default_ids(105, {105, 1, 2, 3}, known_options=options)
        self.assertEqual(ids, [20927])
        self.assertIn("Friendly", reason)


if __name__ == "__main__":
    unittest.main()
