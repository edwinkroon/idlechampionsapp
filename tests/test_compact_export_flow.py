"""End-to-end flow: snapshot export → advice request → freshness → re-export."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ic_gamedata.formation_ai_advice.compact_clipboard import (
    build_advice_request_clipboard_text,
    evaluate_clipboard_budget,
)
from ic_gamedata.formation_ai_advice.export_budget import DEFAULT_CHAR_BUDGET, count_chars
from ic_gamedata.formation_ai_advice.export_validation import (
    mark_request_unvalidated,
    validate_advice_request_export,
)
from ic_gamedata.formation_ai_advice.snapshot_export import (
    build_advice_request,
    build_base_snapshot,
)
from ic_gamedata.formation_ai_advice.snapshot_freshness import (
    USER_HELP_NL,
    SnapshotFreshnessStatus,
    assess_snapshot_freshness,
)
from ic_gamedata.formation_ai_advice.snapshot_store import (
    get_exported_snapshot_meta,
    load_snapshot_registry,
    save_snapshot_to_path,
    set_user_declared_shared,
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


def _set_owned(payload: dict, hero_id: int, owned: bool) -> None:
    for hero in payload.get("details", {}).get("heroes") or []:
        if not isinstance(hero, dict):
            continue
        if int(hero.get("hero_id") or 0) == hero_id:
            hero["owned"] = 1 if owned else 0
            return


def _mutate_active_feats(payload: dict, hero_id: int) -> None:
    for hero in payload.get("details", {}).get("heroes") or []:
        if not isinstance(hero, dict):
            continue
        if int(hero.get("hero_id") or 0) != hero_id:
            continue
        feats = list(hero.get("active_feats") or [])
        feats.append({"id": 900001, "name": "SyntheticTestFeat"})
        hero["active_feats"] = feats
        return


class CompactExportFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        path = Path(__file__).resolve().parent / "fixtures" / "webRequestLog_example.json"
        cls.base_payload = json.loads(path.read_text(encoding="utf-8"))

    def setUp(self) -> None:
        self.payload = json.loads(json.dumps(self.base_payload))
        self.formation = (
            _hero(3, "Nayeli", 1),
            _hero(2, "Celeste", 2),
            _hero(4, "Jarlaxle", 3),
        )
        self._tmpdir = tempfile.TemporaryDirectory()
        root = Path(self._tmpdir.name)
        self.registry_path = root / "advice_snapshot_registry.json"
        self.snapshots_dir = root / "advice_snapshots"
        self.cache_path = root / "owned_roster_cache.json"
        self._patches = [
            patch(
                "ic_gamedata.formation_ai_advice.snapshot_store.ADVICE_SNAPSHOT_REGISTRY_PATH",
                self.registry_path,
            ),
            patch(
                "ic_gamedata.formation_ai_advice.snapshot_store.ADVICE_SNAPSHOTS_DIR",
                self.snapshots_dir,
            ),
            patch(
                "ic_gamedata.formation_ai_advice.owned_roster_cache.OWNED_ROSTER_CACHE_PATH",
                self.cache_path,
            ),
        ]
        for p in self._patches:
            p.start()

    def tearDown(self) -> None:
        for p in self._patches:
            p.stop()
        self._tmpdir.cleanup()

    def test_e2e_snapshot_request_freshness_and_budget(self) -> None:
        # 1–2: build + export base file
        snap1 = build_base_snapshot(self.payload, formation=self.formation)
        sid1 = snap1["meta"]["snapshot_id"]
        dest1 = Path(self._tmpdir.name) / f"{sid1}.json"
        save_snapshot_to_path(snap1, dest1)
        self.assertTrue(dest1.is_file())
        reg = load_snapshot_registry()
        self.assertEqual(reg["last_exported_snapshot_id"], sid1)

        # Shared declaration is user-only.
        set_user_declared_shared(sid1, declared=True)
        reg = load_snapshot_registry()
        self.assertEqual(reg["user_declared_shared_snapshot_id"], sid1)

        freshness = assess_snapshot_freshness(self.payload, self.formation)
        self.assertEqual(
            freshness.status,
            SnapshotFreshnessStatus.NO_RELEVANT_CHANGES_DETECTED,
        )
        self.assertTrue(freshness.user_declared_shared)
        self.assertTrue(freshness.local_comparison_only)

        # 3: compact request references exported snapshot
        req1 = build_advice_request(
            self.payload,
            self.formation,
            snapshot_id=sid1,
            snapshot_meta=snap1["meta"],
            goal="push",
            fixed_main_dps_id=4,
        )
        self.assertEqual(req1["meta"]["snapshot_ref"]["snapshot_id"], sid1)
        self.assertTrue(isinstance(req1.get("goal"), dict))
        self.assertIn("id", req1["goal"])
        for key in ("adventure_id", "campaign_id", "patron_id"):
            self.assertIn(key, req1["goal"])
        self.assertTrue(req1.get("party"))
        self.assertIn("geometry", req1)
        self.assertIn("roster_eligibility", req1)
        for member in req1["party"]:
            self.assertIn("position", member)
            self.assertIn("live_state", member)
            self.assertEqual(member["live_state"]["status"], "unknown")

        validation = validate_advice_request_export(
            payload=self.payload,
            request=req1,
            snapshot_id=sid1,
            exported_snapshot_id=sid1,
        )
        self.assertTrue(validation.ok, validation.summary_nl())

        text1 = build_advice_request_clipboard_text(req1, mode="project")
        chars1 = count_chars(text1)
        print(
            "COMPACT_REQUEST_SIZE",
            json.dumps(
                {
                    "chars": chars1,
                    "budget": DEFAULT_CHAR_BUDGET,
                    "within_15k": chars1 <= DEFAULT_CHAR_BUDGET,
                    "party_size": len(req1["party"]),
                    "owned_in_fixture": len(
                        [
                            h
                            for h in self.payload["details"]["heroes"]
                            if h.get("owned") in ("1", 1, True)
                        ]
                    ),
                }
            ),
        )
        self.assertLessEqual(chars1, DEFAULT_CHAR_BUDGET)

        # 4–5: change party membership/positions → live state updates, same snap ref
        # FormationHero.seat is the formation position; permanent seat comes from defines.
        formation2 = (
            _hero(3, "Nayeli", 5),
            _hero(1, "Bruenor", 1),
            _hero(4, "Jarlaxle", 3),
        )
        req2 = build_advice_request(
            self.payload,
            formation2,
            snapshot_id=sid1,
            snapshot_meta=get_exported_snapshot_meta(),
            goal="push",
            fixed_main_dps_id=4,
        )
        party1 = {m["id"]: m.get("position") for m in req1["party"]}
        party2 = {m["id"]: m.get("position") for m in req2["party"]}
        self.assertNotEqual(party1, party2)
        self.assertIn(1, party2)
        self.assertNotIn(2, party2)
        self.assertEqual(party2.get(3), 5)
        self.assertEqual(req2["meta"]["snapshot_ref"]["snapshot_id"], sid1)

        # Unsaved local rebuild must not become the advice ref.
        _unsaved = build_base_snapshot(self.payload, formation=formation2)
        self.assertTrue(_unsaved["meta"]["snapshot_id"])
        # Without save, registry still points at sid1.
        self.assertEqual(
            get_exported_snapshot_meta()["snapshot_id"],
            sid1,
        )
        # Even if local content matches, advice must use exported id.
        req_ref = build_advice_request(
            self.payload,
            formation2,
            snapshot_id=str(get_exported_snapshot_meta()["snapshot_id"]),
            snapshot_meta=get_exported_snapshot_meta(),
        )
        self.assertEqual(req_ref["meta"]["snapshot_ref"]["snapshot_id"], sid1)

        # 6–7: mutate owned roster / feats → account change detected
        _mutate_active_feats(self.payload, 3)
        # Also flip an owned flag on a non-party hero if present.
        owned_ids = [
            int(h["hero_id"])
            for h in self.payload["details"]["heroes"]
            if h.get("owned") in ("1", 1, True) and int(h.get("hero_id") or 0) not in {2, 3, 4}
        ]
        if owned_ids:
            _set_owned(self.payload, owned_ids[0], False)

        freshness2 = assess_snapshot_freshness(self.payload, formation2)
        self.assertIn(
            freshness2.status,
            {
                SnapshotFreshnessStatus.ACCOUNT_CHANGED,
                SnapshotFreshnessStatus.ACCOUNT_AND_MECHANICS_CHANGED,
            },
        )
        self.assertTrue(freshness2.recommend_new_base_export)
        # Declaration still tied to old exported id until re-export.
        self.assertEqual(freshness2.exported_snapshot_id, sid1)

        # 8–9: new snapshot export replaces reference (new id when content differs)
        snap2 = build_base_snapshot(self.payload, formation=formation2)
        sid2 = snap2["meta"]["snapshot_id"]
        self.assertNotEqual(sid1, sid2)
        dest2 = Path(self._tmpdir.name) / f"{sid2}.json"
        save_snapshot_to_path(snap2, dest2)
        reg2 = load_snapshot_registry()
        self.assertEqual(reg2["last_exported_snapshot_id"], sid2)
        # Sharing declaration cleared on new export id.
        self.assertIsNone(reg2.get("user_declared_shared_snapshot_id"))

        req3 = build_advice_request(
            self.payload,
            formation2,
            snapshot_id=sid2,
            snapshot_meta=get_exported_snapshot_meta(),
            goal="push",
            fixed_main_dps_id=4,
        )
        self.assertEqual(req3["meta"]["snapshot_ref"]["snapshot_id"], sid2)
        self.assertNotEqual(req3["meta"]["snapshot_ref"]["snapshot_id"], sid1)

        freshness3 = assess_snapshot_freshness(self.payload, formation2)
        self.assertEqual(
            freshness3.status,
            SnapshotFreshnessStatus.NO_RELEVANT_CHANGES_DETECTED,
        )

        # 10: over budget blocks copy without silent truncation
        tiny = evaluate_clipboard_budget(text1, max_chars=50)
        self.assertFalse(tiny["within_budget"])
        self.assertEqual(count_chars(text1), chars1)  # original intact

        # 11: conflicting / unknown restriction data stays visible
        payload_conflict = json.loads(json.dumps(self.payload))
        defines = payload_conflict.setdefault("defines", {})
        adventures = list(defines.get("adventure_defines") or [])
        adventures.append(
            {
                "id": 1617,
                "name": "Mental Gymnastics",
                "restrictions_text": (
                    "You may only use Champions with an Intelligence of 11 or less."
                ),
                "game_changes": [
                    {
                        "type": "only_allow_crusaders",
                        "by_stat": {
                            "stats": [
                                {"stat": "int", "comp": "<=", "value": 11},
                                {"stat": "int", "comp": "~=", "value": 11},
                            ],
                        },
                    }
                ],
            }
        )
        defines["adventure_defines"] = adventures
        for inst in payload_conflict.get("details", {}).get("game_instances") or []:
            if isinstance(inst, dict):
                inst["current_adventure_id"] = 1617

        scores = {2: {"int": 10}, 3: {"int": 10}, 4: {"int": 10}, 59: {"int": 19}}
        with patch(
            "ic_gamedata.adventure_restrictions.hero_ability_scores_map_from_cached_definitions",
            return_value=scores,
        ):
            req_r = build_advice_request(
                payload_conflict,
                formation2,
                snapshot_id=sid2,
                snapshot_meta=get_exported_snapshot_meta(),
                goal="push",
            )
        elig = req_r.get("roster_eligibility") or {}
        structured = (req_r.get("goal") or {}).get("structured_restrictions")
        # Unknown comparator must not silently vanish into allowed-only.
        self.assertTrue(
            elig.get("unknown")
            or elig.get("denied")
            or (isinstance(structured, dict) and structured),
            "Restrictiedata moet zichtbaar blijven (unknown/denied/structured).",
        )
        allowed = set(elig.get("allowed_ids") or [])
        unknown_ids = {
            row["id"]
            for row in (elig.get("unknown") or [])
            if isinstance(row, dict) and isinstance(row.get("id"), int)
        }
        for group in elig.get("unknown_groups") or []:
            if isinstance(group, dict):
                unknown_ids.update(
                    hid for hid in (group.get("ids") or []) if isinstance(hid, int)
                )
        self.assertFalse(allowed & unknown_ids)

        # Validation failure → explicit unvalidated label
        bad_req = json.loads(json.dumps(req3))
        bad_req["party"] = list(bad_req.get("party") or []) + list(
            bad_req.get("party") or []
        )
        bad_val = validate_advice_request_export(
            payload=self.payload,
            request=bad_req,
            snapshot_id=sid2,
            exported_snapshot_id=sid2,
        )
        self.assertFalse(bad_val.ok)
        labeled = mark_request_unvalidated(bad_req, bad_val)
        self.assertEqual(
            labeled["meta"]["validation"]["label"],
            "diagnostisch_geldigheid_onbevestigd",
        )
        self.assertFalse(labeled["meta"]["validation"]["ok"])
        self.assertFalse(labeled["meta"]["validation"]["advice_ready"])
        self.assertTrue(labeled["meta"]["validation"]["validation_ran"])

        # Help text present for users.
        self.assertIn("Basisgegevens delen", USER_HELP_NL)
        self.assertIn("adviesvraag", USER_HELP_NL.casefold())
        self.assertIn("snapshot niet", USER_HELP_NL.casefold())

        # No-snapshot status when registry empty.
        self.registry_path.write_text("{}", encoding="utf-8")
        empty = assess_snapshot_freshness(self.payload, self.formation)
        self.assertEqual(empty.status, SnapshotFreshnessStatus.NO_SNAPSHOT)

    def test_request_does_not_inherit_stale_party_from_snapshot(self) -> None:
        snap = build_base_snapshot(self.payload, formation=self.formation)
        save_snapshot_to_path(snap, Path(self._tmpdir.name) / "a.json")
        formation_b = (_hero(3, "Nayeli", 1), _hero(2, "Celeste", 5))
        req = build_advice_request(
            self.payload,
            formation_b,
            snapshot_id=snap["meta"]["snapshot_id"],
            snapshot_meta=snap["meta"],
        )
        party_ids = {m["id"] for m in req["party"]}
        self.assertEqual(party_ids, {2, 3})
        positions = {m["id"]: m["position"] for m in req["party"]}
        self.assertEqual(positions[2], 5)
        # Permanent seat is champion data, not formation position.
        self.assertEqual(
            next(m["seat"] for m in req["party"] if m["id"] == 2),
            2,
        )

    def test_mental_gymnastics_still_blocks_high_int_in_request(self) -> None:
        """Regression check wired through advice-request eligibility."""
        payload = json.loads(json.dumps(self.payload))
        defines = payload.setdefault("defines", {})
        adventures = list(defines.get("adventure_defines") or [])
        adventures.append(
            {
                "id": 1617,
                "name": "Mental Gymnastics",
                "restrictions_text": (
                    "You may only use Champions with an Intelligence of 11 or less."
                ),
                "game_changes": [
                    {
                        "type": "only_allow_crusaders",
                        "by_stat": {
                            "stats": [{"stat": "int", "comp": "<=", "value": 11}],
                        },
                    }
                ],
            }
        )
        defines["adventure_defines"] = adventures
        for inst in payload.get("details", {}).get("game_instances") or []:
            if isinstance(inst, dict):
                inst["current_adventure_id"] = 1617

        scores = {
            59: {"int": 19},
            145: {"int": 17},
            2: {"int": 10},
            3: {"int": 11},
            4: {"int": 12},
        }
        snap = build_base_snapshot(payload, formation=self.formation)
        save_snapshot_to_path(snap, Path(self._tmpdir.name) / "mg.json")
        with patch(
            "ic_gamedata.adventure_restrictions.hero_ability_scores_map_from_cached_definitions",
            return_value=scores,
        ):
            req = build_advice_request(
                payload,
                self.formation,
                snapshot_id=snap["meta"]["snapshot_id"],
                snapshot_meta=snap["meta"],
            )
        elig = req["roster_eligibility"]
        allowed = set(elig.get("allowed_ids") or [])
        denied_ids = {row["id"] for row in (elig.get("denied") or [])}
        summary = (req.get("goal") or {}).get("restriction_text") or ""
        structured = (req.get("goal") or {}).get("structured_restrictions") or {}
        # Label path: Max not Min.
        blob = json.dumps(structured) + summary
        self.assertNotIn("Min. INT 11", blob)
        if 59 in {
            int(h["hero_id"])
            for h in payload["details"]["heroes"]
            if h.get("owned") in ("1", 1, True)
        }:
            self.assertIn(59, denied_ids)
            self.assertNotIn(59, allowed)
        # INT 11 allowed, INT 12 denied when those ids are owned/evaluated.
        if 3 in allowed or 3 in denied_ids:
            self.assertIn(3, allowed)
        if 4 in allowed or 4 in denied_ids:
            self.assertIn(4, denied_ids)


class ExportValidationUnitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        path = Path(__file__).resolve().parent / "fixtures" / "webRequestLog_example.json"
        cls.payload = json.loads(path.read_text(encoding="utf-8"))

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        cache_path = Path(self._tmpdir.name) / "owned_roster_cache.json"
        self._cache_patch = patch(
            "ic_gamedata.formation_ai_advice.owned_roster_cache.OWNED_ROSTER_CACHE_PATH",
            cache_path,
        )
        self._cache_patch.start()
        self.formation = (
            _hero(3, "Nayeli", 1),
            _hero(2, "Celeste", 2),
            _hero(4, "Jarlaxle", 3),
        )

    def tearDown(self) -> None:
        self._cache_patch.stop()
        self._tmpdir.cleanup()

    def test_duplicate_position_detected(self) -> None:
        snap = build_base_snapshot(self.payload, formation=self.formation)
        req = build_advice_request(
            self.payload,
            self.formation,
            snapshot_id=snap["meta"]["snapshot_id"],
            snapshot_meta=snap["meta"],
        )
        if len(req["party"]) >= 2:
            req["party"][1]["position"] = req["party"][0]["position"]
        result = validate_advice_request_export(
            payload=self.payload,
            request=req,
            snapshot_id=snap["meta"]["snapshot_id"],
            exported_snapshot_id=snap["meta"]["snapshot_id"],
        )
        codes = {i.code for i in result.errors}
        self.assertIn("duplicate_position", codes)


if __name__ == "__main__":
    unittest.main()
