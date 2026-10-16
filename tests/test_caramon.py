"""Caramon Majere (179) specialization and role-advice coverage."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from ic_gamedata.champion_role_advice import get_role_advice
from ic_gamedata.specialization_engine import dynamic_default_ids
from ic_gamedata.specialization_models import SpecializationOption


def _caramon_options() -> list[SpecializationOption]:
    return [
        SpecializationOption(20177, "Raise Spirits: Encirclement", 20, 0),
        SpecializationOption(20178, "Raise Spirits: Overwatch", 20, 0),
        SpecializationOption(20179, "Raise Spirits: Spearhead", 20, 0),
        SpecializationOption(20180, "Staunch Allies", 170, 1),
        SpecializationOption(20181, "Sympathetic Allies", 170, 1),
        SpecializationOption(20182, "Stalwart Allies", 170, 1),
    ]


_TAGS = {
    179: ("good", "tanking", "human"),
    3: ("good", "tanking"),
    26: ("good", "tanking"),
    2: ("good",),
    5: ("good",),
    13: ("good",),
    117: ("good",),
    9: ("evil",),
}
_ROLES = {
    179: ("tank", "support"),
    3: ("tank", "support"),
    26: ("tank", "support"),
    2: ("healer", "support"),
    5: ("healer", "support"),
    13: ("support",),
    117: ("healer", "support"),
    9: ("dps",),
}
_SCORES = {hid: {"str": 10} for hid in _TAGS}
_SCORES[179] = {"str": 19}

# Diamond heuristic: carry at seat 4 (col 2). Good champs at 6/8/10 hit it
# with Overwatch without being adjacent, so Encirclement + Staunch lose.
_SEATS = {
    179: 3,
    3: 1,
    26: 12,
    9: 4,
    2: 6,
    5: 8,
    13: 10,
    117: 11,
}
_PARTY = set(_SEATS)


def _patch_caramon_data():
    return (
        patch(
            "ic_gamedata.specialization_engine._hero_tags_map_from_cached_definitions",
            return_value=_TAGS,
        ),
        patch(
            "ic_gamedata.specialization_engine._hero_roles_map_from_champion_config",
            return_value=_ROLES,
        ),
        patch(
            "ic_gamedata.specialization_engine._hero_ability_scores_map_from_cached_definitions",
            return_value=_SCORES,
        ),
        patch(
            "ic_gamedata.specialization_engine._hero_tags_map_from_champion_config",
            return_value={},
        ),
    )


class CaramonSpecializationTests(unittest.TestCase):
    def test_role_advice_embedded(self) -> None:
        advice = get_role_advice(179, "support")
        self.assertIsNotNone(advice)
        assert advice is not None
        self.assertIn("Raise Spirits: Overwatch", advice.specialization_names)
        self.assertIn("Sympathetic Allies", advice.specialization_names)
        self.assertIn(20178, advice.specialization_ids)
        self.assertIn(20181, advice.specialization_ids)
        self.assertTrue(advice.formation)

        tank = get_role_advice(179, "tank")
        assert tank is not None
        self.assertIn("Sympathetic Allies", tank.specialization_names)

    def test_prefers_overwatch_sympathetic_over_encirclement_staunch(self) -> None:
        patches = _patch_caramon_data()
        with patches[0], patches[1], patches[2], patches[3]:
            ids, reason = dynamic_default_ids(
                179,
                _PARTY,
                known_options=_caramon_options(),
                seat_by_hero=_SEATS,
                bud_hero_id=9,
            )
        self.assertEqual(ids, [20178, 20181])
        self.assertNotIn("Encirclement", reason)
        self.assertNotIn("Staunch", reason)
        self.assertIn("Overwatch", reason)
        self.assertIn("Good", reason)
        self.assertIn("BUD hit", reason)

    def test_no_seats_picks_allies_but_not_raise_spirits(self) -> None:
        patches = _patch_caramon_data()
        with patches[0], patches[1], patches[2], patches[3]:
            ids, reason = dynamic_default_ids(
                179,
                _PARTY,
                known_options=_caramon_options(),
            )
        self.assertEqual(ids, [20181])
        self.assertIn("insufficient data", reason)
        self.assertIn("no seat data", reason)
        self.assertNotIn("Overwatch", reason)

    def test_empty_alignment_data_makes_no_guess(self) -> None:
        with (
            patch(
                "ic_gamedata.specialization_engine._hero_tags_map_from_cached_definitions",
                return_value={},
            ),
            patch(
                "ic_gamedata.specialization_engine._hero_ability_scores_map_from_cached_definitions",
                return_value={},
            ),
            patch(
                "ic_gamedata.specialization_engine._hero_tags_map_from_champion_config",
                return_value={},
            ),
        ):
            ids, reason = dynamic_default_ids(
                179,
                {179, 3, 9},
                known_options=_caramon_options(),
                seat_by_hero={179: 3, 3: 1, 9: 8},
                bud_hero_id=9,
            )
        self.assertEqual(ids, [])
        self.assertIn("insufficient data", reason)

    def test_tank_heavy_party_can_still_pick_staunch(self) -> None:
        tags = {
            179: ("good", "tanking"),
            3: ("evil", "tanking"),
            26: ("evil", "tanking"),
            9: ("evil",),
        }
        roles = {
            179: ("tank", "support"),
            3: ("tank",),
            26: ("tank",),
            9: ("dps",),
        }
        scores = {179: {"str": 19}, 3: {"str": 10}, 26: {"str": 10}, 9: {"str": 8}}
        with (
            patch(
                "ic_gamedata.specialization_engine._hero_tags_map_from_cached_definitions",
                return_value=tags,
            ),
            patch(
                "ic_gamedata.specialization_engine._hero_roles_map_from_champion_config",
                return_value=roles,
            ),
            patch(
                "ic_gamedata.specialization_engine._hero_ability_scores_map_from_cached_definitions",
                return_value=scores,
            ),
            patch(
                "ic_gamedata.specialization_engine._hero_tags_map_from_champion_config",
                return_value={},
            ),
        ):
            ids, reason = dynamic_default_ids(
                179,
                {179, 3, 26, 9},
                known_options=_caramon_options(),
            )
        self.assertEqual(ids, [20180])
        self.assertIn("Tanking", reason)
        self.assertIn("insufficient data", reason)


if __name__ == "__main__":
    unittest.main()
