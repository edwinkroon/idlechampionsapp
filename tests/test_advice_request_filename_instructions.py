"""ADVICE_REQUEST: real export filename + execute-now instructions."""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from ic_gamedata.formation_ai_advice.export_clipboard import (
    BASE_LOOKUP_AND_CONTINUE,
    EXECUTION_ORDER_CLIPBOARD,
    MISSING_COMPARISON_CONTINUE,
    build_advice_request_clipboard_text,
    safety_instruction,
)
from ic_gamedata.formation_ai_advice.reply_contract import snapshot_expected_filename
from ic_gamedata.formation_ai_advice.snapshot_export import (
    build_advice_request,
    build_base_snapshot,
)
from ic_gamedata.formation_ai_advice.snapshot_store import (
    get_exported_snapshot_meta,
    load_snapshot_registry,
    save_base_snapshot_to_basisgegevens,
    save_snapshot_registry,
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


class AdviceRequestFilenameInstructionsTests(unittest.TestCase):
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
        self.basis_dir = root / "basisgegevens"
        self.basis_dir.mkdir()
        self.reg_path = root / "registry.json"
        self._patches = [
            patch(
                "ic_gamedata.formation_ai_advice.snapshot_store.BASISGEGEVENS_DIR",
                self.basis_dir,
            ),
            patch(
                "ic_gamedata.formation_ai_advice.snapshot_store.ADVICE_SNAPSHOT_REGISTRY_PATH",
                self.reg_path,
            ),
            patch(
                "ic_gamedata.formation_ai_advice.owned_roster_cache.OWNED_ROSTER_CACHE_PATH",
                root / "owned_roster_cache.json",
            ),
        ]
        for p in self._patches:
            p.start()
        save_snapshot_registry(
            {
                "schema_version": 2,
                "last_exported_snapshot_id": None,
                "history": [],
            }
        )

    def tearDown(self) -> None:
        for p in reversed(self._patches):
            p.stop()
        self._tmpdir.cleanup()

    def test_basicdata_filename_in_ref_and_clipboard(self) -> None:
        snap = build_base_snapshot(self.payload, formation=self.formation)
        when = datetime(2026, 10, 26, 9, 51, 1)
        saved = save_base_snapshot_to_basisgegevens(snap, when=when)
        self.assertEqual(saved.name, "basicdata_26102026_095101.json")
        meta = get_exported_snapshot_meta()
        self.assertIsNotNone(meta)
        self.assertEqual(meta["expected_filename"], saved.name)
        self.assertEqual(meta["snapshot_id"], snap["meta"]["snapshot_id"])
        # Must not claim the id-derived legacy name as the real file.
        self.assertNotEqual(
            meta["expected_filename"],
            snapshot_expected_filename(str(meta["snapshot_id"])),
        )

        req = build_advice_request(
            self.payload,
            self.formation,
            snapshot_id=str(meta["snapshot_id"]),
            snapshot_meta=meta,
            goal="push",
            fixed_main_dps_id=4,
            include_swap_scope=True,
        )
        ref = req["meta"]["snapshot_ref"]
        self.assertEqual(ref["expected_filename"], saved.name)
        self.assertEqual(ref["snapshot_id"], meta["snapshot_id"])
        self.assertEqual(ref["mechanics_hash"], meta["mechanics_hash"])

        text = build_advice_request_clipboard_text(req, mode="project")
        self.assertIn(saved.name, text)
        self.assertIn(f"bestand `{saved.name}`", text)
        self.assertNotIn(snapshot_expected_filename(str(meta["snapshot_id"])), text)

    def test_two_exports_get_distinct_filenames(self) -> None:
        snap1 = build_base_snapshot(self.payload, formation=self.formation)
        path1 = save_base_snapshot_to_basisgegevens(
            snap1, when=datetime(2026, 10, 26, 9, 0, 0)
        )
        meta1 = dict(get_exported_snapshot_meta() or {})
        req1 = build_advice_request(
            self.payload,
            self.formation,
            snapshot_id=str(meta1["snapshot_id"]),
            snapshot_meta=meta1,
            goal="push",
            fixed_main_dps_id=4,
        )

        # Second export after a small payload tweak → new snapshot_id possible.
        heroes = self.payload["details"]["heroes"]
        if heroes:
            heroes[0]["owned"] = "0" if heroes[0].get("owned") in ("1", 1, True) else "1"
        snap2 = build_base_snapshot(self.payload, formation=self.formation)
        path2 = save_base_snapshot_to_basisgegevens(
            snap2, when=datetime(2026, 10, 26, 10, 0, 0)
        )
        meta2 = dict(get_exported_snapshot_meta() or {})
        req2 = build_advice_request(
            self.payload,
            self.formation,
            snapshot_id=str(meta2["snapshot_id"]),
            snapshot_meta=meta2,
            goal="push",
            fixed_main_dps_id=4,
        )

        self.assertEqual(path1.name, "basicdata_26102026_090000.json")
        self.assertEqual(path2.name, "basicdata_26102026_100000.json")
        self.assertNotEqual(path1.name, path2.name)
        self.assertEqual(req1["meta"]["snapshot_ref"]["expected_filename"], path1.name)
        self.assertEqual(req2["meta"]["snapshot_ref"]["expected_filename"], path2.name)

    def test_filename_persists_across_registry_reload(self) -> None:
        snap = build_base_snapshot(self.payload, formation=self.formation)
        saved = save_base_snapshot_to_basisgegevens(
            snap, when=datetime(2026, 1, 2, 3, 4, 5)
        )
        # Reload registry from disk (same patched path).
        reg = load_snapshot_registry()
        self.assertEqual(reg.get("last_exported_filename"), saved.name)
        meta = get_exported_snapshot_meta(reg)
        self.assertEqual(meta["expected_filename"], saved.name)

    def test_legacy_ref_without_filename_stays_usable(self) -> None:
        snap = build_base_snapshot(self.payload, formation=self.formation)
        sid = snap["meta"]["snapshot_id"]
        # Simulate legacy registry: path/filename omitted.
        save_snapshot_registry(
            {
                "schema_version": 2,
                "last_exported_snapshot_id": sid,
                "last_exported_path": None,
                "last_exported_filename": None,
                "last_exported_mechanics_hash": snap["meta"].get("mechanics_hash"),
                "last_exported_account_state_hash": snap["meta"].get(
                    "account_state_hash"
                ),
                "history": [],
            }
        )
        meta = get_exported_snapshot_meta()
        self.assertIsNotNone(meta)
        self.assertIsNone(meta.get("expected_filename"))
        req = build_advice_request(
            self.payload,
            self.formation,
            snapshot_id=sid,
            snapshot_meta=meta,
            goal="push",
            fixed_main_dps_id=4,
        )
        self.assertIsNone(req["meta"]["snapshot_ref"]["expected_filename"])
        text = build_advice_request_clipboard_text(req, mode="project")
        self.assertIn("bestand onbekend", text.casefold())
        self.assertIn("snapshot_id", text.casefold())
        # Metadata search instruction present; no invented id.json as the real file.
        self.assertIn("beschikbare json-bestanden", text.casefold())
        self.assertNotIn(snapshot_expected_filename(sid), text)

    def test_execution_order_and_continue_after_base(self) -> None:
        snap = build_base_snapshot(self.payload, formation=self.formation)
        save_base_snapshot_to_basisgegevens(
            snap, when=datetime(2026, 10, 26, 11, 0, 0)
        )
        meta = get_exported_snapshot_meta()
        req = build_advice_request(
            self.payload,
            self.formation,
            snapshot_id=str(meta["snapshot_id"]),
            snapshot_meta=meta,
            goal="push",
            fixed_main_dps_id=4,
            include_swap_scope=True,
        )
        text = build_advice_request_clipboard_text(req, mode="project")
        self.assertTrue(text.startswith("# Idle Champions — ADVICE_REQUEST"))
        self.assertIn(EXECUTION_ORDER_CLIPBOARD, text)
        self.assertIn("uitvoerverzoek", text.casefold())
        self.assertIn("niet opnieuw of je de analyse moet uitvoeren", text.casefold())
        self.assertIn(BASE_LOOKUP_AND_CONTINUE.split("\n")[0][:40], text)
        self.assertIn(MISSING_COMPARISON_CONTINUE[:40], text)
        # Safety / identity
        self.assertIn("afwijkende bestandsnaam", text.casefold())
        self.assertIn("niet stilzwijgend", text.casefold())
        self.assertIn("snapshot_id", text.casefold())
        # Regression anchors
        self.assertEqual(
            req["answer_contract"].get("request_id_exact")
            or req["answer_contract"].get("ref"),
            req["answer_contract"].get("request_id_exact")
            or "BASE_SNAPSHOT.answer_contract",
        )
        self.assertIn(req["meta"]["request_id"], text)
        self.assertLessEqual(req["constraints"].get("max_swaps_per_proposal", 3), 3)

    def test_safety_instruction_legacy_unknown_filename(self) -> None:
        note = safety_instruction("snap_abc")
        self.assertIn("bestandsnaam onbekend", note.casefold())
        self.assertIn("afwijkende bestandsnaam", note.casefold())
        self.assertIn("verzin geen mechanics", note.casefold())
        self.assertNotIn("snap_abc.json", note)


if __name__ == "__main__":
    unittest.main()
