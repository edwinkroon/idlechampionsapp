"""Regression: adventure by_seat eligibility + INT gate boundaries.

Covers the Ten in Ten-Towns (805) + Strahd false-allow of seat-1/2 champions
(Regis/Sisaspia) and related eligibility contract cases.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from ic_gamedata.adventure_restrictions import (
    AdventureRosterFilter,
    build_adventure_roster_filter,
    evaluate_heroes_against_filter,
    is_hero_allowed,
)
from ic_gamedata.formation_ai_advice.export_validation import (
    validate_advice_request_export,
)


def _payload(
    *,
    adventure_id: int,
    game_changes: list,
    restrictions_text: str = "",
    patron_id: int = 0,
    patron_game_changes: list | None = None,
    formation: list | None = None,
    heroes: list | None = None,
    game_instances: list | None = None,
) -> dict:
    defines: dict = {
        "adventure_defines": [
            {
                "id": adventure_id,
                "name": f"Adventure {adventure_id}",
                "campaign_id": 24,
                "restrictions_text": restrictions_text,
                "game_changes": game_changes,
            }
        ]
    }
    if patron_id and patron_game_changes is not None:
        defines["patron_defines"] = [
            {
                "id": patron_id,
                "name": "TestPatron",
                "game_changes": {"1": patron_game_changes},
                "restrictions_text": {"1": "Only Champions with an INT score of 13 or higher can be used"},
            }
        ]
    instances = game_instances or [
        {
            "game_instance_id": 1,
            "current_adventure_id": adventure_id,
            "current_patron_id": patron_id,
            "formation": formation or [],
        }
    ]
    return {
        "defines": defines,
        "details": {
            "active_game_instance_id": 1,
            "game_instances": instances,
            "heroes": heroes
            or [
                {"hero_id": 20, "owned": "1"},
                {"hero_id": 57, "owned": "1"},
                {"hero_id": 3, "owned": "1"},
                {"hero_id": 102, "owned": "1"},
            ],
        },
    }


def _meta(hid: int, *, seat: int, int_score: int):
    return type(
        "M",
        (),
        {
            "hero_id": hid,
            "roles": frozenset(),
            "tags": frozenset(),
            "stats": {
                "str": 10,
                "dex": 10,
                "con": 10,
                "int": int_score,
                "wis": 10,
                "cha": 10,
            },
            "attack_types": frozenset(),
            "age": None,
            "all_tags": frozenset(),
        },
    )()


class EligibilityBySeatTests(unittest.TestCase):
    """1) Reported run: Regis(20)/Sisaspia(57) must not be direct candidates."""

    def test_adventure_805_strahd_denies_seat_1_and_2_despite_int_13(self) -> None:
        payload = _payload(
            adventure_id=805,
            restrictions_text=(
                "A random Champion from seat 10 is immediately unlocked.\r\n"
                "Champions from the first two bench seats cannot be used."
            ),
            game_changes=[
                {
                    "type": "key_champion",
                    "by_seat": {"seats": [10]},
                    "slot_id": 3,
                    "name": "Shadow",
                },
                {
                    "type": "disallow_crusaders",
                    "by_seat": {
                        "seats": [1, 2],
                        "blocked_portrait": 13093,
                    },
                },
            ],
            patron_id=3,
            patron_game_changes=[
                {
                    "type": "disallow_crusaders",
                    "by_stat": {
                        "stats": [{"stat": "int", "comp": "<", "value": 13}],
                        "blocked_portrait": 7731,
                    },
                },
                {"type": "force_allow_hero", "hero_ids": [102, 177]},
            ],
        )
        seat_map = {20: 2, 57: 1, 3: 3, 102: 5, 38: 1}
        with patch(
            "ic_gamedata.adventure_restrictions.hero_seat_id_map_from_cached_definitions",
            return_value=seat_map,
        ), patch(
            "ic_gamedata.adventure_restrictions._hero_meta",
            side_effect=lambda hid: _meta(
                hid,
                seat=seat_map.get(hid, 3),
                int_score=13 if hid in {20, 57, 38, 3} else 10,
            ),
        ), patch(
            "ic_gamedata.patron_roster.is_hero_allowed_on_patron",
            return_value=True,
        ):
            filt = build_adventure_roster_filter(payload, 805)
            self.assertEqual(filt.banned_seat_ids, {1, 2})
            self.assertIn(("int", ">=", 13), filt.ability_score_gates)
            self.assertIn("GetStat(`int`) < 13", filt.deny_exprs)
            self.assertFalse(filt.has_unevaluable_roster_rules)

            for hid, seat in ((20, 2), (57, 1), (38, 1)):
                self.assertFalse(is_hero_allowed(hid, filt), msg=f"hero {hid}")
                row = evaluate_heroes_against_filter([hid], filt)[0]
                self.assertEqual(row["status"], "denied")
                self.assertIn("by_seat", row["reason"])
                self.assertEqual(row.get("permanent_seat"), seat)

            # Seat 3 with INT 13 passes seat ban; INT gate still applies via deny.
            # hero 3 mocked at INT 13 → allowed by seats + INT.
            self.assertTrue(is_hero_allowed(3, filt))
            self.assertEqual(
                evaluate_heroes_against_filter([3], filt)[0]["status"], "allowed"
            )

    def test_int_boundary_12_13_14_for_deny_getstat_lt_13(self) -> None:
        """2) GetStat(`int`) < 13 denies only 12; 13 and 14 pass that rule."""
        filt = AdventureRosterFilter(
            deny_exprs=["GetStat(`int`) < 13"],
            ability_score_gates=[("int", ">=", 13)],
        )
        with patch(
            "ic_gamedata.adventure_restrictions._hero_meta",
            side_effect=lambda hid: _meta(hid, seat=3, int_score={12: 12, 13: 13, 14: 14}[hid]),
        ):
            self.assertFalse(is_hero_allowed(12, filt))
            self.assertTrue(is_hero_allowed(13, filt))
            self.assertTrue(is_hero_allowed(14, filt))
            statuses = {
                hid: evaluate_heroes_against_filter([hid], filt)[0]["status"]
                for hid in (12, 13, 14)
            }
            self.assertEqual(statuses, {12: "denied", 13: "allowed", 14: "allowed"})

    def test_int_pass_still_denied_by_seat_rule(self) -> None:
        """3) Stat gate pass does not override a separate by_seat ban."""
        payload = _payload(
            adventure_id=805,
            game_changes=[
                {
                    "type": "disallow_crusaders",
                    "by_seat": {"seats": [1, 2]},
                }
            ],
            patron_id=3,
            patron_game_changes=[
                {
                    "type": "disallow_crusaders",
                    "by_stat": {
                        "stats": [{"stat": "int", "comp": "<", "value": 13}],
                    },
                }
            ],
        )
        with patch(
            "ic_gamedata.adventure_restrictions.hero_seat_id_map_from_cached_definitions",
            return_value={57: 1},
        ), patch(
            "ic_gamedata.adventure_restrictions._hero_meta",
            side_effect=lambda hid: _meta(hid, seat=1, int_score=14),
        ), patch(
            "ic_gamedata.patron_roster.is_hero_allowed_on_patron",
            return_value=True,
        ):
            filt = build_adventure_roster_filter(payload, 805)
            self.assertFalse(is_hero_allowed(57, filt))
            row = evaluate_heroes_against_filter([57], filt)[0]
            self.assertEqual(row["status"], "denied")
            self.assertIn("by_seat", row["reason"])

    def test_unsupported_essential_predicate_is_unknown_not_allowed(self) -> None:
        """4) Unhandled by_* must not silently allow (keeps raw params)."""
        payload = _payload(
            adventure_id=9001,
            game_changes=[
                {
                    "type": "disallow_crusaders",
                    "by_edge_stat": {"stat": "dex", "value": 14},
                }
            ],
        )
        with patch(
            "ic_gamedata.adventure_restrictions._hero_meta",
            side_effect=lambda hid: _meta(hid, seat=3, int_score=18),
        ), patch(
            "ic_gamedata.patron_roster.is_hero_allowed_on_patron",
            return_value=True,
        ):
            filt = build_adventure_roster_filter(payload, 9001)
            self.assertTrue(filt.has_unknown_rules)
            self.assertTrue(filt.has_unevaluable_roster_rules)
            self.assertFalse(is_hero_allowed(3, filt))
            row = evaluate_heroes_against_filter([3], filt)[0]
            self.assertEqual(row["status"], "unknown")
            self.assertEqual(len(filt.unevaluable_rules), 1)
            rule = filt.unevaluable_rules[0]
            self.assertEqual(rule.get("predicate"), "by_edge_stat")
            self.assertEqual(rule.get("raw"), {"stat": "dex", "value": 14})

    def test_force_allow_exception_still_works(self) -> None:
        """5) Proven force_allow remains allowed within its scope."""
        payload = _payload(
            adventure_id=805,
            game_changes=[
                {"type": "disallow_crusaders", "by_seat": {"seats": [1, 2]}},
            ],
            patron_id=3,
            patron_game_changes=[
                {
                    "type": "disallow_crusaders",
                    "by_stat": {
                        "stats": [{"stat": "int", "comp": "<", "value": 13}],
                    },
                },
                {"type": "force_allow_hero", "hero_ids": [102]},
            ],
        )
        with patch(
            "ic_gamedata.adventure_restrictions.hero_seat_id_map_from_cached_definitions",
            return_value={102: 1},
        ), patch(
            "ic_gamedata.adventure_restrictions._hero_meta",
            side_effect=lambda hid: _meta(hid, seat=1, int_score=8),
        ), patch(
            "ic_gamedata.patron_roster.is_hero_allowed_on_patron",
            return_value=True,
        ):
            filt = build_adventure_roster_filter(payload, 805)
            self.assertIn(102, filt.exempt_hero_ids)
            self.assertTrue(is_hero_allowed(102, filt))
            self.assertEqual(
                evaluate_heroes_against_filter([102], filt)[0]["status"], "allowed"
            )

    def test_other_party_eligible_not_automatically_available(self) -> None:
        """6) Eligible for the run ≠ available for this party instance."""
        from ic_gamedata.formation_ai_advice.swap_export import _other_party_instance

        payload = {
            "details": {
                "active_game_instance_id": 1,
                "heroes": [
                    {"hero_id": 3, "owned": "1", "game_instance_id": 1},
                    {"hero_id": 20, "owned": "1", "game_instance_id": 2},
                ],
                "game_instances": [
                    {
                        "game_instance_id": 1,
                        "current_adventure_id": 805,
                        "formation": [3],
                    },
                    {
                        "game_instance_id": 2,
                        "current_adventure_id": 1,
                        "formation": [20],
                    },
                ],
            }
        }
        avail = _other_party_instance(payload, 20)
        self.assertIsNotNone(avail)
        assert avail is not None
        self.assertEqual(avail.get("status"), "other_party")
        # Eligibility (seat 3, INT ok) is independent — champion can be eligible
        # while practical_availability is other_party.
        filt = AdventureRosterFilter(banned_seat_ids={1, 2})
        with patch(
            "ic_gamedata.adventure_restrictions.hero_seat_id_map_from_cached_definitions",
            return_value={20: 3},
        ), patch(
            "ic_gamedata.adventure_restrictions._hero_meta",
            side_effect=lambda hid: _meta(hid, seat=3, int_score=14),
        ):
            self.assertTrue(is_hero_allowed(20, filt))

    def test_adventure_context_switch_does_not_reuse_seat_ban(self) -> None:
        """7) Switching adventure rebuilds filter; prior seat ban does not stick."""
        banned_payload = _payload(
            adventure_id=805,
            game_changes=[
                {"type": "disallow_crusaders", "by_seat": {"seats": [1, 2]}},
            ],
        )
        open_payload = _payload(
            adventure_id=1,
            game_changes=[],
            restrictions_text="",
        )
        with patch(
            "ic_gamedata.adventure_restrictions.hero_seat_id_map_from_cached_definitions",
            return_value={57: 1},
        ), patch(
            "ic_gamedata.adventure_restrictions._hero_meta",
            side_effect=lambda hid: _meta(hid, seat=1, int_score=14),
        ), patch(
            "ic_gamedata.patron_roster.is_hero_allowed_on_patron",
            return_value=True,
        ):
            banned = build_adventure_roster_filter(banned_payload, 805)
            opened = build_adventure_roster_filter(open_payload, 1)
            self.assertEqual(banned.banned_seat_ids, {1, 2})
            self.assertFalse(banned.banned_seat_ids & opened.banned_seat_ids or opened.banned_seat_ids)
            self.assertFalse(is_hero_allowed(57, banned))
            self.assertTrue(is_hero_allowed(57, opened))

    def test_party_ok_does_not_imply_all_swap_candidates_ok(self) -> None:
        """8) Valid current party ≠ automatic swap-candidate eligibility."""
        payload = {
            "details": {
                "heroes": [
                    {"hero_id": 3, "owned": "1"},
                    {"hero_id": 20, "owned": "1"},
                    {"hero_id": 57, "owned": "1"},
                ]
            }
        }
        request = {
            "schema_version": "1.4",
            "meta": {"snapshot_ref": {"snapshot_id": "snap_test"}},
            "goal": {
                "id": "g1",
                "party_restriction_status": "ok",
                "structured_restrictions": {"has_unknown_rules": False},
            },
            "geometry": {"valid_position_ids": [1, 2, 3], "occupied": [1]},
            "party": [{"id": 3, "live_state": {"status": "known"}}],
            "roster_eligibility": {
                "allowed_ids": [3],
                "denied_groups": [{"reason": "by_seat", "ids": [20, 57]}],
                "unknown_groups": [],
            },
            "readiness": {"status": "ok"},
            "swap": {
                "coverage": {"external_owned_count": 2},
                "classification": [
                    {"id": 20, "classification": "included_allowed"},
                    {"id": 57, "classification": "included_allowed"},
                ],
            },
        }
        result = validate_advice_request_export(
            payload=payload,
            request=request,
            snapshot_id="snap_test",
            exported_snapshot_id="snap_test",
        )
        self.assertTrue(result.party_restriction_ok)
        self.assertFalse(result.swap_candidates_restriction_ok)
        codes = {i.code for i in result.issues}
        self.assertIn("swap_candidate_denied_but_included", codes)

    def test_only_allow_by_seat_limits_to_listed_seats(self) -> None:
        payload = _payload(
            adventure_id=395,
            game_changes=[
                {
                    "type": "only_allow_crusaders",
                    "by_seat": {"seats": [5, 6, 7]},
                }
            ],
        )
        with patch(
            "ic_gamedata.adventure_restrictions.hero_seat_id_map_from_cached_definitions",
            return_value={10: 5, 11: 4},
        ), patch(
            "ic_gamedata.adventure_restrictions._hero_meta",
            side_effect=lambda hid: _meta(hid, seat=5 if hid == 10 else 4, int_score=14),
        ), patch(
            "ic_gamedata.patron_roster.is_hero_allowed_on_patron",
            return_value=True,
        ):
            filt = build_adventure_roster_filter(payload, 395)
            self.assertEqual(filt.allowed_seat_ids, {5, 6, 7})
            self.assertTrue(is_hero_allowed(10, filt))
            self.assertFalse(is_hero_allowed(11, filt))


if __name__ == "__main__":
    unittest.main()
