"""Tests for kolom-plek display_position mapping and AI reply instructions."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ic_gamedata.formation_ai_advice.clipboard_export import (
    build_advice_payload,
    extract_json_object,
    format_clipboard_markdown,
)
from ic_gamedata.formation_ai_advice.export_clipboard import (
    ADVICE_TABLE_FORMAT,
    PROJECT_INSTRUCTIONS,
    build_advice_request_clipboard_text,
    build_project_instructions_clipboard_text,
)
from ic_gamedata.formation_ai_advice.export import build_export_payload
from ic_gamedata.formation_ai_advice.labels import (
    POSITION_DISPLAY_AI_INSTRUCTION,
    assign_display_positions,
    resolve_column_direction_rule,
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
        role_label="Dps",
        roles=("dps",),
        tags=(),
        highest_damage=0.0,
        active_feats=1,
        is_top_damage=False,
    )


# 2-4-2-2 active layout: geometry columns 3,2,1,0 (back→front under lower_column_is_front)
_ACCEPTANCE_ROWS = [
    # back column (geo 3): 2 slots — row gaps 0, 5
    {"position_id": 12, "column_index": 3, "row_order": 0, "state": "active"},
    {"position_id": 6, "column_index": 3, "row_order": 5, "state": "active"},
    # mid column (geo 2): 4 slots
    {"position_id": 9, "column_index": 2, "row_order": 0, "state": "active"},
    {"position_id": 5, "column_index": 2, "row_order": 2, "state": "active"},
    {"position_id": 10, "column_index": 2, "row_order": 4, "state": "active"},
    {"position_id": 11, "column_index": 2, "row_order": 7, "state": "active"},
    # front-mid (geo 1): 2 slots
    {"position_id": 4, "column_index": 1, "row_order": 0, "state": "active"},
    {"position_id": 8, "column_index": 1, "row_order": 3, "state": "active"},
    # front (geo 0): 2 slots
    {"position_id": 2, "column_index": 0, "row_order": 0, "state": "active"},
    {"position_id": 1, "column_index": 0, "row_order": 2, "state": "active"},
]


class AssignDisplayPositionsTests(unittest.TestCase):
    def test_back_to_front_and_top_to_bottom_acceptance(self) -> None:
        # Shuffle array order deliberately.
        shuffled = list(reversed(_ACCEPTANCE_ROWS))
        out, issues = assign_display_positions(
            shuffled, column_direction="lower_column_is_front"
        )
        self.assertFalse(issues)
        labels = [
            r["display_position"]
            for r in out
            if r.get("display_position")
        ]
        self.assertEqual(
            labels,
            [
                "1-1",
                "1-2",
                "2-1",
                "2-2",
                "2-3",
                "2-4",
                "3-1",
                "3-2",
                "4-1",
                "4-2",
            ],
        )

    def test_row_gaps_yield_contiguous_slots(self) -> None:
        rows = [
            {"position_id": 10, "column_index": 1, "row_order": 0, "state": "active"},
            {"position_id": 20, "column_index": 1, "row_order": 99, "state": "active"},
        ]
        out, _ = assign_display_positions(rows, column_direction="lower_column_is_front")
        by_id = {r["position_id"]: r for r in out}
        self.assertEqual(by_id[10]["display_slot"], 1)
        self.assertEqual(by_id[20]["display_slot"], 2)
        self.assertEqual(by_id[10]["display_position"], "1-1")
        self.assertEqual(by_id[20]["display_position"], "1-2")

    def test_champion_swap_does_not_change_place_mapping(self) -> None:
        a = [
            {
                "position_id": 5,
                "column_index": 2,
                "row_order": 0,
                "state": "active",
                "current_champion_id": 21,
            },
            {
                "position_id": 6,
                "column_index": 2,
                "row_order": 1,
                "state": "active",
                "current_champion_id": 3,
            },
        ]
        b = [
            {**a[0], "current_champion_id": 3},
            {**a[1], "current_champion_id": 21},
        ]
        out_a, _ = assign_display_positions(a, column_direction="lower_column_is_front")
        out_b, _ = assign_display_positions(b, column_direction="lower_column_is_front")
        map_a = {r["position_id"]: r["display_position"] for r in out_a}
        map_b = {r["position_id"]: r["display_position"] for r in out_b}
        self.assertEqual(map_a, map_b)

    def test_array_order_does_not_change_mapping(self) -> None:
        forward, _ = assign_display_positions(
            list(_ACCEPTANCE_ROWS), column_direction="lower_column_is_front"
        )
        backward, _ = assign_display_positions(
            list(reversed(_ACCEPTANCE_ROWS)),
            column_direction="lower_column_is_front",
        )
        self.assertEqual(
            {r["position_id"]: r["display_position"] for r in forward},
            {r["position_id"]: r["display_position"] for r in backward},
        )

    def test_position_id_and_seat_do_not_drive_numbering(self) -> None:
        # High position_ids in front column must still become display column 4
        # under lower_column_is_front (geo column 0 = front).
        rows = [
            {"position_id": 99, "column_index": 0, "row_order": 0, "state": "active"},
            {"position_id": 1, "column_index": 3, "row_order": 0, "state": "active"},
        ]
        out, _ = assign_display_positions(rows, column_direction="lower_column_is_front")
        by_id = {r["position_id"]: r for r in out}
        self.assertEqual(by_id[1]["display_position"], "1-1")  # back
        self.assertEqual(by_id[99]["display_position"], "2-1")  # front

    def test_unique_display_position_per_active(self) -> None:
        out, issues = assign_display_positions(
            _ACCEPTANCE_ROWS, column_direction="lower_column_is_front"
        )
        self.assertFalse(issues)
        labels = [r["display_position"] for r in out if "display_position" in r]
        self.assertEqual(len(labels), len(set(labels)))
        self.assertEqual(len(labels), 10)

    def test_unknown_direction_emits_issue_no_guess(self) -> None:
        out, issues = assign_display_positions(
            _ACCEPTANCE_ROWS, column_direction="sideways_mystery"
        )
        self.assertTrue(any(i.get("code") == "unknown_column_direction" for i in issues))
        self.assertTrue(all("display_position" not in r for r in out))

    def test_blocked_excluded_from_contiguous_slots(self) -> None:
        rows = [
            {"position_id": 1, "column_index": 1, "row_order": 0, "state": "active"},
            {"position_id": 2, "column_index": 1, "row_order": 1, "state": "blocked"},
            {"position_id": 3, "column_index": 1, "row_order": 2, "state": "active"},
        ]
        out, _ = assign_display_positions(rows, column_direction="lower_column_is_front")
        by_id = {r["position_id"]: r for r in out}
        self.assertEqual(by_id[1]["display_slot"], 1)
        self.assertEqual(by_id[3]["display_slot"], 2)
        self.assertNotIn("display_position", by_id[2])

    def test_resolve_aliases(self) -> None:
        self.assertEqual(
            resolve_column_direction_rule({"rule": "lower_column_index_is_front"}),
            "lower_column_is_front",
        )
        self.assertIsNone(resolve_column_direction_rule(None))
        self.assertIsNone(resolve_column_direction_rule("unknown_rule"))


class ExportAndInstructionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        path = Path(__file__).resolve().parent / "fixtures" / "webRequestLog_example.json"
        cls.payload = json.loads(path.read_text(encoding="utf-8"))

    def setUp(self) -> None:
        self.formation = (
            _hero(3, "Nayeli", 1),
            _hero(2, "Celeste", 2),
            _hero(4, "Jarlaxle", 3),
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

    def test_legacy_export_has_display_fields_and_convention(self) -> None:
        export = build_export_payload(
            self.payload,
            self.formation,
            goal="push",
            context="campaign",
            fixed_main_dps_id=4,
            request_id="disp-1",
        )
        formation = export["formation"]
        self.assertIn("position_display_convention", formation)
        self.assertEqual(
            formation["position_display_convention"]["format"], "column-slot"
        )
        self.assertEqual(
            formation["front_direction"].get("row_direction"), "lower_row_is_top"
        )
        active = [
            p
            for p in formation["positions"]
            if isinstance(p, dict) and p.get("state") == "active"
        ]
        self.assertTrue(active)
        for p in active:
            self.assertIn("display_position", p)
            self.assertRegex(str(p["display_position"]), r"^\d+-\d+$")
        labels = [p["display_position"] for p in active]
        self.assertEqual(len(labels), len(set(labels)))

        advice = build_advice_payload(export)
        geom = advice["geometry"]
        self.assertIn("position_display_convention", geom)
        self.assertTrue(
            any(r.get("display_position") for r in (geom.get("positions") or []))
        )

        md = format_clipboard_markdown(export, output_mode="json")
        self.assertIn("| Plek | Champion | Specialisatie(s) |", md)
        self.assertIn(POSITION_DISPLAY_AI_INSTRUCTION[:40], md)
        self.assertIn("display_position", md.casefold())
        self.assertIn("Hitch (seat 3)", md)
        self.assertIn("Specialisatie(s)", POSITION_DISPLAY_AI_INSTRUCTION)
        self.assertIn("Naam (seat N)", POSITION_DISPLAY_AI_INSTRUCTION)

    def test_advice_request_includes_mapping_and_instruction(self) -> None:
        snap = build_base_snapshot(self.payload, formation=self.formation)
        req = build_advice_request(
            self.payload,
            self.formation,
            snapshot_id=snap["meta"]["snapshot_id"],
            snapshot_meta=snap["meta"],
            base_snapshot=snap,
            goal="push",
            fixed_main_dps_id=4,
        )
        geom = req["geometry"]
        # Same layout → thin live occupancy; display convention lives on BASE.
        self.assertEqual(geom.get("ref"), "BASE_SNAPSHOT.geometry")
        self.assertTrue(geom.get("layout_matches_base"))
        self.assertIn("occupied", geom)
        self.assertIn("position_display_convention", snap["geometry"])
        self.assertEqual(
            snap["geometry"]["position_display_convention"]["example"], "1-1"
        )
        positions = snap["geometry"].get("positions") or []
        self.assertTrue(any(p.get("display_position") for p in positions))

        text = build_advice_request_clipboard_text(req, mode="project")
        self.assertIn("| Plek | Champion | Specialisatie(s) |", text)
        self.assertIn("kolom-plek", text.casefold())
        self.assertIn(ADVICE_TABLE_FORMAT[:50], text)

        project = build_project_instructions_clipboard_text()
        self.assertIn("| Plek | Champion | Specialisatie(s) |", project)
        self.assertIn("import-JSON", project)
        self.assertIn(POSITION_DISPLAY_AI_INSTRUCTION[:30], PROJECT_INSTRUCTIONS)

    def test_table_plus_json_still_imports(self) -> None:
        pasted = """
| Plek | Champion | Specialisatie(s) |
| --- | --- | --- |
| 1-1 | Nayeli (seat 3) | Oath of Vengeance (advies) |
| 2-1 | Celeste (seat 2) | War Domain (actief) |

Korte uitleg: baseline behouden.

```json
{"schema_version": "1.9", "request_id": "abc", "placements": [{"position_id": 1, "champion_id": 3}], "specializations": [{"champion_id": 3, "group_id": "tier_0", "option_id": 43}]}
```
"""
        data = extract_json_object(pasted)
        self.assertIsInstance(data, dict)
        self.assertEqual(data["request_id"], "abc")
        self.assertEqual(data["placements"][0]["position_id"], 1)
        # Import JSON must keep technical ids, not display notation.
        self.assertNotIn("display_position", data["placements"][0])
        self.assertNotIn("name", data["placements"][0])
        self.assertEqual(
            data["specializations"][0],
            {"champion_id": 3, "group_id": "tier_0", "option_id": 43},
        )


if __name__ == "__main__":
    unittest.main()
