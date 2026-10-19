"""Tests for compact clipboard budget, preview identity, and part splits."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ic_gamedata.formation_ai_advice.compact_clipboard import (
    ADVICE_TABLE_FORMAT,
    build_advice_request_clipboard_text,
    build_champion_details_clipboard_text,
    build_project_instructions_clipboard_text,
    evaluate_clipboard_budget,
    safety_instruction,
    split_champion_details_for_budget,
    try_loss_free_shrink,
)
from ic_gamedata.formation_ai_advice.export_budget import (
    count_chars,
    count_utf8_bytes,
)
from ic_gamedata.formation_ai_advice.snapshot_export import (
    build_advice_request,
    build_base_snapshot,
    build_champion_details,
)
from ic_gamedata.formation_ai_advice.snapshot_store import (
    load_snapshot_registry,
    save_snapshot_to_path,
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


class ExportBudgetCountingTests(unittest.TestCase):
    def test_unicode_and_newlines_counted_consistently(self) -> None:
        text = "a\nbéé\n🎉"
        self.assertEqual(count_chars(text), len(text))
        self.assertEqual(count_utf8_bytes(text), len(text.encode("utf-8")))
        self.assertGreater(count_utf8_bytes(text), count_chars(text))

    def test_exact_budget_allows_copy(self) -> None:
        text = "x" * 100
        info = evaluate_clipboard_budget(text, max_chars=100)
        self.assertTrue(info["within_budget"])
        self.assertEqual(info["over_by"], 0)

    def test_one_over_budget_blocks_without_truncation(self) -> None:
        text = "x" * 101
        info = evaluate_clipboard_budget(text, max_chars=100)
        self.assertFalse(info["within_budget"])
        self.assertEqual(info["over_by"], 1)
        # Original text unchanged — callers must not slice.
        self.assertEqual(len(text), 101)


class CompactClipboardBuildersTests(unittest.TestCase):
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
        cache_path = Path(self._tmpdir.name) / "owned_roster_cache.json"
        reg_path = Path(self._tmpdir.name) / "advice_snapshot_registry.json"
        snaps_dir = Path(self._tmpdir.name) / "advice_snapshots"
        self._patches = [
            patch(
                "ic_gamedata.formation_ai_advice.owned_roster_cache.OWNED_ROSTER_CACHE_PATH",
                cache_path,
            ),
            patch(
                "ic_gamedata.formation_ai_advice.snapshot_store.ADVICE_SNAPSHOT_REGISTRY_PATH",
                reg_path,
            ),
            patch(
                "ic_gamedata.formation_ai_advice.snapshot_store.ADVICE_SNAPSHOTS_DIR",
                snaps_dir,
            ),
        ]
        for p in self._patches:
            p.start()

    def tearDown(self) -> None:
        for p in self._patches:
            p.stop()
        self._tmpdir.cleanup()

    def test_headers_and_instructions_count_toward_budget(self) -> None:
        from ic_gamedata.formation_ai_advice.compact_clipboard import (
            compact_request_for_clipboard,
        )
        from ic_gamedata.formation_ai_advice.snapshot_export import minify_json

        snap = build_base_snapshot(self.payload, formation=self.formation)
        req = build_advice_request(
            self.payload,
            self.formation,
            snapshot_id=snap["meta"]["snapshot_id"],
            snapshot_meta=snap["meta"],
            goal="push",
            fixed_main_dps_id=4,
        )
        body_only = minify_json(compact_request_for_clipboard(req))
        full = build_advice_request_clipboard_text(req, mode="standalone")
        self.assertGreater(count_chars(full), count_chars(body_only))
        self.assertIn(safety_instruction(snap["meta"]["snapshot_id"]), full)
        self.assertIn("Zelfstandig", full)

    def test_preview_equals_clipboard_builder_output(self) -> None:
        snap = build_base_snapshot(self.payload, formation=self.formation)
        req = build_advice_request(
            self.payload,
            self.formation,
            snapshot_id=snap["meta"]["snapshot_id"],
            snapshot_meta=snap["meta"],
            goal="push",
            fixed_main_dps_id=4,
        )
        text = build_advice_request_clipboard_text(req, mode="project")
        shrunk = try_loss_free_shrink(text)
        # Dialog uses try_loss_free_shrink then copies that exact string.
        again = try_loss_free_shrink(text)
        self.assertEqual(shrunk, again)
        info = evaluate_clipboard_budget(shrunk, max_chars=count_chars(shrunk))
        self.assertTrue(info["within_budget"])

    def test_advice_request_requires_position_table_format(self) -> None:
        snap = build_base_snapshot(self.payload, formation=self.formation)
        req = build_advice_request(
            self.payload,
            self.formation,
            snapshot_id=snap["meta"]["snapshot_id"],
            snapshot_meta=snap["meta"],
            goal="push",
            fixed_main_dps_id=4,
        )
        header = "| Plek | Champion |"
        for mode in ("project", "standalone"):
            text = build_advice_request_clipboard_text(req, mode=mode)
            self.assertIn(header, text)
            self.assertIn(ADVICE_TABLE_FORMAT, text)
            self.assertIn("display_position", text.casefold())
        project = build_project_instructions_clipboard_text()
        self.assertIn(header, project)
        self.assertIn("kolom-plek", project.casefold())

    def test_no_snapshot_means_no_silent_ai_availability_claim(self) -> None:
        # Registry empty → no last snapshot.
        reg = load_snapshot_registry()
        self.assertIsNone(reg.get("last_snapshot_id"))
        # Safety text never claims the AI has the file.
        note = safety_instruction("snap_abc")
        self.assertIn("ontbreekt of onleesbaar", note.casefold())
        self.assertIn("verzin geen mechanics", note.casefold())
        self.assertNotIn("ai heeft", note.casefold())

    def test_snapshot_registry_records_save_not_ai_receipt(self) -> None:
        snap = build_base_snapshot(self.payload, formation=self.formation)
        dest = Path(self._tmpdir.name) / "saved_snap.json"
        save_snapshot_to_path(snap, dest)
        reg = load_snapshot_registry()
        self.assertEqual(reg["last_snapshot_id"], snap["meta"]["snapshot_id"])
        self.assertEqual(reg["last_exported_snapshot_id"], snap["meta"]["snapshot_id"])
        self.assertTrue(Path(reg["last_saved_path"]).is_file())
        self.assertIsNotNone(reg["last_char_count"])
        self.assertIsNone(reg.get("user_declared_shared_snapshot_id"))

    def test_champion_details_split_on_boundaries_only(self) -> None:
        details = build_champion_details(
            self.payload,
            [2, 3, 4],
            formation=self.formation,
            snapshot_id="snap_test",
        )
        # Force tiny budget so multiple parts are required if champions are large.
        tiny = 800
        parts = split_champion_details_for_budget(details, max_chars=tiny)
        self.assertGreaterEqual(len(parts), 1)
        for part in parts:
            # Each part is complete markdown with fenced JSON.
            self.assertIn("```json", part)
            self.assertIn("CHAMPION_DETAILS", part)
            self.assertIn("export_ref:", part)
            # JSON fence must parse as complete object.
            start = part.index("```json") + len("```json")
            end = part.index("```", start)
            blob = part[start:end].strip()
            parsed = json.loads(blob)
            self.assertIsInstance(parsed.get("champions"), list)
            # Never empty champion mid-slice: each included champion is a full dict.
            for c in parsed["champions"]:
                self.assertIsInstance(c, dict)
                self.assertIn("id", c)

    def test_single_champion_over_budget_not_sliced(self) -> None:
        details = build_champion_details(
            self.payload,
            [2],
            formation=self.formation,
        )
        text = build_champion_details_clipboard_text(details)
        # Budget smaller than the single champion pack → still one intact part.
        parts = split_champion_details_for_budget(details, max_chars=50)
        self.assertEqual(len(parts), 1)
        self.assertIn("```json", parts[0])
        info = evaluate_clipboard_budget(parts[0], max_chars=50)
        self.assertFalse(info["within_budget"])
        # Content not truncated to 50 chars — full champion JSON remains.
        self.assertGreater(count_chars(parts[0]), 50)
        self.assertIn(str(details["champions"][0]["id"]), parts[0])
        self.assertGreaterEqual(count_chars(parts[0]), count_chars(try_loss_free_shrink(text)) - 40)

    def test_project_instructions_copyable(self) -> None:
        text = build_project_instructions_clipboard_text()
        folded = text.casefold()
        self.assertIn("permanente seat", folded)
        self.assertIn("geen automatische hoofd-dps-lock", folded)
        self.assertIn("verzin geen schadewinst", folded)


if __name__ == "__main__":
    unittest.main()
