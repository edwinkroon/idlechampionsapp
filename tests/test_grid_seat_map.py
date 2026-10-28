"""Grid seat completion must not park champions on reserved/permanent collisions."""

from __future__ import annotations

import unittest

from ic_gamedata.party_advisor_formation import _complete_grid_seat_map


class GridSeatMapTests(unittest.TestCase):
    def test_avoids_reserved_permanent_seat(self) -> None:
        # Baeloth (73) permanent seat 4 is escort-reserved; grid index 0 → prefer 1.
        result = _complete_grid_seat_map(
            [73, 2, 3],
            {},
            permanent_seats={73: 4, 2: 2, 3: 3},
            reserved_seats={4},
        )
        self.assertEqual(result[73], 1)
        self.assertNotEqual(result[73], 4)
        self.assertEqual(result[2], 2)
        self.assertEqual(result[3], 3)

    def test_keeps_hero_in_seats_and_fills_missing(self) -> None:
        result = _complete_grid_seat_map(
            [1, 2, 10],
            {1: 1, 2: 2},
            permanent_seats={1: 1, 2: 2, 10: 10},
            reserved_seats=set(),
        )
        self.assertEqual(result, {1: 1, 2: 2, 10: 10})

    def test_does_not_reuse_occupied_seat(self) -> None:
        # Permanent seat 4 already taken → Baeloth gets next free (index+1 = 1).
        result = _complete_grid_seat_map(
            [73],
            {96: 4},
            permanent_seats={73: 4, 96: 4},
            reserved_seats=set(),
        )
        self.assertEqual(result[96], 4)
        self.assertEqual(result[73], 1)
        self.assertEqual(len(set(result.values())), 2)

    def test_occupied_reserved_only_as_last_resort(self) -> None:
        # Only seat 4 free, but reserved — still assign when nothing else left.
        result = _complete_grid_seat_map(
            [73],
            {i: i for i in (1, 2, 3, 5, 6, 7, 8, 9, 10, 11, 12)},
            permanent_seats={73: 4},
            reserved_seats={4},
        )
        self.assertEqual(result[73], 4)


if __name__ == "__main__":
    unittest.main()
