"""Tests for formation placement advisor."""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest.mock import patch

from ic_gamedata.formation_advisor.bud_gate import best_swap_to_carry
from ic_gamedata.formation_advisor.context_builder import build_formation_layout_context
from ic_gamedata.formation_advisor.evaluator import evaluate_formation_rules
from ic_gamedata.formation_advisor.handlers import evaluate_placement_handlers
from ic_gamedata.formation_advisor.loader import cached_formation_rules
from ic_gamedata.formation_advisor.models import FormationTopology
from ic_gamedata.formation_advisor.topology import load_formation_topology
from ic_gamedata.party_advisor import FormationHero, analyze_party


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
        gear_score=float(100 - seat),
        ilvl=100,
        ilvl_pct_vs_avg=0.0,
        gear_rank=1,
        gear_rank_total=1,
        gear_pct_of_best=100.0,
        gear_label="ilvl 100",
        role_label=roles[0].capitalize() if roles else "Onbekend",
        roles=roles,
        tags=tags,
        highest_damage=highest_damage,
        active_feats=1,
        is_top_damage=is_top_damage,
    )


class FormationAdvisorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        path = Path(__file__).resolve().parent / "fixtures" / "webRequestLog_example.json"
        cls.payload = json.loads(path.read_text(encoding="utf-8"))
        cached_formation_rules.cache_clear()

    def test_csv_rules_load(self) -> None:
        dataset = cached_formation_rules()
        self.assertGreaterEqual(len(dataset.rules), 5)

    def test_topology_from_payload(self) -> None:
        topo = load_formation_topology(self.payload, 14)
        self.assertIsInstance(topo, FormationTopology)
        self.assertIn(1, topo.seat_adjacency)

    def test_tank_not_front_triggers(self) -> None:
        formation = (
            _hero(147, "Azaka", 4, roles=("dps",), tags=("buffer",)),
            _hero(3, "Nayeli", 10, roles=("tank", "support"), tags=("buffer",)),
            _hero(2, "Celeste", 2, roles=("healer", "support"), tags=("buffer",)),
        )
        payload = dict(self.payload)
        inst = payload["details"]["game_instances"][0]
        inst["hero_in_seats"] = {"4": 147, "10": 3, "2": 2}
        ctx = build_formation_layout_context(
            payload,
            formation,
            goal="bud",
            context="campaign",
        )
        insights = evaluate_formation_rules(ctx)
        rule_ids = {ins.rule_id for ins in insights}
        self.assertIn("tank_not_front", rule_ids)

    def test_tank_on_diamond_front_seat_no_false_positive(self) -> None:
        """UI seat 9 is the diamond front tip — must not warn when tank is already there."""
        formation = (
            _hero(113, "Egbert", 9, roles=("tank", "support", "healer", "gold")),
            _hero(147, "Azaka", 1, roles=("dps",)),
            _hero(2, "Celeste", 2, roles=("healer", "support")),
        )
        payload = json.loads(json.dumps(self.payload))
        inst = payload["details"]["game_instances"][0]
        # Index 0 = front tip in campaign diamond graph.
        inst["formation"] = [113, 147, 2, -1, -1, -1, -1, -1, -1]
        inst["hero_in_seats"] = {"9": 113, "1": 147, "2": 2}
        ctx = build_formation_layout_context(
            payload,
            formation,
            goal="bud",
            context="campaign",
        )
        self.assertEqual(ctx.zone_of_seat(9), "front")
        insights = evaluate_formation_rules(ctx)
        tank_tips = [i for i in insights if i.rule_id == "tank_not_front"]
        self.assertEqual(tank_tips, [])

    def test_tank_on_diamond_mid_seat_triggers(self) -> None:
        """UI seat 1 is mid-column in diamond — tank should be nudged forward."""
        formation = (
            _hero(113, "Egbert", 1, roles=("tank", "support", "healer", "gold")),
            _hero(147, "Azaka", 9, roles=("dps",)),
        )
        payload = json.loads(json.dumps(self.payload))
        inst = payload["details"]["game_instances"][0]
        # Tip (index 0) = DPS; mid column index 3 = tank.
        inst["formation"] = [147, -1, -1, 113, -1, -1, -1, -1, -1]
        inst["hero_in_seats"] = {"1": 113, "9": 147}
        ctx = build_formation_layout_context(
            payload,
            formation,
            goal="bud",
            context="campaign",
        )
        self.assertEqual(ctx.zone_of_seat(1), "mid")
        insights = evaluate_formation_rules(ctx)
        self.assertTrue(any(i.rule_id == "tank_not_front" for i in insights))

    def test_buffer_far_from_carry_suggests_swap(self) -> None:
        formation = (
            _hero(147, "Azaka", 5, roles=("dps",), highest_damage=1e20, is_top_damage=True),
            _hero(1, "Bruenor", 12, roles=("support",), tags=("buffer",)),
            _hero(4, "Jarlaxle", 6, roles=("dps", "gold"), tags=("gold",)),
        )
        payload = dict(self.payload)
        inst = payload["details"]["game_instances"][0]
        inst["hero_in_seats"] = {"5": 147, "12": 1, "6": 4}
        stats = inst.setdefault("stats", {})
        stats["this_reset_highest_damage_dealt_hero_id"] = 147
        ctx = build_formation_layout_context(
            payload,
            formation,
            goal="bud",
            context="push",
        )
        insights = evaluate_formation_rules(ctx)
        swap_insights = [i for i in insights if i.insight_type == "swap"]
        self.assertTrue(swap_insights)
        self.assertTrue(any("BUD proxy" in i.detail for i in swap_insights))

    def test_buffer_and_support_far_rules_collapse_to_one_insight(self) -> None:
        """Buffer+support champions only emit the buffer adjacency tip (no bare support rule)."""
        from ic_gamedata.formation_advisor import build_formation_insights

        formation = (
            _hero(100, "Cazrin", 10, roles=("dps",), tags=()),
            _hero(101, "Dob", 12, roles=("support",), tags=("buffer",)),
            _hero(102, "Strongheart", 11, roles=("gold",), tags=()),
        )
        payload = {
            "details": {
                "active_game_instance_id": 1,
                "game_instances": [
                    {
                        "game_instance_id": 1,
                        "hero_in_seats": {"10": 100, "12": 101, "11": 102},
                        "formation": [100, 101, 102, -1, -1, -1, -1, -1, -1],
                        "stats": {"this_reset_highest_damage_dealt_hero_id": 100},
                    }
                ],
            }
        }
        raw = evaluate_formation_rules(
            build_formation_layout_context(
                payload, formation, goal="bud", context="push"
            )
        )
        far_rules = {
            i.rule_id
            for i in raw
            if i.rule_id in {"buffer_far_from_carry", "support_far_from_carry"}
            and i.hero_id == 101
        }
        self.assertEqual(far_rules, {"buffer_far_from_carry"})

        insights = build_formation_insights(
            payload, formation, goal="bud", context="push"
        )
        dob_far = [
            i
            for i in insights
            if i.hero_id == 101
            and i.rule_id in {"buffer_far_from_carry", "support_far_from_carry"}
        ]
        self.assertEqual(len(dob_far), 1)
        self.assertEqual(dob_far[0].rule_id, "buffer_far_from_carry")
        self.assertIn("Buffer", dob_far[0].headline)

    def test_kos_handler_front_placement(self) -> None:
        formation = (
            _hero(168, "King of Shadows", 10, roles=("dps",)),
            _hero(147, "Azaka", 4, roles=("dps",)),
        )
        payload = dict(self.payload)
        inst = payload["details"]["game_instances"][0]
        inst["hero_in_seats"] = {"10": 168, "4": 147}
        ctx = build_formation_layout_context(
            payload,
            formation,
            goal="bud",
            context="campaign",
        )
        insights = evaluate_placement_handlers(ctx)
        self.assertTrue(any("KoS" in ins.headline or "King" in ins.headline for ins in insights))

    def test_analyze_party_includes_formation_section(self) -> None:
        report = analyze_party(
            self.payload,
            goal="bud",
            context="campaign",
            include_formation=True,
        )
        self.assertIsNotNone(report.formation_insights)

    def test_analyze_party_formation_disabled(self) -> None:
        report = analyze_party(
            self.payload,
            goal="bud",
            context="campaign",
            include_formation=False,
        )
        self.assertEqual(report.formation_insights, ())

    def test_context_ignores_benched_hero_in_seats(self) -> None:
        """Stale seat holders must not get buffer/swap tips."""
        formation = (
            _hero(164, "Tess", 8, roles=("support",), tags=("buffer",)),
            _hero(168, "King of Shadows", 9, roles=("dps", "tank", "support"), tags=("buffer",)),
        )
        payload = {
            "details": {
                "active_game_instance_id": 1,
                "game_instances": [
                    {
                        "game_instance_id": 1,
                        "hero_in_seats": {
                            "3": 3,  # Nayeli listed but not on the board
                            "8": 164,
                            "9": 168,
                        },
                        "formation": [164, 168, -1],
                        "stats": {"this_reset_highest_damage_dealt_hero_id": 168},
                    }
                ],
                "heroes": [
                    {"hero_id": 3, "in_seat": 0, "game_instance_id": 1, "level": 100, "owned": 1},
                    {"hero_id": 164, "in_seat": 1, "game_instance_id": 1, "level": 100, "owned": 1},
                    {"hero_id": 168, "in_seat": 1, "game_instance_id": 1, "level": 100, "owned": 1},
                ],
            }
        }
        ctx = build_formation_layout_context(
            payload,
            formation,
            goal="bud",
            context="campaign",
        )
        self.assertNotIn(3, ctx.active_hero_ids)
        self.assertEqual(ctx.party_size, 2)
        insights = evaluate_formation_rules(ctx)
        self.assertFalse(any(i.hero_id == 3 or "Nayeli" in i.detail for i in insights))

    def test_formation_not_full_skipped_when_layout_is_full(self) -> None:
        """9-seat maps must not warn when all player slots are filled."""
        heroes = [
            _hero(hid, f"H{hid}", seat, roles=("support",), tags=("buffer",))
            for hid, seat in zip(range(1, 10), range(1, 10))
        ]
        # Mark one as DPS carry so party rules have a carry target.
        heroes[0] = _hero(1, "H1", 1, roles=("dps",))
        formation = tuple(heroes)
        payload = {
            "details": {
                "active_game_instance_id": 1,
                "game_instances": [
                    {
                        "game_instance_id": 1,
                        "current_adventure_id": 14,
                        "hero_in_seats": {str(seat): hid for hid, seat in zip(range(1, 10), range(1, 10))},
                        "formation": list(range(1, 10)),
                        "stats": {"this_reset_highest_damage_dealt_hero_id": 1},
                    }
                ],
                "heroes": [
                    {"hero_id": hid, "in_seat": 1, "game_instance_id": 1, "level": 100, "owned": 1}
                    for hid in range(1, 10)
                ],
            }
        }
        ctx = build_formation_layout_context(
            payload,
            formation,
            goal="bud",
            context="campaign",
        )
        self.assertEqual(ctx.party_size, 9)
        self.assertEqual(ctx.formation_capacity, 9)
        insights = evaluate_formation_rules(ctx)
        self.assertFalse(any(i.rule_id == "formation_not_full" for i in insights))

    def test_formation_not_full_triggers_when_under_capacity(self) -> None:
        formation = (
            _hero(1, "H1", 1, roles=("dps",)),
            _hero(2, "H2", 2, roles=("support",), tags=("buffer",)),
            _hero(3, "H3", 3, roles=("tank", "support")),
        )
        payload = {
            "details": {
                "active_game_instance_id": 1,
                "game_instances": [
                    {
                        "game_instance_id": 1,
                        "current_adventure_id": 14,
                        "hero_in_seats": {"1": 1, "2": 2, "3": 3},
                        "formation": [1, 2, 3, -1, -1, -1, -1, -1, -1],
                        "stats": {"this_reset_highest_damage_dealt_hero_id": 1},
                    }
                ],
                "heroes": [
                    {"hero_id": hid, "in_seat": 1, "game_instance_id": 1, "level": 100, "owned": 1}
                    for hid in (1, 2, 3)
                ],
            }
        }
        ctx = build_formation_layout_context(
            payload,
            formation,
            goal="bud",
            context="campaign",
        )
        self.assertEqual(ctx.formation_capacity, 9)
        insights = evaluate_formation_rules(ctx)
        not_full = [i for i in insights if i.rule_id == "formation_not_full"]
        self.assertEqual(len(not_full), 1)
        self.assertIn("3 of 9", not_full[0].detail)

    def test_adjacency_swap_suppressed_when_proxy_worse(self) -> None:
        """No buffer-far tip when every adjacent seat swap lowers BUD proxy."""
        formation = (
            _hero(147, "Azaka", 5, roles=("dps",), highest_damage=1e20, is_top_damage=True),
            _hero(1, "Bruenor", 12, roles=("support",), tags=("buffer",)),
            _hero(53, "Krull", 6, roles=("support",), tags=("debuffer", "bud")),
        )
        payload = dict(self.payload)
        inst = payload["details"]["game_instances"][0]
        inst["hero_in_seats"] = {"5": 147, "12": 1, "6": 53}
        stats = inst.setdefault("stats", {})
        stats["this_reset_highest_damage_dealt_hero_id"] = 147
        ctx = build_formation_layout_context(
            payload, formation, goal="bud", context="push"
        )
        # Force every candidate swap to look worse than current.
        with patch(
            "ic_gamedata.formation_advisor.bud_gate.score_seat_swap",
            return_value=0.8,
        ):
            insights = evaluate_formation_rules(ctx)
        self.assertFalse(
            any(i.rule_id == "buffer_far_from_carry" for i in insights),
            [i.detail for i in insights],
        )

    def test_swap_partner_picks_best_proxy_seat(self) -> None:
        """Prefer the adjacent seat with the highest proxy ratio, not first neighbor."""
        formation = (
            _hero(147, "Azaka", 5, roles=("dps",), highest_damage=1e20, is_top_damage=True),
            _hero(1, "Bruenor", 12, roles=("support",), tags=("buffer",)),
            _hero(2, "Celeste", 6, roles=("healer", "support"), tags=("buffer",)),
            _hero(4, "Jarlaxle", 4, roles=("dps", "gold"), tags=("gold",)),
        )
        payload = dict(self.payload)
        inst = payload["details"]["game_instances"][0]
        # Live 9-slot grid: Azaka at center index 4; Celeste/Jarlaxle on real neighbors.
        inst["formation"] = [-1, 2, -1, -1, 147, 4, -1, -1, -1]
        inst["hero_in_seats"] = {"5": 147, "12": 1, "6": 2, "4": 4}
        stats = inst.setdefault("stats", {})
        stats["this_reset_highest_damage_dealt_hero_id"] = 147
        ctx = build_formation_layout_context(
            payload, formation, goal="bud", context="push"
        )

        def _fake_score(
            _ctx,
            *,
            mover_id: int,
            target_seat: int,
            partner_id: int | None,
        ) -> float | None:
            del mover_id
            # Swapping onto Celeste (buffer) is a wash; onto Jarlaxle is a gain.
            if target_seat == 6 and partner_id == 2:
                return 1.0
            if target_seat == 4 and partner_id == 4:
                return 1.4
            return 0.9

        with patch(
            "ic_gamedata.formation_advisor.bud_gate.score_seat_swap",
            side_effect=_fake_score,
        ):
            best = best_swap_to_carry(ctx, 1)
        self.assertIsNotNone(best)
        assert best is not None
        partner_id, partner_seat, ratio = best
        self.assertEqual(partner_id, 4)
        self.assertEqual(partner_seat, 4)
        self.assertEqual(ratio, 1.4)

    def test_competing_swaps_claim_same_target_seat_once(self) -> None:
        """Two champions must not both be told to take Donaar's seat."""
        from dataclasses import replace as dc_replace

        from ic_gamedata.formation_advisor import build_formation_insights
        from ic_gamedata.formation_advisor.models import FormationInsight

        formation = (
            _hero(100, "Cazrin", 10, roles=("dps",), highest_damage=1e20, is_top_damage=True),
            _hero(34, "Donaar", 2, roles=("tank", "support"), tags=("buffer",)),
            _hero(120, "Lark", 6, roles=("support",), tags=("debuffer", "bud")),
            _hero(164, "Tess", 8, roles=("support",), tags=("buffer",)),
        )
        payload = {
            "details": {
                "active_game_instance_id": 1,
                "game_instances": [
                    {
                        "game_instance_id": 1,
                        "hero_in_seats": {"10": 100, "2": 34, "6": 120, "8": 164},
                        "formation": [100, 34, 120, 164, -1, -1, -1, -1, -1],
                        "stats": {"this_reset_highest_damage_dealt_hero_id": 100},
                    }
                ],
            }
        }

        # Force both far champs to prefer the same adjacent seat (2) with different ratios.
        def _fake_best(ctx, hero_id: int):
            del ctx
            if hero_id == 120:
                return (34, 2, 1.5)
            if hero_id == 164:
                return (34, 2, 1.2)
            return None

        with patch(
            "ic_gamedata.formation_advisor.evaluator.best_swap_to_carry",
            side_effect=_fake_best,
        ):
            insights = build_formation_insights(
                payload, formation, goal="bud", context="push"
            )

        target_seat_swaps = [
            i for i in insights if i.insight_type == "swap" and i.related_seat == 2
        ]
        self.assertEqual(len(target_seat_swaps), 1)
        self.assertEqual(target_seat_swaps[0].hero_id, 120)
        self.assertEqual(target_seat_swaps[0].bud_ratio, 1.5)

        # Sanity: FormationInsight carries bud_ratio through.
        self.assertIsInstance(target_seat_swaps[0], FormationInsight)
        self.assertIsNone(dc_replace(target_seat_swaps[0], bud_ratio=None).bud_ratio)

    def test_bench_buffer_suppressed_when_proxy_worse(self) -> None:
        formation = (
            _hero(147, "Azaka", 5, roles=("dps",), highest_damage=1e20, is_top_damage=True),
            _hero(4, "Jarlaxle", 6, roles=("dps", "gold"), tags=("gold",)),
        )
        payload = {
            "details": {
                "active_game_instance_id": 1,
                "game_instances": [
                    {
                        "game_instance_id": 1,
                        "hero_in_seats": {"5": 147, "6": 4},
                        "formation": [147, 4, -1],
                        "stats": {"this_reset_highest_damage_dealt_hero_id": 147},
                    }
                ],
                "heroes": [
                    {"hero_id": 147, "in_seat": 1, "game_instance_id": 1, "level": 100, "owned": 1},
                    {"hero_id": 4, "in_seat": 1, "game_instance_id": 1, "level": 100, "owned": 1},
                    {"hero_id": 1, "in_seat": 0, "game_instance_id": 1, "level": 100, "owned": 1},
                ],
            }
        }
        from dataclasses import replace as dc_replace

        ctx = build_formation_layout_context(
            payload, formation, goal="bud", context="campaign"
        )
        ctx = dc_replace(
            ctx,
            allowed_bench_ids=frozenset({1}),
            hero_name_by_id={**ctx.hero_name_by_id, 1: "Bruenor"},
            hero_roles_by_id={**ctx.hero_roles_by_id, 1: ("support",)},
            hero_tags_by_id={**ctx.hero_tags_by_id, 1: ("buffer",)},
        )
        with patch(
            "ic_gamedata.formation_advisor.handlers.score_bench_replace",
            return_value=0.7,
        ):
            insights = evaluate_placement_handlers(ctx)
        self.assertFalse(any(i.rule_id == "heuristic_bench_buffer" for i in insights))


if __name__ == "__main__":
    unittest.main()
