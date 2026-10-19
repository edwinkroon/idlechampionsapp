"""User-facing advice goals: definitions, migration, export contract, locks."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from ic_gamedata.advice_goals import (
    GOAL_DEFINITIONS,
    USER_GOAL_IDS,
    build_goal_export_object,
    build_goal_parameters,
    migrate_stored_goal,
    scoring_lane,
    validate_goal_parameters,
)
from ic_gamedata.formation_ai_advice.clipboard_export import (
    build_advice_payload,
    format_clipboard_markdown,
    format_swap_clipboard_markdown,
)
from ic_gamedata.formation_ai_advice.export import build_export_payload
from ic_gamedata.formation_ai_advice.swap_export import build_swap_export_payload
from ic_gamedata.party_advisor_models import FormationHero
from ic_ui.widgets.advisor_controls import AdvisorGoalContextBar, _SHARED_SETTINGS_KEY


def _hero(hid: int, name: str, seat: int, *, roles=()) -> FormationHero:
    return FormationHero(
        hero_id=hid,
        name=name,
        seat=seat,
        level=100,
        gear_score=1.0,
        ilvl=100,
        ilvl_pct_vs_avg=0.0,
        gear_rank=1,
        gear_rank_total=1,
        gear_pct_of_best=1.0,
        gear_label="ok",
        role_label=",".join(roles) or "support",
        roles=tuple(roles),
        tags=(),
        highest_damage=0.0,
        active_feats=0,
        is_top_damage=False,
    )


class AdviceGoalDefinitionTests(unittest.TestCase):
    def test_all_goals_have_label_metric_priorities(self) -> None:
        self.assertEqual(len(USER_GOAL_IDS), 6)
        for gid in USER_GOAL_IDS:
            definition = GOAL_DEFINITIONS[gid]
            self.assertEqual(definition.id, gid)
            self.assertTrue(definition.label.strip())
            self.assertTrue(definition.description.strip())
            self.assertTrue(definition.primary_metric.strip())
            self.assertGreaterEqual(len(definition.priorities), 3)
        self.assertIn("gold_farm", USER_GOAL_IDS)
        self.assertEqual(GOAL_DEFINITIONS["gold_farm"].primary_metric, "gold_income")

    def test_gems_primary_metric_is_gems_per_hour_not_bud(self) -> None:
        definition = GOAL_DEFINITIONS["gem_farm"]
        self.assertEqual(definition.primary_metric, "gems_per_hour")
        joined = " ".join(definition.priorities).casefold()
        self.assertIn("gems", joined)
        self.assertIn("maximale bud", joined)
        self.assertIn("geen zelfstandig doel", joined)

    def test_favor_not_same_as_max_area(self) -> None:
        definition = GOAL_DEFINITIONS["favor_farm"]
        self.assertEqual(definition.primary_metric, "favor_yield_for_chosen_horizon")
        joined = " ".join(definition.priorities).casefold()
        self.assertIn("hoogste gebied niet", joined)

    def test_scoring_lane_is_not_silent_user_migration(self) -> None:
        self.assertEqual(scoring_lane("push"), "bud")
        self.assertEqual(scoring_lane("gem_farm"), "speed")
        self.assertEqual(scoring_lane("gold_farm"), "gold")
        self.assertEqual(scoring_lane("favor_farm"), "gold")
        # Scoring helpers may still see legacy lanes; that is not a user migration.
        self.assertEqual(scoring_lane("speed"), "speed")
        self.assertEqual(scoring_lane("gold"), "gold")


class AdviceGoalMigrationTests(unittest.TestCase):
    def test_bud_proposes_push_with_confirm(self) -> None:
        result = migrate_stored_goal("bud")
        self.assertEqual(result.proposed_id, "push")
        self.assertEqual(result.goal_id, "push")
        self.assertTrue(result.needs_confirm)
        self.assertIn("BUD", result.message or "")

    def test_speed_not_silently_gem_farm(self) -> None:
        result = migrate_stored_goal("speed")
        self.assertIsNone(result.goal_id)
        self.assertIsNone(result.proposed_id)
        self.assertTrue(result.needs_confirm)
        self.assertNotEqual(result.proposed_id, "gem_farm")
        self.assertIn("niet automatisch Gems", result.message or "")

    def test_gold_proposes_gold_farm_not_favor(self) -> None:
        result = migrate_stored_goal("gold")
        self.assertEqual(result.goal_id, "gold_farm")
        self.assertEqual(result.proposed_id, "gold_farm")
        self.assertTrue(result.needs_confirm)
        self.assertIn("Gold verzamelen", result.message or "")
        self.assertIn("Favor", result.message or "")

    def test_new_goal_ids_need_no_confirm(self) -> None:
        for gid in USER_GOAL_IDS:
            result = migrate_stored_goal(gid)
            self.assertEqual(result.goal_id, gid)
            self.assertFalse(result.needs_confirm)


class AdviceGoalParameterTests(unittest.TestCase):
    def test_custom_task_requires_description(self) -> None:
        ok, err = validate_goal_parameters("custom_task", {})
        self.assertFalse(ok)
        self.assertIn("taakomschrijving", (err or "").casefold())

    def test_custom_task_ok_with_description(self) -> None:
        ok, err = validate_goal_parameters(
            "custom_task", {"task_description": "Unlock feat X"}
        )
        self.assertTrue(ok)
        self.assertIsNone(err)

    def test_gem_missing_optional_context_is_unknown_not_zero(self) -> None:
        params, missing = build_goal_parameters("gem_farm", user_parameters={})
        self.assertEqual(params["play_mode"], "unknown")
        self.assertEqual(params["auto_reset"], "unknown")
        self.assertIsNone(params["reset_area"])
        self.assertIn("play_mode", missing)
        self.assertIn("reset_area", missing)

    def test_quest_end_condition_unknown_when_missing(self) -> None:
        params, missing = build_goal_parameters("quest_clear", user_parameters={})
        self.assertIsNone(params["required_area"])
        self.assertEqual(params["required_area_source"], "unknown")
        self.assertIn("end_condition", missing)


class AdviceGoalExportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        path = Path(__file__).resolve().parent / "fixtures" / "webRequestLog_example.json"
        cls.payload = json.loads(path.read_text(encoding="utf-8"))
        cls.formation = (
            _hero(3, "Nayeli", 1, roles=("tank", "support")),
            _hero(2, "Celeste", 2, roles=("healer", "support")),
            _hero(4, "Jarlaxle", 3, roles=("dps", "gold")),
            _hero(47, "Shandie", 6, roles=("support", "speed")),
        )

    def test_label_prompt_and_json_match(self) -> None:
        export = build_export_payload(
            self.payload,
            self.formation,
            goal="quest_clear",
            context="campaign",
            fixed_main_dps_id=None,
            goal_parameters={"required_area": 50},
            request_id="goal-quest-1",
        )
        goal = export["goal"]
        self.assertEqual(goal["id"], "quest_clear")
        self.assertEqual(goal["label"], GOAL_DEFINITIONS["quest_clear"].label)
        self.assertEqual(
            goal["primary_metric"],
            GOAL_DEFINITIONS["quest_clear"].primary_metric,
        )
        self.assertEqual(goal["priorities"], list(GOAL_DEFINITIONS["quest_clear"].priorities))
        self.assertEqual(goal["parameters"]["required_area"], 50)
        self.assertEqual(goal["parameters"]["required_area_source"], "user")
        self.assertNotIn("objective", goal)
        self.assertIsNone(goal.get("fixed_main_dps_id"))

        md = format_clipboard_markdown(export)
        self.assertIn(f"Doel: {goal['label']}.", md)
        self.assertIn(goal["primary_metric"], md)
        advice = build_advice_payload(export)
        ctx_goal = (advice.get("context") or {}).get("goal") or {}
        self.assertEqual(ctx_goal.get("id"), "quest_clear")
        self.assertEqual(ctx_goal.get("label"), goal["label"])
        self.assertEqual(ctx_goal.get("primary_metric"), goal["primary_metric"])

    def test_gem_farm_export_without_fixed_dps(self) -> None:
        export = build_export_payload(
            self.payload,
            self.formation,
            goal="gem_farm",
            context="campaign",
            fixed_main_dps_id=None,
            goal_parameters={"play_mode": "background", "auto_reset": "unknown"},
            request_id="goal-gem-1",
        )
        goal = export["goal"]
        self.assertEqual(goal["id"], "gem_farm")
        self.assertEqual(goal["primary_metric"], "gems_per_hour")
        self.assertEqual(goal["parameters"]["play_mode"], "background")
        self.assertEqual(goal["parameters"]["auto_reset"], "unknown")
        self.assertIsNone(goal.get("damage_focus"))
        self.assertEqual(goal.get("fixed_champion_ids") or [], [])
        self.assertFalse(export["constraints"]["main_dps_locked"])

        md = format_clipboard_markdown(export)
        self.assertIn("Gems verzamelen", md)
        self.assertIn("Geen vaste hoofd-DPS", md)
        self.assertNotIn("objective", json.dumps(goal))

        swap = build_swap_export_payload(
            self.payload,
            self.formation,
            goal="gem_farm",
            context="campaign",
            fixed_main_dps_id=None,
            goal_parameters={"play_mode": "background", "auto_reset": "unknown"},
            request_id="goal-gem-swap-1",
        )
        self.assertEqual(swap["goal"]["id"], "gem_farm")
        self.assertFalse(swap["constraints"]["main_dps_locked"])
        self.assertEqual(swap["constraints"]["fixed_champion_ids"], [])
        for champ in swap["champions"]:
            self.assertFalse(champ.get("locked"))
        # Seat 6 (Shandie) is not locked → seat alternatives remain eligible for coverage.
        seat6_excluded_for_lock = [
            row
            for row in (swap.get("swap") or {}).get("excluded") or []
            if row.get("seat") == 6
            and "lock" in str(row.get("reason") or "").casefold()
        ]
        self.assertEqual(seat6_excluded_for_lock, [])
        swap_md = format_swap_clipboard_markdown(swap)
        self.assertIn("Gems verzamelen", swap_md)
        self.assertIn("geen vaste hoofd-dps", swap_md.casefold())

    def test_push_with_explicit_fixed_main_dps(self) -> None:
        export = build_export_payload(
            self.payload,
            self.formation,
            goal="push",
            context="campaign",
            fixed_main_dps_id=47,
            request_id="goal-push-fixed-1",
        )
        goal = export["goal"]
        self.assertEqual(goal["id"], "push")
        self.assertEqual(goal["fixed_main_dps_id"], 47)
        self.assertEqual(goal["damage_focus"]["kind"], "fixed")
        self.assertEqual(goal["damage_focus"]["champion_id"], 47)
        self.assertEqual(goal["fixed_champion_ids"], [47])
        self.assertTrue(export["constraints"]["main_dps_locked"])

        md = format_clipboard_markdown(export)
        self.assertIn("Doel: Push.", md)
        self.assertIn("Vaste hoofd-DPS", md)
        self.assertIn("Shandie", md)
        advice = build_advice_payload(export)
        self.assertEqual(
            ((advice.get("context") or {}).get("damage_focus") or {}).get("champion_id"),
            47,
        )

    def test_no_auto_main_dps_from_carry(self) -> None:
        export = build_export_payload(
            self.payload,
            self.formation,
            goal="push",
            context="campaign",
            fixed_main_dps_id=None,
            request_id="goal-push-nofixed-1",
        )
        self.assertIsNone(export["goal"].get("fixed_main_dps_id"))
        self.assertIsNone(export["goal"].get("damage_focus"))
        self.assertNotIn("main_dps_id", export["goal"])

    def test_goal_change_changes_next_export(self) -> None:
        push = build_export_payload(
            self.payload,
            self.formation,
            goal="push",
            context="campaign",
            fixed_main_dps_id=None,
            request_id="a",
        )
        gems = build_export_payload(
            self.payload,
            self.formation,
            goal="gem_farm",
            context="campaign",
            fixed_main_dps_id=None,
            request_id="b",
        )
        self.assertEqual(push["goal"]["id"], "push")
        self.assertEqual(gems["goal"]["id"], "gem_farm")
        self.assertNotEqual(push["goal"]["priorities"], gems["goal"]["priorities"])
        self.assertNotEqual(
            push["goal"]["primary_metric"], gems["goal"]["primary_metric"]
        )
        self.assertNotIn("push_damage", json.dumps(gems["goal"]))

        quest = build_export_payload(
            self.payload,
            self.formation,
            goal="quest_clear",
            context="campaign",
            fixed_main_dps_id=None,
            goal_parameters={"required_area": 40},
            request_id="c",
        )
        self.assertEqual(quest["goal"]["id"], "quest_clear")
        self.assertEqual(quest["goal"]["parameters"]["required_area"], 40)
        self.assertNotEqual(quest["goal"]["priorities"], gems["goal"]["priorities"])

    def test_explicit_user_lock_preserved_without_fixed_dps(self) -> None:
        export = build_swap_export_payload(
            self.payload,
            self.formation,
            goal="favor_farm",
            context="campaign",
            fixed_main_dps_id=None,
            locked_champion_ids=[3],
            goal_parameters={"time_horizon": "per_run"},
            request_id="goal-favor-lock-1",
        )
        self.assertEqual(export["goal"]["fixed_champion_ids"], [3])
        self.assertIsNone(export["goal"].get("fixed_main_dps_id"))
        nayeli = next(c for c in export["champions"] if c["champion_id"] == 3)
        self.assertTrue(nayeli.get("locked"))
        self.assertEqual(nayeli.get("lock_reason"), "user_lock")

    def test_legacy_speed_goal_raises_instead_of_silent_gem_farm(self) -> None:
        with self.assertRaises(ValueError):
            build_export_payload(
                self.payload,
                self.formation,
                goal="speed",
                context="campaign",
                fixed_main_dps_id=None,
                request_id="legacy-speed",
            )

    def test_build_goal_export_object_contract(self) -> None:
        goal = build_goal_export_object(
            "gem_farm",
            user_parameters={"play_mode": "unknown"},
            fixed_main_dps_id=None,
        )
        for key in (
            "id",
            "label",
            "description",
            "primary_metric",
            "priorities",
            "parameters",
            "missing_context",
        ):
            self.assertIn(key, goal)
        self.assertEqual(goal["parameters"]["play_mode"], "unknown")
        self.assertIsNone(goal["parameters"]["reset_area"])


class AdvisorGoalBarMigrationUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        AdvisorGoalContextBar._live.clear()
        self._settings = QSettings("IdleChampions", "Companion")
        for key in (
            f"{_SHARED_SETTINGS_KEY}/goal",
            f"{_SHARED_SETTINGS_KEY}/context",
            f"{_SHARED_SETTINGS_KEY}/goal_confirmed",
            "advisor/goal",
            "advisor/context",
        ):
            self._settings.remove(key)

    def test_legacy_speed_requires_confirm_not_gem_farm(self) -> None:
        self._settings.setValue("advisor/goal", "speed")
        bar = AdvisorGoalContextBar()
        self.addCleanup(lambda: AdvisorGoalContextBar._live.clear())
        self.assertTrue(bar.needs_goal_confirm())
        self.assertIsNone(bar.goal_or_none())
        self.assertIn("niet automatisch Gems", bar.migration_message() or "")

    def test_confirming_goal_persists_new_id(self) -> None:
        self._settings.setValue(f"{_SHARED_SETTINGS_KEY}/goal", "bud")
        bar = AdvisorGoalContextBar()
        self.addCleanup(lambda: AdvisorGoalContextBar._live.clear())
        self.assertTrue(bar.needs_goal_confirm())
        bar.set_goal_context("push")
        self.assertFalse(bar.needs_goal_confirm())
        self.assertEqual(bar.goal(), "push")
        self.assertEqual(
            str(self._settings.value(f"{_SHARED_SETTINGS_KEY}/goal")),
            "push",
        )


if __name__ == "__main__":
    unittest.main()
