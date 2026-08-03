"""Tests for Warden specter-cap specialization handler."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from ic_gamedata.specialization_engine import (
    FormationContext,
    _WARDEN_CHARM,
    _WARDEN_DARK_HUNGER,
    _WARDEN_SHADOWS,
    _handle_warden,
)


class WardenHandlerTests(unittest.TestCase):
    def test_picks_shadows_when_dex_beats_evil(self) -> None:
        # Matches in-game: Evil 4, DEX≥16 = 5, CHA-highest = 2.
        tags = {
            1: ("evil",),
            2: ("evil",),
            3: ("evil",),
            4: ("evil",),
            5: (),
            6: (),
            7: (),
            8: (),
            9: (),
        }
        scores = {
            1: {"dex": 16, "cha": 10},
            2: {"dex": 16, "cha": 8},
            3: {"dex": 16, "cha": 8},
            4: {"dex": 16, "cha": 8},
            5: {"dex": 16, "cha": 8},
            6: {"dex": 10, "cha": 18},
            7: {"dex": 10, "cha": 18},
            8: {"dex": 8, "cha": 8},
            9: {"dex": 8, "cha": 8},
        }
        with (
            patch(
                "ic_gamedata.specialization_engine._hero_tags_map_from_cached_definitions",
                return_value=tags,
            ),
            patch(
                "ic_gamedata.specialization_engine._hero_tags_map_from_champion_config",
                return_value={},
            ),
            patch(
                "ic_gamedata.specialization_engine._hero_ability_scores_map_from_cached_definitions",
                return_value=scores,
            ),
        ):
            ids, reason = _handle_warden(
                FormationContext(active_hero_ids=set(tags))
            )  # type: ignore[misc]
        self.assertEqual(ids, [_WARDEN_SHADOWS])
        self.assertIn("DEX≥16", reason)
        self.assertIn("Shadows in the Night", reason)

    def test_picks_dark_hunger_when_evil_leads(self) -> None:
        tags = {1: ("evil",), 2: ("evil",), 3: ("evil",), 4: ()}
        scores = {
            1: {"dex": 10, "cha": 8},
            2: {"dex": 10, "cha": 8},
            3: {"dex": 16, "cha": 8},
            4: {"dex": 8, "cha": 18},
        }
        with (
            patch(
                "ic_gamedata.specialization_engine._hero_tags_map_from_cached_definitions",
                return_value=tags,
            ),
            patch(
                "ic_gamedata.specialization_engine._hero_tags_map_from_champion_config",
                return_value={},
            ),
            patch(
                "ic_gamedata.specialization_engine._hero_ability_scores_map_from_cached_definitions",
                return_value=scores,
            ),
        ):
            ids, reason = _handle_warden(
                FormationContext(active_hero_ids=set(tags))
            )  # type: ignore[misc]
        self.assertEqual(ids, [_WARDEN_DARK_HUNGER])
        self.assertIn("evil", reason)

    def test_picks_charm_when_cha_leads(self) -> None:
        tags = {1: ("evil",), 2: (), 3: (), 4: (), 5: ()}
        scores = {
            1: {"dex": 8, "cha": 18},
            2: {"dex": 8, "cha": 16},
            3: {"dex": 8, "cha": 14},
            4: {"dex": 16, "cha": 10},
            5: {"dex": 8, "cha": 12},
        }
        with (
            patch(
                "ic_gamedata.specialization_engine._hero_tags_map_from_cached_definitions",
                return_value=tags,
            ),
            patch(
                "ic_gamedata.specialization_engine._hero_tags_map_from_champion_config",
                return_value={},
            ),
            patch(
                "ic_gamedata.specialization_engine._hero_ability_scores_map_from_cached_definitions",
                return_value=scores,
            ),
        ):
            ids, reason = _handle_warden(
                FormationContext(active_hero_ids=set(tags))
            )  # type: ignore[misc]
        self.assertEqual(ids, [_WARDEN_CHARM])
        self.assertIn("CHA-hoogst", reason)

    def test_tie_prefers_dark_hunger(self) -> None:
        tags = {1: ("evil",), 2: ("evil",)}
        scores = {
            1: {"dex": 16, "cha": 8},
            2: {"dex": 16, "cha": 8},
        }
        with (
            patch(
                "ic_gamedata.specialization_engine._hero_tags_map_from_cached_definitions",
                return_value=tags,
            ),
            patch(
                "ic_gamedata.specialization_engine._hero_tags_map_from_champion_config",
                return_value={},
            ),
            patch(
                "ic_gamedata.specialization_engine._hero_ability_scores_map_from_cached_definitions",
                return_value=scores,
            ),
        ):
            ids, _reason = _handle_warden(
                FormationContext(active_hero_ids=set(tags))
            )  # type: ignore[misc]
        self.assertEqual(ids, [_WARDEN_DARK_HUNGER])


if __name__ == "__main__":
    unittest.main()
