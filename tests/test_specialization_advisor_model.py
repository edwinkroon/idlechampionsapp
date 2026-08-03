"""Tests for specialization advisor models and mapping fixes."""

from __future__ import annotations

import unittest

from ic_gamedata.specialization_advisor_model import (
    advisor_model_for_hero,
    clear_specialization_advisor_models_cache,
    load_specialization_advisor_models,
    preferred_ids_for_run_goal,
)
from ic_gamedata.specialization_models import SpecializationOption
from ic_gamedata.specialization_rules.route_mapper import (
    clear_route_override_cache,
    map_label_to_upgrade_id,
)


class SpecializationAdvisorModelTests(unittest.TestCase):
    def setUp(self) -> None:
        clear_specialization_advisor_models_cache()
        clear_route_override_cache()

    def test_models_file_loads_curated_heroes(self) -> None:
        models = load_specialization_advisor_models()
        self.assertIn(3, models)
        self.assertFalse(models[3].review_needed)
        self.assertEqual(models[3].safe_default.upgrade_id if models[3].safe_default else None, 44)

    def test_celeste_safe_default_war_domain(self) -> None:
        model = advisor_model_for_hero(2)
        self.assertIsNotNone(model)
        assert model is not None
        self.assertFalse(model.review_needed)
        self.assertEqual(model.safe_default.upgrade_id if model.safe_default else None, 29)
        self.assertEqual(
            preferred_ids_for_run_goal(model, run_goal=None),
            [29],
        )

    def test_calliope_safe_default_valor(self) -> None:
        model = advisor_model_for_hero(5)
        self.assertIsNotNone(model)
        assert model is not None
        self.assertFalse(model.review_needed)
        self.assertEqual(model.safe_default.upgrade_id if model.safe_default else None, 75)

    def test_shandie_safe_and_farm_criminal_contacts(self) -> None:
        model = advisor_model_for_hero(47)
        self.assertIsNotNone(model)
        assert model is not None
        self.assertFalse(model.review_needed)
        self.assertEqual(model.safe_default.upgrade_id if model.safe_default else None, 9732)
        self.assertEqual(
            preferred_ids_for_run_goal(model, run_goal="speed_farm"),
            [9732],
        )

    def test_hitch_high_cha_maps_to_charismatic(self) -> None:
        opts = [
            SpecializationOption(386, "More Daggers", 160, 0),
            SpecializationOption(391, "Charismatic", 160, 0),
        ]
        self.assertEqual(
            map_label_to_upgrade_id("High Cha route", opts, champion_name="Hitch"),
            391,
        )

    def test_krond_damage_maps_to_eldritch_strike_not_war_magic(self) -> None:
        opts = [
            SpecializationOption(17242, "Eldritch Strike", 150, 1),
            SpecializationOption(17243, "Power Behind the Throne", 150, 1),
            SpecializationOption(17244, "War Magic", 150, 1),
        ]
        self.assertEqual(
            map_label_to_upgrade_id("Damage route", opts, champion_name="Krond", tier_index=1),
            17242,
        )

    def test_evelyn_support_maps_to_compel_duel_not_allies(self) -> None:
        opts = [
            SpecializationOption(12210, "Fighting Style: Protection", 240, 0),
            SpecializationOption(12211, "Compel Duel", 240, 0),
            SpecializationOption(12212, "Lathander's Allies", 240, 0),
        ]
        self.assertEqual(
            map_label_to_upgrade_id("Support route", opts, champion_name="Evelyn"),
            12211,
        )

    def test_shandie_dash_maps_to_criminal_contacts(self) -> None:
        opts = [
            SpecializationOption(9730, "Known Allies", 230, 0),
            SpecializationOption(9731, "Alchemist's Fire Expertise", 230, 0),
            SpecializationOption(9732, "Criminal Contacts", 230, 0),
        ]
        self.assertEqual(
            map_label_to_upgrade_id("Dash", opts, champion_name="Shandie"),
            9732,
        )

    def test_batch02_heroes_loaded_without_review(self) -> None:
        models = load_specialization_advisor_models()
        for hero_id in (14, 22, 28, 34, 65, 82, 149, 153):
            self.assertIn(hero_id, models)
            self.assertFalse(models[hero_id].review_needed)

    def test_review_needed_empty_after_resolution(self) -> None:
        from ic_gamedata.specialization_advisor_model import review_needed_models_for_heroes

        models = review_needed_models_for_heroes({3, 2, 47, 6, 7})
        self.assertEqual(models, [])

    def test_deekin_boss_wants_speed_maps(self) -> None:
        opts = [
            SpecializationOption(18860, "Unorthodox Stories", 130, 0),
            SpecializationOption(18861, "DOOOOOM From Afar", 130, 0),
            SpecializationOption(18862, "Troubadour Troupe", 130, 0),
        ]
        self.assertEqual(
            map_label_to_upgrade_id("Boss Wants Speed", opts, champion_name="Deekin"),
            18862,
        )

    def test_omin_gold_and_support_maps(self) -> None:
        opts = [
            SpecializationOption(12304, "Form Ranks", 180, 0),
            SpecializationOption(12305, "Favored Friends", 180, 0),
            SpecializationOption(12306, "Long Term Investments", 180, 0),
        ]
        self.assertEqual(
            map_label_to_upgrade_id("Gold route", opts, champion_name="Omin"),
            12306,
        )
        self.assertEqual(
            map_label_to_upgrade_id("Support route", opts, champion_name="Omin"),
            12305,
        )

    def test_jarlaxle_farm_prefers_bregan(self) -> None:
        model = advisor_model_for_hero(4)
        self.assertIsNotNone(model)
        assert model is not None
        self.assertEqual(preferred_ids_for_run_goal(model, run_goal="gold_farm"), [59])
        self.assertEqual(preferred_ids_for_run_goal(model, run_goal="push"), [58])


if __name__ == "__main__":
    unittest.main()
