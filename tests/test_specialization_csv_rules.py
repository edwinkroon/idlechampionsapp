"""Tests for documentation CSV specialization rules."""

from __future__ import annotations

import csv
import shutil
import tempfile
import unittest
from pathlib import Path

from ic_gamedata.specialization_engine import FormationContext
from ic_gamedata.specialization_models import SpecializationOption
from ic_gamedata.specialization_rules.context_builder import build_evaluation_context
from ic_gamedata.specialization_rules.evaluator import (
    evaluate_specialization,
)
from ic_gamedata.specialization_rules.loader import load_documentation_rules
from ic_gamedata.specialization_rules.models import EvaluationContext
from ic_gamedata.specialization_rules.provenance import classify_rule_provenance
from ic_gamedata.specialization_rules.validator import validate_rule_dataset


def _ctx(
    *,
    hero_id: int,
    hero_name: str,
    seat: int | None,
    run_goal: str,
    evil: int = 0,
    good: int = 0,
    neutral: int = 0,
    magic: int = 0,
    melee: int = 0,
    dwarf_elf: int = 0,
    enemy_type: str | None = None,
    alignment_changed: bool = False,
    enemy_changed: bool = False,
    secondary_bond: bool = False,
) -> EvaluationContext:
    return EvaluationContext(
        hero_id=hero_id,
        hero_name=hero_name,
        seat=seat,
        run_goal=run_goal,
        active_hero_ids=frozenset({hero_id}),
        seat_by_hero={hero_id: seat} if seat is not None else {},
        highest_damage_hero_id=None,
        familiar_count=0,
        evil_count=evil,
        good_count=good,
        neutral_count=neutral,
        magic_count=magic,
        melee_count=melee,
        dwarf_elf_count=dwarf_elf,
        enemy_type=enemy_type,
        adventure_name=None,
        alignment_distribution_changed=alignment_changed,
        enemy_type_changed=enemy_changed,
        secondary_bond_outscores_primary=secondary_bond,
        survival_blocks_progress=run_goal == "survival",
    )


class DocumentationRulesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.doc_dir = Path(__file__).resolve().parent.parent / "documentation"
        cls.dataset = load_documentation_rules(cls.doc_dir)

    def test_dataset_loads_v2_full_as_primary_source(self) -> None:
        self.assertEqual(self.dataset.source, "v2_full")
        self.assertEqual(self.dataset.data_source_version, "v2_full")
        self.assertGreaterEqual(len(self.dataset.rules), 130)
        self.assertEqual(validate_rule_dataset(self.dataset), [])

    def test_authored_rule_classification_deekin(self) -> None:
        deekin = next(rule for rule in self.dataset.rules if rule.champion == "Deekin")
        self.assertEqual(deekin.rule_source_type, "authored")
        self.assertEqual(deekin.default_label, "Boss Wants Speed")
        self.assertEqual(deekin.data_source_version, "v2_full")

    def test_heuristic_rule_classification_evelyn(self) -> None:
        evelyn = next(rule for rule in self.dataset.rules if rule.champion == "Evelyn")
        self.assertEqual(evelyn.rule_source_type, "heuristic")
        self.assertIn("placeholder", evelyn.notes_for_cursor.casefold())

    def test_provenance_classifier_explicit_and_generic(self) -> None:
        self.assertEqual(
            classify_rule_provenance(
                usually_choose="Boss Wants Speed",
                tags=("speed", "farming"),
                notes_for_cursor="default automation/speed pick",
            ),
            "authored",
        )
        self.assertEqual(
            classify_rule_provenance(
                usually_choose="Support route",
                alternative="Other route",
                tags=("support", "generic"),
                notes_for_cursor="placeholder rule; review against champion-specific guide when available",
            ),
            "heuristic",
        )

    def test_speed_farm_briv_prefers_speed_label(self) -> None:
        options = [
            SpecializationOption(1, "Boss Wants Speed", 100, 0),
            SpecializationOption(2, "Tank Route", 100, 0),
        ]
        ctx = _ctx(hero_id=5, hero_name="Briv", seat=5, run_goal="speed_farm")
        advice = evaluate_specialization(ctx, options, self.dataset)
        self.assertIsNotNone(advice)
        assert advice is not None
        self.assertEqual(advice.upgrade_id, 1)
        self.assertEqual(advice.data_source_version, "v2_full")
        self.assertEqual(advice.rule_source_type, "authored")
        self.assertIn("Speed", advice.chosen_label)

    def test_gold_farm_jarlaxle_prefers_gold_label(self) -> None:
        options = [
            SpecializationOption(10, "Piracy", 100, 0),
            SpecializationOption(11, "Damage Route", 100, 0),
        ]
        ctx = _ctx(hero_id=4, hero_name="Jarlaxle", seat=4, run_goal="gold_farm")
        advice = evaluate_specialization(ctx, options, self.dataset)
        self.assertIsNotNone(advice)
        assert advice is not None
        self.assertEqual(advice.upgrade_id, 10)
        self.assertEqual(advice.rule_source_type, "authored")

    def test_formation_dependent_asharra_prefers_bond_label(self) -> None:
        options = [
            SpecializationOption(30, "Potpourri of Bonds", 100, 0),
            SpecializationOption(31, "Support Route", 100, 0),
        ]
        ctx = _ctx(
            hero_id=6,
            hero_name="Asharra",
            seat=6,
            run_goal="push",
            dwarf_elf=4,
        )
        advice = evaluate_specialization(ctx, options, self.dataset)
        self.assertIsNotNone(advice)
        assert advice is not None
        self.assertEqual(advice.upgrade_id, 30)
        self.assertEqual(advice.rule_source_type, "authored")
        self.assertIn("bond", advice.condition_used.casefold())

    def test_heuristic_wyll_returns_lower_confidence_metadata(self) -> None:
        options = [
            SpecializationOption(40, "Pact of the Blade", 100, 0),
            SpecializationOption(41, "Pact of the Tome", 100, 0),
        ]
        ctx = _ctx(hero_id=7, hero_name="Wyll", seat=7, run_goal="generic_progression")
        advice = evaluate_specialization(ctx, options, self.dataset)
        self.assertIsNotNone(advice)
        assert advice is not None
        self.assertEqual(advice.rule_source_type, "heuristic")
        self.assertLessEqual(advice.confidence, 3)

    def test_v3_production_takes_priority_over_v2_full(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in (
                "run_goal_lookup.csv",
                "condition_field_lookup.csv",
                "priority_lookup.csv",
                "manual_review_lookup.csv",
                "specialization_value_lookup.csv",
                "tag_lookup.csv",
                "champion_exception_rules.csv",
                "idle_champions_specialization_ruleset_v2_full.csv",
            ):
                shutil.copy(self.doc_dir / name, root / name)

            with (root / "champion_specialization_rules_v3.csv").open(
                "w", encoding="utf-8", newline=""
            ) as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=[
                        "rule_id",
                        "rule_version",
                        "seat",
                        "champion",
                        "specialization_family",
                        "run_goal",
                        "decision_context",
                        "condition_field",
                        "condition_operator",
                        "condition_value",
                        "machine_default",
                        "machine_alternative",
                        "override_when",
                        "default_confidence",
                        "priority_code",
                        "manual_review_code",
                        "tags",
                        "notes_for_cursor",
                        "advice_pattern",
                        "source_basis",
                        "active",
                    ],
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "rule_id": "seat05_briv_speed",
                        "rule_version": "v3",
                        "seat": "5",
                        "champion": "Briv",
                        "specialization_family": "Speed / Jump",
                        "run_goal": "speed_farm",
                        "decision_context": "speed_farm",
                        "condition_field": "run_goal",
                        "condition_operator": "equals",
                        "condition_value": "speed_farm",
                        "machine_default": "speed_route",
                        "machine_alternative": "tank_route",
                        "override_when": "V3 production override",
                        "default_confidence": "5",
                        "priority_code": "critical",
                        "manual_review_code": "no",
                        "tags": "speed,tank,farming",
                        "notes_for_cursor": "V3 production row",
                        "advice_pattern": "V3 production override",
                        "source_basis": "v3_production",
                        "active": "True",
                    }
                )

            dataset = load_documentation_rules(root)
            self.assertEqual(dataset.source, "v3_production")
            self.assertEqual(dataset.data_source_version, "v3_production")
            options = [
                SpecializationOption(1, "Boss Wants Speed", 100, 0),
                SpecializationOption(2, "Tank Route", 100, 0),
            ]
            ctx = _ctx(hero_id=5, hero_name="Briv", seat=5, run_goal="speed_farm")
            advice = evaluate_specialization(ctx, options, dataset)
            self.assertIsNotNone(advice)
            assert advice is not None
            self.assertEqual(advice.data_source_version, "v3_production")
            self.assertEqual(advice.specialization_key, "speed_route")


class DocumentationIntegrationTests(unittest.TestCase):
    def test_build_evaluation_context_from_formation(self) -> None:
        formation = FormationContext(
            active_hero_ids={6, 7},
            highest_damage_hero_id=6,
            familiar_count=0,
            seat_by_hero={6: 6, 7: 7},
        )
        ctx = build_evaluation_context(
            hero_id=6,
            hero_name="Asharra",
            seat=6,
            run_goal="push",
            formation=formation,
            payload=None,
        )
        self.assertEqual(ctx.hero_name, "Asharra")
        self.assertEqual(ctx.seat, 6)


if __name__ == "__main__":
    unittest.main()
