"""Tests for party advisor."""

from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from ic_gamedata.party_advisor import analyze_party, format_report


class PartyAdvisorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        path = Path(__file__).resolve().parent.parent / "webRequestLog_example.json"
        cls.payload = json.loads(path.read_text(encoding="utf-8"))

    def test_bud_analysis_has_formation(self) -> None:
        report = analyze_party(self.payload, goal="bud", context="campaign")
        self.assertGreater(len(report.formation_heroes), 0)
        self.assertGreater(len(report.improvements), 0)
        self.assertEqual(report.goal, "bud")

    def test_gold_analysis_has_improvements(self) -> None:
        report = analyze_party(self.payload, goal="gold", context="events")
        self.assertGreater(len(report.tips), 0)
        self.assertEqual(report.context, "events")

    def test_format_report_readable(self) -> None:
        report = analyze_party(self.payload, goal="bud", context="push")
        text = format_report(report)
        self.assertIn("Party", text)
        self.assertIn("Formation-tips", text)
        self.assertNotIn("Wat verbeteren", text)
        self.assertNotIn("Party-overzicht", text)
        self.assertRegex(text, r"\[1\]")
        self.assertNotRegex(text, r"\d{20,}")

    def test_tip_numbers_are_sequential(self) -> None:
        report = analyze_party(self.payload, goal="bud", context="campaign")
        numbers = [tip.priority for tip in report.tips]
        self.assertEqual(numbers, list(range(1, len(numbers) + 1)))

    def test_no_restrictions_tip_filtered(self) -> None:
        from ic_gamedata.party_advisor import (
            _is_actionable_adventure_rule,
            _is_useful_adventure_note,
        )

        self.assertFalse(_is_useful_adventure_note("No restrictions"))
        self.assertFalse(_is_useful_adventure_note("no restriction"))
        self.assertFalse(_is_actionable_adventure_rule("No restrictions"))
        self.assertTrue(
            _is_actionable_adventure_rule(
                "Your heroes do three times more damage, but attack a third as often"
            )
        )

    def test_composition_advice_only_when_useful(self) -> None:
        from ic_gamedata.party_advisor import FormationHero, _composition_advice

        def hero(hid: int, name: str, roles: tuple[str, ...], tags: tuple[str, ...] = ()) -> FormationHero:
            return FormationHero(
                hero_id=hid,
                name=name,
                seat=hid,
                level=100,
                gear_score=1.0,
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

        # Balanced party: no composition tips expected
        balanced = (
            hero(1, "Gale", ("dps", "support"), ("buffer",)),
            hero(2, "Nayeli", ("tank", "support"), ("buffer",)),
            hero(3, "Krull", ("support",), ("debuffer", "bud")),
            hero(4, "Avren", ("support",), ("buffer",)),
            hero(5, "Celeste", ("healer", "support"), ("buffer",)),
            hero(6, "Briv", ("tank", "support"), ("speed", "buffer")),
            hero(7, "Jarlaxle", ("dps", "gold"), ("gold",)),
            hero(8, "Asharra", ("dps", "support"), ("buffer",)),
        )
        owned = [(9, "Widdle", ("support",), ("speed",))]
        self.assertEqual(
            _composition_advice(balanced, goal="bud", context="campaign", owned=owned),
            [],
        )

        # No tank in push → tip
        no_tank = (
            hero(1, "Gale", ("dps", "support"), ("buffer",)),
            hero(2, "Asharra", ("dps", "support")),
            hero(3, "Delina", ("dps",)),
        )
        titles = [t.title for t in _composition_advice(no_tank, goal="bud", context="push", owned=[])]
        self.assertTrue(any("tank" in t.lower() for t in titles))

        # Modron without speed → tip
        no_speed = (
            hero(1, "Gale", ("dps", "support"), ("buffer",)),
            hero(2, "Nayeli", ("tank", "support")),
        )
        titles = [
            t.title
            for t in _composition_advice(
                no_speed,
                goal="bud",
                context="modron",
                owned=[(91, "Widdle", ("support",), ("speed",))],
            )
        ]
        self.assertTrue(any("speed" in t.lower() for t in titles))

    def test_resolve_bud_hero_prefers_dps_over_support_gear_leader(self) -> None:
        from ic_gamedata.party_advisor import FormationHero, _resolve_bud_hero

        def hero(
            hid: int,
            name: str,
            roles: tuple[str, ...],
            *,
            gear_score: float = 1.0,
            highest_damage: float = 0.0,
            is_top_damage: bool = False,
            tags: tuple[str, ...] = (),
        ) -> FormationHero:
            return FormationHero(
                hero_id=hid,
                name=name,
                seat=hid,
                level=100,
                gear_score=gear_score,
                ilvl=100,
                ilvl_pct_vs_avg=0.0,
                gear_rank=1,
                gear_rank_total=2,
                gear_pct_of_best=100.0,
                gear_label="ilvl 100",
                role_label=roles[0].capitalize() if roles else "Onbekend",
                roles=roles,
                tags=tags,
                highest_damage=highest_damage,
                active_feats=1,
                is_top_damage=is_top_damage,
            )

        formation = (
            hero(157, "Eric", ("support", "tank", "gold"), gear_score=999.0, tags=("buffer", "gold")),
            hero(147, "Azaka", ("dps",), gear_score=10.0, highest_damage=1e12, is_top_damage=True),
        )
        bud = _resolve_bud_hero(formation)
        self.assertIsNotNone(bud)
        assert bud is not None
        self.assertEqual(bud.name, "Azaka")

    def test_formation_heroes_excludes_benched_top_damage_champion(self) -> None:
        from ic_gamedata.party_advisor import _formation_heroes, analyze_party

        payload = copy.deepcopy(self.payload)
        details = payload["details"]
        active_id = details.get("active_game_instance_id")
        instance = None
        for inst in details.get("game_instances") or []:
            if str(inst.get("game_instance_id")) == str(active_id):
                instance = inst
                break
        self.assertIsNotNone(instance)
        assert instance is not None

        benched_hero_id = 43
        for hero in details.get("heroes") or []:
            if str(hero.get("hero_id")) == str(benched_hero_id):
                hero["in_seat"] = "0"
                break
        else:
            self.skipTest("hero 43 not in fixture")

        stats = instance.setdefault("stats", {})
        stats["this_reset_highest_damage_dealt_hero_id"] = str(benched_hero_id)

        formation = _formation_heroes(payload)
        self.assertFalse(any(h.hero_id == benched_hero_id for h in formation))

        report = analyze_party(payload, goal="bud", context="campaign")
        self.assertFalse(any(h.hero_id == benched_hero_id for h in report.formation_heroes))
        if report.seat_report is not None and report.seat_report.bud_hero_id is not None:
            self.assertNotEqual(report.seat_report.bud_hero_id, benched_hero_id)

    def test_formation_heroes_excludes_benched_when_seat_mapping_stale(self) -> None:
        from ic_gamedata.party_advisor import _formation_heroes, analyze_party

        payload = copy.deepcopy(self.payload)
        details = payload["details"]
        for hero in details.get("heroes") or []:
            if isinstance(hero, dict):
                hero["in_seat"] = "0"
        for inst in details.get("game_instances") or []:
            if not isinstance(inst, dict):
                continue
            inst["formation"] = []
            inst["hero_in_seats"] = {}
            inst["formation_saves_v2"] = []

        formation = _formation_heroes(payload)
        self.assertEqual(formation, ())

        report = analyze_party(payload, goal="bud", context="campaign")
        self.assertEqual(report.formation_heroes, ())
        if report.seat_report is not None:
            self.assertEqual(report.seat_report.seats, ())

    def test_formation_heroes_uses_grid_when_in_seat_zero_after_party_swap(self) -> None:
        """Non-active parties keep in_seat=0 in getuserdetails; still show their formation."""
        from ic_gamedata.party_advisor import _formation_heroes

        payload = {
            "details": {
                "active_game_instance_id": 4,
                "game_instances": [
                    {
                        "game_instance_id": 4,
                        "hero_in_seats": {"1": 12, "2": 128, "6": 26, "12": 1},
                        "formation": [12, 128, 26, 1, -1],
                        "stats": {},
                    }
                ],
                "heroes": [
                    {"hero_id": 12, "in_seat": 0, "game_instance_id": 4, "level": 100},
                    {"hero_id": 128, "in_seat": 0, "game_instance_id": 4, "level": 100},
                    {"hero_id": 26, "in_seat": 0, "game_instance_id": 4, "level": 100},
                    {"hero_id": 1, "in_seat": 0, "game_instance_id": 4, "level": 100},
                    {"hero_id": 58, "in_seat": 1, "game_instance_id": 1, "level": 200},
                ],
            }
        }
        formation = _formation_heroes(payload)
        ids = {hero.hero_id for hero in formation}
        self.assertEqual(ids, {12, 128, 26, 1})
        self.assertNotIn(58, ids)

    def test_formation_buffer_tip_targets_bud_not_support(self) -> None:
        from ic_gamedata.formation_advisor.context_builder import build_formation_layout_context
        from ic_gamedata.formation_advisor.evaluator import evaluate_formation_rules
        from ic_gamedata.party_advisor import FormationHero

        formation = (
            FormationHero(
                hero_id=157,
                name="Eric",
                seat=4,
                level=100,
                gear_score=999.0,
                ilvl=200,
                ilvl_pct_vs_avg=50.0,
                gear_rank=1,
                gear_rank_total=2,
                gear_pct_of_best=100.0,
                gear_label="ilvl 200",
                role_label="Support",
                roles=("support", "tank", "gold"),
                tags=("buffer", "gold"),
                highest_damage=0.0,
                active_feats=1,
                is_top_damage=False,
            ),
            FormationHero(
                hero_id=147,
                name="Azaka",
                seat=1,
                level=100,
                gear_score=10.0,
                ilvl=100,
                ilvl_pct_vs_avg=0.0,
                gear_rank=2,
                gear_rank_total=2,
                gear_pct_of_best=50.0,
                gear_label="ilvl 100",
                role_label="Dps",
                roles=("dps",),
                tags=(),
                highest_damage=1e12,
                active_feats=1,
                is_top_damage=True,
            ),
            FormationHero(
                hero_id=2,
                name="Celeste",
                seat=12,
                level=100,
                gear_score=5.0,
                ilvl=100,
                ilvl_pct_vs_avg=0.0,
                gear_rank=3,
                gear_rank_total=3,
                gear_pct_of_best=25.0,
                gear_label="ilvl 100",
                role_label="Healer",
                roles=("healer", "support"),
                tags=("buffer",),
                highest_damage=0.0,
                active_feats=1,
                is_top_damage=False,
            ),
        )
        payload = copy.deepcopy(self.payload)
        inst = payload["details"]["game_instances"][0]
        inst["hero_in_seats"] = {"4": 157, "1": 147, "12": 2}
        stats = inst.setdefault("stats", {})
        stats["this_reset_highest_damage_dealt_hero_id"] = 147
        ctx = build_formation_layout_context(
            payload,
            formation,
            goal="bud",
            context="campaign",
        )
        self.assertEqual(ctx.carry_hero_id, 147)
        insights = evaluate_formation_rules(ctx)
        buffer_tips = [i for i in insights if i.rule_id == "buffer_far_from_carry"]
        self.assertTrue(buffer_tips)
        self.assertIn("Azaka", buffer_tips[0].detail)
        self.assertNotIn("Eric", buffer_tips[0].detail.split("carry")[0])

    def test_bud_tip_uses_actual_carry_not_gear_leader(self) -> None:
        from ic_gamedata.party_advisor import FormationHero, _formation_tips

        def hero(
            hid: int,
            name: str,
            roles: tuple[str, ...],
            *,
            gear_score: float = 1.0,
            is_top_damage: bool = False,
            tags: tuple[str, ...] = (),
        ) -> FormationHero:
            return FormationHero(
                hero_id=hid,
                name=name,
                seat=hid,
                level=100,
                gear_score=gear_score,
                ilvl=100,
                ilvl_pct_vs_avg=0.0,
                gear_rank=1,
                gear_rank_total=2,
                gear_pct_of_best=100.0,
                gear_label="ilvl 100",
                role_label=roles[0].capitalize() if roles else "Onbekend",
                roles=roles,
                tags=tags,
                highest_damage=1e12 if is_top_damage else 0.0,
                active_feats=1,
                is_top_damage=is_top_damage,
            )

        formation = (
            hero(157, "Eric", ("support", "tank", "gold"), gear_score=999.0, tags=("buffer",)),
            hero(147, "Azaka", ("dps",), is_top_damage=True),
        )
        tips = _formation_tips(
            formation,
            goal="bud",
            context="campaign",
            owned=[],
            modifiers=[],
            adventure_buff_note=None,
            gold_growth_rate=None,
        )
        joined = " ".join(t.title + " " + t.detail for t in tips)
        self.assertIn("BUD deze run: Azaka", joined)
        self.assertIn("Azaka", joined)
        self.assertNotIn("BUD deze run: Eric", joined)
        self.assertIn("Geen debuffer voor Azaka", joined)

    def test_debuffer_tip_suppressed_when_formation_rule_covers(self) -> None:
        from ic_gamedata.formation_advisor.models import FormationInsight
        from ic_gamedata.party_advisor import _coverage_from_formation_insights

        covered = _coverage_from_formation_insights(
            (
                FormationInsight(
                    insight_type="warning",
                    hero_id=None,
                    hero_name="",
                    seat=None,
                    related_hero_id=None,
                    related_hero_name=None,
                    related_seat=None,
                    priority=3,
                    headline="Geen debuffer",
                    detail="",
                    rule_source_type="heuristic",
                    data_source_version="formation_rules_v1",
                    confidence=3,
                    rule_id="carry_no_debuffer",
                ),
            )
        )
        self.assertIn("carry_no_debuffer", covered)

        report = analyze_party(
            self.payload,
            goal="bud",
            context="campaign",
            include_formation=True,
        )
        debuffer_titles = [t.title for t in report.tips if "debuffer" in t.title.lower()]
        # Either suppressed or renamed — should not have generic "Geen debuffer in formation"
        self.assertFalse(any(t == "Geen debuffer in formation" for t in debuffer_titles))

    def test_formation_insights_not_duplicated_in_formation_tips(self) -> None:
        report = analyze_party(
            self.payload,
            goal="bud",
            context="campaign",
            include_formation=True,
        )
        if not report.formation_insights:
            self.skipTest("no formation insights in fixture")
        insight_headlines = {ins.headline for ins in report.formation_insights}
        tip_titles = {t.title for t in report.tips}
        overlap = insight_headlines & tip_titles
        self.assertEqual(overlap, set(), f"duplicated headlines: {overlap}")

    def test_formation_tips_skip_generic_when_seat_report_present(self) -> None:
        report = analyze_party(
            self.payload,
            goal="bud",
            context="campaign",
            include_formation=True,
        )
        if report.seat_report is None or not report.seat_report.seats:
            self.skipTest("no seat report in fixture")
        titles = {tip.title.casefold() for tip in report.tips}
        self.assertNotIn("adventure damage-buff", titles)
        self.assertNotIn("adventure-regel", titles)
        self.assertFalse(
            any(title.startswith("bud deze run:") or title.startswith("bud-focus:") for title in titles)
        )
        self.assertFalse(any(title.endswith("-modus") for title in titles))

    def test_party_section_includes_inline_improves(self) -> None:
        report = analyze_party(self.payload, goal="bud", context="campaign")
        text = format_report(report)
        self.assertIn("ilvl", text)
        if report.improvements:
            # Improve actions appear under Party, not as a separate section.
            self.assertIn("→", text)
            first_action = report.improvements[0].action
            party_idx = text.index("Party")
            action_idx = text.index(first_action)
            tips_idx = text.index("Formation-tips")
            self.assertLess(party_idx, action_idx)
            self.assertLess(action_idx, tips_idx)

    def test_speed_goal_summary_and_role_inference(self) -> None:
        from ic_gamedata.party_advisor import FormationHero, goal_label
        from ic_gamedata.seat_advisor.role_inference import infer_seat_role

        self.assertEqual(goal_label("speed"), "Speed / areas")

        def hero(hid: int, name: str, *, tags: tuple[str, ...] = ()) -> FormationHero:
            return FormationHero(
                hero_id=hid,
                name=name,
                seat=hid,
                level=100,
                gear_score=10.0,
                ilvl=100,
                ilvl_pct_vs_avg=0.0,
                gear_rank=1,
                gear_rank_total=1,
                gear_pct_of_best=100.0,
                gear_label="ilvl 100",
                role_label="Support",
                roles=("support",),
                tags=tags,
                highest_damage=0.0,
                active_feats=1,
                is_top_damage=False,
            )

        briv = hero(58, "Briv", tags=("speed",))
        role = infer_seat_role(briv, zone="mid", bud_hero_id=None, goal="speed", context="campaign")
        self.assertEqual(role, "speed")

        report = analyze_party(self.payload, goal="speed", context="campaign", include_formation=True)
        self.assertEqual(report.goal, "speed")
        self.assertIn("Speed-advies", report.summary)
        if report.seat_report is not None:
            self.assertIsNotNone(report.seat_report.speed_hero_name)

    def test_modron_context_filters_generic_mode_tip(self) -> None:
        report = analyze_party(
            self.payload,
            goal="bud",
            context="modron",
            include_formation=True,
        )
        titles = {tip.title.casefold() for tip in report.tips}
        self.assertNotIn("modron-modus", titles)

    def test_weak_gear_shows_ilvl_vs_avg(self) -> None:
        report = analyze_party(self.payload, goal="bud", context="campaign")
        weak = [
            item
            for item in report.improvements
            if "party-gemiddelde" in item.headline or "onder party-gemiddelde" in item.action
        ]
        self.assertTrue(weak)
        for item in weak:
            self.assertRegex(item.action, r"ilvl \d+")
            self.assertIn("% onder party-gemiddelde", item.action)
            self.assertNotIn("Open chests", item.action)
            self.assertNotIn("wissel uit", item.action)
        for hero in report.formation_heroes:
            self.assertRegex(hero.gear_label, r"^ilvl \d+")

    def test_ilvl_is_average_per_slot_not_sum(self) -> None:
        from ic_gamedata.party_advisor import _loot_ilvl_by_hero

        details = {
            "loot": [
                {"hero_id": 1, "slot_id": 1, "enchant": 1446},
                {"hero_id": 1, "slot_id": 2, "enchant": 1446},
                {"hero_id": 1, "slot_id": 3, "enchant": 1446},
                {"hero_id": 1, "slot_id": 4, "enchant": 1446},
                {"hero_id": 1, "slot_id": 5, "enchant": 1446},
                {"hero_id": 1, "slot_id": 6, "enchant": 1446},
                # duplicate row for slot 1 must not inflate ilvl
                {"hero_id": 1, "slot_id": 1, "enchant": 1446},
            ]
        }
        ilvl = _loot_ilvl_by_hero(details)[1]
        self.assertEqual(ilvl, 1447)
        self.assertLess(ilvl, 2000)

    def test_disallowed_adventure_tip_suggests_bench_alternatives(self) -> None:
        from ic_gamedata.adventure_restrictions import AdventureRosterFilter, is_hero_allowed
        from ic_gamedata.party_advisor import FormationHero, _formation_tips

        def hero(
            hid: int,
            name: str,
            seat: int,
            roles: tuple[str, ...],
            *,
            tags: tuple[str, ...] = (),
            is_top_damage: bool = False,
        ) -> FormationHero:
            return FormationHero(
                hero_id=hid,
                name=name,
                seat=seat,
                level=400,
                gear_score=1.0,
                ilvl=500,
                ilvl_pct_vs_avg=0.0,
                gear_rank=1,
                gear_rank_total=5,
                gear_pct_of_best=100.0,
                gear_label="ilvl 500",
                role_label=roles[0].capitalize() if roles else "Onbekend",
                roles=roles,
                tags=tags,
                highest_damage=1e12 if is_top_damage else 0.0,
                active_feats=1,
                is_top_damage=is_top_damage,
            )

        roster_filter = AdventureRosterFilter(
            min_stats=[("int", 10), ("str", 9)],
            active_notes=["Min. INT 10", "Min. STR 9"],
        )
        self.assertFalse(is_hero_allowed(166, roster_filter))
        self.assertFalse(is_hero_allowed(172, roster_filter))
        self.assertTrue(is_hero_allowed(2, roster_filter))

        formation = (
            hero(147, "Azaka", 1, ("dps",), is_top_damage=True),
            hero(166, "Cazrin", 3, ("dps", "support"), tags=("buffer",)),
            hero(172, "Kyre", 7, ("support",), tags=("buffer",)),
        )
        formation_ids = frozenset({147, 166, 172})
        self.assertTrue(is_hero_allowed(166, roster_filter, formation_hero_ids=formation_ids))
        self.assertTrue(is_hero_allowed(172, roster_filter, formation_hero_ids=formation_ids))

        owned = [
            (147, "Azaka", ("dps",), ()),
            (166, "Cazrin", ("dps", "support"), ("buffer",)),
            (172, "Kyre", ("support",), ("buffer",)),
            (2, "Celeste", ("healer", "support"), ("buffer",)),
            (6, "Asharra", ("dps", "support"), ("buffer",)),
        ]
        tips = _formation_tips(
            formation,
            goal="bud",
            context="campaign",
            owned=owned,
            modifiers=[],
            adventure_buff_note=None,
            gold_growth_rate=None,
            roster_filter=roster_filter,
            ilvl_by_hero={2: 900, 6: 850},
        )
        self.assertFalse(any("niet toegestaan" in tip.title.casefold() for tip in tips))

    def test_formation_not_full_skipped_when_npc_slots_fill_capacity(self) -> None:
        from ic_gamedata.party_advisor import FormationHero, _composition_advice

        def hero(hid: int, name: str, seat: int) -> FormationHero:
            return FormationHero(
                hero_id=hid,
                name=name,
                seat=seat,
                level=400,
                gear_score=1.0,
                ilvl=500,
                ilvl_pct_vs_avg=0.0,
                gear_rank=1,
                gear_rank_total=5,
                gear_pct_of_best=100.0,
                gear_label="ilvl 500",
                role_label="Support",
                roles=("support",),
                tags=("buffer",),
                highest_damage=0.0,
                active_feats=1,
                is_top_damage=False,
            )

        formation = tuple(hero(hid, f"H{hid}", seat) for hid, seat in zip((1, 2, 3, 4, 5, 6), range(1, 7)))
        tips = _composition_advice(
            formation,
            goal="bud",
            context="campaign",
            owned=[],
            player_capacity=6,
        )
        self.assertFalse(any(tip.title == "Formatie niet vol" for tip in tips))


if __name__ == "__main__":
    unittest.main()
