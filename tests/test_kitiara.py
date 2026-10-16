"""Kitiara Uth Matar (180) specialization and role-advice coverage."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from ic_gamedata.champion_role_advice import get_role_advice
from ic_gamedata.specialization_engine import dynamic_default_ids
from ic_gamedata.specialization_qualified_rules import (
    QualifiedStackOptionRule,
    QualifiedStackTierRule,
)
from ic_gamedata.specializations import SpecializationOption, load_specialization_rules


def _kitiara_options() -> list[SpecializationOption]:
    return [
        SpecializationOption(20602, "Loyal to Her Past", 300, 0),
        SpecializationOption(20603, "Loyal to Herself", 300, 0),
        SpecializationOption(20604, "Loyal to Darkness", 300, 0),
    ]


def _kitiara_tier_rule() -> QualifiedStackTierRule:
    return QualifiedStackTierRule(
        hero_id=180,
        hero_name="Kitiara",
        required_level=300,
        options=(
            QualifiedStackOptionRule(
                upgrade_id=20602,
                name="Loyal to Her Past",
                pct=100.0,
                kind="expr",
                expr="HasTag(`heroeslance`)",
                supported=True,
            ),
            QualifiedStackOptionRule(
                upgrade_id=20603,
                name="Loyal to Herself",
                pct=100.0,
                kind="expr",
                expr="HasTag(`unaffiliated`)",
                supported=True,
            ),
            QualifiedStackOptionRule(
                upgrade_id=20604,
                name="Loyal to Darkness",
                pct=100.0,
                kind="expr",
                expr="HasTag(`evil`)",
                supported=True,
            ),
        ),
    )


class KitiaraSpecializationTests(unittest.TestCase):
    def test_in_specializations_config(self) -> None:
        rules = load_specialization_rules()
        hero = (rules.get("heroes") or {}).get("180")
        self.assertIsInstance(hero, dict)
        assert hero is not None
        self.assertEqual(hero.get("name"), "Kitiara")
        ids = {int(o["upgrade_id"]) for o in hero.get("options") or []}
        self.assertEqual(ids, {20602, 20603, 20604})

    def test_role_advice_embedded(self) -> None:
        advice = get_role_advice(180, "support")
        self.assertIsNotNone(advice)
        assert advice is not None
        self.assertTrue(advice.specialization_names)
        self.assertTrue(advice.formation)
        self.assertIn("Merciless Resolve", advice.formation)

        tank = get_role_advice(180, "tank")
        assert tank is not None
        self.assertTrue(tank.feats)

    def test_generic_stack_prefers_unaffiliated(self) -> None:
        party = {180, 4, 51, 90, 105}

        def _count(active: set[int], opt: QualifiedStackOptionRule) -> tuple[int, bool]:
            if opt.upgrade_id == 20602:
                return 1, False
            if opt.upgrade_id == 20603:
                return 5, False
            if opt.upgrade_id == 20604:
                return 2, False
            return 0, False

        with (
            patch(
                "ic_gamedata.specialization_qualified_rules.tier_rule_for_hero_level",
                return_value=_kitiara_tier_rule(),
            ),
            patch(
                "ic_gamedata.specialization_qualified_counts.count_qualified_heroes",
                side_effect=_count,
            ),
        ):
            ids, reason = dynamic_default_ids(180, party, known_options=_kitiara_options())
        self.assertEqual(ids[0], 20603)
        self.assertIn("Loyal to Herself", reason)


if __name__ == "__main__":
    unittest.main()
