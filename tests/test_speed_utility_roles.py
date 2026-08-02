"""Tests for speed-team utility roles (gem gold, modron scavenger)."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from ic_gamedata.party_advisor import FormationHero, analyze_party
from ic_gamedata.seat_advisor import build_seat_advisor_report
from ic_gamedata.seat_advisor.role_inference import infer_seat_role
from ic_gamedata.speed_utility_roles import (
    best_presto_spec_for_party,
    recommended_spec_for_speed_utility,
    speed_utility_role,
)


def _hero(
    hid: int,
    name: str,
    seat: int,
    *,
    roles: tuple[str, ...] = ("support",),
    tags: tuple[str, ...] = (),
) -> FormationHero:
    return FormationHero(
        hero_id=hid,
        name=name,
        seat=seat,
        level=200,
        gear_score=10.0,
        ilvl=100,
        ilvl_pct_vs_avg=0.0,
        gear_rank=1,
        gear_rank_total=1,
        gear_pct_of_best=100.0,
        gear_label="ilvl 100",
        role_label=roles[0].capitalize() if roles else "Support",
        roles=roles,
        tags=tags,
        highest_damage=0.0,
        active_feats=1,
        is_top_damage=False,
    )


class SpeedUtilityRoleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        path = Path(__file__).resolve().parent.parent / "webRequestLog_example.json"
        cls.payload = json.loads(path.read_text(encoding="utf-8"))

    def test_ellywick_in_speed_team_is_gold_utility(self) -> None:
        hero = _hero(83, "Ellywick", 3, roles=("support", "gold", "healer"), tags=("gold", "buffer"))
        self.assertEqual(speed_utility_role(hero, "speed"), "gold")
        self.assertEqual(
            infer_seat_role(hero, zone="mid", bud_hero_id=None, goal="speed", context="campaign"),
            "gold",
        )

    def test_presto_in_speed_team_is_modron_utility(self) -> None:
        hero = _hero(144, "Presto", 2, roles=("support",), tags=("debuffer",))
        self.assertEqual(speed_utility_role(hero, "speed"), "modron")
        self.assertEqual(
            infer_seat_role(hero, zone="mid", bud_hero_id=None, goal="speed", context="campaign"),
            "modron",
        )

    def test_ellywick_utility_spec_is_all_that_sparkles(self) -> None:
        hero = _hero(83, "Ellywick", 3, roles=("support", "gold", "healer"), tags=("gold", "buffer"))
        spec = recommended_spec_for_speed_utility(hero, (hero,), utility="gold")
        self.assertEqual(spec, "All That Sparkles")

    def test_presto_utility_spec_prefers_humble_for_mixed_party(self) -> None:
        formation = (
            _hero(139, "Thellora", 1, roles=("support",)),
            _hero(144, "Presto", 2, roles=("support",)),
            _hero(125, "BBEG", 3, roles=("support",)),
            _hero(75, "Hew Maan", 4, roles=("support",)),
            _hero(148, "Diana", 5, roles=("support",)),
            _hero(58, "Briv", 6, roles=("support",), tags=("speed",)),
        )
        self.assertEqual(best_presto_spec_for_party(formation), "Humble Heroes")
        presto = formation[1]
        spec = recommended_spec_for_speed_utility(presto, formation, utility="modron")
        self.assertEqual(spec, "Humble Heroes")

    def test_speed_seat_report_recommends_utility_specs(self) -> None:
        formation = (
            _hero(139, "Thellora", 1, roles=("support",)),
            _hero(144, "Presto", 2, roles=("support",), tags=("debuffer",)),
            _hero(83, "Ellywick", 3, roles=("support", "gold", "healer"), tags=("gold", "buffer")),
            _hero(58, "Briv", 4, roles=("support",), tags=("speed",)),
        )
        report = build_seat_advisor_report(
            self.payload,
            formation,
            goal="speed",
            context="campaign",
        )
        self.assertIsNotNone(report)
        assert report is not None
        by_name = {seat.hero_name: seat for seat in report.seats}
        self.assertEqual(by_name["Ellywick"].effective_role, "gold")
        self.assertEqual(by_name["Ellywick"].best_spec, "All That Sparkles")
        self.assertEqual(by_name["Presto"].effective_role, "modron")
        self.assertEqual(
            by_name["Presto"].best_spec,
            best_presto_spec_for_party(formation),
        )
        self.assertIn("Transmute Gems", [feat.name for feat in by_name["Ellywick"].recommended_feats])
        self.assertIn("Morning Lineup", [feat.name for feat in by_name["Presto"].recommended_feats])

    def test_analyze_party_speed_includes_utility_spec_insights(self) -> None:
        report = analyze_party(
            self.payload,
            goal="speed",
            context="campaign",
            include_specializations=True,
        )
        if not report.seat_report:
            self.skipTest("no active formation in example payload")
        elly = next((s for s in report.seat_report.seats if s.hero_name == "Ellywick"), None)
        if elly is None:
            self.skipTest("Ellywick not in example formation")
        if elly.effective_role == "gold":
            self.assertEqual(elly.best_spec, "All That Sparkles")


if __name__ == "__main__":
    unittest.main()
