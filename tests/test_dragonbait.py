"""Dragonbait (67) Herbs and Spices vs Roasted Chicken."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from ic_gamedata.specialization_advice_text import human_specialization_reason
from ic_gamedata.specialization_engine import dynamic_default_ids
from ic_gamedata.specialization_models import PendingSpecialization, SpecializationOption


def _roles() -> dict[int, tuple[str, ...]]:
    return {
        67: ("tank", "support"),
        3: ("tank",),
        26: ("tank",),
        68: ("support",),
    }


class DragonbaitSpecializationTests(unittest.TestCase):
    def test_far_support_and_one_tank_picks_roasted_chicken(self) -> None:
        # Seat 1 → seat 12 is 5 slots on the heuristic diamond: base 25%, chicken 200%.
        with patch(
            "ic_gamedata.specialization_engine._hero_roles_map_from_champion_config",
            return_value=_roles(),
        ):
            ids, reason = dynamic_default_ids(
                67,
                {67, 68},
                seat_by_hero={67: 1, 68: 12},
            )
        self.assertEqual(ids, [3277])
        self.assertIn("Roasted Chicken", reason)
        self.assertIn("1 tanking", reason)

    def test_nearby_support_and_several_tanks_picks_herbs(self) -> None:
        # Three tanks is ×3.375. One adjacent Support is only 50% → 75%.
        with patch(
            "ic_gamedata.specialization_engine._hero_roles_map_from_champion_config",
            return_value=_roles(),
        ):
            ids, reason = dynamic_default_ids(
                67,
                {67, 3, 26, 68},
                seat_by_hero={67: 1, 3: 4, 26: 7, 68: 2},
            )
        self.assertEqual(ids, [3278])
        self.assertIn("3 tanking", reason)
        self.assertIn("Herbs and Spices", reason)

    def test_missing_seats_keep_herbs_default(self) -> None:
        with patch(
            "ic_gamedata.specialization_engine._hero_roles_map_from_champion_config",
            return_value=_roles(),
        ):
            ids, reason = dynamic_default_ids(67, {67, 68})
        self.assertEqual(ids, [3278])
        self.assertIn("no seat data", reason)

    def test_advice_text_names_the_comparison(self) -> None:
        chicken = PendingSpecialization(
            hero_id=67,
            hero_name="Dragonbait",
            seat=1,
            game_instance_id=1,
            current_choices=(),
            options=(
                SpecializationOption(3277, "Scent: Roasted Chicken", 120, 0),
                SpecializationOption(3278, "Scent: Herbs and Spices", 120, 0),
            ),
            desired_upgrade_id=3277,
            desired_option_index=0,
            reason="rule match",
            rationale=(
                "Chosen via formation rule (1 supports farther, 1 tanking "
                "×1.50=1.50 < meat curve → Scent: Roasted Chicken): "
                "Scent: Roasted Chicken."
            ),
        )
        text = human_specialization_reason(chicken, {})
        self.assertIn("Meat Sauce", text)
        self.assertIn("far enough", text)

        herbs = PendingSpecialization(
            hero_id=67,
            hero_name="Dragonbait",
            seat=None,
            game_instance_id=1,
            current_choices=(),
            options=chicken.options,
            desired_upgrade_id=3278,
            desired_option_index=1,
            reason="rule match",
            rationale="Chosen via formation rule (no seat data → Scent: Herbs and Spices): Scent: Herbs and Spices.",
        )
        missing = human_specialization_reason(herbs, {})
        self.assertIn("Seat positions are missing", missing)


if __name__ == "__main__":
    unittest.main()
