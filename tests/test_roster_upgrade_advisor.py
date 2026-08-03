"""Tests for owned-roster upgrade suggestions."""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest.mock import patch

from ic_gamedata.party_advisor import FormationHero
from ic_gamedata.roster_upgrade_advisor import suggest_roster_upgrades


def _hero(
    hid: int,
    name: str,
    seat: int,
    *,
    roles: tuple[str, ...] = ("dps",),
    tags: tuple[str, ...] = (),
    ilvl: int = 100,
    is_top_damage: bool = False,
) -> FormationHero:
    return FormationHero(
        hero_id=hid,
        name=name,
        seat=seat,
        level=100,
        gear_score=float(ilvl),
        ilvl=ilvl,
        ilvl_pct_vs_avg=0.0,
        gear_rank=1,
        gear_rank_total=1,
        gear_pct_of_best=100.0,
        gear_label=f"ilvl {ilvl}",
        role_label=roles[0].capitalize() if roles else "Onbekend",
        roles=roles,
        tags=tags,
        highest_damage=1e12 if is_top_damage else 0.0,
        active_feats=1,
        is_top_damage=is_top_damage,
    )


class RosterUpgradeAdvisorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        path = Path(__file__).resolve().parent / "fixtures" / "webRequestLog_example.json"
        cls.payload = json.loads(path.read_text(encoding="utf-8"))

    def test_missing_debuffer_brings_in_unused_seat(self) -> None:
        """Spurt (seat 3) cannot replace Catti-brie (seat 7) — must be seat-legal."""
        formation = (
            _hero(147, "Azaka", 9, roles=("dps",), is_top_damage=True, ilvl=500),
            _hero(1, "Bruenor", 1, roles=("tank", "support"), tags=("buffer",), ilvl=400),
            _hero(25, "Catti-brie", 7, roles=("dps", "support"), tags=("debuffer",), ilvl=37),
        )
        # Party already has a weak debuffer tag on Catti; remove that for missing-role case.
        formation = (
            _hero(147, "Azaka", 9, roles=("dps",), is_top_damage=True, ilvl=500),
            _hero(1, "Bruenor", 1, roles=("tank", "support"), tags=("buffer",), ilvl=400),
            _hero(8, "Tyril", 8, roles=("tank",), ilvl=200),
        )
        owned = [
            (147, "Azaka", ("dps",), ()),
            (1, "Bruenor", ("tank", "support"), ("buffer",)),
            (8, "Tyril", ("tank",), ()),
            (43, "Spurt", ("support",), ("debuffer", "bud")),
            (25, "Catti-brie", ("dps", "support"), ("debuffer", "bud")),
        ]
        seat_map = {147: 9, 1: 1, 8: 8, 43: 3, 25: 7}
        with (
            patch(
                "ic_gamedata.roster_upgrade_advisor._formation_heroes",
                return_value=formation,
            ),
            patch(
                "ic_gamedata.roster_upgrade_advisor._owned_heroes",
                return_value=owned,
            ),
            patch(
                "ic_gamedata.roster_upgrade_advisor._loot_ilvl_by_hero",
                return_value={43: 404, 25: 37},
            ),
            patch(
                "ic_gamedata.roster_upgrade_advisor._hero_seat_id_map",
                return_value=seat_map,
            ),
            patch(
                "ic_gamedata.roster_upgrade_advisor.build_adventure_roster_filter",
                return_value=None,
            ),
            patch(
                "ic_gamedata.roster_upgrade_advisor.is_hero_allowed",
                return_value=True,
            ),
        ):
            suggestions = suggest_roster_upgrades(self.payload, goal="bud", context="campaign")
        self.assertTrue(suggestions)
        top = suggestions[0]
        self.assertEqual(top.candidate_name, "Spurt")
        self.assertEqual(top.candidate_seat, 3)
        self.assertFalse(top.same_seat_swap)
        self.assertNotEqual(top.replace_name, "Catti-brie")
        self.assertIn("seat 3", top.why)
        self.assertIn("bench", top.title.casefold())

    def test_same_seat_upgrade_only(self) -> None:
        formation = (
            _hero(3, "Nayeli", 3, roles=("tank", "support"), tags=("buffer",), ilvl=100),
            _hero(147, "Azaka", 9, roles=("dps",), is_top_damage=True, ilvl=500),
        )
        owned = [
            (3, "Nayeli", ("tank", "support"), ("buffer",)),
            (147, "Azaka", ("dps",), ()),
            (43, "Spurt", ("support",), ("debuffer", "bud")),
        ]
        with (
            patch(
                "ic_gamedata.roster_upgrade_advisor._formation_heroes",
                return_value=formation,
            ),
            patch(
                "ic_gamedata.roster_upgrade_advisor._owned_heroes",
                return_value=owned,
            ),
            patch(
                "ic_gamedata.roster_upgrade_advisor._loot_ilvl_by_hero",
                return_value={43: 404},
            ),
            patch(
                "ic_gamedata.roster_upgrade_advisor._hero_seat_id_map",
                return_value={3: 3, 147: 9, 43: 3},
            ),
            patch(
                "ic_gamedata.roster_upgrade_advisor.build_adventure_roster_filter",
                return_value=None,
            ),
            patch(
                "ic_gamedata.roster_upgrade_advisor.is_hero_allowed",
                return_value=True,
            ),
        ):
            suggestions = suggest_roster_upgrades(self.payload, goal="bud", context="campaign")
        self.assertTrue(suggestions)
        # Spurt and Nayeli share seat 3 → legal same-seat swap for missing debuffer.
        spurts = [s for s in suggestions if s.candidate_name == "Spurt"]
        self.assertTrue(spurts)
        self.assertTrue(spurts[0].same_seat_swap)
        self.assertEqual(spurts[0].replace_name, "Nayeli")
        self.assertEqual(spurts[0].replace_seat, 3)

    def test_rejects_cross_seat_stronger_same_role(self) -> None:
        """Spurt must not be suggested as a direct replacement for Catti-brie."""
        formation = (
            _hero(25, "Catti-brie", 7, roles=("dps", "support"), tags=("debuffer", "bud"), ilvl=37),
            _hero(147, "Azaka", 9, roles=("dps",), is_top_damage=True, ilvl=500),
            _hero(1, "Bruenor", 1, roles=("tank",), ilvl=300),
        )
        owned = [
            (25, "Catti-brie", ("dps", "support"), ("debuffer", "bud")),
            (147, "Azaka", ("dps",), ()),
            (1, "Bruenor", ("tank",), ()),
            (43, "Spurt", ("support",), ("debuffer", "bud")),
        ]
        with (
            patch(
                "ic_gamedata.roster_upgrade_advisor._formation_heroes",
                return_value=formation,
            ),
            patch(
                "ic_gamedata.roster_upgrade_advisor._owned_heroes",
                return_value=owned,
            ),
            patch(
                "ic_gamedata.roster_upgrade_advisor._loot_ilvl_by_hero",
                return_value={43: 404, 25: 37},
            ),
            patch(
                "ic_gamedata.roster_upgrade_advisor._hero_seat_id_map",
                return_value={25: 7, 147: 9, 1: 1, 43: 3},
            ),
            patch(
                "ic_gamedata.roster_upgrade_advisor.build_adventure_roster_filter",
                return_value=None,
            ),
            patch(
                "ic_gamedata.roster_upgrade_advisor.is_hero_allowed",
                return_value=True,
            ),
        ):
            suggestions = suggest_roster_upgrades(self.payload, goal="bud", context="campaign")
        for item in suggestions:
            if item.candidate_name == "Spurt" and item.replace_name == "Catti-brie":
                self.fail("Cross-seat Spurt→Catti-brie suggestion must not appear")
            if item.candidate_name == "Spurt" and item.same_seat_swap:
                self.assertEqual(item.replace_seat, 3)

    def test_does_not_replace_kos_carry_with_makos_on_ilvl(self) -> None:
        """Seat 9: Makos must not replace King of Shadows when KoS is the damage carry."""
        formation = (
            _hero(
                168,
                "King of Shadows",
                9,
                roles=("dps", "tank", "support"),
                tags=("buffer",),
                ilvl=100,
                is_top_damage=True,
            ),
            _hero(1, "Bruenor", 1, roles=("support",), tags=("buffer",), ilvl=300),
        )
        owned = [
            (168, "King of Shadows", ("dps", "tank", "support"), ("buffer",)),
            (1, "Bruenor", ("support",), ("buffer",)),
            (9, "Makos", ("dps", "support", "gold"), ("gold", "buffer")),
        ]
        with (
            patch(
                "ic_gamedata.roster_upgrade_advisor._formation_heroes",
                return_value=formation,
            ),
            patch(
                "ic_gamedata.roster_upgrade_advisor._owned_heroes",
                return_value=owned,
            ),
            patch(
                "ic_gamedata.roster_upgrade_advisor._loot_ilvl_by_hero",
                return_value={9: 500, 168: 100, 1: 300},
            ),
            patch(
                "ic_gamedata.roster_upgrade_advisor._hero_seat_id_map",
                return_value={168: 9, 9: 9, 1: 1},
            ),
            patch(
                "ic_gamedata.roster_upgrade_advisor.build_adventure_roster_filter",
                return_value=None,
            ),
            patch(
                "ic_gamedata.roster_upgrade_advisor.is_hero_allowed",
                return_value=True,
            ),
        ):
            suggestions = suggest_roster_upgrades(self.payload, goal="bud", context="campaign")
        for item in suggestions:
            if item.candidate_name == "Makos" and item.replace_name == "King of Shadows":
                self.fail("Must not replace KoS carry with Makos based on gear/tags")

    def test_does_not_replace_kos_dps_tank_with_makos_when_other_bud(self) -> None:
        """Even if another champ is BUD, don't bench KoS for Makos on buffer/gold tags."""
        formation = (
            _hero(
                168,
                "King of Shadows",
                9,
                roles=("dps", "tank", "support"),
                tags=("buffer",),
                ilvl=120,
            ),
            _hero(
                147,
                "Azaka",
                4,
                roles=("dps",),
                is_top_damage=True,
                ilvl=500,
            ),
        )
        owned = [
            (168, "King of Shadows", ("dps", "tank", "support"), ("buffer",)),
            (147, "Azaka", ("dps",), ()),
            (9, "Makos", ("dps", "support", "gold"), ("gold", "buffer")),
        ]
        with (
            patch(
                "ic_gamedata.roster_upgrade_advisor._formation_heroes",
                return_value=formation,
            ),
            patch(
                "ic_gamedata.roster_upgrade_advisor._owned_heroes",
                return_value=owned,
            ),
            patch(
                "ic_gamedata.roster_upgrade_advisor._loot_ilvl_by_hero",
                return_value={9: 800, 168: 120, 147: 500},
            ),
            patch(
                "ic_gamedata.roster_upgrade_advisor._hero_seat_id_map",
                return_value={168: 9, 9: 9, 147: 4},
            ),
            patch(
                "ic_gamedata.roster_upgrade_advisor.build_adventure_roster_filter",
                return_value=None,
            ),
            patch(
                "ic_gamedata.roster_upgrade_advisor.is_hero_allowed",
                return_value=True,
            ),
        ):
            suggestions = suggest_roster_upgrades(self.payload, goal="bud", context="campaign")
        for item in suggestions:
            if item.candidate_name == "Makos" and item.replace_name == "King of Shadows":
                self.fail("Must not replace KoS with Makos via buffer/gold role heuristics")

    def test_empty_formation_returns_no_suggestions(self) -> None:
        with patch(
            "ic_gamedata.roster_upgrade_advisor._formation_heroes",
            return_value=(),
        ):
            self.assertEqual(
                suggest_roster_upgrades(self.payload, goal="bud", context="campaign"),
                (),
            )

    def test_fixture_payload_runs_without_error(self) -> None:
        suggestions = suggest_roster_upgrades(self.payload, goal="bud", context="campaign")
        self.assertIsInstance(suggestions, tuple)
        for item in suggestions:
            self.assertTrue(item.title)
            self.assertTrue(item.why)
            if item.same_seat_swap:
                self.assertEqual(item.candidate_seat, item.replace_seat)
            self.assertIsNotNone(item.bud_ratio)

    def test_missing_debuffer_includes_bud_proxy_gain(self) -> None:
        formation = (
            _hero(147, "Azaka", 9, roles=("dps",), is_top_damage=True, ilvl=500),
            _hero(1, "Bruenor", 1, roles=("tank", "support"), tags=("buffer",), ilvl=400),
            _hero(8, "Tyril", 8, roles=("tank",), ilvl=200),
        )
        owned = [
            (147, "Azaka", ("dps",), ()),
            (1, "Bruenor", ("tank", "support"), ("buffer",)),
            (8, "Tyril", ("tank",), ()),
            (43, "Spurt", ("support",), ("debuffer", "bud")),
        ]
        with (
            patch(
                "ic_gamedata.roster_upgrade_advisor._formation_heroes",
                return_value=formation,
            ),
            patch(
                "ic_gamedata.roster_upgrade_advisor._owned_heroes",
                return_value=owned,
            ),
            patch(
                "ic_gamedata.roster_upgrade_advisor._loot_ilvl_by_hero",
                return_value={43: 404},
            ),
            patch(
                "ic_gamedata.roster_upgrade_advisor._hero_seat_id_map",
                return_value={147: 9, 1: 1, 8: 8, 43: 3},
            ),
            patch(
                "ic_gamedata.roster_upgrade_advisor.build_adventure_roster_filter",
                return_value=None,
            ),
            patch(
                "ic_gamedata.roster_upgrade_advisor.is_hero_allowed",
                return_value=True,
            ),
        ):
            suggestions = suggest_roster_upgrades(self.payload, goal="bud", context="campaign")
        spurts = [s for s in suggestions if s.candidate_name == "Spurt"]
        self.assertTrue(spurts)
        self.assertIsNotNone(spurts[0].bud_ratio)
        self.assertGreater(spurts[0].bud_ratio or 0.0, 1.2)
        self.assertIn("BUD-proxy", spurts[0].why)

    def test_does_not_replace_speed_buffer_with_pure_buffer_on_ilvl(self) -> None:
        """Halsin (speed+buffer) must not lose to Nayeli on ilvl alone."""
        formation = (
            _hero(147, "Azaka", 9, roles=("dps",), is_top_damage=True, ilvl=500),
            _hero(156, "Halsin", 3, roles=("support", "healer"), tags=("speed", "buffer"), ilvl=9),
        )
        owned = [
            (147, "Azaka", ("dps",), ()),
            (156, "Halsin", ("support", "healer"), ("speed", "buffer")),
            (3, "Nayeli", ("tank", "support"), ("buffer",)),
        ]
        with (
            patch(
                "ic_gamedata.roster_upgrade_advisor._formation_heroes",
                return_value=formation,
            ),
            patch(
                "ic_gamedata.roster_upgrade_advisor._owned_heroes",
                return_value=owned,
            ),
            patch(
                "ic_gamedata.roster_upgrade_advisor._loot_ilvl_by_hero",
                return_value={3: 1462, 156: 9, 147: 500},
            ),
            patch(
                "ic_gamedata.roster_upgrade_advisor._hero_seat_id_map",
                return_value={147: 9, 156: 3, 3: 3},
            ),
            patch(
                "ic_gamedata.roster_upgrade_advisor.build_adventure_roster_filter",
                return_value=None,
            ),
            patch(
                "ic_gamedata.roster_upgrade_advisor.is_hero_allowed",
                return_value=True,
            ),
        ):
            suggestions = suggest_roster_upgrades(self.payload, goal="bud", context="campaign")
        for item in suggestions:
            if item.candidate_name == "Nayeli" and item.replace_name == "Halsin":
                self.fail("Must not suggest Nayeli over Halsin when that drops speed")
            if item.bud_ratio is not None:
                self.assertGreaterEqual(item.bud_ratio, 1.0)

    def test_does_not_suggest_omin_to_nayeli_on_ilvl(self) -> None:
        """Omin→Nayeli dropped BUD in-game despite ×3 proxy; block ilvl-only buffer swaps."""
        formation = (
            _hero(147, "Azaka", 9, roles=("dps",), is_top_damage=True, ilvl=500),
            _hero(65, "Omin", 3, roles=("support", "gold", "healer"), tags=("gold", "buffer"), ilvl=7),
            _hero(1, "Bruenor", 1, roles=("tank", "support"), tags=("buffer",), ilvl=1500),
        )
        owned = [
            (147, "Azaka", ("dps",), ()),
            (65, "Omin", ("support", "gold", "healer"), ("gold", "buffer")),
            (1, "Bruenor", ("tank", "support"), ("buffer",)),
            (3, "Nayeli", ("tank", "support"), ("buffer",)),
        ]
        with (
            patch(
                "ic_gamedata.roster_upgrade_advisor._formation_heroes",
                return_value=formation,
            ),
            patch(
                "ic_gamedata.roster_upgrade_advisor._owned_heroes",
                return_value=owned,
            ),
            patch(
                "ic_gamedata.roster_upgrade_advisor._loot_ilvl_by_hero",
                return_value={3: 1462, 65: 7, 147: 500, 1: 1500},
            ),
            patch(
                "ic_gamedata.roster_upgrade_advisor._hero_seat_id_map",
                return_value={147: 9, 65: 3, 3: 3, 1: 1},
            ),
            patch(
                "ic_gamedata.roster_upgrade_advisor.build_adventure_roster_filter",
                return_value=None,
            ),
            patch(
                "ic_gamedata.roster_upgrade_advisor.is_hero_allowed",
                return_value=True,
            ),
        ):
            suggestions = suggest_roster_upgrades(self.payload, goal="bud", context="campaign")
        for item in suggestions:
            if item.candidate_name == "Nayeli" and item.replace_name == "Omin":
                self.fail("Must not suggest Nayeli over Omin on buffer ilvl alone")



if __name__ == "__main__":
    unittest.main()
