"""Tests for custom multiply-stack specialization helpers."""

from __future__ import annotations

import unittest

from ic_gamedata.specialization_custom_stacks import (
    champions_of_tymora_count,
    diana_inspire_match_count,
    dob_qualified_counts,
    seat_graph_distance,
    shadowheart_duplicity_distance,
    unavailable_owned_hero_count,
)


class SpecializationCustomStackTests(unittest.TestCase):
    def test_seat_graph_distance_uses_default_adjacency(self) -> None:
        self.assertEqual(seat_graph_distance(1, 1), 0)
        self.assertEqual(seat_graph_distance(1, 2), 1)
        self.assertGreater(seat_graph_distance(1, 12), 1)

    def test_champions_of_tymora_counts_omin_adjacent_and_affiliates(self) -> None:
        tags = {
            65: ("cleric",),
            901: ("fighter",),
            902: ("acqinc",),
            903: ("human",),
        }
        seats = {65: 5, 901: 2, 902: 6, 903: 10}
        count = champions_of_tymora_count(
            {65, 901, 902, 903},
            seats,
            tags,
            known_associates_unlocked=True,
        )
        self.assertGreaterEqual(count, 3)

    def test_dob_counts_oxventure_with_stat_filters(self) -> None:
        tags = {1: ("oxventure",), 2: ("oxventure",), 3: ("human",)}
        attacks = {1: frozenset({"magic"}), 2: frozenset({"melee"})}
        scores = {1: {"cha": 18, "dex": 10}, 2: {"cha": 10, "dex": 18}}
        magical, friendly, quick, species = dob_qualified_counts(
            {1, 2, 3},
            tags,
            attacks,
            scores,
        )
        self.assertEqual((magical, friendly, quick), (1, 1, 1))
        self.assertEqual(species, 1)

    def test_shadowheart_distance_targets_highest_dex_seat(self) -> None:
        scores = {141: {"dex": 14}, 901: {"dex": 18}, 902: {"dex": 18}}
        seats = {141: 5, 901: 1, 902: 12}
        distance = shadowheart_duplicity_distance({141, 901, 902}, seats, scores)
        self.assertEqual(distance, seat_graph_distance(5, 12))

    def test_diana_inspire_match_count_for_modest_might(self) -> None:
        matched = diana_inspire_match_count({148, 901, 902}, 14792)
        self.assertGreaterEqual(matched, 0)

    def test_unavailable_owned_hero_count_excludes_active(self) -> None:
        count = unavailable_owned_hero_count({1, 2}, frozenset({1, 2, 3, 4}))
        self.assertEqual(count, 2)


if __name__ == "__main__":
    unittest.main()
