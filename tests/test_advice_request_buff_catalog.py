"""Regressions: catalog refs, reach≠activation, BUD naming, budget protection."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ic_gamedata.formation_ai_advice.export_budget import (
    DEFAULT_CHAR_BUDGET,
    count_utf8_bytes,
)
from ic_gamedata.formation_ai_advice.export_clipboard import (
    build_advice_request_clipboard_text,
    request_for_export,
)
from ic_gamedata.formation_ai_advice.incoming_buffs import (
    _unresolved_activation_deps,
    mechanic_reaches_main_dps,
)
from ic_gamedata.formation_ai_advice.snapshot_export import (
    SNAPSHOT_EXPORT_SCHEMA,
    build_advice_request,
    build_base_snapshot,
)
from ic_gamedata.formation_advisor.models import (
    FormationLayoutContext,
    FormationTopology,
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


def _ctx() -> FormationLayoutContext:
    seats = {180: 1, 4: 2}
    columns = {1: 0, 2: 3}
    adjacency = {1: frozenset({2}), 2: frozenset({1})}
    topo = FormationTopology(
        seat_adjacency=adjacency,
        seat_column=columns,
        seat_zone={1: "front", 2: "back"},
        source="test",
    )
    return FormationLayoutContext(
        active_hero_ids=frozenset(seats),
        seat_by_hero=seats,
        hero_name_by_id={180: "Kitiara", 4: "Carry"},
        hero_roles_by_id={180: ("support",), 4: ("dps",)},
        hero_tags_by_id={180: (), 4: ()},
        carry_hero_id=4,
        highest_damage_hero_id=4,
        topology=topo,
        run_goal="push",
        context="campaign",
        goal="push",
        party_size=2,
        formation_capacity=2,
        owned_hero_ids=frozenset(seats),
        allowed_bench_ids=frozenset(),
    )


class CatalogRefAndSemanticsTests(unittest.TestCase):
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

    def test_schema_1_4(self) -> None:
        req, _ = self._request()
        self.assertEqual(req["meta"]["export_schema_version"], "1.4")
        self.assertEqual(SNAPSHOT_EXPORT_SCHEMA, "1.4")

    def test_buff_ref_is_upgrade_id_not_effect_defines(self) -> None:
        """Born Into Evil: ability_id 15619 vs effect_defines 2081."""
        from ic_gamedata.formation_ai_advice.export import _ability_texts

        rows = _ability_texts(153)
        born = next(a for a in rows if a.get("ability_id") == 15619)
        self.assertEqual(born.get("effect_id"), 2081)
        self.assertNotEqual(born.get("ability_id"), born.get("effect_id"))

        # Synthetic party with Kas if definitions allow building request —
        # validate thin-row mapping via incoming collect path on fixture party.
        req, snap = self._request()
        shared = (snap.get("shared") or {}).get("abilities") or {}
        buffs = req.get("main_dps_buffs") or {}
        for row in buffs.get("effects") or []:
            cat = row.get("cat")
            ref = row.get("ref")
            eid = row.get("effect_def_id")
            if ref is None:
                self.assertEqual(row.get("reason"), "unresolved_catalog_reference")
                continue
            if cat == "ability":
                self.assertIn(str(ref), shared)
                # effect_defines id must not equal catalog ref when both present
                # for mismatched namespaces (common case).
                if isinstance(eid, int):
                    # Allow equality only if they truly coincide in data.
                    if eid in shared and ref == eid:
                        continue
                    self.assertNotEqual(
                        ref,
                        eid,
                        msg=f"catalog ref {ref} must not be effect_def {eid}",
                    )

    def test_cruel_cunning_keeps_merciless_dependency(self) -> None:
        row = {
            "name": "Cruel Cunning",
            "effect_facts": {
                "effect_scope": "filtered",
                "targets": ["all"],
                "semantics": {
                    "scope": "filtered",
                    "recipients": {"targets": ["all"]},
                    "predicate": {
                        "base_clauses": ["HasEffect(`merciless_resolve`)"],
                        "status": "partial",
                    },
                },
            },
        }
        deps = _unresolved_activation_deps(
            row["effect_facts"], row["effect_facts"]["semantics"]
        )
        self.assertTrue(any(d.get("key") == "merciless_resolve" for d in deps))
        reach, reason = mechanic_reaches_main_dps(
            row, ctx=_ctx(), owner_id=180, dps_id=4
        )
        self.assertEqual(reach, "unknown")
        self.assertTrue(
            "unresolved" in reason.casefold() or "activatie" in reason.casefold(),
            msg=reason,
        )

    def test_computed_in_range_is_not_runtime_active(self) -> None:
        req, _ = self._request()
        buffs = req.get("main_dps_buffs") or {}
        self.assertEqual(buffs.get("activation_basis_default"), "unknown")
        self.assertEqual(buffs.get("reach_basis_default"), "computed")
        for row in buffs.get("effects") or []:
            if row.get("reach") == "in_range":
                self.assertEqual(row.get("activation"), "unknown")
                self.assertNotEqual(row.get("activation"), "active")

    def test_bud_reset_highest_is_not_current_setter(self) -> None:
        for inst in self.payload["details"]["game_instances"]:
            if isinstance(inst, dict):
                inst.setdefault("stats", {})[
                    "this_reset_highest_damage_dealt_hero_id"
                ] = "4"
        req, _ = self._request()
        bud = req["bud_observation"]
        self.assertEqual(bud.get("reset_highest_damage_champion_id"), 4)
        self.assertEqual(bud.get("reset_highest_damage_status"), "known")
        self.assertNotIn("setter_champion_id", bud)
        self.assertEqual(bud.get("current_bud_setter_status"), "unknown")
        self.assertEqual(bud["current_bud"]["status"], "unknown")
        self.assertEqual(bud["peak"]["reason_code"], "no_bud_poll_loop")

    def test_high_level_does_not_claim_upgrades_purchased(self) -> None:
        for hero in self.payload["details"]["heroes"]:
            if isinstance(hero, dict) and int(hero.get("hero_id") or 0) == 4:
                hero["level"] = "5489"
        req, _ = self._request()
        by_id = {p["id"]: p for p in req["party"]}
        self.assertEqual(by_id[4]["level"], 5489)
        self.assertEqual(by_id[4]["upgrade_status"], "unknown")
        self.assertEqual(
            by_id[4]["upgrade_status_reason"],
            "upgrade_purchase_state_unavailable",
        )
        self.assertNotIn("all_upgrades_purchased", by_id[4])

    def test_protected_uncertain_survive_budget_pressure(self) -> None:
        req, snap = self._request()
        # Force many uncertain-like protected rows and tiny budget fit path.
        buffs = req.get("main_dps_buffs")
        if not isinstance(buffs, dict):
            self.skipTest("no main_dps_buffs")
        effects = list(buffs.get("effects") or [])
        # Inject protected unknown rows
        for i in range(5):
            effects.append(
                {
                    "src": 180,
                    "cat": "ability",
                    "ref": 20597,
                    "reach": "unknown",
                    "reach_basis": "computed",
                    "activation": "unknown",
                    "reason": "targeting_uncertain",
                    "protected": True,
                    "deps": [
                        {
                            "kind": "has_effect",
                            "key": "merciless_resolve",
                            "status": "unknown",
                        }
                    ],
                }
            )
        buffs["effects"] = effects
        req["main_dps_buffs"] = buffs
        text = build_advice_request_clipboard_text(req, mode="project")
        self.assertLessEqual(count_utf8_bytes(text), DEFAULT_CHAR_BUDGET)
        # Parse JSON body
        start = text.rindex("```json") + len("```json")
        end = text.index("```", start)
        body = json.loads(text[start:end].strip())
        out_effects = (body.get("main_dps_buffs") or {}).get("effects") or []
        protected = [e for e in out_effects if e.get("protected") or e.get("reach") == "unknown"]
        self.assertGreaterEqual(len(protected), 1)
        omit = (body.get("main_dps_buffs") or {}).get("completeness", {}).get(
            "omit_reason"
        )
        if omit:
            self.assertNotEqual(omit, "budget_drop_uncertain_buffs")

    def test_clipboard_utf8_limit(self) -> None:
        req, _ = self._request()
        text = build_advice_request_clipboard_text(req, mode="project")
        self.assertLessEqual(count_utf8_bytes(text), DEFAULT_CHAR_BUDGET)
        # Non-ASCII inflates bytes vs code points
        self.assertGreaterEqual(count_utf8_bytes(text), len(text))


class NameMappingForbiddenTests(unittest.TestCase):
    def test_no_silent_name_to_id_mapping_in_thin_row(self) -> None:
        from ic_gamedata.formation_ai_advice.snapshot_export import _thin_buff_row

        row = {
            "owner_id": 153,
            "name": "Born Into Evil",
            "catalog_ref": None,
            "effect_def_id": 2081,
            "effect_catalog": "ability",
            "dependencies": None,
        }
        thin = _thin_buff_row(
            row,
            reach="yes",
            catalog_keys={"ability": {15619}, "feat": set(), "spec": set()},
            main_dps_id=4,
            bucket="incoming",
        )
        self.assertIsNone(thin.get("ref"))
        self.assertEqual(thin.get("reason"), "unresolved_catalog_reference")
        self.assertEqual(thin.get("unresolved_reason"), "runtime_to_catalog_mapping_unresolved")
        self.assertEqual(thin.get("effect_def_id"), 2081)


if __name__ == "__main__":
    unittest.main()
