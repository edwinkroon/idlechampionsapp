"""Vlahnya (35) specialization: Spy Network vs Breaking Out Solo."""

from __future__ import annotations

import unittest

from ic_gamedata.specialization_engine import dynamic_default_ids


class VlahnyaSpecializationTests(unittest.TestCase):
    def test_spy_network_when_bud_shares_column(self) -> None:
        # Diamond heuristic: seats 4 and 5 are both mid-column (col 2).
        ids, reason = dynamic_default_ids(
            35,
            {35, 9, 3, 2},
            seat_by_hero={35: 5, 9: 4, 3: 1, 2: 2},
            highest_damage_hero_id=9,
            bud_hero_id=9,
        )
        self.assertEqual(ids, [1658])
        self.assertIn("BUD shares Vlahnya's column", reason)

    def test_solo_when_column_is_sparse_and_bud_ahead(self) -> None:
        # Vlahnya alone in a back column; BUD further forward.
        ids, reason = dynamic_default_ids(
            35,
            {35, 9, 3},
            seat_by_hero={35: 10, 9: 4, 3: 1},
            highest_damage_hero_id=9,
            bud_hero_id=9,
        )
        self.assertEqual(ids, [1659])
        self.assertIn("≤2 champions", reason)

    def test_spy_network_when_column_crowded(self) -> None:
        # Three champions in the same mid column; BUD elsewhere.
        ids, reason = dynamic_default_ids(
            35,
            {35, 2, 5, 9},
            seat_by_hero={35: 5, 2: 4, 5: 6, 9: 1},
            highest_damage_hero_id=9,
            bud_hero_id=9,
        )
        self.assertEqual(ids, [1658])
        self.assertIn("crowded", reason)

    def test_default_solo_without_seats(self) -> None:
        ids, reason = dynamic_default_ids(35, {35, 9}, highest_damage_hero_id=9)
        self.assertEqual(ids, [1659])
        self.assertIn("default", reason.casefold())

    def test_spy_network_stable_across_goals(self) -> None:
        seats = {35: 5, 9: 4, 3: 1, 2: 2}
        for goal in ("bud", "gold", "speed"):
            ids, _reason = dynamic_default_ids(
                35,
                {35, 9, 3, 2},
                seat_by_hero=seats,
                highest_damage_hero_id=9,
                bud_hero_id=9,
                run_goal=goal,
            )
            self.assertEqual(ids, [1658], msg=goal)


if __name__ == "__main__":
    unittest.main()
