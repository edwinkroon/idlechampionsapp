"""ADVICE_REQUEST export schema 1.4 regressions: budget 17k, buff priority, refs."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ic_gamedata.formation_ai_advice.export_budget import (
    DEFAULT_CHAR_BUDGET,
    MAX_EXPORT_BYTES,
    TARGET_EXPORT_BYTES,
    count_chars,
    count_utf8_bytes,
)
from ic_gamedata.formation_ai_advice.export_clipboard import (
    AdviceRequestBudgetError,
    build_advice_request_clipboard_text,
    evaluate_clipboard_budget,
    request_for_export,
)
from ic_gamedata.formation_ai_advice.snapshot_export import (
    SNAPSHOT_EXPORT_SCHEMA,
    _eligibility_presence_conflicts,
    _thin_buff_row,
    build_advice_request,
    build_base_snapshot,
)
from ic_gamedata.party_advisor_models import FormationHero


def _hero(hero_id: int, name: str, seat: int, *, level: int = 100) -> FormationHero:
    return FormationHero(
        hero_id=hero_id,
        name=name,
        seat=seat,
        level=level,
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


def _parse_clipboard_json(text: str) -> dict:
    start = text.rindex("```json") + len("```json")
    end = text.index("```", start)
    return json.loads(text[start:end].strip())


class BudgetLimitTests(unittest.TestCase):
    def test_central_limit_is_17000(self) -> None:
        self.assertEqual(MAX_EXPORT_BYTES, 17_000)
        self.assertEqual(DEFAULT_CHAR_BUDGET, MAX_EXPORT_BYTES)
        self.assertEqual(TARGET_EXPORT_BYTES, 16_000)

    def test_utf8_not_strlen(self) -> None:
        s = "é" * 100
        self.assertEqual(count_chars(s), 100)
        self.assertEqual(count_utf8_bytes(s), 200)

    def test_payload_16001_to_17000_accepted(self) -> None:
        # Synthetic clipboard-sized string just over soft 16k, under hard 17k.
        body = "x" * 16_100
        text = f"# hdr\n```json\n{body}\n```\n"
        utf8 = count_utf8_bytes(text)
        self.assertGreater(utf8, 16_000)
        self.assertLessEqual(utf8, 17_000)
        info = evaluate_clipboard_budget(text, max_chars=MAX_EXPORT_BYTES)
        self.assertTrue(info["within_budget"])

    def test_payload_over_17000_rejected(self) -> None:
        text = "y" * 17_100
        info = evaluate_clipboard_budget(text, max_chars=MAX_EXPORT_BYTES)
        self.assertFalse(info["within_budget"])


class ThinBuffPriorityTests(unittest.TestCase):
    def test_head_ability_outranks_feat_modifier(self) -> None:
        keys = {"ability": {15631, 15942}, "feat": {2788}, "spec": {12092}}
        head = _thin_buff_row(
            {
                "owner_id": 104,
                "name": "Calculating Guidance",
                "catalog_ref": 15631,
                "effect_catalog": "ability",
                "kind": "ability",
            },
            reach="yes",
            catalog_keys=keys,
            main_dps_id=153,
            bucket="incoming",
        )
        feat = _thin_buff_row(
            {
                "owner_id": 104,
                "name": "Some Feat",
                "catalog_ref": 2788,
                "effect_catalog": "feat",
                "kind": "feat",
            },
            reach="unknown",
            catalog_keys=keys,
            main_dps_id=153,
            bucket="uncertain",
        )
        self.assertEqual(head.get("pri"), "A")
        self.assertEqual(feat.get("pri"), "D")
        self.assertTrue(head.get("protected"))

    def test_unknown_head_still_protected(self) -> None:
        thin = _thin_buff_row(
            {
                "owner_id": 154,
                "catalog_ref": 15942,
                "effect_catalog": "ability",
                "kind": "ability",
            },
            reach="unknown",
            catalog_keys={"ability": {15942}, "feat": set(), "spec": set()},
            main_dps_id=153,
            bucket="uncertain",
        )
        self.assertEqual(thin.get("pri"), "A")
        self.assertEqual(thin.get("reach"), "unknown")
        self.assertTrue(thin.get("protected"))

    def test_missing_feat_2788_named_catalog_entry_missing(self) -> None:
        thin = _thin_buff_row(
            {
                "owner_id": 104,
                "catalog_ref": 2788,
                "effect_catalog": "feat",
                "kind": "feat",
            },
            reach="yes",
            catalog_keys={"ability": set(), "feat": {100}, "spec": set()},
            main_dps_id=153,
            bucket="incoming",
        )
        self.assertIsNone(thin.get("ref"))
        self.assertEqual(thin.get("unresolved_ref"), 2788)
        self.assertEqual(thin.get("unresolved_reason"), "catalog_entry_missing")
        self.assertEqual(thin.get("reason"), "unresolved_catalog_reference")

    def test_entry_without_mechanic_body_distinct_reason(self) -> None:
        # Body check happens in _build_main_dps_buffs via shared_bodies;
        # thin row still exports ref when key is present.
        thin = _thin_buff_row(
            {
                "owner_id": 104,
                "catalog_ref": 15631,
                "effect_catalog": "ability",
                "kind": "ability",
            },
            reach="yes",
            catalog_keys={"ability": {15631}, "feat": set(), "spec": set()},
            main_dps_id=153,
            bucket="incoming",
        )
        self.assertEqual(thin.get("ref"), 15631)
        self.assertIsNone(thin.get("unresolved_reason"))


class AdviceRequestV14IntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        path = Path(__file__).resolve().parent / "fixtures" / "webRequestLog_example.json"
        cls.base_payload = json.loads(path.read_text(encoding="utf-8"))

    def setUp(self) -> None:
        self.payload = json.loads(json.dumps(self.base_payload))
        self.formation = (
            _hero(3, "Nayeli", 1, level=220),
            _hero(2, "Celeste", 2, level=180),
            _hero(4, "Jarlaxle", 3, level=5489),
        )
        self._tmpdir = tempfile.TemporaryDirectory()
        cache_path = Path(self._tmpdir.name) / "owned_roster_cache.json"
        self._cache_patch = patch(
            "ic_gamedata.formation_ai_advice.owned_roster_cache.OWNED_ROSTER_CACHE_PATH",
            cache_path,
        )
        self._cache_patch.start()

    def tearDown(self) -> None:
        self._cache_patch.stop()
        self._tmpdir.cleanup()

    def _request(self, **kwargs):
        snap = build_base_snapshot(self.payload, formation=self.formation)
        defaults = dict(
            payload=self.payload,
            formation=self.formation,
            snapshot_id=snap["meta"]["snapshot_id"],
            snapshot_meta=snap["meta"],
            base_snapshot=snap,
            goal="push",
            fixed_main_dps_id=4,
        )
        defaults.update(kwargs)
        return build_advice_request(**defaults), snap

    def test_schema_1_4_and_live_diagnostics(self) -> None:
        self.assertEqual(SNAPSHOT_EXPORT_SCHEMA, "1.4")
        req, _ = self._request()
        self.assertEqual(req["meta"]["export_schema_version"], "1.4")
        live = req.get("live_diagnostics")
        self.assertIsInstance(live, dict)
        # Fixture party has none of the focus champs → empty champions ok.
        self.assertIn("observed_at", live)

    def test_completeness_partition_fields(self) -> None:
        req, _ = self._request()
        buffs = req.get("main_dps_buffs") or {}
        c = buffs.get("completeness") or {}
        for key in (
            "raw_rows_examined",
            "unique_effects_examined",
            "records_exported",
            "effect_refs_exported",
            "unique_effects_omitted",
            "unresolved_catalog_refs",
            "unknown_reach_count",
            "unknown_activation_count",
            "unknown_magnitude_count",
        ):
            self.assertIn(key, c)
        examined = int(c["unique_effects_examined"])
        exported = int(c["effect_refs_exported"])
        omitted = int(c["unique_effects_omitted"])
        self.assertEqual(examined, exported + omitted)

    def test_head_buffs_survive_budget_pressure(self) -> None:
        req, _ = self._request()
        buffs = req.setdefault("main_dps_buffs", {})
        effects = list(buffs.get("effects") or [])
        # Regression refs (synthetic, catalog-present in synthetic keys via ref only).
        heads = [
            {"src": 104, "cat": "ability", "ref": 15631, "reach": "in_range",
             "activation": "unknown", "pri": "A", "relevance": "head", "protected": True},
            {"src": 154, "cat": "ability", "ref": 15942, "reach": "in_range",
             "activation": "unknown", "pri": "A", "relevance": "head", "protected": True},
            {"src": 127, "cat": "spec", "ref": 12092, "reach": "unknown",
             "activation": "unknown", "pri": "A", "relevance": "head", "protected": True},
            {"src": 106, "cat": "ability", "ref": 99901, "reach": "in_range",
             "activation": "unknown", "pri": "A", "relevance": "head", "protected": True},
            {"src": 121, "cat": "ability", "ref": 99902, "reach": "in_range",
             "activation": "unknown", "pri": "A", "relevance": "head", "protected": True},
            {"src": 180, "cat": "ability", "ref": 20597, "reach": "unknown",
             "activation": "unknown", "pri": "B", "relevance": "condition",
             "protected": True,
             "deps": [{"kind": "has_effect", "key": "merciless_resolve", "status": "unknown"}]},
        ]
        noise = [
            {
                "src": 2,
                "cat": "ability",
                "ref": 80000 + i,
                "reach": "unknown",
                "activation": "unknown",
                "pri": "E",
                "relevance": "support",
            }
            for i in range(40)
        ]
        mods = [
            {
                "src": 104,
                "cat": "feat",
                "ref": 90000 + i,
                "reach": "in_range",
                "activation": "unknown",
                "pri": "D",
                "relevance": "modifier",
            }
            for i in range(20)
        ]
        buffs["effects"] = heads + mods + noise
        buffs["completeness"] = {
            "unique_effects_examined": len(buffs["effects"]),
            "raw_rows_examined": len(buffs["effects"]),
            "records_exported": len(buffs["effects"]),
            "effect_refs_exported": len(buffs["effects"]),
            "unique_effects_omitted": 0,
            "unresolved_catalog_refs": 0,
            "unknown_reach_count": 0,
            "unknown_activation_count": 0,
            "unknown_magnitude_count": 0,
        }
        req["main_dps_buffs"] = buffs
        text = build_advice_request_clipboard_text(req, mode="project")
        self.assertLessEqual(count_utf8_bytes(text), MAX_EXPORT_BYTES)
        body = _parse_clipboard_json(text)
        out = (body.get("main_dps_buffs") or {}).get("effects") or []
        refs = {
            (e.get("src"), e.get("ref") or e.get("unresolved_ref"))
            for e in out
            if isinstance(e, dict)
        }
        for src, ref in (
            (104, 15631),
            (154, 15942),
            (127, 12092),
            (106, 99901),
            (121, 99902),
            (180, 20597),
        ):
            self.assertIn((src, ref), refs, msg=f"missing head {src}/{ref}")
        omit = (body.get("main_dps_buffs") or {}).get("completeness", {}).get(
            "omit_reason"
        )
        if omit:
            self.assertNotEqual(omit, "budget_group_unknown_by_src")
            self.assertNotIn("drop_uncertain", str(omit))

    def test_modifiers_without_head_do_not_hide_gap(self) -> None:
        """If only D feats remain, completeness must show omitted heads if any."""
        req, _ = self._request()
        buffs = {
            "fixed_main_dps_id": 4,
            "reach_basis_default": "computed",
            "activation_basis_default": "unknown",
            "magnitude_status_default": "unknown",
            "effects": [
                {
                    "src": 104,
                    "cat": "feat",
                    "ref": 2788,
                    "reach": "in_range",
                    "activation": "unknown",
                    "pri": "D",
                    "relevance": "modifier",
                }
            ],
            "unresolved_catalog": [
                {"src": 104, "cat": "feat", "ref": 2788, "reason": "catalog_entry_missing"}
            ],
            "completeness": {
                "unique_effects_examined": 2,
                "raw_rows_examined": 2,
                "records_exported": 1,
                "effect_refs_exported": 1,
                "unique_effects_omitted": 1,
                "unresolved_catalog_refs": 1,
                "unknown_reach_count": 0,
                "unknown_activation_count": 1,
                "unknown_magnitude_count": 1,
                "omit_reason": "budget_drop_low_relevance_support",
            },
        }
        req["main_dps_buffs"] = buffs
        exported = request_for_export(req)
        urefs = (exported.get("main_dps_buffs") or {}).get("unresolved_catalog") or []
        self.assertTrue(
            any(
                isinstance(u, dict)
                and u.get("ref") == 2788
                and u.get("reason") == "catalog_entry_missing"
                for u in urefs
            )
        )

    def test_no_ability_spec_double_count_key(self) -> None:
        from ic_gamedata.formation_ai_advice.snapshot_export import _effect_unique_key

        a = {"src": 127, "cat": "ability", "ref": 12092}
        s = {"src": 127, "cat": "spec", "ref": 12092}
        # Different catalog namespaces → distinct keys (caller dedupes ability
        # when same id is selected spec via incoming_buffs filter).
        self.assertNotEqual(_effect_unique_key(a), _effect_unique_key(s))

    def test_live_ref_is_not_measured_value(self) -> None:
        req, _ = self._request()
        # Inject focus champ into live_diagnostics via formation with Kas.
        formation = (
            _hero(153, "Kas", 1),
            _hero(4, "Jarlaxle", 2),
            _hero(180, "Kitiara", 3),
        )
        req, _ = self._request(formation=formation, fixed_main_dps_id=153)
        live = req.get("live_diagnostics") or {}
        by_id = {c["id"]: c for c in (live.get("champions") or []) if isinstance(c, dict)}
        self.assertIn(153, by_id)
        for field in by_id[153].get("fields") or []:
            if field.get("key") == "mortal_pawns_stacks":
                self.assertEqual(field.get("status"), "unknown")
                self.assertEqual(field.get("reason_code"), "source_not_exposed")
                self.assertNotIn("value", field)

    def test_bud_not_from_reset_highest(self) -> None:
        for inst in self.payload["details"]["game_instances"]:
            if isinstance(inst, dict):
                inst.setdefault("stats", {})[
                    "this_reset_highest_damage_dealt_hero_id"
                ] = "4"
        req, _ = self._request()
        bud = req["bud_observation"]
        self.assertEqual(bud.get("reset_highest_damage_champion_id"), 4)
        self.assertEqual(bud.get("current_bud_setter_status"), "unknown")
        self.assertNotIn("setter_champion_id", bud)

    def test_presence_conflict_unresolved_not_position_lock(self) -> None:
        conflicts = _eligibility_presence_conflicts(
            {
                "overrides_applied": [
                    {
                        "champion_id": 180,
                        "base": "denied",
                        "effective": "allowed",
                        "reason": "seated without proven exemption",
                    }
                ]
            },
            exempt_hero_ids=set(),
        )
        self.assertIsNotNone(conflicts)
        row = next(c for c in conflicts if c["champion_id"] == 180)
        self.assertEqual(row["status"], "unresolved")
        self.assertIs(row["position_locked"], False)

    def test_presence_conflict_resolved_by_force_allow(self) -> None:
        conflicts = _eligibility_presence_conflicts(
            {
                "overrides_applied": [
                    {
                        "champion_id": 180,
                        "base": "denied",
                        "effective": "allowed",
                    }
                ]
            },
            exempt_hero_ids={180},
        )
        row = next(c for c in conflicts if c["champion_id"] == 180)
        self.assertEqual(row["status"], "resolved")
        self.assertEqual(row["resolution"], "force_allow_hero")
        self.assertIs(row["position_locked"], False)

    def test_presence_conflict_resolved_by_campaign_scope(self) -> None:
        conflicts = _eligibility_presence_conflicts(
            {
                "overrides_applied": [
                    {
                        "champion_id": 159,
                        "base": "denied",
                        "effective": "allowed",
                        "reason": (
                            "Campaign scope matched "
                            "(A Grand Tour of the Sword Coast)"
                        ),
                    }
                ]
            },
            exempt_hero_ids=set(),
        )
        row = next(c for c in conflicts if c["champion_id"] == 159)
        self.assertEqual(row["status"], "resolved")
        self.assertEqual(row["resolution"], "campaign_scoped_eligibility")
        self.assertIs(row["replacement_locked"], False)
        self.assertIs(row["position_locked"], False)

    def test_clipboard_wrapper_counts_and_fits(self) -> None:
        req, _ = self._request()
        text = build_advice_request_clipboard_text(req, mode="project")
        utf8 = count_utf8_bytes(text)
        self.assertLessEqual(utf8, MAX_EXPORT_BYTES)
        self.assertIn("ADVICE_REQUEST", text)
        self.assertIn("```json", text)
        # Wrapper (instructions + fences) is part of measured UTF-8 payload.
        json_only = json.dumps(
            _parse_clipboard_json(text), separators=(",", ":"), ensure_ascii=False
        )
        self.assertGreater(utf8, count_utf8_bytes(json_only))

    def test_over_budget_explicit_error_with_size(self) -> None:
        req, _ = self._request()
        with self.assertRaises(AdviceRequestBudgetError) as ctx:
            build_advice_request_clipboard_text(
                req,
                mode="project",
                max_chars=500,
                raise_on_over_budget=True,
            )
        err = ctx.exception
        self.assertGreater(err.utf8_bytes, 500)
        self.assertIn("UTF-8", str(err))


if __name__ == "__main__":
    unittest.main()
