"""Tests for seat-centric party advisor."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ic_gamedata.adventure_restrictions import (
    build_adventure_roster_filter,
    is_hero_allowed,
)
from ic_gamedata.party_advisor import FormationHero, analyze_party
from ic_gamedata.seat_advisor import build_seat_advisor_report
from ic_gamedata.seat_advisor.role_inference import infer_seat_role
from ic_gamedata.seat_advisor.role_prefs import (
    get_chosen_role,
    set_chosen_role,
)


def _hero(
    hid: int,
    name: str,
    seat: int,
    *,
    roles: tuple[str, ...] = ("dps",),
    tags: tuple[str, ...] = (),
    is_top_damage: bool = False,
) -> FormationHero:
    return FormationHero(
        hero_id=hid,
        name=name,
        seat=seat,
        level=100,
        gear_score=10.0,
        ilvl=100,
        ilvl_pct_vs_avg=0.0,
        gear_rank=1,
        gear_rank_total=1,
        gear_pct_of_best=100.0,
        gear_label="ilvl 100",
        role_label=roles[0].capitalize() if roles else "Onbekend",
        roles=roles,
        tags=tags,
        highest_damage=1e12 if is_top_damage else 0.0,
        active_feats=1,
        is_top_damage=is_top_damage,
    )


class SeatAdvisorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        path = Path(__file__).resolve().parent / "fixtures" / "webRequestLog_example.json"
        cls.payload = json.loads(path.read_text(encoding="utf-8"))

    def test_infer_bud_role_for_top_damage(self) -> None:
        hero = _hero(147, "Azaka", 1, roles=("dps",), is_top_damage=True)
        role = infer_seat_role(hero, zone="mid", bud_hero_id=147, goal="bud", context="campaign")
        self.assertEqual(role, "bud")

    def test_build_seat_report_sorted_by_priority(self) -> None:
        report = analyze_party(self.payload, goal="bud", context="campaign", include_formation=True)
        self.assertIsNotNone(report.seat_report)
        assert report.seat_report is not None
        seats = report.seat_report.seats
        self.assertGreater(len(seats), 0)
        priorities = [seat.priority for seat in seats]
        self.assertEqual(priorities, sorted(priorities))

    def test_role_preferences_persist_per_goal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            prefs_path = Path(tmp) / "champion_role_preferences.json"
            with patch("ic_gamedata.seat_advisor.role_prefs._prefs_path", return_value=prefs_path):
                set_chosen_role(157, "bud", "buffer")
                self.assertEqual(get_chosen_role(157, "bud"), "buffer")
                self.assertIsNone(get_chosen_role(157, "gold"))
                set_chosen_role(157, "bud", None)
                self.assertIsNone(get_chosen_role(157, "bud"))

    def test_seat_report_includes_html_grid(self) -> None:
        formation = (_hero(147, "Azaka", 9, roles=("dps",), is_top_damage=True),)
        seat_report = build_seat_advisor_report(
            self.payload,
            formation,
            goal="bud",
            context="campaign",
        )
        self.assertIsNotNone(seat_report)
        assert seat_report is not None
        self.assertIn("<html", seat_report.html_grid.lower())
        self.assertEqual(seat_report.seats[0].hero_name, "Azaka")

    def test_disallowed_hero_gets_replace_priority(self) -> None:
        payload = json.loads(
            (Path(__file__).resolve().parent / "fixtures" / "webRequestLog_example.json").read_text(encoding="utf-8")
        )
        payload["details"]["active_game_instance_id"] = "1"
        payload["details"]["game_instances"] = [
            {
                "game_instance_id": 1,
                "current_adventure_id": 14,
                "current_patron_id": 3,
            }
        ]
        formation = (_hero(1, "Bruenor", 1, roles=("support",), tags=("buffer",)),)
        roster_filter = build_adventure_roster_filter(payload, 14)
        seat_report = build_seat_advisor_report(
            payload,
            formation,
            goal="bud",
            context="campaign",
            roster_filter=roster_filter,
        )
        self.assertIsNotNone(seat_report)
        assert seat_report is not None
        bruenor = seat_report.seats[0]
        formation_ids = frozenset({1})
        self.assertTrue(is_hero_allowed(1, roster_filter, formation_hero_ids=formation_ids))
        self.assertFalse(is_hero_allowed(1, roster_filter))
        self.assertNotEqual(bruenor.relevance_reason, "Niet toegestaan op adventure/patron")


    def test_formation_visual_positions_do_not_overlap(self) -> None:
        report = analyze_party(self.payload, goal="bud", context="campaign", include_formation=True)
        self.assertIsNotNone(report.seat_report)
        assert report.seat_report is not None
        nodes = [n for n in report.seat_report.visual_nodes if n.hero_id is not None]
        self.assertGreaterEqual(len(nodes), 5)
        # Cards are ~100×58; require centers to be meaningfully apart.
        for i, a in enumerate(nodes):
            for b in nodes[i + 1 :]:
                dx = abs(a.x - b.x)
                dy = abs(a.y - b.y)
                self.assertTrue(
                    dx >= 90 or dy >= 50,
                    f"overlap seat {a.seat}@({a.x},{a.y}) vs seat {b.seat}@({b.x},{b.y})",
                )

        """hero_in_seats alone must still populate the formation board."""
        payload = json.loads(
            (Path(__file__).resolve().parent / "fixtures" / "webRequestLog_example.json").read_text(encoding="utf-8")
        )
        aid = int(payload["details"]["active_game_instance_id"])
        for inst in payload["details"]["game_instances"]:
            if int(inst["game_instance_id"]) != aid:
                continue
            inst["formation"] = [-1] * 9
            inst["formation_saves_v2"] = []
            break
        payload["details"]["formation"] = [-1] * 9
        payload["details"]["formation_saves_v2"] = []

        report = analyze_party(payload, goal="bud", context="campaign", include_formation=True)
        self.assertIsNotNone(report.seat_report)
        assert report.seat_report is not None
        nodes = [n for n in report.seat_report.visual_nodes if n.hero_id is not None]
        self.assertGreaterEqual(len(nodes), 10)
        self.assertNotIn("Geen formatie-posities", report.seat_report.html_grid)

    def test_formation_visual_uses_formation_seats_when_api_grid_missing(self) -> None:
        payload = json.loads(
            (Path(__file__).resolve().parent / "fixtures" / "webRequestLog_example.json").read_text(encoding="utf-8")
        )
        aid = int(payload["details"]["active_game_instance_id"])
        for inst in payload["details"]["game_instances"]:
            if int(inst["game_instance_id"]) != aid:
                continue
            inst["formation"] = [-1] * 9
            inst["formation_saves_v2"] = []
            inst["hero_in_seats"] = {}
            break
        payload["details"]["formation"] = [-1] * 9
        payload["details"]["formation_saves_v2"] = []

        # Party list still comes from another instance field in real runs; inject seats via analyze path
        # by restoring hero_in_seats for formation heroes only through seat report fallback.
        # Here we call build_seat_advisor_report with an explicit formation.
        from ic_gamedata.party_advisor import FormationHero
        from ic_gamedata.seat_advisor import build_seat_advisor_report

        formation = (
            FormationHero(
                hero_id=147,
                name="Gale",
                seat=1,
                level=100,
                gear_score=1.0,
                ilvl=100,
                ilvl_pct_vs_avg=0.0,
                gear_rank=1,
                gear_rank_total=1,
                gear_pct_of_best=100.0,
                gear_label="ilvl 100",
                role_label="Dps",
                roles=("dps",),
                tags=(),
                highest_damage=1.0,
                active_feats=0,
                is_top_damage=True,
            ),
            FormationHero(
                hero_id=58,
                name="Briv",
                seat=5,
                level=100,
                gear_score=1.0,
                ilvl=100,
                ilvl_pct_vs_avg=0.0,
                gear_rank=1,
                gear_rank_total=1,
                gear_pct_of_best=100.0,
                gear_label="ilvl 100",
                role_label="Support",
                roles=("support",),
                tags=("speed",),
                highest_damage=0.0,
                active_feats=0,
                is_top_damage=False,
            ),
        )
        seat_report = build_seat_advisor_report(payload, formation, goal="bud", context="campaign")
        self.assertIsNotNone(seat_report)
        assert seat_report is not None
        nodes = [n for n in seat_report.visual_nodes if n.hero_id is not None]
        self.assertEqual({n.seat for n in nodes}, {1, 5})
        self.assertNotIn("Geen formatie-posities", seat_report.html_grid)

    def test_role_advice_differs_for_nayeli_tank_vs_support(self) -> None:
        from ic_gamedata.champion_role_advice import clear_role_advice_cache, get_role_advice

        clear_role_advice_cache()
        tank = get_role_advice(3, "tank")
        support = get_role_advice(3, "support")
        self.assertIsNotNone(tank)
        self.assertIsNotNone(support)
        assert tank is not None and support is not None
        self.assertIn("Vengeance", " ".join(tank.specialization_names))
        self.assertIn("Devotion", " ".join(support.specialization_names))
        self.assertNotEqual(tank.specialization_names, support.specialization_names)

    def test_sentry_speed_feats_exclude_pushing_gems(self) -> None:
        from ic_gamedata.champion_role_advice import clear_role_advice_cache, get_role_advice

        clear_role_advice_cache()
        speed = get_role_advice(52, "speed")
        support = get_role_advice(52, "support")
        self.assertIsNotNone(speed)
        self.assertIsNotNone(support)
        assert speed is not None and support is not None
        self.assertNotIn("Prodigal Leader", speed.feats)
        self.assertNotIn("Her Majesty's Rose", speed.feats)
        self.assertIn("Prodigal Leader", support.feats)
        self.assertIn("Her Majesty's Rose", support.feats)

    def test_speed_champs_exclude_pushing_feats_from_speed_role(self) -> None:
        from ic_gamedata.champion_role_advice import clear_role_advice_cache, get_role_advice

        clear_role_advice_cache()
        cases = (
            (58, "Briv", ("Wasting Haste",), ("Pirate Plating",)),
            (47, "Shandie", (), ("Explosive Ordinance", "Abyssal Trinkets")),
            (7, "Minsc", (), ("Prodigal Leader", "Weapon Master")),
        )
        for hero_id, _name, expected_speed, support_push in cases:
            speed = get_role_advice(hero_id, "speed")
            support = get_role_advice(hero_id, "support")
            self.assertIsNotNone(speed, msg=f"hero {hero_id}")
            self.assertIsNotNone(support, msg=f"hero {hero_id}")
            assert speed is not None and support is not None
            self.assertEqual(speed.feats, expected_speed, msg=f"hero {hero_id} speed feats")
            for feat in support_push:
                self.assertIn(feat, support.feats, msg=f"hero {hero_id} support")
                self.assertNotIn(feat, speed.feats, msg=f"hero {hero_id} speed")

    def test_role_advice_differs_for_fen_bud_vs_support(self) -> None:
        from ic_gamedata.champion_role_advice import clear_role_advice_cache, get_role_advice

        clear_role_advice_cache()
        bud = get_role_advice(118, "bud")
        support = get_role_advice(118, "support")
        self.assertIsNotNone(bud)
        self.assertIsNotNone(support)
        assert bud is not None and support is not None
        self.assertNotEqual(bud.specialization_names, support.specialization_names)

    def test_cazrin_bud_role_advice_prefers_ancestors_shadow(self) -> None:
        from ic_gamedata.champion_role_advice import clear_role_advice_cache, get_role_advice

        clear_role_advice_cache()
        bud = get_role_advice(166, "bud")
        self.assertIsNotNone(bud)
        assert bud is not None
        self.assertIn("Ancestor's Shadow", bud.specialization_names)
        self.assertEqual(bud.specialization_ids, (17679,))

    def test_seat_report_exposes_source_url_and_feats_block(self) -> None:
        formation = (_hero(3, "Nayeli", 2, roles=("tank", "support")),)
        seat_report = build_seat_advisor_report(
            self.payload, formation, goal="bud", context="campaign"
        )
        self.assertIsNotNone(seat_report)
        assert seat_report is not None
        seat = seat_report.seats[0]
        self.assertTrue(seat.advice_source)
        self.assertTrue(seat.recommended_feats)
        self.assertTrue(seat.advice_source_url.startswith("https://"))
        self.assertTrue(seat.formation_advice)


if __name__ == "__main__":
    unittest.main()
