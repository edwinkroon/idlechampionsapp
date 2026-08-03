"""Tests for custom multiply-stack specialization helpers."""

from __future__ import annotations

import unittest

from ic_gamedata.adventure_restrictions import AdventureRosterFilter
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

    def test_dob_counts_oxventure_or_stat_filters(self) -> None:
        # Oxventure OR filter: magic-only and high-stat non-Oxventure still count.
        tags = {
            1: ("oxventure",),
            2: ("oxventure",),
            3: ("human",),
            4: ("elf",),
            5: ("dwarf",),
        }
        attacks = {
            1: frozenset({"magic"}),
            2: frozenset({"melee"}),
            3: frozenset({"magic"}),
            4: frozenset({"ranged"}),
            5: frozenset({"melee"}),
        }
        scores = {
            1: {"cha": 18, "dex": 10},
            2: {"cha": 10, "dex": 18},
            3: {"cha": 10, "dex": 10},
            4: {"cha": 17, "dex": 10},
            5: {"cha": 10, "dex": 17},
        }
        magical, friendly, quick, species = dob_qualified_counts(
            {1, 2, 3, 4, 5},
            tags,
            attacks,
            scores,
        )
        # Magical: ox 1+2, magic 3 → 3
        # Friendly: ox 1+2, CHA 4 → 3
        # Quick: ox 1+2, DEX 5 → 3
        self.assertEqual((magical, friendly, quick), (3, 3, 3))
        self.assertEqual(species, 3)

    def test_shadowheart_distance_targets_highest_dex_seat(self) -> None:
        scores = {141: {"dex": 14}, 901: {"dex": 18}, 902: {"dex": 18}}
        seats = {141: 5, 901: 1, 902: 12}
        distance = shadowheart_duplicity_distance({141, 901, 902}, seats, scores)
        self.assertEqual(distance, seat_graph_distance(5, 12))

    def test_diana_inspire_match_count_for_modest_might(self) -> None:
        matched = diana_inspire_match_count({148, 901, 902}, 14792)
        self.assertGreaterEqual(matched, 0)

    def test_unavailable_owned_hero_count_uses_adventure_eligibility(self) -> None:
        owned = frozenset({1, 2, 3, 4})
        self.assertEqual(unavailable_owned_hero_count(owned, None), 0)
        unrestricted = AdventureRosterFilter()
        self.assertEqual(unavailable_owned_hero_count(owned, unrestricted), 0)
        banned = AdventureRosterFilter(banned_hero_ids={3, 4})
        self.assertEqual(unavailable_owned_hero_count(owned, banned), 2)

    def test_unavailable_owned_is_not_owned_minus_formation(self) -> None:
        """Regression: Finite Fellowship must not count benched owned champions."""
        active = {1, 2}
        owned = frozenset(range(1, 120))
        unrestricted = AdventureRosterFilter()
        self.assertEqual(unavailable_owned_hero_count(owned, unrestricted), 0)
        self.assertNotEqual(
            unavailable_owned_hero_count(owned, unrestricted),
            len(owned - active),
        )


class GaleFiniteFellowshipTests(unittest.TestCase):
    def test_mystical_mentor_beats_finite_fellowship_when_unrestricted(self) -> None:
        from ic_gamedata.specialization_data import hero_ability_scores_map_from_cached_definitions
        from ic_gamedata.specialization_engine import dynamic_default_ids

        scores = hero_ability_scores_map_from_cached_definitions()
        high_int = [hid for hid, stats in scores.items() if stats.get("int", 0) >= 13][:7]
        self.assertGreaterEqual(len(high_int), 7)
        active = set(high_int)
        active.add(147)
        owned = frozenset(set(range(1, 180)) | active)
        ids, reason = dynamic_default_ids(
            147,
            active,
            owned_hero_ids=owned,
            roster_filter=AdventureRosterFilter(),
        )
        self.assertEqual(ids, [14576, 14579])
        self.assertIn("Mystical Mentor", reason)

    def test_finite_fellowship_wins_with_many_ineligible(self) -> None:
        from ic_gamedata.specialization_data import hero_ability_scores_map_from_cached_definitions
        from ic_gamedata.specialization_engine import dynamic_default_ids

        scores = hero_ability_scores_map_from_cached_definitions()
        high_int = [hid for hid, stats in scores.items() if stats.get("int", 0) >= 13][:7]
        active = set(high_int)
        active.add(147)
        owned = frozenset(set(range(1, 180)) | active)
        banned = AdventureRosterFilter(banned_hero_ids=set(range(50, 150)))
        ids, reason = dynamic_default_ids(
            147,
            active,
            owned_hero_ids=owned,
            roster_filter=banned,
        )
        self.assertEqual(ids, [14576, 14580])
        self.assertIn("Finite Fellowship", reason)


if __name__ == "__main__":
    unittest.main()
