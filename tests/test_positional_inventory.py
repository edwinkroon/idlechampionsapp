"""Position-critical champions added via declarative positional rules."""

from __future__ import annotations

import unittest

from ic_gamedata.specialization_engine import dynamic_default_ids
from ic_gamedata.specialization_positional_rules import (
    clear_positional_rules_cache,
    load_positional_rules,
)


class PositionalInventoryTests(unittest.TestCase):
    def setUp(self) -> None:
        clear_positional_rules_cache()

    def test_inventory_covers_expected_heroes(self) -> None:
        heroes = load_positional_rules()
        self.assertEqual(
            set(heroes),
            {10, 11, 20, 35, 45, 49, 70, 77, 127},
        )

    def test_korth_beside_then_in_front(self) -> None:
        # Seat 5 adj includes 2; BUD on 2 → Beside.
        ids, reason = dynamic_default_ids(
            45,
            {45, 9},
            seat_by_hero={45: 5, 9: 2},
            bud_hero_id=9,
            run_goal="bud",
        )
        self.assertEqual(ids, [13043])
        self.assertIn("Beside", reason)

        # BUD further forward, not adjacent (Korth seat 8, BUD seat 1).
        ids, reason = dynamic_default_ids(
            45,
            {45, 9},
            seat_by_hero={45: 8, 9: 1},
            bud_hero_id=9,
            run_goal="gold",
        )
        self.assertEqual(ids, [13042])
        self.assertIn("In Front", reason)

    def test_ezmerelda_column_split(self) -> None:
        ids, reason = dynamic_default_ids(
            70,
            {70, 9},
            seat_by_hero={70: 5, 9: 4},
            bud_hero_id=9,
            run_goal="speed",
        )
        self.assertEqual(ids, [15042])
        self.assertIn("Vampire Hunter", reason)

        ids, reason = dynamic_default_ids(
            70,
            {70, 9},
            seat_by_hero={70: 10, 9: 4},
            bud_hero_id=9,
            run_goal="bud",
        )
        self.assertEqual(ids, [15041])
        self.assertIn("We've Trained For This", reason)

    def test_turiel_and_tyril_frontline(self) -> None:
        ids, reason = dynamic_default_ids(
            49,
            {49, 9},
            seat_by_hero={49: 1, 9: 5},
            bud_hero_id=9,
            run_goal="bud",
        )
        self.assertEqual(ids, [10663])
        self.assertIn("Resilience", reason)

        ids, reason = dynamic_default_ids(
            10,
            {10, 9},
            seat_by_hero={10: 11, 9: 5},
            bud_hero_id=9,
            run_goal="bud",
        )
        self.assertEqual(ids, [145])
        self.assertIn("Moonbeam", reason)

    def test_alyndra_adjacency(self) -> None:
        ids, reason = dynamic_default_ids(
            77,
            {77, 9},
            seat_by_hero={77: 5, 9: 2},
            bud_hero_id=9,
            run_goal="bud",
        )
        self.assertEqual(ids, [17749])
        self.assertIn("Expansive Vision", reason)

        ids, reason = dynamic_default_ids(
            77,
            {77, 9},
            seat_by_hero={77: 12, 9: 1},
            bud_hero_id=9,
            run_goal="gold",
        )
        self.assertEqual(ids, [17750])
        self.assertIn("Extra Judgy", reason)

    def test_vin_ursa_deck_by_zone(self) -> None:
        ids, reason = dynamic_default_ids(
            127,
            {127, 9},
            seat_by_hero={127: 1, 9: 5},
            bud_hero_id=9,
            run_goal="bud",
        )
        self.assertEqual(ids, [12090, 12094])
        self.assertIn("Front Deck", reason)

        ids, reason = dynamic_default_ids(
            127,
            {127, 9},
            seat_by_hero={127: 11, 9: 5},
            bud_hero_id=9,
            run_goal="speed",
        )
        self.assertEqual(ids, [12091, 12094])
        self.assertIn("Rear Deck", reason)

    def test_jamilah_adjacent_tank(self) -> None:
        # Nayeli (3) is a tank and adjacent to seat 5 via seat 2.
        ids, reason = dynamic_default_ids(
            11,
            {11, 3, 9},
            seat_by_hero={11: 5, 3: 2, 9: 12},
            bud_hero_id=9,
            run_goal="bud",
        )
        self.assertEqual(ids, [239])
        self.assertIn("Bruiser", reason)

        ids, reason = dynamic_default_ids(
            11,
            {11, 9},
            seat_by_hero={11: 5, 9: 12},
            bud_hero_id=9,
            run_goal="bud",
        )
        self.assertEqual(ids, [240])
        self.assertIn("Indomitable Might", reason)


if __name__ == "__main__":
    unittest.main()
