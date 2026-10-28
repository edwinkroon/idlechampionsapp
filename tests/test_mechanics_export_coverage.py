"""Mechanics export coverage: BASE_SNAPSHOT prose + safe delta omission."""

from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ic_gamedata.formation_ai_advice.export_clipboard import (
    _fit_payload_to_budget,
    request_for_export,
)
from ic_gamedata.formation_ai_advice.export_validation import (
    validate_advice_request_export,
)
from ic_gamedata.formation_ai_advice.mechanics_completeness import (
    assess_snapshot_mechanics_export_coverage,
    build_mechanics_completeness,
    compact_mechanics_for_clipboard,
    delta_row_is_essential_for_request,
)
from ic_gamedata.formation_ai_advice.snapshot_export import (
    build_advice_request,
    build_base_snapshot,
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
        role_label="Support",
        roles=("support",),
        tags=(),
        highest_damage=0.0,
        active_feats=1,
        is_top_damage=False,
    )


class SnapshotCoverageAssessmentTests(unittest.TestCase):
    def test_g_broken_snap_acf_not_usable(self) -> None:
        path = Path("roster/snap_acf062c97a43aaae5bb1.json")
        if not path.is_file():
            self.skipTest("local snap_acf fixture missing")
        snap = json.loads(path.read_text(encoding="utf-8"))
        cov = assess_snapshot_mechanics_export_coverage(snap)
        self.assertFalse(cov["usable_for_qualitative_advice"])
        self.assertFalse(cov["export_complete"])
        self.assertEqual(cov["ability_with_effect"], 0)
        self.assertEqual(cov["option_with_effect"], 0)
        self.assertIn(cov["reason"], {
            "shared_abilities_catalog_empty",
            "no_usable_ability_effects",
            "no_usable_specialization_effects",
        })

    def test_a_good_snap_has_effects(self) -> None:
        path = Path("roster/snap_1876dd276a94a25bd0c6.json")
        if not path.is_file():
            self.skipTest("local good snap fixture missing")
        snap = json.loads(path.read_text(encoding="utf-8"))
        cov = assess_snapshot_mechanics_export_coverage(snap)
        self.assertTrue(cov["usable_for_qualitative_advice"])
        self.assertTrue(cov["export_complete"])
        self.assertGreater(cov["ability_with_effect"], 100)
        opts = snap["shared"]["specialization_options"]
        # Example options must resolve to effect prose (not advice_hint only).
        for oid in ("17679", "17682", "17321", "20700"):
            body = opts.get(oid) or {}
            self.assertTrue(
                body.get("effect"),
                msg=f"{oid} missing effect in good snapshot",
            )
            self.assertNotEqual(
                body.get("advice_hint"),
                "Keuze open — effect ontbreekt.",
            )


class MechanicsDeltaVsIncompleteBaseTests(unittest.TestCase):
    def test_e_incomplete_base_produces_essential_supplements(self) -> None:
        # Synthetic incomplete base (like snap_acf): option refs without effect.
        snap = {
            "shared": {
                "abilities": {},
                "specialization_options": {
                    "17679": {
                        "name": "Ancestor's Shadow",
                        "advice_hint": "Keuze open — effect ontbreekt.",
                        "required_level": 180,
                    }
                },
            },
            "champions": [{"id": 166, "specializations": [{"options": [{"ref": 17679}]}]}],
        }
        cov = assess_snapshot_mechanics_export_coverage(snap)
        self.assertFalse(cov["usable_for_qualitative_advice"])

        entries = {
            166: {
                "champion_id": 166,
                "name": "Cazrin",
                "abilities": [{"ability_id": 17674}],
                "specialization_groups": [
                    {
                        "group_id": "tier_0",
                        "options": [{"option_id": 17679}],
                    }
                ],
            }
        }
        block = build_mechanics_completeness(
            party_ids=[166],
            entries_by_id=entries,
            base_snapshot=snap,
        )
        delta = block.get("mechanics_delta") or []
        self.assertTrue(delta, msg="expected supplements when base lacks effects")
        essential = [r for r in delta if delta_row_is_essential_for_request(r)]
        self.assertTrue(essential)
        # Live definitions should restore real prose (not invented).
        for row in essential:
            if row.get("id") == 17679:
                self.assertTrue(row.get("effect"))
                self.assertNotIn("effect ontbreekt", (row.get("effect") or "").casefold())
                self.assertEqual(row.get("role"), "supplement")
                break
        else:
            # Ability 17674 may be the only resolved id depending on walk — still OK.
            self.assertTrue(any(r.get("effect") for r in essential))

    def test_e_budget_keeps_essential_delta(self) -> None:
        request = {
            "meta": {
                "snapshot_ref": {
                    "snapshot_id": "snap_incomplete",
                    "expected_filename": "snap_incomplete.json",
                }
            },
            "goal": {"id": "push"},
            "geometry": {"ref": "BASE_SNAPSHOT.geometry", "valid_position_ids": [1]},
            "party": [
                {
                    "id": 166,
                    "position": 1,
                    "seat": 1,
                    "live_state": {"status": "unknown"},
                }
            ],
            "readiness": {"status": "ready_with_warnings"},
            "roster_eligibility": {},
            "mechanics_completeness": {
                "base_mechanics_export_coverage": {
                    "export_complete": False,
                    "usable_for_qualitative_advice": False,
                    "reason": "shared_abilities_catalog_empty",
                    "ability_with_effect": 0,
                    "option_with_effect": 0,
                },
                "mechanics_delta": [
                    {
                        "catalog": "specialization_option",
                        "id": 17679,
                        "role": "supplement",
                        "name": "Ancestor's Shadow",
                        "effect": (
                            "Cazrin increases the damage bonus of Sunny Disposition "
                            "by 100% for each Fallbacks Champion and/or Good Champion "
                            "in the formation, stacking multiplicatively."
                        ),
                        "snapshot_had_effect": False,
                    },
                    {
                        "catalog": "ability",
                        "id": 1,
                        "role": "correction",
                        "name": "AlreadyInBase",
                        "effect": "x" * 5000,
                        "snapshot_had_effect": True,
                    },
                ],
            },
            "answer_contract": {"ref": "BASE_SNAPSHOT.answer_contract"},
        }
        exported = request_for_export(request)
        # Force a tight budget so step 3 would previously drop everything.
        fitted = _fit_payload_to_budget(
            exported,
            mode="project",
            snapshot_id="snap_incomplete",
            expected_filename="snap_incomplete.json",
            max_chars=3500,
        )
        delta = fitted.get("mechanics_delta") or []
        self.assertTrue(
            any(r.get("id") == 17679 and r.get("effect") for r in delta),
            msg=f"essential supplement must survive budget fit; got {delta!r}",
        )
        self.assertFalse(fitted.get("mechanics_delta_omitted_for_budget"))
        self.assertIn("base_mechanics_export_coverage", fitted)

    def test_b_hint_not_substitute_when_effect_present(self) -> None:
        from ic_gamedata.formation_ai_advice.clipboard_export import _mechanic_entry
        from ic_gamedata.formation_ai_advice.export import _mechanic_fields_from_upgrade
        from ic_gamedata.formation_ai_advice.export import _upgrade_row_map

        row = _upgrade_row_map().get(17679)
        if not row:
            self.skipTest("upgrade 17679 not in local definitions")
        fields = _mechanic_fields_from_upgrade(row)
        self.assertTrue(fields.get("mechanical_text"))
        projected = _mechanic_entry(
            {"option_id": 17679, "name": row.get("name"), **fields},
            kind="specialization",
        )
        assert projected is not None
        self.assertTrue(projected.get("effect"))
        self.assertIsNone(projected.get("advice_hint"))

    def test_c_d_prose_without_full_parse_stays_usable(self) -> None:
        body = {
            "name": "Synthetic Prose Only",
            "effect": (
                "Increases damage of adjacent Champions by an unknown amount "
                "when the formation has at least one Good Champion."
            ),
            "effect_kind": "bron",
            "magnitude": "parameter_onbekend",
        }
        self.assertTrue(
            assess_snapshot_mechanics_export_coverage(
                {
                    "shared": {
                        "abilities": {"9": body},
                        "specialization_options": {},
                    },
                    "champions": [{"id": 1, "abilities": [{"ref": 9}]}],
                }
            )["usable_for_qualitative_advice"]
        )

    def test_f_budget_does_not_silently_drop_essential(self) -> None:
        rows = [
            {
                "catalog": "ability",
                "id": 1,
                "role": "supplement",
                "effect": "Essential prose that BASE lacks.",
                "snapshot_had_effect": False,
            }
        ]
        block = compact_mechanics_for_clipboard({"mechanics_delta": rows})
        self.assertEqual(
            block["mechanics_delta"][0]["effect"],
            "Essential prose that BASE lacks.",
        )
        self.assertTrue(delta_row_is_essential_for_request(rows[0]))

    def test_validation_blocks_omitted_delta_on_incomplete_base(self) -> None:
        request = {
            "meta": {"snapshot_ref": {"snapshot_id": "snap_x"}},
            "goal": {"id": "push"},
            "geometry": {"ref": "BASE_SNAPSHOT.geometry", "valid_position_ids": [1]},
            "party": [
                {"id": 1, "position": 1, "seat": 1, "live_state": {"status": "unknown"}}
            ],
            "readiness": {"status": "ready"},
            "roster_eligibility": {},
            "mechanics_delta_omitted_for_budget": True,
            "mechanics_delta_omitted_count": 97,
            "base_mechanics_export_coverage": {
                "export_complete": False,
                "usable_for_qualitative_advice": False,
                "reason": "shared_abilities_catalog_empty",
                "ability_with_effect": 0,
                "option_with_effect": 0,
            },
        }
        result = validate_advice_request_export(
            payload={"details": {"heroes": []}},
            request=request,
            snapshot_id="snap_x",
            exported_snapshot_id="snap_x",
        )
        self.assertFalse(result.advice_ready)
        codes = {i.code for i in result.errors}
        self.assertTrue(
            {
                "mechanics_delta_omitted_despite_incomplete_base",
                "base_mechanics_missing_and_delta_unavailable",
            }
            & codes
        )


class FreshBaseSnapshotMechanicsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        path = Path(__file__).resolve().parent / "fixtures" / "webRequestLog_example.json"
        cls.base_payload = json.loads(path.read_text(encoding="utf-8"))

    def setUp(self) -> None:
        self.payload = copy.deepcopy(self.base_payload)
        self.formation = (
            _hero(3, "Nayeli", 1),
            _hero(2, "Celeste", 2),
            _hero(4, "Jarlaxle", 3),
        )
        self._tmpdir = tempfile.TemporaryDirectory()
        root = Path(self._tmpdir.name)
        self._patches = [
            patch(
                "ic_gamedata.formation_ai_advice.owned_roster_cache.OWNED_ROSTER_CACHE_PATH",
                root / "owned_roster_cache.json",
            ),
            patch(
                "ic_gamedata.paths.OWNED_ROSTER_CACHE_PATH",
                root / "owned_roster_cache.json",
            ),
        ]
        for p in self._patches:
            p.start()

    def tearDown(self) -> None:
        for p in self._patches:
            p.stop()
        self._tmpdir.cleanup()

    def test_a_new_base_snapshot_keeps_ability_effects(self) -> None:
        snap = build_base_snapshot(
            self.payload,
            formation=self.formation,
            force_refresh_roster=True,
        )
        cov = assess_snapshot_mechanics_export_coverage(snap)
        self.assertTrue(
            cov["usable_for_qualitative_advice"],
            msg=f"fresh snapshot coverage failed: {cov}",
        )
        self.assertGreater(cov["ability_with_effect"], 0)
        self.assertTrue(
            (snap.get("meta") or {}).get("mechanics_export_coverage", {}).get(
                "usable_for_qualitative_advice"
            )
        )
        # Consumer can resolve ability refs from shared catalog.
        shared_ab = (snap.get("shared") or {}).get("abilities") or {}
        champ = next(
            c
            for c in snap["champions"]
            if isinstance(c.get("abilities"), list) and c["abilities"]
        )
        ref = champ["abilities"][0]["ref"]
        body = shared_ab[str(ref)]
        self.assertTrue(body.get("effect") or body.get("name"))

    def test_i_j_request_against_good_base_stays_thin_when_covered(self) -> None:
        snap = build_base_snapshot(
            self.payload,
            formation=self.formation,
            force_refresh_roster=True,
        )
        req = build_advice_request(
            self.payload,
            self.formation,
            snapshot_id=str(snap["meta"]["snapshot_id"]),
            snapshot_meta=snap["meta"],
            base_snapshot=snap,
            goal="push",
        )
        mech = req.get("mechanics_completeness") or {}
        cov = mech.get("base_mechanics_export_coverage") or {}
        self.assertTrue(cov.get("usable_for_qualitative_advice"))
        # No blocked readiness solely for mechanics when base is complete.
        ready_codes = {
            i.get("code")
            for i in ((req.get("readiness") or {}).get("issues") or [])
            if isinstance(i, dict)
        }
        self.assertNotIn("base_mechanics_export_incomplete", ready_codes)


if __name__ == "__main__":
    unittest.main()
