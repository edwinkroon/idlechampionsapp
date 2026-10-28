"""Tests for seat-centric party advisor."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ic_gamedata.adventure_restrictions import (
    AdventureRosterFilter,
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

    def test_bud_seats_keep_best_spec_without_match_insights(self) -> None:
        """Regression: Specializations tab only showed role-guide matches.

        Match insights are omitted on purpose; BUD/campaign must still resolve
        best_spec so every formation seat can appear in In orde / Actie nodig.
        """
        report = analyze_party(
            self.payload,
            goal="bud",
            context="campaign",
            include_specializations=True,
            include_formation=False,
        )
        self.assertIsNotNone(report.seat_report)
        assert report.seat_report is not None
        self.assertGreaterEqual(len(report.formation_heroes), 5)
        self.assertEqual(len(report.seat_report.seats), len(report.formation_heroes))
        with_spec = [s for s in report.seat_report.seats if s.best_spec]
        # Most formation heroes should get a recommendation; requiring only
        # role-guide specialization_names previously left ~2 visible.
        self.assertGreaterEqual(len(with_spec), max(3, len(report.seat_report.seats) // 2))
        for seat in with_spec:
            self.assertIn(seat.spec_status, {"match", "mismatch", "pending"})

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
        # Presence does not override patron/adventure blocks.
        self.assertFalse(
            is_hero_allowed(1, roster_filter, formation_hero_ids=formation_ids)
        )
        self.assertFalse(is_hero_allowed(1, roster_filter))
        # Without presence-override, seated blocked heroes get replace priority.
        self.assertEqual(bruenor.relevance_reason, "Not allowed — replace")


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
        self.assertNotIn("No formation positions", report.seat_report.html_grid)

    def test_formation_visual_matches_live_grid_not_saves_or_bench(self) -> None:
        """Formatie tab must show the live board, not denser saves / benched seats."""
        live = [139, 91, 59, 113, 43, -1, -1, -1, -1]
        payload = {
            "details": {
                "active_game_instance_id": 1,
                "current_adventure_id": 1,
                "game_instances": [
                    {
                        "game_instance_id": 1,
                        "hero_in_seats": {
                            "1": 139,
                            "2": 91,
                            "3": 59,
                            "4": 113,
                            "5": 43,
                            # Benched seat-holders still listed — must not appear.
                            "6": 6,
                            "7": 7,
                            "8": 8,
                            "9": 9,
                            "10": 10,
                            "11": 11,
                            "12": 12,
                        },
                        "formation": live,
                        "formation_saves_v2": [
                            {
                                "name": "gemfarm",
                                "formation": [58, 1, 2, 3, 4, 5, 6, 7, 8],
                            }
                        ],
                        "stats": {},
                    }
                ],
                "heroes": [
                    {"hero_id": hid, "owned": 1, "level": 100, "game_instance_id": 1, "in_seat": 1}
                    for hid in (
                        list(range(1, 13))
                        + [139, 91, 59, 113, 43, 58]
                    )
                ],
            }
        }
        report = analyze_party(payload, goal="bud", context="campaign", include_formation=True)
        self.assertIsNotNone(report.seat_report)
        assert report.seat_report is not None
        node_ids = {n.hero_id for n in report.seat_report.visual_nodes if n.hero_id is not None}
        self.assertEqual(node_ids, {139, 91, 59, 113, 43})
        formation_ids = {h.hero_id for h in report.formation_heroes}
        self.assertEqual(formation_ids, {139, 91, 59, 113, 43})
        self.assertNotIn(58, node_ids)
        self.assertNotIn(1, node_ids)

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
        self.assertNotIn("No formation positions", seat_report.html_grid)

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

    def test_seat_report_includes_recommended_visual_nodes_for_owned_upgrades(self) -> None:
        formation = (
            _hero(3, "Nayeli", 3, roles=("tank", "support"), tags=("buffer",)),
            _hero(147, "Azaka", 9, roles=("dps",), is_top_damage=True),
        )
        with patch(
            "ic_gamedata.roster_upgrade_advisor.suggest_roster_upgrades",
            return_value=(
                type(
                    "Suggestion",
                    (),
                    {
                        "candidate_hero_id": 43,
                        "candidate_name": "Spurt",
                        "candidate_seat": 3,
                        "replace_hero_id": 3,
                        "replace_name": "Nayeli",
                        "replace_seat": 3,
                        "same_seat_swap": True,
                    },
                )(),
            ),
        ):
            seat_report = build_seat_advisor_report(
                self.payload,
                formation,
                goal="bud",
                context="campaign",
            )
        self.assertIsNotNone(seat_report)
        assert seat_report is not None
        nodes = [n for n in seat_report.recommended_visual_nodes if n.hero_id is not None]
        self.assertTrue(nodes)
        self.assertIn(43, {n.hero_id for n in nodes})
        self.assertNotIn(3, {n.hero_id for n in nodes})

    def test_recommended_visual_nodes_hidden_when_restrictions_are_uncertain(self) -> None:
        formation = (
            _hero(3, "Nayeli", 3, roles=("tank", "support"), tags=("buffer",)),
            _hero(147, "Azaka", 9, roles=("dps",), is_top_damage=True),
        )
        with patch(
            "ic_gamedata.roster_upgrade_advisor.suggest_roster_upgrades",
            return_value=(
                type(
                    "Suggestion",
                    (),
                    {
                        "candidate_hero_id": 43,
                        "candidate_name": "Spurt",
                        "candidate_seat": 3,
                        "replace_hero_id": 3,
                        "replace_name": "Nayeli",
                        "replace_seat": 3,
                        "same_seat_swap": True,
                    },
                )(),
            ),
        ):
            seat_report = build_seat_advisor_report(
                self.payload,
                formation,
                goal="bud",
                context="campaign",
                roster_filter=AdventureRosterFilter(has_unknown_rules=True),
            )
        self.assertIsNotNone(seat_report)
        assert seat_report is not None
        self.assertEqual(seat_report.recommended_visual_nodes, ())
        self.assertIn("restrictions", seat_report.recommended_hidden_reason or "")

    def test_recommended_visual_nodes_shown_when_patron_rules_allow_candidate(self) -> None:
        formation = (
            _hero(3, "Nayeli", 3, roles=("tank", "support"), tags=("buffer",)),
            _hero(147, "Azaka", 9, roles=("dps",), is_top_damage=True),
        )
        with patch(
            "ic_gamedata.roster_upgrade_advisor.suggest_roster_upgrades",
            return_value=(
                type(
                    "Suggestion",
                    (),
                    {
                        "candidate_hero_id": 43,
                        "candidate_name": "Spurt",
                        "candidate_seat": 3,
                        "replace_hero_id": 3,
                        "replace_name": "Nayeli",
                        "replace_seat": 3,
                        "same_seat_swap": True,
                    },
                )(),
            ),
        ):
            seat_report = build_seat_advisor_report(
                self.payload,
                formation,
                goal="bud",
                context="campaign",
                roster_filter=AdventureRosterFilter(patron_id=2),
            )
        self.assertIsNotNone(seat_report)
        assert seat_report is not None
        self.assertIsNone(seat_report.recommended_hidden_reason)
        self.assertTrue(
            any(n.hero_id == 43 for n in seat_report.recommended_visual_nodes),
            msg=seat_report.recommended_visual_nodes,
        )

    def test_recommended_visual_nodes_skip_disallowed_candidates(self) -> None:
        formation = (
            _hero(3, "Nayeli", 3, roles=("tank", "support"), tags=("buffer",)),
            _hero(147, "Azaka", 9, roles=("dps",), is_top_damage=True),
        )
        with patch(
            "ic_gamedata.roster_upgrade_advisor.suggest_roster_upgrades",
            return_value=(
                type(
                    "Suggestion",
                    (),
                    {
                        "candidate_hero_id": 43,
                        "candidate_name": "Spurt",
                        "candidate_seat": 3,
                        "replace_hero_id": 3,
                        "replace_name": "Nayeli",
                        "replace_seat": 3,
                        "same_seat_swap": True,
                    },
                )(),
            ),
        ):
            seat_report = build_seat_advisor_report(
                self.payload,
                formation,
                goal="bud",
                context="campaign",
                roster_filter=AdventureRosterFilter(
                    patron_id=2,
                    banned_hero_ids={43},
                ),
            )
        self.assertIsNotNone(seat_report)
        assert seat_report is not None
        self.assertFalse(any(n.hero_id == 43 for n in seat_report.recommended_visual_nodes))

    def test_seat_report_resolves_seat_when_formation_hero_seat_missing(self) -> None:
        """Champ overview must not stay empty when only permanent seat_id is known."""
        formation = (
            FormationHero(
                hero_id=139,
                name="Thellora",
                seat=None,
                level=100,
                gear_score=10.0,
                ilvl=100,
                ilvl_pct_vs_avg=0.0,
                gear_rank=1,
                gear_rank_total=1,
                gear_pct_of_best=100.0,
                gear_label="ilvl 100",
                role_label="Dps",
                roles=("dps",),
                tags=(),
                highest_damage=1e12,
                active_feats=1,
                is_top_damage=True,
            ),
        )
        seat_report = build_seat_advisor_report(
            self.payload,
            formation,
            goal="bud",
            context="campaign",
        )
        self.assertIsNotNone(seat_report)
        assert seat_report is not None
        self.assertEqual(len(seat_report.seats), 1)
        self.assertEqual(seat_report.seats[0].hero_id, 139)
        self.assertEqual(seat_report.seats[0].seat, 1)

    def test_recommended_visual_nodes_recheck_candidate_against_current_roster_filter(self) -> None:
        formation = (
            _hero(3, "Nayeli", 3, roles=("tank", "support"), tags=("buffer",)),
            _hero(147, "Azaka", 9, roles=("dps",), is_top_damage=True),
        )
        with patch(
            "ic_gamedata.roster_upgrade_advisor.suggest_roster_upgrades",
            return_value=(
                type(
                    "Suggestion",
                    (),
                    {
                        "candidate_hero_id": 43,
                        "candidate_name": "Spurt",
                        "candidate_seat": 3,
                        "replace_hero_id": 3,
                        "replace_name": "Nayeli",
                        "replace_seat": 3,
                        "same_seat_swap": True,
                    },
                )(),
            ),
        ):
            seat_report = build_seat_advisor_report(
                self.payload,
                formation,
                goal="bud",
                context="campaign",
                roster_filter=AdventureRosterFilter(banned_hero_ids={43}),
            )
        self.assertIsNotNone(seat_report)
        assert seat_report is not None
        self.assertEqual(seat_report.recommended_visual_nodes, ())


if __name__ == "__main__":
    unittest.main()
