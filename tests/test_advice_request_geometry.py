"""ADVICE_REQUEST geometry: thin ref vs full current layout override."""

from __future__ import annotations

import copy
import unittest

from ic_gamedata.formation_ai_advice.export_validation import (
    validate_advice_request_export,
)
from ic_gamedata.formation_ai_advice.labels import (
    assign_display_positions,
    sort_positions_for_display,
)
from ic_gamedata.formation_ai_advice.snapshot_export import (
    geometry_for_advice_request,
    geometry_layout_canonical,
    geometry_layout_fingerprint,
    geometry_layout_gaps,
    geometry_layouts_equal,
)


def _pos(
    pid: int,
    column: int,
    row: int,
    *,
    champion_id: int | None = None,
    zone: str | None = None,
) -> dict:
    item: dict = {
        "id": pid,
        "column": column,
        "row": row,
        "zone": zone or "mid",
    }
    if champion_id is not None:
        item["champion_id"] = champion_id
    return item


def _with_display(positions: list[dict]) -> list[dict]:
    """Attach display_* via the real layout convention (not invented)."""
    rows = [
        {
            "position_id": p["id"],
            "column_index": p["column"],
            "row_order": p["row"],
            "state": "active",
            "zone": p.get("zone"),
            "current_champion_id": p.get("champion_id"),
        }
        for p in positions
    ]
    numbered, issues = assign_display_positions(
        rows, column_direction="lower_column_is_front", active_only=True
    )
    assert not issues, issues
    numbered = sort_positions_for_display(
        numbered, column_direction_rule="lower_column_is_front"
    )
    out: list[dict] = []
    for row in numbered:
        item = {
            "id": row["position_id"],
            "column": row["column_index"],
            "row": row["row_order"],
            "zone": row.get("zone"),
            "display_column": row["display_column"],
            "display_slot": row["display_slot"],
            "display_position": row["display_position"],
        }
        if row.get("current_champion_id") is not None:
            item["champion_id"] = row["current_champion_id"]
        out.append(item)
    return out


def _adj_from_ids(ids: list[int]) -> dict[str, list[int]]:
    """Minimal synthetic chain adjacency for tests (not a production layout)."""
    adj: dict[str, list[int]] = {}
    for i, pid in enumerate(ids):
        neighbors: list[int] = []
        if i > 0:
            neighbors.append(ids[i - 1])
        if i + 1 < len(ids):
            neighbors.append(ids[i + 1])
        adj[str(pid)] = neighbors
    return adj


def _geometry(
    position_specs: list[tuple[int, int, int]],
    *,
    occupied: dict[int, int] | None = None,
    adjacency: dict[str, list[int]] | None = None,
    source: str = "synthetic_test",
) -> dict:
    """Build a complete synthetic geometry (explicit test layout, not adventure 909)."""
    occupied = occupied or {}
    raw = [
        _pos(pid, col, row, champion_id=occupied.get(pid))
        for pid, col, row in position_specs
    ]
    positions = _with_display(raw)
    ids = [pid for pid, *_ in position_specs]
    return {
        "source": source,
        "valid_position_ids": list(ids),
        "positions": positions,
        "adjacency": adjacency if adjacency is not None else _adj_from_ids(ids),
        "column_direction": {"rule": "lower_column_is_front"},
        "row_direction": "lower_row_is_top",
        "distance_rule": "hops_on_active_adjacency",
        "position_display_convention": {
            "technical_id_field": "id",
            "example": "1-1",
        },
    }


# Synthetic base shape (mirrors common 9-slot patterns; not adventure 909).
_BASE_SPECS = [
    (2, 0, 0),
    (3, 0, 1),
    (4, 1, 0),
    (5, 1, 1),
    (6, 2, 0),
    (7, 2, 1),
    (9, 3, 0),
    (11, 3, 1),
    (12, 4, 0),
]

# Synthetic current shape with different active ids (1,8,10 instead of 3,7).
_CURRENT_SPECS = [
    (1, 0, 0),
    (2, 0, 1),
    (4, 1, 0),
    (5, 1, 1),
    (6, 2, 0),
    (8, 2, 1),
    (9, 3, 0),
    (10, 3, 1),
    (11, 4, 0),
    (12, 4, 1),
]


class GeometryLayoutCompareTests(unittest.TestCase):
    def test_a_same_layout_different_occupancy_allows_thin_ref(self) -> None:
        base = _geometry(_BASE_SPECS, occupied={2: 1, 4: 2})
        current = _geometry(_BASE_SPECS, occupied={2: 99, 5: 3, 12: 4})
        self.assertTrue(geometry_layouts_equal(base, current))
        block, meta = geometry_for_advice_request(current, base)
        self.assertEqual(meta["mode"], "thin")
        self.assertEqual(block.get("ref"), "BASE_SNAPSHOT.geometry")
        self.assertTrue(block.get("layout_matches_base"))
        self.assertNotIn("positions", block)
        self.assertNotIn("adjacency", block)
        occ = {row["id"]: row["champion_id"] for row in block["occupied"]}
        self.assertEqual(occ[2], 99)
        self.assertEqual(occ[5], 3)
        self.assertEqual(occ[12], 4)

    def test_b_changed_active_positions_exports_full_current(self) -> None:
        base = _geometry(_BASE_SPECS, occupied={2: 1})
        current = _geometry(
            _CURRENT_SPECS,
            occupied={1: 10, 8: 20, 10: 30},
            source="synthetic_current_override",
        )
        self.assertFalse(geometry_layouts_equal(base, current))
        block, meta = geometry_for_advice_request(current, base)
        self.assertEqual(meta["mode"], "full")
        self.assertTrue(block.get("overrides_base_snapshot_geometry"))
        self.assertEqual(block.get("override_kind"), "expected_state_override")
        self.assertNotIn("ref", block)
        self.assertEqual(
            sorted(block["valid_position_ids"]),
            [1, 2, 4, 5, 6, 8, 9, 10, 11, 12],
        )
        pos_ids = sorted(p["id"] for p in block["positions"])
        self.assertEqual(pos_ids, [1, 2, 4, 5, 6, 8, 9, 10, 11, 12])
        self.assertNotIn(3, pos_ids)
        self.assertNotIn(7, pos_ids)
        for row in block["positions"]:
            self.assertIsNotNone(row.get("display_position"))
            self.assertIsNotNone(row.get("display_column"))
            self.assertIsNotNone(row.get("display_slot"))
            self.assertIsNotNone(row.get("column"))
            self.assertIsNotNone(row.get("row"))
        adj_keys = {_as_int(k) for k in block["adjacency"]}
        self.assertNotIn(3, adj_keys)
        self.assertNotIn(7, adj_keys)
        for neighbors in block["adjacency"].values():
            self.assertNotIn(3, neighbors)
            self.assertNotIn(7, neighbors)
        self.assertIn("column_direction", block)
        self.assertIn("row_direction", block)
        occ = {row["id"]: row["champion_id"] for row in block["occupied"]}
        self.assertEqual(occ[1], 10)

    def test_c_same_ids_different_columns_exports_full(self) -> None:
        base = _geometry(_BASE_SPECS)
        # Same ids, shifted columns → layout change without id-set change.
        shifted = [
            (pid, col + 1, row) for pid, col, row in _BASE_SPECS
        ]
        current = _geometry(shifted, occupied={2: 1})
        self.assertEqual(
            sorted(base["valid_position_ids"]),
            sorted(current["valid_position_ids"]),
        )
        self.assertFalse(geometry_layouts_equal(base, current))
        block, meta = geometry_for_advice_request(current, base)
        self.assertEqual(meta["mode"], "full")
        self.assertTrue(block.get("overrides_base_snapshot_geometry"))
        self.assertNotIn("ref", block)
        self.assertIn("positions", block)
        self.assertIn("adjacency", block)

    def test_d_incomplete_current_no_invented_fallback(self) -> None:
        base = _geometry(_BASE_SPECS)
        current = _geometry(_CURRENT_SPECS)
        # Strip coordinates / adjacency to simulate incomplete live layout.
        for row in current["positions"]:
            row.pop("column", None)
            row.pop("display_position", None)
            row.pop("display_column", None)
            row.pop("display_slot", None)
        current["adjacency"] = None
        gaps = geometry_layout_gaps(current)
        self.assertTrue(gaps)
        block, meta = geometry_for_advice_request(current, base)
        self.assertEqual(meta["mode"], "incomplete")
        self.assertTrue(block.get("layout_incomplete"))
        self.assertTrue(block.get("overrides_base_snapshot_geometry"))
        self.assertNotIn("ref", block)
        self.assertIn("missing_layout_fields", block)
        # Must not invent adjacency or display coords.
        self.assertIsNone(block.get("adjacency"))
        for row in block.get("positions") or []:
            self.assertIsNone(row.get("display_position"))

    def test_e_display_sort_and_technical_ids(self) -> None:
        geo = _geometry(_CURRENT_SPECS, occupied={1: 3, 8: 4})
        block, _meta = geometry_for_advice_request(geo, None)
        positions = list(block["positions"])
        # Table order: display_column then display_slot.
        ordered = sorted(
            positions,
            key=lambda r: (r["display_column"], r["display_slot"]),
        )
        labels = [r["display_position"] for r in ordered]
        self.assertEqual(labels, sorted(labels, key=lambda lab: tuple(
            int(x) for x in lab.split("-")
        )))
        for row in positions:
            self.assertIsInstance(row["id"], int)
            # Permanent seat must never appear as formation position key.
            self.assertNotIn("seat", row)
        for row in block["occupied"]:
            self.assertIn("id", row)
            self.assertIn("champion_id", row)
            self.assertNotIn("seat", row)

    def test_f_order_independent_comparison(self) -> None:
        base = _geometry(_BASE_SPECS)
        shuffled = copy.deepcopy(base)
        shuffled["valid_position_ids"] = list(
            reversed(shuffled["valid_position_ids"])
        )
        shuffled["positions"] = list(reversed(shuffled["positions"]))
        # Rebuild adjacency with different key insertion order / neighbor order.
        adj = {}
        for key in reversed(list(shuffled["adjacency"])):
            adj[key] = list(reversed(shuffled["adjacency"][key]))
        shuffled["adjacency"] = adj
        self.assertTrue(geometry_layouts_equal(base, shuffled))
        self.assertEqual(
            geometry_layout_fingerprint(base),
            geometry_layout_fingerprint(shuffled),
        )
        # Canonical ignores occupancy.
        with_occ = copy.deepcopy(base)
        with_occ["positions"][0]["champion_id"] = 999
        self.assertTrue(geometry_layouts_equal(base, with_occ))

    def test_g_consistency_validation(self) -> None:
        geo = _geometry(_CURRENT_SPECS, occupied={1: 7, 8: 8})
        block, _meta = geometry_for_advice_request(geo, None)
        request = {
            "meta": {"snapshot_ref": {"snapshot_id": "snap_test"}},
            "goal": {"id": "push"},
            "geometry": block,
            "party": [
                {"id": 7, "position": 1, "seat": 1, "live_state": {"status": "unknown"}},
                {"id": 8, "position": 8, "seat": 2, "live_state": {"status": "unknown"}},
            ],
            "readiness": {"status": "ready"},
            "roster_eligibility": {},
        }
        result = validate_advice_request_export(
            payload={"details": {"heroes": []}},
            request=request,
            snapshot_id="snap_test",
            exported_snapshot_id="snap_test",
        )
        geo_codes = {
            i.code
            for i in result.issues
            if i.code.startswith("geometry_")
            or i.code.startswith("adjacency_")
            or i.code.startswith("occupied_")
        }
        self.assertNotIn("geometry_layout_incomplete", geo_codes)
        self.assertNotIn("geometry_missing_position_record", geo_codes)
        self.assertNotIn("adjacency_edge_to_inactive", geo_codes)
        self.assertNotIn("geometry_duplicate_display_position", geo_codes)

        # Inject inactive adjacency + missing record → errors.
        bad = copy.deepcopy(block)
        bad["adjacency"]["3"] = [1]
        bad["adjacency"]["1"] = list(bad["adjacency"]["1"]) + [3]
        bad["positions"] = [p for p in bad["positions"] if p["id"] != 10]
        request["geometry"] = bad
        bad_result = validate_advice_request_export(
            payload={"details": {"heroes": []}},
            request=request,
            snapshot_id="snap_test",
            exported_snapshot_id="snap_test",
        )
        codes = {i.code for i in bad_result.errors}
        self.assertTrue(
            {"geometry_missing_position_record", "adjacency_inactive_key"} & codes
            or {"adjacency_edge_to_inactive"} & codes
        )
        self.assertFalse(bad_result.advice_ready)

    def test_incomplete_sets_advice_not_ready(self) -> None:
        base = _geometry(_BASE_SPECS)
        current = _geometry(_CURRENT_SPECS)
        current["adjacency"] = {}
        block, meta = geometry_for_advice_request(current, base)
        self.assertEqual(meta["mode"], "incomplete")
        request = {
            "meta": {"snapshot_ref": {"snapshot_id": "snap_test"}},
            "goal": {"id": "push"},
            "geometry": block,
            "party": [
                {"id": 1, "position": 1, "seat": 1, "live_state": {"status": "unknown"}},
            ],
            "readiness": {
                "status": "blocked",
                "placement_advice": "insufficient",
                "issues": [
                    {
                        "code": "geometry_layout_incomplete",
                        "severity": "error",
                        "dimension": "geometry",
                    }
                ],
            },
            "roster_eligibility": {},
        }
        result = validate_advice_request_export(
            payload={"details": {"heroes": []}},
            request=request,
            snapshot_id="snap_test",
            exported_snapshot_id="snap_test",
        )
        self.assertFalse(result.advice_ready)
        self.assertTrue(
            any(i.code == "geometry_layout_incomplete" for i in result.errors)
        )

    def test_canonical_excludes_occupancy_keys(self) -> None:
        geo = _geometry(_BASE_SPECS, occupied={2: 1})
        canon = geometry_layout_canonical(geo)
        blob = str(canon)
        self.assertNotIn("champion_id", blob)
        self.assertNotIn("occupied", blob)


def _as_int(value: object) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


if __name__ == "__main__":
    unittest.main()
