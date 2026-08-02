"""Tests for adventure champion restriction filtering."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from ic_gamedata.adventure_restrictions import (
    AdventureRosterFilter,
    allowed_hero_ids,
    build_adventure_roster_filter,
    filter_allowed_hero_names,
    is_hero_allowed,
)


def _mock_adventure(adventure_id: int, *, restrictions_text: str = "", game_changes: list | None = None) -> dict:
    return {
        "defines": {
            "adventure_defines": [
                {
                    "id": adventure_id,
                    "restrictions_text": restrictions_text,
                    "game_changes": game_changes or [],
                }
            ]
        }
    }


class AdventureRestrictionsTests(unittest.TestCase):
    def test_support_only_adventure_blocks_non_support(self) -> None:
        payload = _mock_adventure(
            736,
            restrictions_text="Only Champions with the Support tag can be used.",
            game_changes=[
                {
                    "type": "only_allow_crusaders",
                    "by_tags": {"tags": "support"},
                }
            ],
        )
        filt = build_adventure_roster_filter(payload, 736)
        self.assertTrue(is_hero_allowed(2, filt))  # Celeste: support role
        self.assertFalse(is_hero_allowed(4, filt))  # Jarlaxle: dps/gold
        self.assertFalse(is_hero_allowed(8, filt))  # Delina: dps only

    def test_no_tanks_adventure_blocks_tanks(self) -> None:
        payload = _mock_adventure(
            474,
            restrictions_text="Champions with the tanking role can not be used.",
            game_changes=[
                {
                    "type": "only_allow_crusaders",
                    "by_tags": {"tags": "!tanking"},
                }
            ],
        )
        filt = build_adventure_roster_filter(payload, 474)
        self.assertFalse(is_hero_allowed(3, filt))  # Nayeli: tank
        self.assertTrue(is_hero_allowed(1, filt))  # Bruenor: support

    def test_disallow_tanks(self) -> None:
        payload = _mock_adventure(
            1483,
            game_changes=[
                {
                    "type": "disallow_crusaders",
                    "by_tags": {"tags": "tanking"},
                }
            ],
        )
        filt = build_adventure_roster_filter(payload, 1483)
        self.assertFalse(is_hero_allowed(3, filt))

    def test_min_str_requirement(self) -> None:
        payload = _mock_adventure(
            974,
            game_changes=[
                {
                    "type": "only_allow_crusaders",
                    "by_stat": {
                        "stats": [{"stat": "str", "comp": ">=", "value": 16}],
                    },
                }
            ],
        )
        filt = build_adventure_roster_filter(payload, 974)
        fake_scores = {
            1: {"str": 18, "dex": 10},
            8: {"str": 10, "dex": 14},
        }
        with patch(
            "ic_gamedata.adventure_restrictions.hero_ability_scores_map_from_cached_definitions",
            return_value=fake_scores,
        ):
            self.assertTrue(is_hero_allowed(1, filt))
            self.assertFalse(is_hero_allowed(8, filt))

    def test_allow_expr_good_or_melee(self) -> None:
        payload = _mock_adventure(
            100,
            game_changes=[
                {
                    "type": "only_allow_crusaders",
                    "by_expr": {
                        "expr": "HasTag(`good`) || has_base_attack_dmg_type_melee",
                    },
                }
            ],
        )
        filt = build_adventure_roster_filter(payload, 100)
        fake_tags = {1: ("good", "buffer"), 8: ("evil",)}
        fake_attacks = {3: frozenset({"melee"})}
        with patch(
            "ic_gamedata.adventure_restrictions.hero_tags_map_from_cached_definitions",
            return_value=fake_tags,
        ), patch(
            "ic_gamedata.adventure_restrictions.hero_attack_types_map_from_cached_definitions",
            return_value=fake_attacks,
        ):
            self.assertTrue(is_hero_allowed(1, filt))
            self.assertFalse(is_hero_allowed(8, filt))
            self.assertTrue(is_hero_allowed(3, filt))

    def test_filter_bench_suggestions_respects_restrictions(self) -> None:
        filt = AdventureRosterFilter(required_tags={"support"})
        owned = [
            (1, "Bruenor", ("support",), ("buffer",)),
            (4, "Jarlaxle", ("dps", "gold"), ("gold",)),
            (2, "Celeste", ("healer", "support"), ("buffer",)),
        ]
        names = filter_allowed_hero_names(owned, {2}, filt, limit=5)
        self.assertEqual(names, ["Bruenor"])

    def test_exempt_hero_from_force_use_expr(self) -> None:
        filt = AdventureRosterFilter(
            allow_exprs=["hero_id == 173 || is_any_upgrade_positional"],
            has_unknown_rules=True,
        )
        self.assertTrue(is_hero_allowed(173, filt))

    def test_unrestricted_adventure_allows_all(self) -> None:
        payload = _mock_adventure(14, restrictions_text="Your heroes do three times more damage")
        filt = build_adventure_roster_filter(payload, 14)
        self.assertTrue(is_hero_allowed(1, filt))
        self.assertTrue(is_hero_allowed(3, filt))

    def test_trials_unavailable_hero_ids(self) -> None:
        payload = _mock_adventure(14)
        payload["details"] = {"trials_data": {"unavailable_hero_ids": [1, 3]}}
        filt = build_adventure_roster_filter(payload, 14)
        self.assertFalse(is_hero_allowed(1, filt))
        self.assertFalse(is_hero_allowed(3, filt))
        self.assertTrue(is_hero_allowed(2, filt))

    def test_api_game_changes_take_priority_over_text(self) -> None:
        payload = _mock_adventure(
            736,
            restrictions_text="Only Champions with the Support tag can be used.",
            game_changes=[
                {
                    "type": "only_allow_crusaders",
                    "by_tags": {"tags": "support"},
                }
            ],
        )
        filt = build_adventure_roster_filter(payload, 736)
        self.assertTrue(filt.uses_api_game_changes)

    def test_allowed_hero_ids_subset(self) -> None:
        filt = AdventureRosterFilter(required_tags={"support"})
        allowed = allowed_hero_ids([1, 2, 4, 8], filt)
        self.assertIn(1, allowed)
        self.assertIn(2, allowed)
        self.assertNotIn(4, allowed)
        self.assertNotIn(8, allowed)

    def test_patron_strahd_blocks_bruenor(self) -> None:
        payload = _mock_adventure(14)
        payload["details"] = {
            "active_game_instance_id": "1",
            "game_instances": [
                {
                    "game_instance_id": 1,
                    "current_adventure_id": 14,
                    "current_patron_id": 3,
                }
            ],
        }
        filt = build_adventure_roster_filter(payload, 14)
        self.assertIn(1, filt.patron_blocked_hero_ids)
        self.assertFalse(is_hero_allowed(1, filt))

    def test_patron_mirt_allows_bruenor(self) -> None:
        payload = _mock_adventure(14)
        payload["details"] = {
            "active_game_instance_id": "1",
            "game_instances": [
                {
                    "game_instance_id": 1,
                    "current_adventure_id": 14,
                    "current_patron_id": 1,
                }
            ],
        }
        filt = build_adventure_roster_filter(payload, 14)
        self.assertNotIn(1, filt.patron_blocked_hero_ids)
        self.assertTrue(is_hero_allowed(1, filt))

    def test_formation_trust_allows_active_formation_heroes(self) -> None:
        filt = AdventureRosterFilter(banned_tags={"event"})
        self.assertFalse(is_hero_allowed(159, filt))
        self.assertTrue(is_hero_allowed(159, filt, formation_hero_ids=frozenset({159})))

    def test_reserved_formation_seats_from_slot_escort(self) -> None:
        from ic_gamedata.adventure_restrictions import (
            player_formation_capacity,
            reserved_formation_seats,
        )

        payload = _mock_adventure(
            563,
            game_changes=[
                {
                    "type": "slot_escort",
                    "slot_ids": [8, 6, 7],
                }
            ],
        )
        payload["details"] = {
            "active_game_instance_id": 1,
            "game_instances": [
                {
                    "game_instance_id": 1,
                    "current_adventure_id": 563,
                    "hero_in_seats": {
                        "1": 67,
                        "3": 4,
                        "5": 106,
                        "6": 86,
                        "7": 13,
                        "9": 159,
                        "10": 177,
                        "12": 22,
                    },
                    "formation": [67, 4, 159, 13, 86, 106, -1, -1, -1],
                }
            ],
            "heroes": [
                {"hero_id": hid, "in_seat": 1, "game_instance_id": 1, "owned": 1}
                for hid in (67, 4, 159, 13, 86, 106)
            ],
        }
        self.assertEqual(reserved_formation_seats(payload, 563), frozenset({6, 7, 8}))
        self.assertEqual(player_formation_capacity(payload, 563), 6)


if __name__ == "__main__":
    unittest.main()
