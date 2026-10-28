"""Acceptance: project pointer, goal≠modron, eligibility corrections."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ic_gamedata.advice_goals import (
    build_goal_export_object,
    build_goal_parameters,
)
from ic_gamedata.formation_ai_advice.eligibility_corrections import (
    find_correction,
    load_corrections,
    make_user_confirmation,
    revoke_correction,
    upsert_correction,
)
from ic_gamedata.formation_ai_advice.export_clipboard import (
    TEST_FOCUSED_ADVICE_POINTER,
    build_advice_request_clipboard_text,
    instruction_mode_assumption,
)
from ic_gamedata.formation_ai_advice.export_validation import (
    validate_advice_request_export,
)
from ic_gamedata.formation_ai_advice.snapshot_export import (
    _eligibility_presence_conflicts,
    build_advice_request,
    build_base_snapshot,
)
from ic_gamedata.formation_ai_advice.snapshot_store import (
    get_exported_snapshot_meta,
    save_base_snapshot_to_basisgegevens,
)
from ic_gamedata.party_advisor_models import FormationHero


def _hero(hero_id: int, name: str, seat: int) -> FormationHero:
    return FormationHero(
        hero_id=hero_id,
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
        role_label="Dps",
        roles=("dps",),
        tags=(),
        highest_damage=0.0,
        active_feats=1,
        is_top_damage=False,
    )


class ProjectInstructionPointerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        path = Path(__file__).resolve().parent / "fixtures" / "webRequestLog_example.json"
        cls.payload = json.loads(path.read_text(encoding="utf-8"))
        cls.formation = (
            _hero(3, "Nayeli", 1),
            _hero(2, "Celeste", 2),
            _hero(4, "Jarlaxle", 3),
        )

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        root = Path(self._tmpdir.name)
        self._patches = [
            patch(
                "ic_gamedata.paths.ADVICE_SNAPSHOT_REGISTRY_PATH",
                root / "reg.json",
            ),
            patch(
                "ic_gamedata.formation_ai_advice.snapshot_store.ADVICE_SNAPSHOT_REGISTRY_PATH",
                root / "reg.json",
            ),
            patch(
                "ic_gamedata.paths.BASISGEGEVENS_DIR",
                root / "basisgegevens",
            ),
            patch(
                "ic_gamedata.formation_ai_advice.snapshot_store.BASISGEGEVENS_DIR",
                root / "basisgegevens",
            ),
            patch(
                "ic_gamedata.formation_ai_advice.owned_roster_cache.OWNED_ROSTER_CACHE_PATH",
                root / "owned.json",
            ),
            patch(
                "ic_gamedata.formation_ai_advice.eligibility_corrections.CORRECTIONS_PATH",
                root / "elig.json",
            ),
        ]
        for p in self._patches:
            p.start()

    def tearDown(self) -> None:
        for p in self._patches:
            p.stop()
        self._tmpdir.cleanup()

    def test_project_mode_contains_pointer_once(self) -> None:
        snap = build_base_snapshot(
            self.payload, formation=self.formation, goal="push", context="campaign"
        )
        saved = save_base_snapshot_to_basisgegevens(snap)
        meta = get_exported_snapshot_meta()
        assert meta is not None
        req = build_advice_request(
            self.payload,
            self.formation,
            snapshot_id=str(meta["snapshot_id"]),
            snapshot_meta=meta,
            goal="push",
            context="campaign",
            include_swap_scope=False,
        )
        text = build_advice_request_clipboard_text(req, mode="project")
        self.assertEqual(text.count(TEST_FOCUSED_ADVICE_POINTER), 1)
        self.assertIn("Voer onderstaande ADVICE_REQUEST nu uit", text)
        self.assertIn(instruction_mode_assumption("project"), text)
        self.assertIn(str(meta["snapshot_id"]), text)
        self.assertIn(saved.name, text)
        # Full PROJECT_INSTRUCTIONS body must not be re-embedded.
        self.assertNotIn("# Idle Champions — vaste projectinstructies", text)

    def test_standalone_mode_does_not_embed_project_pointer(self) -> None:
        snap = build_base_snapshot(
            self.payload, formation=self.formation, goal="push", context="campaign"
        )
        save_base_snapshot_to_basisgegevens(snap)
        meta = get_exported_snapshot_meta()
        assert meta is not None
        req = build_advice_request(
            self.payload,
            self.formation,
            snapshot_id=str(meta["snapshot_id"]),
            snapshot_meta=meta,
            goal="push",
            context="campaign",
            include_swap_scope=False,
        )
        text = build_advice_request_clipboard_text(req, mode="standalone")
        self.assertNotIn(TEST_FOCUSED_ADVICE_POINTER, text)


class GoalModronSeparationTests(unittest.TestCase):
    def test_quest_clear_keeps_user_area_despite_modron(self) -> None:
        payload = {
            "details": {
                "game_instances": [
                    {
                        "game_instance_id": 1,
                        "current_adventure_id": 100,
                        "current_patron_id": 5,
                        "current_area": 10,
                        "modron_reset_area": 350,
                    }
                ],
                "active_game_instance_id": 1,
            }
        }
        with patch(
            "ic_gamedata.advice_goals.extract_live_goal_context",
            return_value={
                "current_area": 10,
                "adventure_area_goal": None,
                "modron_area_goal": 350,
                "campaign_id": 1,
                "campaign_name": "Test",
                "adventure_id": 100,
                "adventure_name": "Variant",
            },
        ):
            goal = build_goal_export_object(
                "quest_clear",
                user_parameters={"required_area": 825},
                payload=payload,
            )
        self.assertEqual(goal["id"], "quest_clear")
        self.assertEqual(goal["parameters"]["required_area"], 825)
        self.assertEqual(goal["parameters"]["required_area_source"], "user")
        self.assertEqual(goal["observed_modron"]["reset_area"], 350)
        self.assertEqual(goal["observed_modron"]["reset_area_source"], "modron_data")
        self.assertEqual(goal["observed_modron"]["auto_reset"], "unknown")
        self.assertEqual(goal["observed_modron"]["play_mode"], "unknown")

    def test_modron_alone_does_not_invent_gem_farm_flags(self) -> None:
        with patch(
            "ic_gamedata.advice_goals.extract_live_goal_context",
            return_value={
                "current_area": 1,
                "adventure_area_goal": None,
                "modron_area_goal": 350,
                "campaign_id": None,
                "campaign_name": None,
                "adventure_id": None,
                "adventure_name": None,
            },
        ):
            params, missing = build_goal_parameters("gem_farm", user_parameters={})
        self.assertEqual(params["reset_area"], 350)
        self.assertEqual(params["reset_area_source"], "modron_data")
        self.assertEqual(params["play_mode"], "unknown")
        self.assertEqual(params["auto_reset"], "unknown")
        self.assertIn("play_mode", missing)
        self.assertIn("auto_reset", missing)

    def test_explicit_gem_farm_keeps_user_reset(self) -> None:
        with patch(
            "ic_gamedata.advice_goals.extract_live_goal_context",
            return_value={
                "current_area": 1,
                "adventure_area_goal": None,
                "modron_area_goal": 999,
                "campaign_id": None,
                "campaign_name": None,
                "adventure_id": None,
                "adventure_name": None,
            },
        ):
            params, _missing = build_goal_parameters(
                "gem_farm",
                user_parameters={
                    "reset_area": 350,
                    "play_mode": "background",
                    "auto_reset": "yes",
                },
            )
        self.assertEqual(params["reset_area"], 350)
        self.assertEqual(params["reset_area_source"], "user")
        self.assertEqual(params["play_mode"], "background")
        self.assertEqual(params["auto_reset"], "yes")


class EligibilityCorrectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.path = Path(self._tmpdir.name) / "elig.json"
        self._patch = patch(
            "ic_gamedata.formation_ai_advice.eligibility_corrections.CORRECTIONS_PATH",
            self.path,
        )
        self._patch.start()

    def tearDown(self) -> None:
        self._patch.stop()
        self._tmpdir.cleanup()

    def _deny_rows(self, hero_ids, _filt, **_kwargs):
        return [
            {
                "champion_id": hid,
                "status": "denied",
                "reason": "CON gate",
            }
            for hid in hero_ids
        ]

    def test_presence_without_correction_stays_unresolved(self) -> None:
        with patch(
            "ic_gamedata.adventure_restrictions.build_adventure_roster_filter",
            return_value=object(),
        ), patch(
            "ic_gamedata.adventure_restrictions.evaluate_heroes_against_filter",
            side_effect=self._deny_rows,
        ):
            conflicts = _eligibility_presence_conflicts(
                {"denied": [{"id": 161}]},
                payload={"details": {}},
                adventure_id=1,
                party_ids=[161],
                party_id=3,
                patron_id=5,
                user_corrections=[],
            )
        assert conflicts is not None
        row = next(c for c in conflicts if c.get("champion_id") == 161)
        self.assertEqual(row["status"], "unresolved")

    def test_scoped_user_confirmation_resolves_only_that_context(self) -> None:
        corr = make_user_confirmation(
            champion_id=161,
            party_id=3,
            adventure_id=431,
            patron_id=5,
            base_status="denied",
            base_reason="CON gate",
            note="confirmed in-game",
        )
        upsert_correction(corr, path=self.path)
        hit = find_correction(
            load_corrections(self.path),
            champion_id=161,
            party_id=3,
            adventure_id=431,
            patron_id=5,
        )
        self.assertIsNotNone(hit)
        other = find_correction(
            load_corrections(self.path),
            champion_id=161,
            party_id=3,
            adventure_id=999,
            patron_id=5,
        )
        self.assertIsNone(other)

        with patch(
            "ic_gamedata.adventure_restrictions.build_adventure_roster_filter",
            return_value=object(),
        ), patch(
            "ic_gamedata.adventure_restrictions.evaluate_heroes_against_filter",
            side_effect=self._deny_rows,
        ):
            conflicts = _eligibility_presence_conflicts(
                {"denied": [{"id": 161}]},
                payload={"details": {}},
                adventure_id=431,
                party_ids=[161],
                party_id=3,
                patron_id=5,
                user_corrections=load_corrections(self.path),
            )
        assert conflicts is not None
        row = next(c for c in conflicts if c.get("champion_id") == 161)
        self.assertEqual(row["status"], "resolved")
        self.assertEqual(row["resolution"], "user_confirmation")
        self.assertEqual(row["base_reason"], "CON gate")
        self.assertEqual(row["source"], "user_confirmation")

        revoke_correction(
            champion_id=161,
            party_id=3,
            adventure_id=431,
            patron_id=5,
            path=self.path,
        )
        with patch(
            "ic_gamedata.adventure_restrictions.build_adventure_roster_filter",
            return_value=object(),
        ), patch(
            "ic_gamedata.adventure_restrictions.evaluate_heroes_against_filter",
            side_effect=self._deny_rows,
        ):
            conflicts2 = _eligibility_presence_conflicts(
                {"denied": [{"id": 161}]},
                payload={"details": {}},
                adventure_id=431,
                party_ids=[161],
                party_id=3,
                patron_id=5,
                user_corrections=load_corrections(self.path),
            )
        assert conflicts2 is not None
        row2 = next(c for c in conflicts2 if c.get("champion_id") == 161)
        self.assertEqual(row2["status"], "unresolved")

    def test_validation_warns_on_user_confirmation(self) -> None:
        request = {
            "meta": {"request_id": "r1"},
            "party": [{"id": 161, "eligibility": "allowed"}],
            "roster_eligibility": {
                "allowed_ids": [161],
                "denied": [],
                "presence_conflicts": [
                    {
                        "champion_id": 161,
                        "status": "resolved",
                        "resolution": "user_confirmation",
                        "base_reason": "static deny",
                        "source": "user_confirmation",
                    }
                ],
            },
            "goal": {"id": "push", "party_restriction_status": "ok"},
            "geometry": {"valid_position_ids": [1], "occupied": {"1": 161}},
        }
        result = validate_advice_request_export(
            payload={},
            request=request,
            snapshot_id="snap_test",
            exported_snapshot_id="snap_test",
        )
        codes = {i.code for i in result.issues}
        self.assertIn("user_eligibility_confirmation", codes)
        self.assertTrue(result.party_restriction_ok)


if __name__ == "__main__":
    unittest.main()
