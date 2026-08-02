"""Tests for generic qualified-stack specialization rules."""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest.mock import patch

from ic_gamedata.adventure_restrictions import hero_matches_specialization_expr
from ic_gamedata.specialization_engine import (
    _merge_tier_default_ids,
    dynamic_default_ids,
)
from ic_gamedata.specialization_qualified_counts import (
    count_qualified_heroes,
    hero_matches_qualified_option,
)
from ic_gamedata.specialization_qualified_rules import (
    QualifiedStackOptionRule,
    QualifiedStackTierRule,
    generic_qualified_stack_hero_ids,
    qualified_stack_tiers_by_hero,
)
from ic_gamedata.specialization_stack_audit import audit_qualified_stack_specs
from ic_gamedata.specializations import (
    SpecializationOption,
    load_specialization_rules,
    pending_specializations,
)

BATCH2_HERO_IDS = (14, 59, 71, 116, 121, 122, 123, 124, 125, 144, 161, 165, 171, 174)


BATCH3_HERO_IDS = (80, 31, 139, 140, 160)


class SpecializationQualifiedRulesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        base = Path(__file__).resolve().parent.parent
        cls.payload = json.loads((base / "webRequestLog_example.json").read_text(encoding="utf-8"))
        cls.rules = load_specialization_rules()

    def test_hero_matches_unaffiliated_expr(self) -> None:
        option = QualifiedStackOptionRule(
            upgrade_id=18475,
            name="Found Family",
            pct=125,
            kind="expr",
            expr="HasTag(`unaffiliated`) || HasTag(`fallbacks`)",
            supported=True,
        )
        with patch(
            "ic_gamedata.adventure_restrictions.hero_tags_map_from_cached_definitions",
            return_value={901: ("unaffiliated",), 902: ("companion",)},
        ):
            self.assertTrue(hero_matches_qualified_option(901, option))
            self.assertFalse(hero_matches_qualified_option(902, option))

    def test_count_ranged_attack_filter(self) -> None:
        option = QualifiedStackOptionRule(
            upgrade_id=17084,
            name="Arrow Alliance",
            pct=125,
            kind="target_filter",
            target_filter={"type": "attack_type", "attack": "ranged"},
            supported=True,
        )
        with patch(
            "ic_gamedata.adventure_restrictions.hero_attack_types_map_from_cached_definitions",
            return_value={901: frozenset({"ranged"}), 902: frozenset({"melee"})},
        ):
            count, partial = count_qualified_heroes({901, 902}, option)
        self.assertEqual(count, 1)
        self.assertFalse(partial)

    def test_cazrin_prefers_self_taught_for_melee_party(self) -> None:
        payload = json.loads(json.dumps(self.payload))
        payload["details"]["active_game_instance_id"] = 1
        inst = next(i for i in payload["details"]["game_instances"] if int(i["game_instance_id"]) == 1)
        inst["hero_in_seats"] = {"1": 166, "2": 901, "3": 902, "4": 903}
        payload["details"]["heroes"] = [
            {
                "hero_id": 166,
                "game_instance_id": 1,
                "in_seat": 1,
                "level": 250,
                "specialization_choices": [],
                "upgrades": [],
            }
        ]
        payload["defines"]["upgrade_defines"] = []
        known = [
            SpecializationOption(17678, "Self Taught", 180, 0),
            SpecializationOption(17679, "Ancestor's Shadow", 180, 0),
        ]
        tier = QualifiedStackTierRule(
            hero_id=166,
            hero_name="Cazrin",
            required_level=180,
            options=(
                QualifiedStackOptionRule(
                    17678,
                    "Self Taught",
                    100,
                    "expr",
                    "HasTag(`fallbacks`) || has_base_attack_dmg_type_melee || has_base_attack_dmg_type_ranged",
                ),
                QualifiedStackOptionRule(
                    17679,
                    "Ancestor's Shadow",
                    100,
                    "expr",
                    "HasTag(`fallbacks`) || HasTag(`good`)",
                ),
            ),
        )
        fake_tags = {
            166: ("fallbacks",),
            901: ("human",),
            902: ("human",),
            903: ("human",),
        }
        fake_types = {
            166: frozenset({"magic"}),
            901: frozenset({"melee"}),
            902: frozenset({"melee"}),
            903: frozenset({"ranged"}),
        }
        with (
            patch("ic_gamedata.specializations._choices_from_cached_definitions", return_value={166: known}),
            patch(
                "ic_gamedata.specialization_qualified_rules.tiers_for_known_options",
                return_value=[tier],
            ),
            patch("ic_gamedata.specialization_engine._hero_tags_map_from_cached_definitions", return_value=fake_tags),
            patch("ic_gamedata.specialization_engine._hero_attack_types_map_from_cached_definitions", return_value=fake_types),
            patch("ic_gamedata.adventure_restrictions.hero_tags_map_from_cached_definitions", return_value=fake_tags),
            patch("ic_gamedata.adventure_restrictions.hero_attack_types_map_from_cached_definitions", return_value=fake_types),
        ):
            pending = pending_specializations(payload, self.rules)
        cazrin_t0 = [
            item
            for item in pending
            if item.hero_id == 166 and item.options and item.options[0].tier_index == 0
        ]
        self.assertEqual(len(cazrin_t0), 1)
        # Self Taught: 166 + 3 melee/ranged = 4; Ancestor's Shadow: 166 only = 1
        self.assertEqual(cazrin_t0[0].desired_upgrade_id, 17678)

    def test_audit_marks_generic_batch_heroes_handled(self) -> None:
        generic_ids = generic_qualified_stack_hero_ids(
            exclude_hero_ids={151, 159, 162, 164, 168}
        )
        self.assertIn(166, generic_ids)
        self.assertIn(15, generic_ids)
        tiers = audit_qualified_stack_specs()
        cazrin = [t for t in tiers if t.hero_id == 166 and t.required_level == 180]
        if cazrin:
            self.assertEqual(cazrin[0].status, "handled")

    def test_batch2_heroes_are_generic_covered(self) -> None:
        generic_ids = generic_qualified_stack_hero_ids()
        for hero_id in BATCH2_HERO_IDS:
            self.assertIn(hero_id, generic_ids, msg=f"hero {hero_id} should be generic-covered")

    def test_warduke_prefers_league_of_malevolence_for_evil_party(self) -> None:
        tier = qualified_stack_tiers_by_hero()[116][250]
        party = {116, 901, 902, 903}
        fake_tags = {
            116: ("evil",),
            901: ("evil",),
            902: ("evil",),
            903: ("chaotic",),
        }
        with patch(
            "ic_gamedata.adventure_restrictions.hero_tags_map_from_cached_definitions",
            return_value=fake_tags,
        ):
            ids, reason = dynamic_default_ids(116, party)
        self.assertIn(9621, ids)
        self.assertIn("League of Malevolence", reason)

    def test_miria_independent_counts_unaffiliated(self) -> None:
        option = next(
            opt for opt in qualified_stack_tiers_by_hero()[121][80].supported_options if opt.upgrade_id == 10672
        )
        fake_tags = {901: ("unaffiliated",), 902: ("acqinc",), 903: ("acqinc", "elf")}
        with patch(
            "ic_gamedata.adventure_restrictions.hero_tags_map_from_cached_definitions",
            return_value=fake_tags,
        ):
            count, partial = count_qualified_heroes({901, 902, 903}, option)
        self.assertEqual(count, 1)
        self.assertFalse(partial)

    def test_anson_partial_tier_prefers_found_family(self) -> None:
        party = {171, 901, 902, 903}
        fake_tags = {
            171: ("fallbacks",),
            901: ("unaffiliated",),
            902: ("unaffiliated",),
            903: ("good",),
        }
        with patch(
            "ic_gamedata.adventure_restrictions.hero_tags_map_from_cached_definitions",
            return_value=fake_tags,
        ):
            ids, reason = dynamic_default_ids(171, party)
        self.assertEqual(ids, [18475])
        self.assertIn("Found Family", reason)

    def test_tasslehoff_old_friends_counts_heroeslance(self) -> None:
        option = next(
            opt for opt in qualified_stack_tiers_by_hero()[174][150].supported_options if opt.upgrade_id == 19239
        )
        fake_tags = {901: ("human",), 902: ("heroeslance",), 903: ("elf",)}
        fake_ages = {901: 25, 902: 30, 903: 30}
        with (
            patch(
                "ic_gamedata.adventure_restrictions.hero_tags_map_from_cached_definitions",
                return_value=fake_tags,
            ),
            patch(
                "ic_gamedata.adventure_restrictions.hero_age_map_from_cached_definitions",
                return_value=fake_ages,
            ),
        ):
            count, partial = count_qualified_heroes({901, 902, 903}, option)
        self.assertEqual(count, 1)
        self.assertFalse(partial)

    def test_presto_junior_juggernauts_excludes_diana(self) -> None:
        option = next(
            opt for opt in qualified_stack_tiers_by_hero()[144][200].supported_options if opt.upgrade_id == 13766
        )
        fake_ages = {144: 18, 146: 19, 901: 19, 902: 30}
        with patch(
            "ic_gamedata.adventure_restrictions.hero_age_map_from_cached_definitions",
            return_value=fake_ages,
        ):
            self.assertFalse(hero_matches_qualified_option(146, option))
            count, partial = count_qualified_heroes({144, 146, 901}, option)
        self.assertEqual(count, 2)
        self.assertFalse(partial)

    def test_batch3_expr_normalization(self) -> None:
        with patch(
            "ic_gamedata.adventure_restrictions.hero_age_map_from_cached_definitions",
            return_value={901: 18, 146: 19},
        ):
            self.assertTrue(hero_matches_specialization_expr(901, "min_age <= 20 && hero_id != 146"))
            self.assertFalse(hero_matches_specialization_expr(146, "min_age <= 20 && hero_id != 146"))
        with patch(
            "ic_gamedata.adventure_restrictions.hero_roles_map_from_champion_config",
            return_value={901: ("dps",)},
        ):
            self.assertTrue(hero_matches_specialization_expr(901, "as_int(HasTag(`dps`))"))
        with patch(
            "ic_gamedata.adventure_restrictions.hero_tags_map_from_cached_definitions",
            return_value={901: ("tabaxi",)},
        ):
            self.assertTrue(hero_matches_specialization_expr(901, "has_non_standard_race"))
        with patch(
            "ic_gamedata.adventure_restrictions.hero_tags_map_from_cached_definitions",
            return_value={901: ("speed",)},
        ):
            self.assertTrue(hero_matches_specialization_expr(901, "has_tag_speed"))
        with patch(
            "ic_gamedata.adventure_restrictions.hero_ability_scores_map_from_cached_definitions",
            return_value={901: {"str": 14, "dex": 8, "con": 12, "int": 10, "wis": 16, "cha": 11}},
        ):
            self.assertTrue(hero_matches_specialization_expr(901, "clamp(wis+1-min_stat_amount,0,1)"))
            self.assertFalse(hero_matches_specialization_expr(901, "clamp(min_stat_amount+1-str,0,1)"))

    def test_batch3_heroes_are_generic_covered(self) -> None:
        qualified_stack_tiers_by_hero.cache_clear()
        generic_ids = generic_qualified_stack_hero_ids()
        for hero_id in (80, 140):
            self.assertIn(hero_id, generic_ids, msg=f"hero {hero_id} should be generic-covered")

    def test_mehen_prefers_found_family_with_dragonborn_party(self) -> None:
        qualified_stack_tiers_by_hero.cache_clear()
        party = {80, 901, 902, 903}
        fake_tags = {80: ("dragonborn",), 901: ("dragonborn",), 902: ("dragonborn",), 903: ("human",)}
        fake_ages = {903: 18}
        with (
            patch("ic_gamedata.adventure_restrictions.hero_tags_map_from_cached_definitions", return_value=fake_tags),
            patch("ic_gamedata.adventure_restrictions.hero_age_map_from_cached_definitions", return_value=fake_ages),
            patch("ic_gamedata.adventure_restrictions.hero_roles_map_from_champion_config", return_value={903: ("dps",)}),
            patch("ic_gamedata.specialization_engine._hero_tags_map_from_cached_definitions", return_value=fake_tags),
        ):
            ids, _reason = dynamic_default_ids(80, party)
        self.assertEqual(ids, [16152])

    def test_merge_tier_default_ids_combines_multiply_and_smart(self) -> None:
        options = [
            SpecializationOption(100, "Tier0 A", 120, 0),
            SpecializationOption(101, "Tier0 B", 120, 0),
            SpecializationOption(200, "Tier1 C", 220, 1),
            SpecializationOption(201, "Tier1 D", 220, 1),
        ]
        merged = _merge_tier_default_ids(options, [100], [201])
        self.assertEqual(merged, [100, 201])


if __name__ == "__main__":
    unittest.main()
