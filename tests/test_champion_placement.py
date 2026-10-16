"""BUD-relative champion placement rules."""

from __future__ import annotations

import json
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from ic_gamedata.formation_advisor.champion_placement import (
    clear_champion_placement_cache,
    evaluate_champion_placement_rules,
)
from ic_gamedata.formation_advisor.context_builder import build_formation_layout_context
from ic_gamedata.formation_advisor.topology import _heuristic_topology
from ic_gamedata.party_advisor import FormationHero


def _hero(
    hid: int,
    name: str,
    seat: int,
    *,
    roles: tuple[str, ...] = ("dps",),
    tags: tuple[str, ...] = (),
    highest_damage: float = 0.0,
    is_top_damage: bool = False,
) -> FormationHero:
    return FormationHero(
        hero_id=hid,
        name=name,
        seat=seat,
        level=100,
        gear_score=100.0,
        ilvl=100,
        ilvl_pct_vs_avg=0.0,
        gear_rank=1,
        gear_rank_total=1,
        gear_pct_of_best=100.0,
        gear_label="ilvl 100",
        role_label=roles[0].capitalize() if roles else "?",
        roles=roles,
        tags=tags,
        highest_damage=highest_damage,
        active_feats=1,
        is_top_damage=is_top_damage,
    )


class ChampionPlacementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        path = Path(__file__).resolve().parent / "fixtures" / "webRequestLog_example.json"
        cls.payload = json.loads(path.read_text(encoding="utf-8"))

    def setUp(self) -> None:
        clear_champion_placement_cache()

    def _ctx(self, formation: tuple[FormationHero, ...], seats: dict[str, int]):
        payload = json.loads(json.dumps(self.payload))
        inst = payload["details"]["game_instances"][0]
        inst["hero_in_seats"] = seats
        ctx = build_formation_layout_context(
            payload,
            formation,
            goal="bud",
            context="campaign",
        )
        # Use diamond heuristic columns so seat→column mapping is stable in tests.
        return replace(ctx, topology=_heuristic_topology())

    def test_kitiara_wants_bud_in_farthest_column(self) -> None:
        # Kitiara seat 1 (col 0); BUD seat 5 (col 2) is not farthest (col 4).
        formation = (
            _hero(180, "Kitiara", 1, roles=("support",), tags=("buffer",)),
            _hero(9, "Azaka", 5, roles=("dps",), highest_damage=1e9, is_top_damage=True),
        )
        ctx = self._ctx(formation, {"1": 180, "5": 9})
        tips = evaluate_champion_placement_rules(ctx)
        farthest = [t for t in tips if t.hero_id == 180 and "far" in t.headline.casefold()]
        self.assertTrue(farthest, msg=[t.headline for t in tips])

        # BUD on seat 11 (col 4) — farthest from col 0.
        formation_ok = (
            _hero(180, "Kitiara", 1, roles=("support",), tags=("buffer",)),
            _hero(9, "Azaka", 11, roles=("dps",), highest_damage=1e9, is_top_damage=True),
        )
        ctx_ok = self._ctx(formation_ok, {"1": 180, "11": 9})
        tips_ok = evaluate_champion_placement_rules(ctx_ok)
        farthest_ok = [t for t in tips_ok if t.hero_id == 180 and "far" in t.headline.casefold()]
        self.assertEqual(farthest_ok, [])

    def test_bruenor_same_column(self) -> None:
        formation = (
            _hero(1, "Bruenor", 5, roles=("support",), tags=("buffer",)),
            _hero(9, "Azaka", 1, roles=("dps",), highest_damage=1e9, is_top_damage=True),
        )
        ctx = self._ctx(formation, {"5": 1, "1": 9})
        tips = evaluate_champion_placement_rules(ctx)
        self.assertTrue(any(t.hero_id == 1 and "column" in t.headline.casefold() for t in tips))

        formation_ok = (
            _hero(1, "Bruenor", 5, roles=("support",), tags=("buffer",)),
            _hero(9, "Azaka", 4, roles=("dps",), highest_damage=1e9, is_top_damage=True),
        )
        ctx_ok = self._ctx(formation_ok, {"5": 1, "4": 9})
        tips_ok = evaluate_champion_placement_rules(ctx_ok)
        self.assertFalse(any(t.hero_id == 1 and "column" in t.headline.casefold() for t in tips_ok))

    def test_celeste_prefer_second_column(self) -> None:
        formation = (
            _hero(2, "Celeste", 5, roles=("healer", "support"), tags=("buffer",)),
            _hero(9, "Azaka", 1, roles=("dps",), highest_damage=1e9, is_top_damage=True),
        )
        ctx = self._ctx(formation, {"5": 2, "1": 9})
        tips = evaluate_champion_placement_rules(ctx)
        self.assertTrue(any(t.hero_id == 2 and "2nd" in t.headline for t in tips))

    def test_qillek_avoid_adjacent_tanks(self) -> None:
        # Seat 5 adj includes 2 — Nayeli tank on 2.
        formation = (
            _hero(44, "Qillek", 5, roles=("healer", "support"), tags=("buffer",)),
            _hero(3, "Nayeli", 2, roles=("tank", "support"), tags=("buffer",)),
            _hero(9, "Azaka", 11, roles=("dps",), highest_damage=1e9, is_top_damage=True),
        )
        ctx = self._ctx(formation, {"5": 44, "2": 3, "11": 9})
        tips = evaluate_champion_placement_rules(ctx)
        self.assertTrue(any(t.hero_id == 44 and "tank" in t.headline.casefold() for t in tips))

    def test_buffer_tag_default_adjacent(self) -> None:
        # Generic buffer (not in heroes overrides) far from BUD.
        formation = (
            _hero(14, "Arkhan", 12, roles=("support",), tags=("buffer",)),
            _hero(9, "Azaka", 1, roles=("dps",), highest_damage=1e9, is_top_damage=True),
        )
        ctx = self._ctx(formation, {"12": 14, "1": 9})
        tips = evaluate_champion_placement_rules(ctx)
        self.assertTrue(
            any(t.hero_id == 14 and "BUD" in t.headline for t in tips),
            msg=[t.headline for t in tips],
        )

    def test_batch_b_laezel_same_column(self) -> None:
        formation = (
            _hero(128, "Lae'zel", 5, roles=("dps", "support")),
            _hero(9, "Azaka", 1, roles=("dps",), highest_damage=1e9, is_top_damage=True),
        )
        ctx = self._ctx(formation, {"5": 128, "1": 9})
        tips = evaluate_champion_placement_rules(ctx)
        self.assertTrue(any(t.hero_id == 128 and "column" in t.headline.casefold() for t in tips))

    def test_batch_b_thellora_ahead(self) -> None:
        # Thellora behind BUD (higher column) should tip.
        formation = (
            _hero(139, "Thellora", 11, roles=("support",), tags=("buffer",)),
            _hero(9, "Azaka", 5, roles=("dps",), highest_damage=1e9, is_top_damage=True),
        )
        ctx = self._ctx(formation, {"11": 139, "5": 9})
        tips = evaluate_champion_placement_rules(ctx)
        self.assertTrue(any(t.hero_id == 139 and "front" in t.headline.casefold() for t in tips))

    def test_batch_c_vlithryn_behind(self) -> None:
        formation = (
            _hero(162, "Vlithryn", 2, roles=("support",), tags=("buffer",)),
            _hero(9, "Azaka", 8, roles=("dps",), highest_damage=1e9, is_top_damage=True),
        )
        # Seat 2 col1, seat 8 col3 → Vlithryn ahead of BUD, should tip for behind.
        ctx = self._ctx(formation, {"2": 162, "8": 9})
        tips = evaluate_champion_placement_rules(ctx)
        self.assertTrue(any(t.hero_id == 162 and "behind" in t.headline.casefold() for t in tips))

    def test_batch_c_beadle_distance(self) -> None:
        formation = (
            _hero(64, "Beadle", 12, roles=("support",), tags=("buffer",)),
            _hero(9, "Azaka", 1, roles=("dps",), highest_damage=1e9, is_top_damage=True),
        )
        ctx = self._ctx(formation, {"12": 64, "1": 9})
        tips = evaluate_champion_placement_rules(ctx)
        self.assertTrue(any(t.hero_id == 64 and "2 seats" in t.headline for t in tips))

    def test_batch_c_umberto_column_distance(self) -> None:
        formation = (
            _hero(151, "Umberto", 1, roles=("support",), tags=("buffer",)),
            _hero(9, "Azaka", 12, roles=("dps",), highest_damage=1e9, is_top_damage=True),
        )
        # col 0 vs col 4 → distance 4 > 2
        ctx = self._ctx(formation, {"1": 151, "12": 9})
        tips = evaluate_champion_placement_rules(ctx)
        self.assertTrue(any(t.hero_id == 151 and "2 columns" in t.headline for t in tips))

    def test_batch_c_jamilah_prefer_tank(self) -> None:
        formation = (
            _hero(11, "Jamilah", 5, roles=("dps",)),
            _hero(9, "Azaka", 12, roles=("dps",), highest_damage=1e9, is_top_damage=True),
        )
        ctx = self._ctx(formation, {"5": 11, "12": 9})
        tips = evaluate_champion_placement_rules(ctx)
        self.assertTrue(any(t.hero_id == 11 and "tank" in t.headline.casefold() for t in tips))

    def test_shadowheart_dex_spread(self) -> None:
        # Shadowheart seat 1, high-DEX ally adjacent on seat 2 → distance 1 < 2.
        formation = (
            _hero(141, "Shadowheart", 1, roles=("healer", "support"), tags=("buffer",)),
            _hero(9, "Azaka", 2, roles=("dps",), highest_damage=1e9, is_top_damage=True),
            _hero(3, "Nayeli", 11, roles=("tank", "support")),
        )
        scores = {
            141: {"dex": 10},
            9: {"dex": 18},
            3: {"dex": 12},
        }
        with patch(
            "ic_gamedata.formation_advisor.champion_placement.hero_ability_scores_map_from_cached_definitions",
            return_value=scores,
        ):
            ctx = self._ctx(formation, {"1": 141, "2": 9, "11": 3})
            tips = evaluate_champion_placement_rules(ctx)
        self.assertTrue(
            any(t.hero_id == 141 and "DEX" in t.headline for t in tips),
            msg=[t.headline for t in tips],
        )

        # Far duplicate (seat 12 from seat 1) → no tip.
        formation_ok = (
            _hero(141, "Shadowheart", 1, roles=("healer", "support"), tags=("buffer",)),
            _hero(9, "Azaka", 12, roles=("dps",), highest_damage=1e9, is_top_damage=True),
        )
        with patch(
            "ic_gamedata.formation_advisor.champion_placement.hero_ability_scores_map_from_cached_definitions",
            return_value={141: {"dex": 10}, 9: {"dex": 18}},
        ):
            ctx_ok = self._ctx(formation_ok, {"1": 141, "12": 9})
            tips_ok = evaluate_champion_placement_rules(ctx_ok)
        self.assertFalse(any(t.hero_id == 141 and "DEX" in t.headline for t in tips_ok))

    def test_batch_d_birdsong_distance(self) -> None:
        formation = (
            _hero(21, "Birdsong", 12, roles=("support",), tags=("buffer",)),
            _hero(9, "Azaka", 1, roles=("dps",), highest_damage=1e9, is_top_damage=True),
        )
        ctx = self._ctx(formation, {"12": 21, "1": 9})
        tips = evaluate_champion_placement_rules(ctx)
        self.assertTrue(any(t.hero_id == 21 and "2 seats" in t.headline for t in tips))

    def test_batch_d_kthriss_farthest(self) -> None:
        formation = (
            _hero(38, "K'thriss", 1, roles=("support",), tags=("buffer",)),
            _hero(9, "Azaka", 5, roles=("dps",), highest_damage=1e9, is_top_damage=True),
        )
        ctx = self._ctx(formation, {"1": 38, "5": 9})
        tips = evaluate_champion_placement_rules(ctx)
        self.assertTrue(any(t.hero_id == 38 and "far" in t.headline.casefold() for t in tips))

    def test_batch_d_not_adjacent(self) -> None:
        # Kalix adjacent to BUD on seats 1–2.
        formation = (
            _hero(158, "Kalix", 1, roles=("support",), tags=("buffer",)),
            _hero(9, "Azaka", 2, roles=("dps",), highest_damage=1e9, is_top_damage=True),
        )
        ctx = self._ctx(formation, {"1": 158, "2": 9})
        tips = evaluate_champion_placement_rules(ctx)
        self.assertTrue(
            any(t.hero_id == 158 and "edge" in t.headline.casefold() for t in tips),
            msg=[t.headline for t in tips],
        )

        formation_ok = (
            _hero(158, "Kalix", 1, roles=("support",), tags=("buffer",)),
            _hero(9, "Azaka", 12, roles=("dps",), highest_damage=1e9, is_top_damage=True),
        )
        ctx_ok = self._ctx(formation_ok, {"1": 158, "12": 9})
        tips_ok = evaluate_champion_placement_rules(ctx_ok)
        self.assertFalse(any(t.hero_id == 158 and "edge" in t.headline.casefold() for t in tips_ok))

    def test_batch_d_gale_behind(self) -> None:
        formation = (
            _hero(147, "Gale", 2, roles=("support",), tags=("debuffer",)),
            _hero(9, "Azaka", 8, roles=("dps",), highest_damage=1e9, is_top_damage=True),
        )
        ctx = self._ctx(formation, {"2": 147, "8": 9})
        tips = evaluate_champion_placement_rules(ctx)
        self.assertTrue(any(t.hero_id == 147 and "behind" in t.headline.casefold() for t in tips))

    def test_batch_e_baeloth_adjacent_column(self) -> None:
        # Same column → tip; one column apart → ok.
        formation = (
            _hero(73, "Baeloth", 5, roles=("support", "gold"), tags=("gold", "buffer")),
            _hero(9, "Azaka", 4, roles=("dps",), highest_damage=1e9, is_top_damage=True),
        )
        ctx = self._ctx(formation, {"5": 73, "4": 9})
        tips = evaluate_champion_placement_rules(ctx)
        self.assertTrue(
            any(t.hero_id == 73 and "adjacent column" in t.headline.casefold() for t in tips),
            msg=[t.headline for t in tips],
        )

        formation_ok = (
            _hero(73, "Baeloth", 5, roles=("support", "gold"), tags=("gold", "buffer")),
            _hero(9, "Azaka", 2, roles=("dps",), highest_damage=1e9, is_top_damage=True),
        )
        # seat 5 col2, seat 2 col1 → distance 1
        ctx_ok = self._ctx(formation_ok, {"5": 73, "2": 9})
        tips_ok = evaluate_champion_placement_rules(ctx_ok)
        self.assertFalse(
            any(t.hero_id == 73 and "adjacent column" in t.headline.casefold() for t in tips_ok)
        )

    def test_batch_e_karlach_same_or_one_behind(self) -> None:
        # Karlach col2 (seat 5), BUD col0 (seat 1) ahead → tip.
        formation = (
            _hero(143, "Karlach", 5, roles=("support",), tags=("buffer",)),
            _hero(9, "Azaka", 1, roles=("dps",), highest_damage=1e9, is_top_damage=True),
        )
        ctx = self._ctx(formation, {"5": 143, "1": 9})
        tips = evaluate_champion_placement_rules(ctx)
        self.assertTrue(
            any(t.hero_id == 143 and "behind" in t.headline.casefold() for t in tips),
            msg=[t.headline for t in tips],
        )

        # BUD one column behind (seat 7 col3) → ok.
        formation_ok = (
            _hero(143, "Karlach", 5, roles=("support",), tags=("buffer",)),
            _hero(9, "Azaka", 7, roles=("dps",), highest_damage=1e9, is_top_damage=True),
        )
        ctx_ok = self._ctx(formation_ok, {"5": 143, "7": 9})
        tips_ok = evaluate_champion_placement_rules(ctx_ok)
        self.assertFalse(
            any(t.hero_id == 143 and "behind" in t.headline.casefold() for t in tips_ok)
        )

    def test_batch_e_melf_range_and_edge(self) -> None:
        formation = (
            _hero(59, "Melf", 12, roles=("support",), tags=("speed", "buffer")),
            _hero(9, "Azaka", 1, roles=("dps",), highest_damage=1e9, is_top_damage=True),
        )
        ctx = self._ctx(formation, {"12": 59, "1": 9})
        tips = evaluate_champion_placement_rules(ctx)
        self.assertTrue(
            any(t.hero_id == 59 for t in tips),
            msg=[t.headline for t in tips],
        )

    def test_batch_e_trixie_adjacent_behind(self) -> None:
        # Adjacent but Trixie behind BUD (higher col) → tip.
        formation = (
            _hero(176, "Trixie", 5, roles=("support",), tags=("buffer",)),
            _hero(9, "Azaka", 2, roles=("dps",), highest_damage=1e9, is_top_damage=True),
        )
        ctx = self._ctx(formation, {"5": 176, "2": 9})
        tips = evaluate_champion_placement_rules(ctx)
        self.assertTrue(
            any(t.hero_id == 176 and "behind" in t.headline.casefold() for t in tips),
            msg=[t.headline for t in tips],
        )

    def test_batch_e_hew_teamwork(self) -> None:
        # Diamond has 5 columns → X=2; col0 vs col4 → distance 4 > 2.
        formation = (
            _hero(75, "Hew Maan", 1, roles=("support",), tags=("speed", "buffer")),
            _hero(9, "Azaka", 12, roles=("dps",), highest_damage=1e9, is_top_damage=True),
        )
        ctx = self._ctx(formation, {"1": 75, "12": 9})
        tips = evaluate_champion_placement_rules(ctx)
        self.assertTrue(
            any(t.hero_id == 75 and "Teamwork" in t.headline for t in tips),
            msg=[t.headline for t in tips],
        )

    def test_batch_b_lark_carry_not_edge(self) -> None:
        formation = (
            _hero(170, "Lark", 5, roles=("support",), tags=("buffer",)),
            _hero(9, "Azaka", 1, roles=("dps",), highest_damage=1e9, is_top_damage=True),
        )
        ctx = self._ctx(formation, {"5": 170, "1": 9})
        tips = evaluate_champion_placement_rules(ctx)
        self.assertTrue(any(t.hero_id == 170 and "edge" in t.headline.casefold() for t in tips))

        # BUD mid (seat 5) — OK for Lark rule.
        formation_ok = (
            _hero(170, "Lark", 1, roles=("support",), tags=("buffer",)),
            _hero(9, "Azaka", 5, roles=("dps",), highest_damage=1e9, is_top_damage=True),
        )
        ctx_ok = self._ctx(formation_ok, {"1": 170, "5": 9})
        tips_ok = evaluate_champion_placement_rules(ctx_ok)
        self.assertFalse(any(t.hero_id == 170 and "edge" in t.headline.casefold() for t in tips_ok))


if __name__ == "__main__":
    unittest.main()
