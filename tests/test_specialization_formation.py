"""Shared specialization topology + positional rules + three-goal lanes."""

from __future__ import annotations

import unittest

from ic_gamedata.specialization_advisor_model import (
    AdvisorChoice,
    AdvisorContextFlags,
    SpecializationAdvisorModel,
    normalize_goal_lane,
    preferred_ids_for_run_goal,
)
from ic_gamedata.specialization_engine import FormationContext, dynamic_default_ids
from ic_gamedata.formation_advisor.topology import fallback_seat_column
from ic_gamedata.specialization_formation import (
    bud_column_relation,
    bud_shares_column,
    is_front_seat,
    seat_column,
)
from ic_gamedata.specialization_positional_rules import (
    clear_positional_rules_cache,
    evaluate_positional_rules,
)


class GoalLaneTests(unittest.TestCase):
    def test_normalize_maps_ui_and_aliases(self) -> None:
        self.assertEqual(normalize_goal_lane("bud"), "bud")
        self.assertEqual(normalize_goal_lane("push"), "bud")
        self.assertEqual(normalize_goal_lane("generic_progression"), "bud")
        self.assertEqual(normalize_goal_lane("gold"), "gold")
        self.assertEqual(normalize_goal_lane("gold_farm"), "gold")
        self.assertEqual(normalize_goal_lane("farm"), "gold")
        self.assertEqual(normalize_goal_lane("speed"), "speed")
        self.assertEqual(normalize_goal_lane("speed_farm"), "speed")
        self.assertIsNone(normalize_goal_lane(None))

    def test_speed_does_not_use_farm_default(self) -> None:
        model = SpecializationAdvisorModel(
            hero_id=999,
            name="Test",
            has_dynamic_handler=False,
            advice_model="farm_default",
            safe_default=AdvisorChoice(1, "Safe"),
            push_default=AdvisorChoice(2, "Push"),
            farm_default=AdvisorChoice(3, "FarmGold"),
            bud_default=None,
            gold_default=None,
            speed_default=AdvisorChoice(4, "SpeedPick"),
            conditionals=(),
            context_flags=AdvisorContextFlags(False, False, True),
            explanation_summary="",
            review_needed=False,
            review_reasons=(),
            options_by_tier={},
        )
        self.assertEqual(preferred_ids_for_run_goal(model, run_goal="gold_farm"), [3])
        self.assertEqual(preferred_ids_for_run_goal(model, run_goal="speed_farm"), [4])
        self.assertEqual(preferred_ids_for_run_goal(model, run_goal="bud"), [2])
        self.assertEqual(preferred_ids_for_run_goal(model, run_goal="speed"), [4])

    def test_jarlaxle_three_goals(self) -> None:
        from ic_gamedata.specialization_advisor_model import (
            advisor_model_for_hero,
            clear_specialization_advisor_models_cache,
        )

        clear_specialization_advisor_models_cache()
        model = advisor_model_for_hero(4)
        self.assertIsNotNone(model)
        assert model is not None
        self.assertEqual(preferred_ids_for_run_goal(model, run_goal="bud"), [58])
        self.assertEqual(preferred_ids_for_run_goal(model, run_goal="gold"), [59])
        self.assertEqual(preferred_ids_for_run_goal(model, run_goal="speed"), [59])


class TopologyHelperTests(unittest.TestCase):
    def test_diamond_columns_match_heuristic(self) -> None:
        self.assertEqual(seat_column(1), 0)
        self.assertEqual(seat_column(4), 2)
        self.assertEqual(seat_column(5), 2)
        self.assertTrue(is_front_seat(1))
        self.assertTrue(is_front_seat(9))
        self.assertFalse(is_front_seat(11))

    def test_bud_column_relation(self) -> None:
        seats = {20: 8, 9: 2}  # Regis mid-back, BUD further forward
        self.assertEqual(
            bud_column_relation(
                20,
                seat_by_hero=seats,
                bud_hero_id=9,
            ),
            "ahead",
        )
        self.assertTrue(
            bud_shares_column(
                35,
                seat_by_hero={35: 5, 9: 4},
                bud_hero_id=9,
            )
        )


class PositionalRuleTests(unittest.TestCase):
    def setUp(self) -> None:
        clear_positional_rules_cache()

    def test_vlahnya_via_positional_all_goals(self) -> None:
        seats = {35: 5, 9: 4, 3: 1, 2: 2}
        party = {35, 9, 3, 2}
        for goal in ("bud", "gold", "speed", "gold_farm", "speed_farm"):
            ids, reason = dynamic_default_ids(
                35,
                party,
                seat_by_hero=seats,
                highest_damage_hero_id=9,
                bud_hero_id=9,
                run_goal=goal,
            )
            self.assertEqual(ids, [1658], msg=goal)
            self.assertIn("BUD shares Vlahnya's column", reason)

    def test_regis_ahead_via_positional_tier(self) -> None:
        ctx = FormationContext(
            active_hero_ids={20, 9},
            seat_by_hero={20: 8, 9: 2},
            bud_hero_id=9,
            highest_damage_hero_id=9,
        )
        ids, reason = evaluate_positional_rules(20, ctx)
        self.assertIsNotNone(ids)
        assert ids is not None
        self.assertEqual(ids, [11530])
        self.assertIn("Ahead", reason)

        full, full_reason = dynamic_default_ids(
            20,
            {20, 9},
            seat_by_hero={20: 8, 9: 2},
            bud_hero_id=9,
            highest_damage_hero_id=9,
            run_goal="bud",
        )
        self.assertEqual(full[0], 11530)
        self.assertIn("Ahead", full_reason)


class ColumnFallbackTests(unittest.TestCase):
    def test_fallback_seat_column_is_shared_0_based(self) -> None:
        # Handlers previously used ((seat-1)%4)+1 (1-based); shared helper is 0-based.
        self.assertEqual(fallback_seat_column(1), 0)
        self.assertEqual(fallback_seat_column(5), 4)
        self.assertEqual(fallback_seat_column(6), 0)
        self.assertEqual(fallback_seat_column(13), 2)

    def test_seat_column_uses_shared_fallback_for_unknown_seats(self) -> None:
        from unittest.mock import patch

        from ic_gamedata.formation_advisor.models import FormationTopology
        from ic_gamedata.specialization_formation import clear_formation_topology_cache

        empty = FormationTopology(
            seat_adjacency={},
            seat_column={},
            seat_zone={},
            source="test",
        )
        clear_formation_topology_cache()
        with patch(
            "ic_gamedata.specialization_formation.formation_topology",
            return_value=empty,
        ):
            self.assertEqual(seat_column(5), fallback_seat_column(5))
        clear_formation_topology_cache()


if __name__ == "__main__":
    unittest.main()
