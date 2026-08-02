"""Tests for formation placement advisor."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from ic_gamedata.formation_advisor.context_builder import build_formation_layout_context
from ic_gamedata.formation_advisor.evaluator import evaluate_formation_rules
from ic_gamedata.formation_advisor.handlers import evaluate_placement_handlers
from ic_gamedata.formation_advisor.loader import cached_formation_rules
from ic_gamedata.formation_advisor.models import FormationTopology
from ic_gamedata.formation_advisor.topology import load_formation_topology
from ic_gamedata.formation_advisor.advisor import build_formation_insights
from ic_gamedata.party_advisor import FormationHero, analyze_party


def _hero(
    hid: int,
    name: str,
    seat: int,
    *,
    roles: tuple[str, ...] = ("dps",),
    tags: tuple[str, ...] = (),
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
        highest_damage=0.0,
        active_feats=1,
        is_top_damage=False,
    )


class FormationAdvisorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        path = Path(__file__).resolve().parent.parent / "webRequestLog_example.json"
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
        payload = dict(self.payload)
        inst = payload["details"]["game_instances"][0]
        inst["hero_in_seats"] = {"9": 113, "1": 147, "2": 2}
        save = inst.get("formation_saves_v2") or payload["details"].get("formation_saves_v2")
        if isinstance(save, list) and save:
            grid = list(save[0].get("formation") or [])
            if len(grid) >= 1:
                grid[0] = 113
                save[0]["formation"] = grid
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
        payload = dict(self.payload)
        inst = payload["details"]["game_instances"][0]
        inst["hero_in_seats"] = {"1": 113, "9": 147}
        save = inst.get("formation_saves_v2") or payload["details"].get("formation_saves_v2")
        if isinstance(save, list) and save:
            grid = list(save[0].get("formation") or [])
            if len(grid) >= 4:
                grid[3] = 113
                grid[0] = 147
                save[0]["formation"] = grid
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
            _hero(147, "Azaka", 5, roles=("dps",)),
            _hero(1, "Bruenor", 12, roles=("support",), tags=("buffer",)),
            _hero(2, "Celeste", 6, roles=("healer", "support"), tags=("buffer",)),
        )
        payload = dict(self.payload)
        inst = payload["details"]["game_instances"][0]
        inst["hero_in_seats"] = {"5": 147, "12": 1, "6": 2}
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


if __name__ == "__main__":
    unittest.main()
