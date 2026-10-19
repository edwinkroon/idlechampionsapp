"""Tests for adventure champion restriction filtering."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from ic_gamedata.adventure_restrictions import (
    AdventureRosterFilter,
    allowed_hero_ids,
    build_adventure_roster_filter,
    evaluate_heroes_against_filter,
    filter_allowed_hero_names,
    is_hero_allowed,
    restriction_summary,
    structured_stat_gates,
)


def _mock_adventure(adventure_id: int, *, restrictions_text: str = "", game_changes: list | None = None) -> dict:
    return {
        "defines": {
            "adventure_defines": [
                {
                    "id": adventure_id,
                    "restrictions_text": restrictions_text,
                    "game_changes": game_changes or [],
                }
            ]
        }
    }


class AdventureRestrictionsTests(unittest.TestCase):
    def test_support_only_adventure_blocks_non_support(self) -> None:
        payload = _mock_adventure(
            736,
            restrictions_text="Only Champions with the Support tag can be used.",
            game_changes=[
                {
                    "type": "only_allow_crusaders",
                    "by_tags": {"tags": "support"},
                }
            ],
        )
        filt = build_adventure_roster_filter(payload, 736)
        self.assertTrue(is_hero_allowed(2, filt))  # Celeste: support role
        self.assertFalse(is_hero_allowed(4, filt))  # Jarlaxle: dps/gold
        self.assertFalse(is_hero_allowed(8, filt))  # Delina: dps only

    def test_no_tanks_adventure_blocks_tanks(self) -> None:
        payload = _mock_adventure(
            474,
            restrictions_text="Champions with the tanking role can not be used.",
            game_changes=[
                {
                    "type": "only_allow_crusaders",
                    "by_tags": {"tags": "!tanking"},
                }
            ],
        )
        filt = build_adventure_roster_filter(payload, 474)
        self.assertFalse(is_hero_allowed(3, filt))  # Nayeli: tank
        self.assertTrue(is_hero_allowed(1, filt))  # Bruenor: support

    def test_disallow_tanks(self) -> None:
        payload = _mock_adventure(
            1483,
            game_changes=[
                {
                    "type": "disallow_crusaders",
                    "by_tags": {"tags": "tanking"},
                }
            ],
        )
        filt = build_adventure_roster_filter(payload, 1483)
        self.assertFalse(is_hero_allowed(3, filt))

    def test_min_str_requirement(self) -> None:
        payload = _mock_adventure(
            974,
            game_changes=[
                {
                    "type": "only_allow_crusaders",
                    "by_stat": {
                        "stats": [{"stat": "str", "comp": ">=", "value": 16}],
                    },
                }
            ],
        )
        filt = build_adventure_roster_filter(payload, 974)
        fake_scores = {
            1: {"str": 18, "dex": 10},
            8: {"str": 10, "dex": 14},
        }
        with patch(
            "ic_gamedata.adventure_restrictions.hero_ability_scores_map_from_cached_definitions",
            return_value=fake_scores,
        ):
            self.assertTrue(is_hero_allowed(1, filt))
            self.assertFalse(is_hero_allowed(8, filt))

    def test_allow_expr_good_or_melee(self) -> None:
        payload = _mock_adventure(
            100,
            game_changes=[
                {
                    "type": "only_allow_crusaders",
                    "by_expr": {
                        "expr": "HasTag(`good`) || has_base_attack_dmg_type_melee",
                    },
                }
            ],
        )
        filt = build_adventure_roster_filter(payload, 100)
        fake_tags = {1: ("good", "buffer"), 8: ("evil",)}
        fake_attacks = {3: frozenset({"melee"})}
        with patch(
            "ic_gamedata.adventure_restrictions.hero_tags_map_from_cached_definitions",
            return_value=fake_tags,
        ), patch(
            "ic_gamedata.adventure_restrictions.hero_attack_types_map_from_cached_definitions",
            return_value=fake_attacks,
        ):
            self.assertTrue(is_hero_allowed(1, filt))
            self.assertFalse(is_hero_allowed(8, filt))
            self.assertTrue(is_hero_allowed(3, filt))

    def test_filter_bench_suggestions_respects_restrictions(self) -> None:
        filt = AdventureRosterFilter(required_tags={"support"})
        owned = [
            (1, "Bruenor", ("support",), ("buffer",)),
            (4, "Jarlaxle", ("dps", "gold"), ("gold",)),
            (2, "Celeste", ("healer", "support"), ("buffer",)),
        ]
        names = filter_allowed_hero_names(owned, {2}, filt, limit=5)
        self.assertEqual(names, ["Bruenor"])

    def test_exempt_hero_from_force_use_expr(self) -> None:
        filt = AdventureRosterFilter(
            allow_exprs=["hero_id == 173 || is_any_upgrade_positional"],
            has_unknown_rules=True,
        )
        self.assertTrue(is_hero_allowed(173, filt))

    def test_unrestricted_adventure_allows_all(self) -> None:
        payload = _mock_adventure(14, restrictions_text="Your heroes do three times more damage")
        filt = build_adventure_roster_filter(payload, 14)
        self.assertTrue(is_hero_allowed(1, filt))
        self.assertTrue(is_hero_allowed(3, filt))

    def test_trials_unavailable_hero_ids(self) -> None:
        payload = _mock_adventure(14)
        payload["details"] = {"trials_data": {"unavailable_hero_ids": [1, 3]}}
        filt = build_adventure_roster_filter(payload, 14)
        self.assertFalse(is_hero_allowed(1, filt))
        self.assertFalse(is_hero_allowed(3, filt))
        self.assertTrue(is_hero_allowed(2, filt))

    def test_api_game_changes_take_priority_over_text(self) -> None:
        payload = _mock_adventure(
            736,
            restrictions_text="Only Champions with the Support tag can be used.",
            game_changes=[
                {
                    "type": "only_allow_crusaders",
                    "by_tags": {"tags": "support"},
                }
            ],
        )
        filt = build_adventure_roster_filter(payload, 736)
        self.assertTrue(filt.uses_api_game_changes)

    def test_allowed_hero_ids_subset(self) -> None:
        filt = AdventureRosterFilter(required_tags={"support"})
        allowed = allowed_hero_ids([1, 2, 4, 8], filt)
        self.assertIn(1, allowed)
        self.assertIn(2, allowed)
        self.assertNotIn(4, allowed)
        self.assertNotIn(8, allowed)

    def test_patron_strahd_blocks_bruenor(self) -> None:
        payload = _mock_adventure(14)
        payload["details"] = {
            "active_game_instance_id": "1",
            "game_instances": [
                {
                    "game_instance_id": 1,
                    "current_adventure_id": 14,
                    "current_patron_id": 3,
                }
            ],
        }
        filt = build_adventure_roster_filter(payload, 14)
        self.assertIn(1, filt.patron_blocked_hero_ids)
        self.assertFalse(is_hero_allowed(1, filt))

    def test_patron_mirt_allows_bruenor(self) -> None:
        payload = _mock_adventure(14)
        payload["details"] = {
            "active_game_instance_id": "1",
            "game_instances": [
                {
                    "game_instance_id": 1,
                    "current_adventure_id": 14,
                    "current_patron_id": 1,
                }
            ],
        }
        filt = build_adventure_roster_filter(payload, 14)
        self.assertNotIn(1, filt.patron_blocked_hero_ids)
        self.assertTrue(is_hero_allowed(1, filt))

    def test_formation_trust_allows_active_formation_heroes(self) -> None:
        filt = AdventureRosterFilter(banned_tags={"event"})
        self.assertFalse(is_hero_allowed(159, filt))
        self.assertTrue(is_hero_allowed(159, filt, formation_hero_ids=frozenset({159})))

    def test_reserved_formation_seats_from_slot_escort(self) -> None:
        from ic_gamedata.adventure_restrictions import (
            player_formation_capacity,
            reserved_formation_seats,
        )

        payload = _mock_adventure(
            563,
            game_changes=[
                {
                    "type": "slot_escort",
                    "slot_ids": [8, 6, 7],
                }
            ],
        )
        payload["details"] = {
            "active_game_instance_id": 1,
            "game_instances": [
                {
                    "game_instance_id": 1,
                    "current_adventure_id": 563,
                    "hero_in_seats": {
                        "1": 67,
                        "3": 4,
                        "5": 106,
                        "6": 86,
                        "7": 13,
                        "9": 159,
                        "10": 177,
                        "12": 22,
                    },
                    "formation": [67, 4, 159, 13, 86, 106, -1, -1, -1],
                }
            ],
            "heroes": [
                {"hero_id": hid, "in_seat": 1, "game_instance_id": 1, "owned": 1}
                for hid in (67, 4, 159, 13, 86, 106)
            ],
        }
        self.assertEqual(reserved_formation_seats(payload, 563), frozenset({6, 7, 8}))
        self.assertEqual(player_formation_capacity(payload, 563), 6)

    def test_player_formation_capacity_without_npc_slots(self) -> None:
        from ic_gamedata.adventure_restrictions import player_formation_capacity

        payload = _mock_adventure(14)
        payload["details"] = {
            "active_game_instance_id": 1,
            "game_instances": [
                {
                    "game_instance_id": 1,
                    "current_adventure_id": 14,
                    "formation": [1, 2, 3, 4, 5, 6, 7, 8, 9],
                }
            ],
        }
        self.assertEqual(player_formation_capacity(payload, 14), 9)

    def test_player_formation_filled_count_from_grid(self) -> None:
        from ic_gamedata.adventure_restrictions import player_formation_filled_count

        payload = _mock_adventure(14)
        payload["details"] = {
            "active_game_instance_id": 1,
            "game_instances": [
                {
                    "game_instance_id": 1,
                    "current_adventure_id": 14,
                    "formation": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
                }
            ],
        }
        self.assertEqual(player_formation_filled_count(payload), 10)

    def test_int_lte_11_inclusive_bounds(self) -> None:
        payload = _mock_adventure(
            9001,
            game_changes=[
                {
                    "type": "only_allow_crusaders",
                    "by_stat": {
                        "stats": [{"stat": "int", "comp": "<=", "value": 11}],
                    },
                }
            ],
        )
        filt = build_adventure_roster_filter(payload, 9001)
        scores = {1: {"int": 10}, 2: {"int": 11}, 3: {"int": 12}}
        with patch(
            "ic_gamedata.adventure_restrictions.hero_ability_scores_map_from_cached_definitions",
            return_value=scores,
        ):
            self.assertTrue(is_hero_allowed(1, filt))
            self.assertTrue(is_hero_allowed(2, filt))
            self.assertFalse(is_hero_allowed(3, filt))

    def test_int_gte_11_inclusive_bounds(self) -> None:
        payload = _mock_adventure(
            9002,
            game_changes=[
                {
                    "type": "only_allow_crusaders",
                    "by_stat": {
                        "stats": [{"stat": "int", "comp": ">=", "value": 11}],
                    },
                }
            ],
        )
        filt = build_adventure_roster_filter(payload, 9002)
        scores = {1: {"int": 10}, 2: {"int": 11}, 3: {"int": 12}}
        with patch(
            "ic_gamedata.adventure_restrictions.hero_ability_scores_map_from_cached_definitions",
            return_value=scores,
        ):
            self.assertFalse(is_hero_allowed(1, filt))
            self.assertTrue(is_hero_allowed(2, filt))
            self.assertTrue(is_hero_allowed(3, filt))

    def test_exclusive_comparators_not_swapped_with_inclusive(self) -> None:
        lt_payload = _mock_adventure(
            9003,
            game_changes=[
                {
                    "type": "only_allow_crusaders",
                    "by_stat": {
                        "stats": [{"stat": "int", "comp": "<", "value": 11}],
                    },
                }
            ],
        )
        gt_payload = _mock_adventure(
            9004,
            game_changes=[
                {
                    "type": "only_allow_crusaders",
                    "by_stat": {
                        "stats": [{"stat": "int", "comp": ">", "value": 11}],
                    },
                }
            ],
        )
        scores = {1: {"int": 10}, 2: {"int": 11}, 3: {"int": 12}}
        with patch(
            "ic_gamedata.adventure_restrictions.hero_ability_scores_map_from_cached_definitions",
            return_value=scores,
        ):
            lt = build_adventure_roster_filter(lt_payload, 9003)
            self.assertTrue(is_hero_allowed(1, lt))
            self.assertFalse(is_hero_allowed(2, lt))
            self.assertFalse(is_hero_allowed(3, lt))
            gt = build_adventure_roster_filter(gt_payload, 9004)
            self.assertFalse(is_hero_allowed(1, gt))
            self.assertFalse(is_hero_allowed(2, gt))
            self.assertTrue(is_hero_allowed(3, gt))

    def test_mental_gymnastics_int_max_blocks_melf_and_dynaheir(self) -> None:
        """Regression: INT 11 or less must not be labeled/evaluated as Min. INT 11."""
        adventure_id = 1617
        payload = _mock_adventure(
            adventure_id,
            restrictions_text=(
                "You may only use Champions with an Intelligence of 11 or less."
            ),
            game_changes=[
                {
                    "type": "only_allow_crusaders",
                    "by_stat": {
                        "stats": [{"stat": "int", "comp": "<=", "value": 11}],
                    },
                }
            ],
        )
        payload["details"] = {
            "active_game_instance_id": 1,
            "game_instances": [
                {
                    "game_instance_id": 1,
                    "current_adventure_id": adventure_id,
                    "current_patron_id": 1,  # Mirt
                }
            ],
        }
        # Melf=59 INT19, Dynaheir=145 INT17, low-INT bench=1 INT10.
        scores = {
            59: {"int": 19, "str": 10},
            145: {"int": 17, "str": 10},
            1: {"int": 10, "str": 14},
            12: {"int": 11, "str": 10},
        }
        with patch(
            "ic_gamedata.adventure_restrictions.hero_ability_scores_map_from_cached_definitions",
            return_value=scores,
        ):
            filt = build_adventure_roster_filter(payload, adventure_id)
            summary = restriction_summary(filt) or ""
            notes = " · ".join(filt.active_notes)
            self.assertNotIn("Min. INT 11", summary)
            self.assertNotIn("Min. INT 11", notes)
            self.assertTrue(
                "Max. INT 11" in summary or "Max. INT 11" in notes,
                msg=f"expected Max. INT 11 in summary/notes, got: {summary!r}",
            )
            gates = structured_stat_gates(filt)
            hard_max = [
                g
                for g in gates
                if g.get("stat") == "int" and g.get("operator") == "<="
            ]
            self.assertTrue(hard_max)
            self.assertEqual(hard_max[0].get("scope"), "hard_max")

            self.assertFalse(is_hero_allowed(59, filt))
            self.assertFalse(is_hero_allowed(145, filt))
            self.assertTrue(is_hero_allowed(1, filt))
            self.assertTrue(is_hero_allowed(12, filt))

            rows = {
                row["champion_id"]: row
                for row in evaluate_heroes_against_filter([59, 145, 1, 12], filt)
            }
            self.assertEqual(rows[59]["status"], "denied")
            self.assertIn("bovengrens", rows[59]["reason"].casefold())
            self.assertEqual(rows[145]["status"], "denied")
            self.assertEqual(rows[1]["status"], "allowed")
            self.assertEqual(rows[12]["status"], "allowed")

    def test_restrictions_text_or_less_parsed_as_max(self) -> None:
        payload = _mock_adventure(
            9005,
            restrictions_text=(
                "You may only use Champions with an Intelligence of 11 or less."
            ),
        )
        filt = build_adventure_roster_filter(payload, 9005)
        scores = {1: {"int": 11}, 2: {"int": 12}}
        with patch(
            "ic_gamedata.adventure_restrictions.hero_ability_scores_map_from_cached_definitions",
            return_value=scores,
        ):
            self.assertTrue(is_hero_allowed(1, filt))
            self.assertFalse(is_hero_allowed(2, filt))
        self.assertIn("Max. INT 11", restriction_summary(filt) or "")

    def test_unknown_comparator_not_silently_allowed_as_min(self) -> None:
        payload = _mock_adventure(
            9006,
            game_changes=[
                {
                    "type": "only_allow_crusaders",
                    "by_stat": {
                        "stats": [{"stat": "int", "comp": "~=", "value": 11}],
                    },
                }
            ],
        )
        filt = build_adventure_roster_filter(payload, 9006)
        self.assertTrue(filt.has_unknown_rules)
        self.assertTrue(filt.has_unevaluable_stat_rules)
        self.assertFalse(filt.ability_score_gates)
        summary = restriction_summary(filt) or ""
        self.assertNotIn("Min. INT 11", summary)
        scores = {1: {"int": 19}}
        with patch(
            "ic_gamedata.adventure_restrictions.hero_ability_scores_map_from_cached_definitions",
            return_value=scores,
        ):
            self.assertFalse(is_hero_allowed(1, filt))
            row = evaluate_heroes_against_filter([1], filt)[0]
            self.assertEqual(row["status"], "unknown")
            self.assertIn("niet evalueerbaar", row["reason"].casefold())

    def test_missing_int_not_silently_allowed_for_max_gate(self) -> None:
        filt = AdventureRosterFilter(ability_score_gates=[("int", "<=", 11)])
        with patch(
            "ic_gamedata.adventure_restrictions.hero_ability_scores_map_from_cached_definitions",
            return_value={1: {"str": 10}},
        ):
            self.assertFalse(is_hero_allowed(1, filt))
            row = evaluate_heroes_against_filter([1], filt)[0]
            self.assertEqual(row["status"], "unknown")
            self.assertIn("onbekend", row["reason"].casefold())

    def test_passing_int_max_can_still_fail_other_restriction(self) -> None:
        filt = AdventureRosterFilter(
            ability_score_gates=[("int", "<=", 11)],
            required_tags={"support"},
        )
        with patch(
            "ic_gamedata.adventure_restrictions.hero_ability_scores_map_from_cached_definitions",
            return_value={4: {"int": 10}},
        ), patch(
            "ic_gamedata.adventure_restrictions.hero_tags_map_from_cached_definitions",
            return_value={4: ("gold",)},
        ), patch(
            "ic_gamedata.adventure_restrictions.hero_roles_map_from_champion_config",
            return_value={4: ("dps", "gold")},
        ), patch(
            "ic_gamedata.adventure_restrictions.hero_tags_map_from_champion_config",
            return_value={4: ()},
        ):
            self.assertFalse(is_hero_allowed(4, filt))

    def test_party_and_external_use_same_evaluator(self) -> None:
        filt = AdventureRosterFilter(ability_score_gates=[("int", "<=", 11)])
        scores = {59: {"int": 19}, 1: {"int": 10}}
        with patch(
            "ic_gamedata.adventure_restrictions.hero_ability_scores_map_from_cached_definitions",
            return_value=scores,
        ):
            party = evaluate_heroes_against_filter([59], filt)
            bench = evaluate_heroes_against_filter([1], filt)
            self.assertEqual(party[0]["status"], "denied")
            self.assertEqual(bench[0]["status"], "allowed")
            self.assertFalse(is_hero_allowed(59, filt))
            self.assertTrue(is_hero_allowed(1, filt))


class RestrictionOverrideScopeTests(unittest.TestCase):
    def test_dark_urge_override_can_allow_despite_int_max(self) -> None:
        from ic_gamedata.formation_ai_advice.mechanics import (
            detect_restriction_override,
            evaluate_restriction_overrides,
        )

        dark = detect_restriction_override(
            mechanical_text=(
                "The Dark Urge is eligible to start in all adventures, even if the "
                "Patron, Variant, or other restrictions would say otherwise."
            ),
            effect_strings=["do_nothing"],
            source_ability_id=14378,
            source_champion_id=146,
        )
        self.assertIsNotNone(dark)
        record = evaluate_restriction_overrides(
            base_status="denied",
            base_reason="INT 16 overschrijdt de toegestane bovengrens van 11.",
            overrides=[dark],
            champion_tags=[],
            tags_known=True,
            campaign_id=1,
            campaign_name="A Grand Tour of the Sword Coast",
        )
        self.assertEqual(record["effective_eligibility"], "allowed")

    def test_volo_campaign_override_in_grand_tour(self) -> None:
        from ic_gamedata.formation_ai_advice.mechanics import (
            detect_restriction_override,
            evaluate_restriction_overrides,
        )

        volo = detect_restriction_override(
            mechanical_text=(
                "Volo can be used in any Grand Tour of the Sword Coast campaign "
                "adventure or variant, even if he would not normally be available "
                "to be used due to variant or patron restrictions."
            ),
            effect_strings=["do_nothing"],
            source_ability_id=16549,
            source_champion_id=159,
        )
        self.assertEqual(volo["kind"], "campaign_scoped_eligibility")
        in_scope = evaluate_restriction_overrides(
            base_status="denied",
            base_reason="INT 15 overschrijdt de toegestane bovengrens van 11.",
            overrides=[volo],
            champion_tags=[],
            tags_known=True,
            campaign_id=1,
            campaign_name="A Grand Tour of the Sword Coast",
        )
        self.assertEqual(in_scope["effective_eligibility"], "allowed")

        out_of_scope = evaluate_restriction_overrides(
            base_status="denied",
            base_reason="INT 15 overschrijdt de toegestane bovengrens van 11.",
            overrides=[volo],
            champion_tags=[],
            tags_known=True,
            campaign_id=3,
            campaign_name="Tomb of Annihilation",
        )
        self.assertEqual(out_of_scope["effective_eligibility"], "denied")

    def test_unverified_override_does_not_auto_allow(self) -> None:
        from ic_gamedata.formation_ai_advice.mechanics import (
            evaluate_restriction_overrides,
        )

        # Prose-only / unverified campaign scope without campaign context.
        fake = {
            "kind": "campaign_scoped_eligibility",
            "source_ability_id": 1,
            "condition": "active_campaign_matches_scope",
            "campaign_scope_text": "Grand Tour of the Sword Coast",
            "evidence": "effect_string_do_nothing+description",
        }
        record = evaluate_restriction_overrides(
            base_status="denied",
            base_reason="INT 19 overschrijdt de toegestane bovengrens van 11.",
            overrides=[fake],
            champion_tags=[],
            tags_known=True,
            campaign_id=None,
            campaign_name=None,
        )
        self.assertEqual(record["effective_eligibility"], "unknown")

    def test_patron_only_reason_still_requires_matching_override(self) -> None:
        """A campaign-scoped override may lift variant/patron blocks in Grand Tour;
        without a verified override, patron denial stays denied.
        """
        from ic_gamedata.formation_ai_advice.mechanics import (
            evaluate_restriction_overrides,
        )

        record = evaluate_restriction_overrides(
            base_status="denied",
            base_reason="patron_blocked",
            overrides=[],
            champion_tags=[],
            tags_known=True,
            campaign_id=1,
            campaign_name="A Grand Tour of the Sword Coast",
        )
        self.assertEqual(record["effective_eligibility"], "denied")

    def test_by_i_levels_least_per_seat(self) -> None:
        """Undergeared: only lowest average ilevel champion per F-seat."""
        payload = {
            "defines": {
                "adventure_defines": [
                    {
                        "id": 1101,
                        "restrictions_text": (
                            "Only valid Champions with the lowest average ilevels "
                            "(average level of items in their equipment loot slots) "
                            "in each bench seat can be used."
                        ),
                        "game_changes": [
                            {
                                "type": "only_allow_crusaders",
                                "by_i_levels": {
                                    "comparison": "least",
                                    "blocked_portrait": 13093,
                                },
                            }
                        ],
                    }
                ]
            },
            "details": {
                "active_game_instance_id": 1,
                "game_instances": [
                    {
                        "game_instance_id": 1,
                        "current_adventure_id": 1101,
                        "current_patron_id": 0,
                        "formation": [1, 3],
                    }
                ],
                "heroes": [
                    {"hero_id": 1, "owned": "1"},
                    {"hero_id": 28, "owned": "1"},  # same seat as Bruenor (1)
                    {"hero_id": 3, "owned": "1"},
                ],
                "loot": [
                    # hero 1: avg 10
                    {"hero_id": 1, "slot_id": 1, "enchant": 9},
                    {"hero_id": 1, "slot_id": 2, "enchant": 9},
                    # hero 28: avg 5 (lowest on seat 1)
                    {"hero_id": 28, "slot_id": 1, "enchant": 4},
                    {"hero_id": 28, "slot_id": 2, "enchant": 4},
                    # hero 3 alone on seat 3
                    {"hero_id": 3, "slot_id": 1, "enchant": 100},
                ],
            },
        }
        with patch(
            "ic_gamedata.specialization_data.hero_seat_id_map_from_cached_definitions",
            return_value={1: 1, 28: 1, 3: 3},
        ):
            filt = build_adventure_roster_filter(payload, 1101)
        self.assertEqual(filt.ilvl_seat_comparison, "least")
        self.assertIsNotNone(filt.ilvl_allowed_hero_ids)
        self.assertIn(28, filt.ilvl_allowed_hero_ids or set())
        self.assertNotIn(1, filt.ilvl_allowed_hero_ids or set())
        self.assertIn(3, filt.ilvl_allowed_hero_ids or set())
        self.assertFalse(is_hero_allowed(1, filt))
        self.assertTrue(is_hero_allowed(28, filt))
        self.assertTrue(is_hero_allowed(3, filt))
        self.assertTrue(
            any("ilevel" in (n or "").casefold() for n in filt.active_notes)
            or any("ilevel" in (t or "").casefold() for t in filt.raw_restriction_texts)
        )

    def test_disallow_negated_or_tags_good_or_evil(self) -> None:
        """Mirt: disallow !(good|evil) → only Good or Evil allowed."""
        from ic_gamedata.adventure_restrictions import _filter_from_by_tags

        filt = _filter_from_by_tags("!(good|evil)", disallow=True)
        self.assertIn("HasTag(`good`) || HasTag(`evil`)", filt.allow_exprs)
        with patch(
            "ic_gamedata.adventure_restrictions._hero_meta",
            side_effect=lambda hid: type(
                "M",
                (),
                {
                    "hero_id": hid,
                    "roles": frozenset(),
                    "tags": frozenset({"good"} if hid == 1 else {"neutral"}),
                    "stats": {},
                    "attack_types": frozenset(),
                    "age": None,
                    "all_tags": frozenset({"good"} if hid == 1 else {"neutral"}),
                },
            )(),
        ):
            self.assertTrue(is_hero_allowed(1, filt))
            self.assertFalse(is_hero_allowed(2, filt))

    def test_all_patron_api_rules_parse(self) -> None:
        """Vajra/Strahd/Zariel/Elminster/Mirt game_changes must all surface."""
        from datetime import datetime, timezone

        from ic_gamedata.adventure_restrictions import (
            _filter_from_by_stat,
            _parse_time_available_rule,
            _resolve_time_available_banned_ids,
        )
        from ic_gamedata.specialization_data import cached_definitions_data

        data = cached_definitions_data()
        patrons = {
            int(p["id"]): p
            for p in (data.get("patron_defines") or [])
            if isinstance(p, dict) and isinstance(p.get("id"), int)
        }
        self.assertIn(1, patrons)
        self.assertIn(2, patrons)
        self.assertIn(3, patrons)
        self.assertIn(4, patrons)
        self.assertIn(5, patrons)

        # Mirt — already covered by tag test; ensure define text is present.
        self.assertIn("Good or Evil", str(patrons[1].get("restrictions_text")))

        # Vajra — CON >= 14 via deny con < 14
        vajra = _filter_from_by_stat(
            [{"stat": "con", "comp": "<", "value": 14}],
            disallow=True,
        )
        self.assertIn(("con", ">=", 14), vajra.ability_score_gates)

        # Strahd — INT >= 13
        strahd = _filter_from_by_stat(
            [{"stat": "int", "comp": "<", "value": 13}],
            disallow=True,
        )
        self.assertIn(("int", ">=", 13), strahd.ability_score_gates)

        # Zariel — pass_any deny comps → AND of allow gates (STR≥10 and CHA≥13)
        zariel = _filter_from_by_stat(
            [
                {"stat": "cha", "comp": "<", "value": 13},
                {"stat": "str", "comp": "<", "value": 10},
            ],
            disallow=True,
            pass_any=True,
        )
        self.assertIn(("cha", ">=", 13), zariel.ability_score_gates)
        self.assertIn(("str", ">=", 10), zariel.ability_score_gates)

        # Elminster — TimeAvailable
        rule = _parse_time_available_rule("TimeAvailable(`days`) > (365 * 3)")
        self.assertIsNotNone(rule)
        assert rule is not None
        self.assertEqual(rule["threshold_days"], 1095)
        self.assertEqual(rule["operator"], ">")

        now = datetime(2026, 10, 18, tzinfo=timezone.utc)
        with patch(
            "ic_gamedata.adventure_restrictions._hero_availability_dates",
            return_value={
                10: datetime(2017, 1, 1, tzinfo=timezone.utc),  # old → banned
                20: datetime(2025, 1, 1, tzinfo=timezone.utc),  # recent → ok
            },
        ), patch(
            "ic_gamedata.adventure_restrictions._payload_now",
            return_value=now,
        ):
            banned = _resolve_time_available_banned_ids({}, rule)
        self.assertIsNotNone(banned)
        self.assertIn(10, banned or set())
        self.assertNotIn(20, banned or set())

        # End-to-end: each patron builds without crashing and records raw text.
        for patron_id, expected_snip in (
            (1, "Good or Evil"),
            (2, "CON"),
            (3, "INT"),
            (4, "STR"),
            (5, "past 3 years"),
        ):
            payload = {
                "defines": {"adventure_defines": []},
                "details": {
                    "active_game_instance_id": 1,
                    "game_instances": [
                        {
                            "game_instance_id": 1,
                            "current_adventure_id": 1,
                            "current_patron_id": patron_id,
                        }
                    ],
                    "heroes": [{"hero_id": 1, "owned": "1"}],
                },
            }
            with patch(
                "ic_gamedata.adventure_restrictions._patron_define",
                return_value=patrons[patron_id],
            ), patch(
                "ic_gamedata.patron_roster.load_patron_roster",
                return_value={1: {"mirt": "available"}},
            ), patch(
                "ic_gamedata.patron_roster.is_hero_allowed_on_patron",
                return_value=True,
            ):
                filt = build_adventure_roster_filter(payload, 1)
            joined = " ".join(filt.raw_restriction_texts + filt.active_notes)
            self.assertTrue(
                expected_snip.casefold() in joined.casefold()
                or any(
                    expected_snip.casefold() in str(g).casefold()
                    for g in filt.ability_score_gates
                )
                or filt.time_available_rule is not None
                or filt.allow_exprs,
                msg=f"patron {patron_id}: missing {expected_snip!r} in {joined!r}",
            )


if __name__ == "__main__":
    unittest.main()
