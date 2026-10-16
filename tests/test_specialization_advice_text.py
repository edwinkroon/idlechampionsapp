"""Tests for human-readable specialization advice text."""

from __future__ import annotations

import unittest

from ic_gamedata.specialization_advice_text import human_specialization_reason
from ic_gamedata.specialization_models import PendingSpecialization, SpecializationOption


class HumanSpecializationReasonTests(unittest.TestCase):
    def test_cazrin_tier0_ignores_embedded_smell_reason(self) -> None:
        arrow = "\u2192"
        item = PendingSpecialization(
            hero_id=166,
            hero_name="Cazrin",
            seat=10,
            game_instance_id=1,
            current_choices=(),
            options=(
                SpecializationOption(17678, "Self Taught", 180, 0),
                SpecializationOption(17679, "Ancestor's Shadow", 180, 0),
                SpecializationOption(17680, "Lost in the Library", 180, 0),
            ),
            desired_upgrade_id=17678,
            desired_option_index=0,
            reason="rule match",
            rationale=(
                f"Chosen via formation rule (10 qualified × 100% multiplicative {arrow} "
                f"Self Taught; Cazrin as support {arrow} Smell Mastery): Self Taught."
            ),
        )
        text = human_specialization_reason(item, {})
        self.assertIn("qualified champions", text.casefold())
        self.assertNotIn("Smell Mastery", text)

    def test_cazrin_tier1_keeps_smell_mastery_reason(self) -> None:
        arrow = "\u2192"
        item = PendingSpecialization(
            hero_id=166,
            hero_name="Cazrin",
            seat=10,
            game_instance_id=1,
            current_choices=(),
            options=(
                SpecializationOption(17681, "Signature Smell", 240, 1),
                SpecializationOption(17682, "Smell Mastery", 240, 1),
            ),
            desired_upgrade_id=17682,
            desired_option_index=1,
            reason="rule match",
            rationale=(
                f"Chosen via formation rule (10 qualified × 100% multiplicative {arrow} "
                f"Self Taught; Cazrin as support {arrow} Smell Mastery): Smell Mastery."
            ),
        )
        text = human_specialization_reason(item, {})
        self.assertIn("Smell Mastery", text)
        self.assertIn("support Cazrin", text)

    def test_valentine_bodyguard_reason_with_tatyana(self) -> None:
        item = PendingSpecialization(
            hero_id=103,
            hero_name="Valentine",
            seat=5,
            game_instance_id=1,
            current_choices=(),
            options=(
                SpecializationOption(8149, "All Hail the God Brain", 300, 0),
                SpecializationOption(8150, "My Loyal Bodyguard", 300, 0),
                SpecializationOption(8151, "Family Business", 300, 0),
            ),
            desired_upgrade_id=8150,
            desired_option_index=1,
            reason="rule match",
            rationale="Chosen via formation rule (Tatyana present → My Loyal Bodyguard): My Loyal Bodyguard.",
        )
        text = human_specialization_reason(item, {})
        self.assertIn("Tatyana", text)
        self.assertIn("Faithful Friend", text)

    def test_valentine_god_brain_reason_without_tatyana(self) -> None:
        item = PendingSpecialization(
            hero_id=103,
            hero_name="Valentine",
            seat=5,
            game_instance_id=1,
            current_choices=(),
            options=(
                SpecializationOption(8149, "All Hail the God Brain", 300, 0),
                SpecializationOption(8150, "My Loyal Bodyguard", 300, 0),
                SpecializationOption(8151, "Family Business", 300, 0),
            ),
            desired_upgrade_id=8149,
            desired_option_index=0,
            reason="rule match",
            rationale="Chosen via formation rule (no Tatyana → All Hail the God Brain): All Hail the God Brain.",
        )
        text = human_specialization_reason(item, {})
        self.assertIn("Tatyana is not", text)
        self.assertIn("Tregrum", text)

    def test_caramon_bud_hit_reason(self) -> None:
        item = PendingSpecialization(
            hero_id=179,
            hero_name="Caramon",
            seat=3,
            game_instance_id=1,
            current_choices=(),
            options=(
                SpecializationOption(20177, "Raise Spirits: Encirclement", 20, 0),
                SpecializationOption(20178, "Raise Spirits: Overwatch", 20, 0),
                SpecializationOption(20179, "Raise Spirits: Spearhead", 20, 0),
            ),
            desired_upgrade_id=20178,
            desired_option_index=1,
            reason="rule match",
            rationale="Chosen via formation rule (BUD hit 4× by Overwatch via 7 Good allies): Raise Spirits: Overwatch.",
        )
        text = human_specialization_reason(item, {})
        self.assertIn("stacks raise spirits", text.casefold())
        self.assertIn("BUD", text)

    def test_caramon_insufficient_alignment_data(self) -> None:
        item = PendingSpecialization(
            hero_id=179,
            hero_name="Caramon",
            seat=3,
            game_instance_id=1,
            current_choices=(),
            options=(
                SpecializationOption(20177, "Raise Spirits: Encirclement", 20, 0),
                SpecializationOption(20178, "Raise Spirits: Overwatch", 20, 0),
                SpecializationOption(20179, "Raise Spirits: Spearhead", 20, 0),
            ),
            desired_upgrade_id=None,
            desired_option_index=None,
            reason="insufficient data",
            rationale="insufficient data (no alignment/STR data; cannot score Allies or Raise Spirits)",
        )
        text = human_specialization_reason(item, {})
        self.assertIn("not enough champion data", text.casefold())
        self.assertIn("no recommendation", text.casefold())

    def test_caramon_insufficient_seat_data_with_allies_pick(self) -> None:
        item = PendingSpecialization(
            hero_id=179,
            hero_name="Caramon",
            seat=3,
            game_instance_id=1,
            current_choices=(),
            options=(
                SpecializationOption(20180, "Staunch Allies", 170, 1),
                SpecializationOption(20181, "Sympathetic Allies", 170, 1),
                SpecializationOption(20182, "Stalwart Allies", 170, 1),
            ),
            desired_upgrade_id=20181,
            desired_option_index=1,
            reason="rule match",
            rationale="Chosen via insufficient data (no seat data; Raise Spirits unscored; 7 Good → Good Allies): Sympathetic Allies.",
        )
        text = human_specialization_reason(item, {})
        self.assertIn("seat positions are missing", text.casefold())
        self.assertIn("allies pick", text.casefold())


if __name__ == "__main__":
    unittest.main()
