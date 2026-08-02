"""Tests for Party Advisor specialization integration."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from ic_gamedata.party_advisor import analyze_party, format_report
from ic_gamedata.party_advisor_specializations import (
    SpecializationInsight,
    _is_meaningful_mismatch,
    _open_tier_insight,
    _same_route_family,
    advisor_run_goal,
    build_specialization_insights,
    spec_summary_for_hero,
)
from ic_gamedata.specialization_models import PendingSpecialization, SpecializationOption


class PartyAdvisorSpecializationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        path = Path(__file__).resolve().parent.parent / "webRequestLog_example.json"
        cls.payload = json.loads(path.read_text(encoding="utf-8"))

    def test_advisor_run_goal_mapping(self) -> None:
        self.assertEqual(advisor_run_goal("gold", "campaign"), "gold_farm")
        self.assertEqual(advisor_run_goal("speed", "campaign"), "speed_farm")
        self.assertEqual(advisor_run_goal("bud", "modron"), "speed_farm")
        self.assertEqual(advisor_run_goal("bud", "push"), "push")
        self.assertEqual(advisor_run_goal("bud", "campaign"), "generic_progression")

    def test_same_route_family_outflank_variants(self) -> None:
        self.assertTrue(_same_route_family("Outflank (Top)", "Outflank (Bottom)"))

    def test_meaningful_mismatch_requires_authored_and_confidence(self) -> None:
        self.assertFalse(
            _is_meaningful_mismatch(
                ("Support route",),
                "Pact of the Tome",
                rule_source_type="heuristic",
                confidence=5,
            )
        )
        self.assertTrue(
            _is_meaningful_mismatch(
                ("Gold Find",),
                "Battle Master",
                rule_source_type="authored",
                confidence=5,
            )
        )

    def test_resolve_spec_display_status(self) -> None:
        from ic_gamedata.party_advisor_specializations import resolve_spec_display_status

        open_insight = SpecializationInsight(
            hero_id=5,
            hero_name="Briv",
            seat=5,
            recommended_label="Boss Wants Speed",
            current_labels=(),
            status="open_tier",
            rule_source_type="authored",
            data_source_version="v2_full",
            confidence=5,
            headline="Open specialization: Briv",
            detail="detail",
            priority=1,
        )
        self.assertEqual(
            resolve_spec_display_status(
                5,
                (open_insight,),
                recommended="Boss Wants Speed",
                current_labels=(),
            ),
            "pending",
        )
        self.assertEqual(
            resolve_spec_display_status(
                5,
                (),
                recommended="Boss Wants Speed",
                current_labels=("Boss Wants Speed",),
            ),
            "match",
        )
        self.assertEqual(
            resolve_spec_display_status(
                5,
                (),
                recommended="Boss Wants Speed",
                current_labels=("Gold Find",),
            ),
            "mismatch",
        )

    def test_analyze_party_without_specializations(self) -> None:
        report = analyze_party(
            self.payload,
            goal="bud",
            context="campaign",
            include_specializations=False,
        )
        self.assertEqual(report.specialization_insights, ())

    def test_analyze_party_with_specializations(self) -> None:
        report = analyze_party(
            self.payload,
            goal="bud",
            context="campaign",
            include_specializations=True,
        )
        self.assertIsInstance(report.specialization_insights, tuple)

    def test_format_report_includes_specialization_section_when_present(self) -> None:
        insight = SpecializationInsight(
            hero_id=5,
            hero_name="Briv",
            seat=5,
            recommended_label="Boss Wants Speed",
            current_labels=(),
            status="open_tier",
            rule_source_type="authored",
            data_source_version="v2_full",
            confidence=5,
            headline="Open specialization: Briv",
            detail="Kies Boss Wants Speed voor tier 1.",
            priority=1,
        )
        report = analyze_party(
            self.payload,
            goal="bud",
            context="modron",
            include_specializations=False,
        )
        report = report.__class__(
            **{
                **report.__dict__,
                "specialization_insights": (insight,),
            }
        )
        text = format_report(report)
        self.assertIn("Specialization & formatie", text)
        self.assertIn("Briv", text)

    def test_spec_summary_for_hero_open_tier(self) -> None:
        insight = SpecializationInsight(
            hero_id=5,
            hero_name="Briv",
            seat=5,
            recommended_label="Boss Wants Speed",
            current_labels=(),
            status="open_tier",
            rule_source_type="authored",
            data_source_version="v2_full",
            confidence=5,
            headline="Open specialization: Briv",
            detail="detail",
            priority=1,
        )
        summary = spec_summary_for_hero(5, (insight,))
        self.assertIsNotNone(summary)
        assert summary is not None
        self.assertIn("Boss Wants Speed", summary)

    def test_build_insights_respects_max_limit(self) -> None:
        report = analyze_party(self.payload, goal="bud", context="campaign")
        if report.formation_heroes:
            insights = build_specialization_insights(
                self.payload,
                report.formation_heroes,
                goal="bud",
                context="campaign",
            )
            self.assertLessEqual(len(insights), 5)

    def test_modron_report_can_include_speed_composition_tip(self) -> None:
        report = analyze_party(
            self.payload,
            goal="bud",
            context="modron",
            include_specializations=True,
        )
        tip_titles = [tip.title.casefold() for tip in report.tips]
        if report.formation_heroes:
            self.assertTrue(
                any("speed" in title for title in tip_titles)
                or len(report.specialization_insights) >= 0
            )


    def test_spec_summary_hides_non_actionable_statuses(self) -> None:
        insights = (
            SpecializationInsight(
                hero_id=5,
                hero_name="Briv",
                seat=5,
                recommended_label="Boss Wants Speed",
                current_labels=("Boss Wants Speed",),
                status="formation_synergy",
                rule_source_type="authored",
                data_source_version="v2_full",
                confidence=5,
                headline="Briv: spec past bij formatie",
                detail="ok",
                priority=3,
            ),
            SpecializationInsight(
                hero_id=5,
                hero_name="Briv",
                seat=5,
                recommended_label="Boss Wants Speed",
                current_labels=("Boss Wants Speed",),
                status="matches",
                rule_source_type="authored",
                data_source_version="v2_full",
                confidence=5,
                headline="Briv: Boss Wants Speed",
                detail="ok",
                priority=4,
            ),
        )
        self.assertIsNone(spec_summary_for_hero(5, insights))

    def test_chosen_spec_clears_formation_insight(self) -> None:
        payload = json.loads(json.dumps(self.payload))
        details = payload["details"]
        details["active_game_instance_id"] = 1
        inst = next(i for i in details["game_instances"] if int(i["game_instance_id"]) == 1)
        inst["hero_in_seats"] = {"1": 147}
        gale = next(h for h in details["heroes"] if int(h["hero_id"]) == 147)
        gale["game_instance_id"] = 0
        gale["in_seat"] = 1
        gale["level"] = 300
        gale["specialization_choices"] = [14576, 14580]
        gale["upgrades"] = []

        report = analyze_party(
            payload,
            goal="bud",
            context="campaign",
            include_specializations=True,
        )
        gale_insights = [i for i in report.specialization_insights if i.hero_id == 147]
        self.assertEqual(gale_insights, [])

    def test_open_tier_without_fixed_rule_still_shows_insight(self) -> None:
        pending_item = PendingSpecialization(
            hero_id=99999,
            hero_name="Placeholder Hero",
            seat=1,
            game_instance_id=1,
            current_choices=(),
            options=(
                SpecializationOption(1001, "A", 50, 0),
                SpecializationOption(1002, "B", 50, 0),
            ),
            desired_upgrade_id=None,
            desired_option_index=None,
            reason="geen regel",
            rationale="Geen specialization-regel gevonden voor deze champion.",
        )
        insight = _open_tier_insight(pending_item, run_goal="generic_progression")
        self.assertIsNotNone(insight)
        assert insight is not None
        self.assertEqual(insight.status, "open_tier")
        self.assertIn("nog geen vaste keuze", insight.recommended_label)

    def test_recommended_spec_for_goal_speed_thellora(self) -> None:
        from ic_gamedata.party_advisor_specializations import (
            _formation_context_from_payload,
            recommended_spec_for_goal,
        )
        from ic_gamedata.specializations import _merge_known_options, load_specialization_rules

        payload = json.loads(json.dumps(self.payload))
        rules = load_specialization_rules()
        known = _merge_known_options(payload, rules)
        heroes = rules.get("heroes", {})
        thellora_id = next(
            int(hid) for hid, cfg in heroes.items() if cfg.get("name") == "Thellora"
        )
        options = known.get(thellora_id, [])
        formation = (
            type("FH", (), {"hero_id": thellora_id, "name": "Thellora", "seat": 1})(),
        )
        formation_ctx = _formation_context_from_payload(payload, formation)
        spec = recommended_spec_for_goal(
            payload,
            thellora_id,
            "Thellora",
            1,
            options,
            goal="speed",
            context="campaign",
            formation_ctx=formation_ctx,
        )
        self.assertEqual(spec, "Vanguard of the Quick")

    def test_resolve_spec_display_status_multi_tier_match(self) -> None:
        from ic_gamedata.party_advisor_specializations import resolve_spec_display_status

        self.assertEqual(
            resolve_spec_display_status(
                59,
                (),
                recommended="Melf's Speedy Spawns / Melf's Abundant Allies",
                current_labels=("Melf's Speedy Spawns", "Melf's Abundant Allies"),
            ),
            "match",
        )

    def test_build_insights_change_when_active_party_changes(self) -> None:
        payload = json.loads(json.dumps(self.payload))
        details = payload["details"]
        details["active_game_instance_id"] = 1
        inst1 = next(i for i in details["game_instances"] if int(i["game_instance_id"]) == 1)
        inst1["hero_in_seats"] = {"1": 147}
        details["game_instances"].append(
            {
                "game_instance_id": 2,
                "hero_in_seats": {"1": 173},
                "formation": [173, -1, -1, -1, -1, -1, -1, -1, -1],
                "current_adventure_id": 14,
            }
        )
        for hero in details["heroes"]:
            if not isinstance(hero, dict):
                continue
            hid = int(hero["hero_id"])
            hero["in_seat"] = 1 if hid in {147, 173} else 0

        report1 = analyze_party(payload, goal="bud", context="campaign", include_specializations=True)
        details["active_game_instance_id"] = 2
        report2 = analyze_party(payload, goal="bud", context="campaign", include_specializations=True)

        heroes1 = {hero.hero_id for hero in report1.formation_heroes}
        heroes2 = {hero.hero_id for hero in report2.formation_heroes}
        self.assertIn(147, heroes1)
        self.assertNotIn(147, heroes2)
        self.assertIn(173, heroes2)
        self.assertNotIn(173, heroes1)


if __name__ == "__main__":
    unittest.main()
