"""Flint Fireforge (178) specialization and role-advice coverage."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from ic_gamedata.champion_role_advice import get_role_advice
from ic_gamedata.specialization_engine import dynamic_default_ids
from ic_gamedata.specialization_qualified_rules import QualifiedStackOptionRule, QualifiedStackTierRule
from ic_gamedata.specializations import SpecializationOption


def _flint_options() -> list[SpecializationOption]:
    return [
        SpecializationOption(20134, "Fatherly Advice", 90, 0),
        SpecializationOption(20135, "Forged in War", 90, 0),
        SpecializationOption(20136, "Blood of Reorx", 90, 0),
        SpecializationOption(20137, "Craft Maker", 200, 1),
        SpecializationOption(20138, "Foe Breaker", 200, 1),
        SpecializationOption(20139, "Life Taker", 200, 1),
    ]


def _flint_tier0_rule() -> QualifiedStackTierRule:
    return QualifiedStackTierRule(
        hero_id=178,
        hero_name="Flint",
        required_level=90,
        options=(
            QualifiedStackOptionRule(
                upgrade_id=20134,
                name="Fatherly Advice",
                pct=100.0,
                kind="expr",
                expr="age<=40",
                supported=True,
            ),
            QualifiedStackOptionRule(
                upgrade_id=20135,
                name="Forged in War",
                pct=150.0,
                kind="expr",
                expr="HasTag(`heroeslance`)",
                supported=True,
            ),
            QualifiedStackOptionRule(
                upgrade_id=20136,
                name="Blood of Reorx",
                pct=200.0,
                kind="expr",
                expr="HasTag(`dwarf`)",
                supported=True,
            ),
        ),
    )


class FlintSpecializationTests(unittest.TestCase):
    def test_role_advice_embedded(self) -> None:
        advice = get_role_advice(178, "support")
        self.assertIsNotNone(advice)
        assert advice is not None
        self.assertIn("Fatherly Advice", advice.specialization_names)
        self.assertIn(20134, advice.specialization_ids)
        self.assertTrue(advice.formation)
        self.assertIn("Proven Bond", advice.feats)

        gold = get_role_advice(178, "gold")
        assert gold is not None
        self.assertIn("Craft Maker", gold.specialization_names)
        self.assertIn(20137, gold.specialization_ids)

    def test_tier0_prefers_fatherly_advice_with_many_young(self) -> None:
        party = {178, 2, 3, 13, 26, 25, 91, 147, 6}

        def _count(active: set[int], opt: QualifiedStackOptionRule) -> tuple[int, bool]:
            if opt.upgrade_id == 20134:
                return 7, False
            if opt.upgrade_id == 20135:
                return 1, False
            if opt.upgrade_id == 20136:
                return 1, False
            return 0, False

        with (
            patch(
                "ic_gamedata.specialization_qualified_rules.tier_rule_for_hero_level",
                return_value=_flint_tier0_rule(),
            ),
            patch(
                "ic_gamedata.specialization_qualified_counts.count_qualified_heroes",
                side_effect=_count,
            ),
        ):
            ids, reason = dynamic_default_ids(178, party, known_options=_flint_options())
        self.assertEqual(ids[0], 20134)
        self.assertIn("Fatherly Advice", reason)
        self.assertEqual(ids[1], 20138)

    def test_tier0_prefers_blood_of_reorx_for_dwarf_party(self) -> None:
        party = {178, 1, 19, 27, 50, 64, 68, 155, 165}

        def _count(active: set[int], opt: QualifiedStackOptionRule) -> tuple[int, bool]:
            if opt.upgrade_id == 20134:
                return 1, False
            if opt.upgrade_id == 20135:
                return 1, False
            if opt.upgrade_id == 20136:
                return 9, False
            return 0, False

        with (
            patch(
                "ic_gamedata.specialization_qualified_rules.tier_rule_for_hero_level",
                return_value=_flint_tier0_rule(),
            ),
            patch(
                "ic_gamedata.specialization_qualified_counts.count_qualified_heroes",
                side_effect=_count,
            ),
        ):
            ids, reason = dynamic_default_ids(178, party, known_options=_flint_options())
        self.assertEqual(ids[0], 20136)
        self.assertIn("Blood of Reorx", reason)

    def test_tier1_craft_maker_for_gold_goal(self) -> None:
        with patch(
            "ic_gamedata.specialization_qualified_rules.tier_rule_for_hero_level",
            return_value=_flint_tier0_rule(),
        ), patch(
            "ic_gamedata.specialization_qualified_counts.count_qualified_heroes",
            return_value=(0, False),
        ):
            ids, reason = dynamic_default_ids(
                178,
                {178, 1, 2},
                known_options=_flint_options(),
                run_goal="gold",
            )
        self.assertEqual(ids[1], 20137)
        self.assertIn("Craft Maker", reason)

    def test_tier1_life_taker_when_flint_is_bud(self) -> None:
        with patch(
            "ic_gamedata.specialization_qualified_rules.tier_rule_for_hero_level",
            return_value=_flint_tier0_rule(),
        ), patch(
            "ic_gamedata.specialization_qualified_counts.count_qualified_heroes",
            return_value=(0, False),
        ):
            ids, reason = dynamic_default_ids(
                178,
                {178, 1, 2},
                known_options=_flint_options(),
                run_goal="bud",
                bud_hero_id=178,
            )
        self.assertEqual(ids[1], 20139)
        self.assertIn("Life Taker", reason)

    def test_tier1_speed_does_not_pick_craft_maker(self) -> None:
        with patch(
            "ic_gamedata.specialization_qualified_rules.tier_rule_for_hero_level",
            return_value=_flint_tier0_rule(),
        ), patch(
            "ic_gamedata.specialization_qualified_counts.count_qualified_heroes",
            return_value=(0, False),
        ):
            ids, reason = dynamic_default_ids(
                178,
                {178, 1, 2},
                known_options=_flint_options(),
                run_goal="speed_farm",
                bud_hero_id=1,
                highest_damage_hero_id=1,
            )
        self.assertEqual(ids[1], 20138)
        self.assertNotEqual(ids[1], 20137)
        self.assertIn("speed goal", reason)

    def test_tier1_gold_farm_alias_still_craft_maker(self) -> None:
        with patch(
            "ic_gamedata.specialization_qualified_rules.tier_rule_for_hero_level",
            return_value=_flint_tier0_rule(),
        ), patch(
            "ic_gamedata.specialization_qualified_counts.count_qualified_heroes",
            return_value=(0, False),
        ):
            ids, reason = dynamic_default_ids(
                178,
                {178, 1, 2},
                known_options=_flint_options(),
                run_goal="gold_farm",
            )
        self.assertEqual(ids[1], 20137)
        self.assertIn("Craft Maker", reason)


if __name__ == "__main__":
    unittest.main()
