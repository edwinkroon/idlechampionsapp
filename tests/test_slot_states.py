"""Explicit geometry.slot_states: NPC/escort blocks vs free vs unknown."""

from __future__ import annotations

import unittest
from typing import Any

from ic_gamedata.formation_ai_advice.models import (
    AssignmentProposal,
    FormationAdviceProposal,
    SCHEMA_VERSION,
)
from ic_gamedata.formation_ai_advice.slot_states import (
    build_slot_states,
    derive_position_id_lists,
    validate_slot_states,
)
from ic_gamedata.formation_ai_advice.snapshot_export import (
    geometry_for_advice_request,
    geometry_layouts_equal,
)
from ic_gamedata.formation_ai_advice.validate import validate_proposal_against_export
from ic_gamedata.seat_advisor.formation_visual import build_slot_overlay_nodes


def _states(
    *,
    layout: list[int],
    champions: dict[int, int],
    reserved: list[int],
    placeability_known: bool,
) -> list[dict[str, Any]]:
    return build_slot_states(
        layout,
        champion_by_position=champions,
        reserved_seats=reserved,
        placeability_known=placeability_known,
    )


def _proposal(placements: list[tuple[int, int]]) -> FormationAdviceProposal:
    return FormationAdviceProposal(
        schema_version=SCHEMA_VERSION,
        request_id="req-slot-test",
        status="proposal",
        summary="test",
        assignments=tuple(
            AssignmentProposal(position_id=pos, champion_id=cid)
            for cid, pos in placements
        ),
    )


def _export_from_states(
    *,
    layout: list[int],
    champions: dict[int, int],
    slot_states: list[dict[str, Any]],
    adjacency: dict[str, list[int]] | None = None,
) -> dict[str, Any]:
    derived = derive_position_id_lists(slot_states)
    party_champs = [
        {
            "champion_id": hid,
            # Unique permanent F-seats for tests (not formation position_ids).
            "seat": 10 + idx,
            "current_position": pos,
        }
        for idx, (pos, hid) in enumerate(sorted(champions.items()))
    ]
    adj = adjacency or {
        str(pid): [n for n in layout if n != pid][:2] for pid in layout
    }
    return {
        "meta": {"schema_version": SCHEMA_VERSION, "request_id": "req-slot-test"},
        "champions": party_champs,
        "formation": {
            "valid_position_ids": layout,
            "active_position_ids": [
                p
                for p in layout
                if p not in set(derived["blocked_position_ids"])
            ],
            "blocked_position_ids": derived["blocked_position_ids"],
            "available_position_ids": derived["available_position_ids"],
            "unknown_placeability_position_ids": derived[
                "unknown_placeability_position_ids"
            ],
            "slot_states": slot_states,
            "adjacency_by_position": adj,
            "current_champion_by_position": {
                str(pos): hid for pos, hid in champions.items()
            },
            "positions": [
                {
                    "position_id": pid,
                    "current_champion_id": champions.get(pid),
                    "state": (
                        "blocked"
                        if pid in derived["blocked_position_ids"]
                        else "active"
                    ),
                }
                for pid in layout
            ],
        },
        "geometry": {
            "valid_position_ids": layout,
            "occupied": [
                {"id": pos, "champion_id": hid}
                for pos, hid in sorted(champions.items())
            ],
            "slot_states": slot_states,
            **derived,
            "adjacency": adj,
        },
    }


class SlotStateBuildTests(unittest.TestCase):
    def test_nine_layout_seven_champs_two_npc_no_free(self) -> None:
        layout = list(range(1, 10))
        champs = {i: 100 + i for i in range(1, 8)}
        reserved = [8, 9]
        states = _states(
            layout=layout,
            champions=champs,
            reserved=reserved,
            placeability_known=True,
        )
        derived = derive_position_id_lists(states)
        self.assertEqual(len(layout), 9)
        self.assertEqual(len(champs), 7)
        self.assertEqual(derived["blocked_position_ids"], [8, 9])
        self.assertEqual(derived["available_position_ids"], [])
        self.assertEqual(derived["unknown_placeability_position_ids"], [])
        by_id = {s["position_id"]: s for s in states}
        self.assertEqual(by_id[8]["occupancy"], "escort")
        self.assertEqual(by_id[8]["placeability"], "blocked")
        self.assertEqual(by_id[8]["blocker"]["type"], "escort")
        self.assertIsNone(by_id[8]["blocker"].get("id"))
        self.assertIsNone(by_id[8]["blocker"].get("name"))

    def test_nine_layout_seven_champs_two_free(self) -> None:
        layout = list(range(1, 10))
        champs = {i: 100 + i for i in range(1, 8)}
        states = _states(
            layout=layout,
            champions=champs,
            reserved=[],
            placeability_known=True,
        )
        derived = derive_position_id_lists(states)
        self.assertEqual(derived["available_position_ids"], [8, 9])
        self.assertEqual(derived["blocked_position_ids"], [])
        by_id = {s["position_id"]: s for s in states}
        self.assertEqual(by_id[8]["occupancy"], "empty")
        self.assertEqual(by_id[8]["placeability"], "placeable")

    def test_nine_layout_seven_champs_two_unknown(self) -> None:
        layout = list(range(1, 10))
        champs = {i: 100 + i for i in range(1, 8)}
        states = _states(
            layout=layout,
            champions=champs,
            reserved=[],
            placeability_known=False,
        )
        derived = derive_position_id_lists(states)
        self.assertEqual(derived["available_position_ids"], [])
        self.assertEqual(derived["unknown_placeability_position_ids"], [8, 9])
        by_id = {s["position_id"]: s for s in states}
        self.assertEqual(by_id[8]["occupancy"], "unknown")
        self.assertEqual(by_id[8]["placeability"], "unknown")


class SlotStateValidationTests(unittest.TestCase):
    def test_reject_placement_on_npc_blocks(self) -> None:
        layout = list(range(1, 10))
        champs = {i: 100 + i for i in range(1, 8)}
        states = _states(
            layout=layout,
            champions=champs,
            reserved=[8, 9],
            placeability_known=True,
        )
        export = _export_from_states(
            layout=layout, champions=champs, slot_states=states
        )
        # Full party plus illegal fills of NPC seats with extra "champions"
        # would fail selected-set check; instead reassign existing champs onto
        # NPC seats (same set, wrong positions).
        placements = [(100 + i, i) for i in range(1, 8)]
        placements[0] = (101, 8)  # move champ onto NPC seat 8
        placements[1] = (102, 9)
        # Keep remaining champs on 3..7; seat 1–2 empty of their original — still
        # seven assignments on positions including blocked.
        placements = [
            (101, 8),
            (102, 9),
            (103, 3),
            (104, 4),
            (105, 5),
            (106, 6),
            (107, 7),
        ]
        result = validate_proposal_against_export(
            _proposal(placements),
            export,
            api_sources=(),
            formation_fingerprint_at_request="fp",
            current_formation_fingerprint="fp",
        )
        self.assertFalse(result.can_apply)
        joined = " ".join(result.errors)
        self.assertIn("8", joined)
        self.assertIn("9", joined)
        self.assertIn("geweigerd", joined.lower())

    def test_allow_add_on_confirmed_free(self) -> None:
        layout = list(range(1, 10))
        champs = {i: 100 + i for i in range(1, 8)}
        states = _states(
            layout=layout,
            champions=champs,
            reserved=[],
            placeability_known=True,
        )
        # Party of 9 with two new champs on free seats 8 and 9.
        champs9 = dict(champs)
        champs9[8] = 208
        champs9[9] = 209
        export = _export_from_states(
            layout=layout, champions=champs9, slot_states=states
        )
        # Re-build states with 9 champions so selected set matches.
        states9 = _states(
            layout=layout,
            champions=champs9,
            reserved=[],
            placeability_known=True,
        )
        export = _export_from_states(
            layout=layout, champions=champs9, slot_states=states9
        )
        placements = [(hid, pos) for pos, hid in sorted(champs9.items())]
        result = validate_proposal_against_export(
            _proposal(placements),
            export,
            api_sources=(),
            formation_fingerprint_at_request="fp",
            current_formation_fingerprint="fp",
        )
        self.assertTrue(result.can_apply, result.errors)
        self.assertEqual(result.status, "valid")

    def test_reject_auto_add_on_unknown(self) -> None:
        layout = list(range(1, 10))
        champs = {i: 100 + i for i in range(1, 8)}
        states = _states(
            layout=layout,
            champions=champs,
            reserved=[],
            placeability_known=False,
        )
        # Export still has 7 champions; proposal tries to place one onto
        # unknown seat 8 while keeping the party set — use a 7-champ set with
        # one champ moved onto unknown 8.
        export = _export_from_states(
            layout=layout, champions=champs, slot_states=states
        )
        placements = [
            (101, 1),
            (102, 2),
            (103, 3),
            (104, 4),
            (105, 5),
            (106, 6),
            (107, 8),  # unknown placeability
        ]
        result = validate_proposal_against_export(
            _proposal(placements),
            export,
            api_sources=(),
            formation_fingerprint_at_request="fp",
            current_formation_fingerprint="fp",
        )
        self.assertFalse(result.can_apply)
        self.assertTrue(
            any("unknown" in e.lower() or "8" in e for e in result.errors)
        )


class SlotStateGeometryRequestTests(unittest.TestCase):
    def _geo(
        self,
        *,
        layout: list[int],
        champs: dict[int, int],
        reserved: list[int],
        known: bool,
        source: str = "test",
    ) -> dict[str, Any]:
        states = _states(
            layout=layout,
            champions=champs,
            reserved=reserved,
            placeability_known=known,
        )
        derived = derive_position_id_lists(states)
        positions = [
            {
                "id": pid,
                "column": 0,
                "row": pid - 1,
                "zone": "mid",
                "display_column": 1,
                "display_slot": pid,
                "display_position": f"1-{pid}",
                "champion_id": champs.get(pid),
            }
            for pid in layout
        ]
        return {
            "source": source,
            "valid_position_ids": layout,
            "positions": positions,
            "adjacency": {
                str(pid): [n for n in layout if abs(n - pid) == 1] for pid in layout
            },
            "column_direction": {"rule": "lower_column_is_front"},
            "row_direction": "lower_row_is_top",
            "distance_rule": "hops_on_active_adjacency",
            "slot_states": states,
            **derived,
        }

    def test_thin_request_uses_current_slot_states_not_base(self) -> None:
        layout = list(range(1, 10))
        champs = {i: 100 + i for i in range(1, 8)}
        base = self._geo(
            layout=layout, champs=champs, reserved=[], known=True, source="base"
        )
        # Same layout, but escorts now occupy 8 and 9.
        current = self._geo(
            layout=layout,
            champs=champs,
            reserved=[8, 9],
            known=True,
            source="live",
        )
        self.assertTrue(geometry_layouts_equal(base, current))
        geo, meta = geometry_for_advice_request(current, base)
        self.assertEqual(meta["mode"], "thin")
        self.assertTrue(geo.get("layout_matches_base"))
        self.assertEqual(geo.get("ref"), "BASE_SNAPSHOT.geometry")
        blocked = {
            s["position_id"]
            for s in (geo.get("slot_states") or [])
            if s.get("placeability") == "blocked"
        }
        self.assertEqual(blocked, {8, 9})
        self.assertEqual(geo.get("blocked_position_ids"), [8, 9])
        self.assertEqual(geo.get("available_position_ids") or [], [])

    def test_full_override_no_mix_with_base_layout(self) -> None:
        layout_a = list(range(1, 10))
        layout_b = list(range(1, 8))  # different technical layout
        champs = {i: 100 + i for i in range(1, 8)}
        base = self._geo(
            layout=layout_a, champs=champs, reserved=[8, 9], known=True
        )
        current = self._geo(
            layout=layout_b, champs=champs, reserved=[], known=True, source="live"
        )
        self.assertFalse(geometry_layouts_equal(base, current))
        geo, meta = geometry_for_advice_request(current, base)
        self.assertIn(meta["mode"], ("full", "incomplete"))
        self.assertTrue(geo.get("overrides_base_snapshot_geometry"))
        self.assertEqual(geo.get("valid_position_ids"), layout_b)
        # Must not retain base escort blocks 8/9.
        self.assertNotIn(8, geo.get("valid_position_ids") or [])
        self.assertNotIn(9, set(geo.get("blocked_position_ids") or []))


class SlotStateAdjacencyAndSwapTests(unittest.TestCase):
    def test_npc_remain_in_layout_adjacency(self) -> None:
        layout = list(range(1, 10))
        champs = {i: 100 + i for i in range(1, 8)}
        states = _states(
            layout=layout,
            champions=champs,
            reserved=[8, 9],
            placeability_known=True,
        )
        # Physical adjacency includes blocked seats (not removed from layout).
        adj = {
            str(pid): [n for n in layout if abs(n - pid) == 1] for pid in layout
        }
        self.assertIn(8, adj["7"])
        self.assertIn(9, adj["8"])
        self.assertEqual(len(layout), 9)
        self.assertIn(8, {s["position_id"] for s in states})
        self.assertIn(9, {s["position_id"] for s in states})

    def test_npc_not_counted_as_champions_or_swaps(self) -> None:
        layout = list(range(1, 10))
        champs = {i: 100 + i for i in range(1, 8)}
        states = _states(
            layout=layout,
            champions=champs,
            reserved=[8, 9],
            placeability_known=True,
        )
        export = _export_from_states(
            layout=layout, champions=champs, slot_states=states
        )
        self.assertEqual(len(export["champions"]), 7)
        self.assertEqual(len(export["geometry"]["occupied"]), 7)
        for row in states:
            if row["placeability"] == "blocked":
                self.assertNotIn(row["occupancy"], ("champion",))
                self.assertIsNone(row.get("blocker", {}).get("id"))

    def test_preview_and_import_share_blockades(self) -> None:
        layout = list(range(1, 10))
        champs = {i: 100 + i for i in range(1, 8)}
        states = _states(
            layout=layout,
            champions=champs,
            reserved=[8, 9],
            placeability_known=True,
        )
        geom = {pid: (float(pid), 0.0, "mid") for pid in layout}
        overlay = build_slot_overlay_nodes(states, geom)
        kinds = {n.seat: n.slot_kind for n in overlay}
        self.assertEqual(kinds.get(8), "escort")
        self.assertEqual(kinds.get(9), "escort")
        # Confirmed free seats are not rendered as free-add cards.
        free_states = _states(
            layout=layout,
            champions=champs,
            reserved=[],
            placeability_known=True,
        )
        free_overlay = build_slot_overlay_nodes(free_states, geom)
        self.assertEqual(free_overlay, ())

        export = _export_from_states(
            layout=layout, champions=champs, slot_states=states
        )
        result = validate_proposal_against_export(
            _proposal(
                [
                    (101, 8),
                    (102, 2),
                    (103, 3),
                    (104, 4),
                    (105, 5),
                    (106, 6),
                    (107, 7),
                ]
            ),
            export,
            api_sources=(),
            formation_fingerprint_at_request="fp",
            current_formation_fingerprint="fp",
        )
        self.assertFalse(result.can_apply)
        self.assertTrue(any("8" in e for e in result.errors))


class SlotStateLegacyCompatTests(unittest.TestCase):
    def test_missing_slot_states_do_not_imply_free(self) -> None:
        # Legacy export: blocked listed, no slot_states — still reject.
        export = {
            "meta": {"schema_version": SCHEMA_VERSION, "request_id": "req"},
            "champions": [
                {"champion_id": 101, "seat": 1},
                {"champion_id": 102, "seat": 2},
            ],
            "formation": {
                "valid_position_ids": [1, 2, 3],
                "active_position_ids": [1, 2],
                "blocked_position_ids": [3],
                "adjacency_by_position": {"1": [2], "2": [1]},
                "current_champion_by_position": {"1": 101, "2": 102},
            },
        }
        result = validate_proposal_against_export(
            _proposal([(101, 1), (102, 3)]),
            export,
            api_sources=(),
            formation_fingerprint_at_request="fp",
            current_formation_fingerprint="fp",
        )
        self.assertFalse(result.can_apply)

    def test_validate_slot_states_duplicates(self) -> None:
        errs = validate_slot_states(
            [
                {
                    "position_id": 1,
                    "occupancy": "empty",
                    "placeability": "placeable",
                },
                {
                    "position_id": 1,
                    "occupancy": "escort",
                    "placeability": "blocked",
                },
            ],
            valid_position_ids=[1, 2],
        )
        self.assertTrue(any("Dubbele" in e for e in errs))


class FormationBlockIntegrationTests(unittest.TestCase):
    """End-to-end via _formation_block when adventure define has slot_escort."""

    def test_formation_block_exports_escort_slot_states(self) -> None:
        from ic_gamedata.formation_advisor.context_builder import (
            build_formation_layout_context,
        )
        from ic_gamedata.formation_ai_advice.export import _formation_block
        from ic_gamedata.party_advisor_models import FormationHero

        adventure_id = 563
        # slot_ids are 0-based formation indices; empty indices 7,8 → seats 8,9.
        nodes = [
            {"x": float(i), "y": 0, "col": i, "adj": []} for i in range(9)
        ]
        payload = {
            "defines": {
                "adventure_defines": [
                    {
                        "id": adventure_id,
                        "game_changes": [
                            {"type": "slot_escort", "slot_ids": [7, 8]},
                            {
                                "type": "formation",
                                "name": "test nine",
                                "formation": nodes,
                            },
                        ],
                    }
                ]
            },
            "details": {
                "active_game_instance_id": 1,
                "game_instances": [
                    {
                        "game_instance_id": 1,
                        "current_adventure_id": adventure_id,
                        "hero_in_seats": {
                            str(i): 100 + i for i in range(1, 8)
                        },
                        "formation": [
                            101,
                            102,
                            103,
                            104,
                            105,
                            106,
                            107,
                            -1,
                            -1,
                        ],
                    }
                ],
                "heroes": [
                    {
                        "hero_id": 100 + i,
                        "owned": 1,
                        "in_seat": i,
                        "game_instance_id": 1,
                    }
                    for i in range(1, 8)
                ],
            },
        }
        heroes = tuple(
            FormationHero(
                hero_id=100 + i,
                name=f"H{i}",
                seat=i,
                level=1,
                gear_score=0.0,
                ilvl=0,
                ilvl_pct_vs_avg=0.0,
                gear_rank=1,
                gear_rank_total=1,
                gear_pct_of_best=0.0,
                gear_label="",
                role_label="",
                roles=(),
                tags=(),
                highest_damage=0.0,
                active_feats=0,
                is_top_damage=False,
            )
            for i in range(1, 8)
        )
        ctx = build_formation_layout_context(
            payload,
            heroes,
            goal="push",
            context="campaign",
        )
        block = _formation_block(payload, ctx, adventure_id=adventure_id)
        valid = set(block["valid_position_ids"])
        self.assertTrue({8, 9}.issubset(valid) or len(valid) >= 7)
        states = {s["position_id"]: s for s in (block.get("slot_states") or [])}
        # Escort seats must be blocked when present in the layout.
        for pid in (8, 9):
            if pid in states:
                self.assertEqual(states[pid]["placeability"], "blocked")
                self.assertEqual(states[pid]["occupancy"], "escort")
        self.assertEqual(block.get("available_position_ids") or [], [])
        # Adjacency must not drop blocked seats from the physical graph when
        # those seats are part of the exported layout.
        adj = block.get("adjacency_by_position") or {}
        layout_ids = set(block["valid_position_ids"])
        for pid in layout_ids:
            self.assertIn(str(pid), adj)


if __name__ == "__main__":
    unittest.main()
