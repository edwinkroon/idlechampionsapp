"""NPC/escort slot_ids are 0-based formation indices → technical position_ids."""

from __future__ import annotations

import unittest
from typing import Any

from ic_gamedata.formation_advisor.topology import formation_index_to_position_id
from ic_gamedata.formation_ai_advice.models import (
    AssignmentProposal,
    FormationAdviceProposal,
    SCHEMA_VERSION,
)
from ic_gamedata.formation_ai_advice.slot_states import (
    build_slot_states,
    derive_position_id_lists,
)
from ic_gamedata.formation_ai_advice.validate import validate_proposal_against_export
from ic_gamedata.formation_position_resolve import (
    resolve_formation_indices,
    resolve_slot_escort_seats,
)
from ic_gamedata.seat_advisor.formation_visual import build_slot_overlay_nodes

# Real adventure 1919 game_changes.formation (cached_definitions).
_SHADOWS_FORMATION_NODES: list[dict[str, Any]] = [
    {"x": 80, "y": 20, "col": 0, "adj": [1, 3]},
    {"x": 80, "y": 40, "col": 0, "adj": [0, 2, 3, 4]},
    {"x": 80, "y": 60, "col": 0, "adj": [1, 4]},
    {"x": 60, "y": 30, "col": 1, "adj": [0, 1, 4, 5, 6]},
    {"x": 60, "y": 50, "col": 1, "adj": [1, 2, 3, 6, 7]},
    {"x": 40, "y": 20, "col": 2, "adj": [3, 6]},
    {"x": 40, "y": 40, "col": 2, "adj": [3, 4, 5, 7, 8]},
    {"x": 40, "y": 60, "col": 2, "adj": [4, 6, 8]},
    {"x": 20, "y": 50, "col": 3, "adj": [6, 7, 9]},
    {"x": 0, "y": 40, "col": 4, "adj": [8]},
]

# Live board matching the reported Shadows of the Past export occupancy.
_SHADOWS_FORMATION_IDS = [171, 168, 179, 172, 164, -1, 166, 34, -1, 165]
_SHADOWS_SEAT_BY_HERO = {
    165: 12,  # Baldric
    166: 10,  # Cazrin
    34: 2,  # Donaar
    172: 5,  # Kyre
    164: 8,  # Tess
    171: 1,  # Anson
    168: 9,  # King of Shadows
    179: 3,  # Caramon
}
_SHADOWS_CHAMPIONS = {
    12: 165,
    10: 166,
    2: 34,
    5: 172,
    8: 164,
    1: 171,
    9: 168,
    3: 179,
}
_SHADOWS_LAYOUT = [1, 2, 3, 4, 5, 6, 8, 9, 10, 12]


def _shadows_payload(
    *,
    slot_ids: list[int] | None = None,
    formation_ids: list[int] | None = None,
    seat_by_hero: dict[int, int] | None = None,
    include_formation: bool = True,
    base_snapshot_nodes: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    ids = list(formation_ids if formation_ids is not None else _SHADOWS_FORMATION_IDS)
    seats = dict(seat_by_hero if seat_by_hero is not None else _SHADOWS_SEAT_BY_HERO)
    escort_ids = list(slot_ids if slot_ids is not None else [5, 8])
    game_changes: list[dict[str, Any]] = [
        {
            "type": "slot_escort",
            "slot_ids": escort_ids,
            "hps": [1, 1],
            "graphics": [1216, 1217],
            "names": ["Shadow", "Shadow"],
        }
    ]
    if include_formation:
        game_changes.append(
            {
                "type": "formation",
                "name": "King of Shadows formation",
                "formation": list(_SHADOWS_FORMATION_NODES),
            }
        )
    defines: dict[str, Any] = {
        "adventure_defines": [
            {
                "id": 1919,
                "campaign_id": 4,
                "name": "Shadows of the Past",
                "game_changes": game_changes,
            }
        ]
    }
    if base_snapshot_nodes is not None:
        defines["campaign_defines"] = [
            {
                "id": 4,
                "game_changes": [
                    {
                        "type": "formation",
                        "name": "BASE_SNAPSHOT layout decoy",
                        "formation": base_snapshot_nodes,
                    }
                ],
            }
        ]
    return {
        "defines": defines,
        "details": {
            "active_game_instance_id": 1,
            "game_instances": [
                {
                    "game_instance_id": 1,
                    "current_adventure_id": 1919,
                    "hero_in_seats": {str(s): h for h, s in seats.items()},
                    "formation": ids,
                }
            ],
            "heroes": [
                {
                    "hero_id": hid,
                    "owned": 1,
                    "in_seat": seat,
                    "game_instance_id": 1,
                }
                for hid, seat in seats.items()
            ],
        },
    }


def _proposal(placements: list[tuple[int, int]]) -> FormationAdviceProposal:
    return FormationAdviceProposal(
        schema_version=SCHEMA_VERSION,
        request_id="req-escort-test",
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
) -> dict[str, Any]:
    derived = derive_position_id_lists(slot_states)
    return {
        "meta": {"schema_version": SCHEMA_VERSION, "request_id": "req-escort-test"},
        "champions": [
            {
                "champion_id": hid,
                "seat": 20 + idx,
                "current_position": pos,
            }
            for idx, (pos, hid) in enumerate(sorted(champions.items()))
        ],
        "formation": {
            "valid_position_ids": layout,
            "active_position_ids": [
                p for p in layout if p not in set(derived["blocked_position_ids"])
            ],
            "blocked_position_ids": derived["blocked_position_ids"],
            "available_position_ids": derived["available_position_ids"],
            "unknown_placeability_position_ids": derived[
                "unknown_placeability_position_ids"
            ],
            "slot_states": slot_states,
            "adjacency_by_position": {
                str(pid): [n for n in layout if n != pid][:2] for pid in layout
            },
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
        },
    }


class ShadowsOfThePastEscortTests(unittest.TestCase):
    """1. Regression: raw slot_ids [5,8] → NPC positions 4 and 6."""

    def test_raw_slot_escort_maps_to_positions_4_and_6(self) -> None:
        payload = _shadows_payload()
        resolution = resolve_slot_escort_seats(payload, 1919)
        self.assertEqual(resolution.raw_indices, (5, 8))
        self.assertEqual(resolution.position_ids, frozenset({4, 6}))
        self.assertEqual(resolution.unresolved_indices, ())
        self.assertTrue(resolution.mapping_reliable)

        states = build_slot_states(
            _SHADOWS_LAYOUT,
            champion_by_position=_SHADOWS_CHAMPIONS,
            reserved_seats=resolution.position_ids,
            placeability_known=True,
            escort_meta_by_position=resolution.meta_by_position,
        )
        derived = derive_position_id_lists(states)
        by_id = {s["position_id"]: s for s in states}

        self.assertEqual(by_id[4]["occupancy"], "escort")
        self.assertEqual(by_id[4]["placeability"], "blocked")
        self.assertEqual(by_id[6]["occupancy"], "escort")
        self.assertEqual(by_id[6]["placeability"], "blocked")
        self.assertEqual(by_id[4]["blocker"].get("name"), "Shadow")
        self.assertEqual(len(_SHADOWS_CHAMPIONS), 8)
        for pid, hid in _SHADOWS_CHAMPIONS.items():
            self.assertEqual(by_id[pid]["occupancy"], "champion")
            self.assertNotIn("conflict", by_id[pid])
            self.assertEqual(by_id[pid].get("champion_id", hid), hid)
        self.assertEqual(derived["available_position_ids"], [])
        self.assertEqual(sorted(derived["blocked_position_ids"]), [4, 6])
        # Wrong seat-id interpretation would mark 5/8 as escorts.
        self.assertEqual(by_id[5]["occupancy"], "champion")
        self.assertEqual(by_id[8]["occupancy"], "champion")


class IndexSemanticsTests(unittest.TestCase):
    """2–4. Non-contiguous IDs, display order, confirmed 0-based indices."""

    def test_array_indexes_are_not_used_as_position_ids(self) -> None:
        # Non-contiguous technical IDs; index 0/1 must not become position 0/1.
        nodes = [
            {"x": 0, "y": 0, "col": 0, "adj": [1]},
            {"x": 10, "y": 0, "col": 1, "adj": [0]},
            {"x": 20, "y": 0, "col": 2, "adj": []},
        ]
        formation_ids = [101, -1, 102]
        seat_by_hero = {101: 12, 102: 3}
        index_map = formation_index_to_position_id(nodes, formation_ids, seat_by_hero)
        self.assertEqual(index_map[0], 12)
        self.assertEqual(index_map[2], 3)
        # Empty index 1 prefers seat 2 (index+1), not technical id 1-as-index.
        self.assertEqual(index_map[1], 2)
        resolved = resolve_formation_indices(
            [1], index_to_position=index_map, layout_node_count=3
        )
        self.assertEqual(resolved.position_ids, frozenset({2}))
        self.assertNotIn(1, resolved.position_ids)

    def test_display_sort_order_does_not_change_escort_mapping(self) -> None:
        index_map = formation_index_to_position_id(
            _SHADOWS_FORMATION_NODES,
            _SHADOWS_FORMATION_IDS,
            _SHADOWS_SEAT_BY_HERO,
        )
        # Display reading order differs from graph index order.
        display_order = [12, 4, 6, 10, 2, 5, 8, 1, 9, 3]
        self.assertNotEqual(display_order, sorted(display_order))
        a = resolve_formation_indices(
            [5, 8],
            index_to_position=index_map,
            layout_node_count=len(_SHADOWS_FORMATION_NODES),
        )
        # Same indices after sorting "by display" must yield the same seats.
        b = resolve_formation_indices(
            [5, 8],
            index_to_position={
                idx: index_map[idx]
                for idx in sorted(index_map, key=lambda i: display_order.index(index_map[i]))
            },
            layout_node_count=len(_SHADOWS_FORMATION_NODES),
        )
        self.assertEqual(a.position_ids, frozenset({4, 6}))
        self.assertEqual(b.position_ids, frozenset({4, 6}))

    def test_slot_ids_are_zero_based_formation_indices(self) -> None:
        # Source data includes index 0 (Drunk Farmer style) — proves 0-based.
        nodes = [{"x": i, "y": 0, "col": i, "adj": []} for i in range(3)]
        index_map = formation_index_to_position_id(
            nodes, [-1, 10, 11], {10: 2, 11: 3}
        )
        self.assertEqual(index_map[0], 1)  # preferred index+1
        resolved = resolve_formation_indices(
            [0], index_to_position=index_map, layout_node_count=3
        )
        self.assertEqual(resolved.position_ids, frozenset({1}))
        # Treating 0 as a seat would be invalid / empty; we map via index.


class LayoutOverrideAndCacheTests(unittest.TestCase):
    """5–6. Current layout override; rebuilt slot state on NPC change."""

    def test_resolver_uses_current_adventure_layout_not_campaign_decoy(self) -> None:
        # Campaign decoy: 5-node layout where index 5 does not exist.
        decoy = [{"x": i, "y": 0, "col": 0, "adj": []} for i in range(5)]
        payload = _shadows_payload(base_snapshot_nodes=decoy)
        resolution = resolve_slot_escort_seats(payload, 1919)
        self.assertEqual(resolution.position_ids, frozenset({4, 6}))
        self.assertTrue(resolution.mapping_reliable)

    def test_same_layout_changed_npc_occupancy_rebuilds_slot_state(self) -> None:
        payload_a = _shadows_payload(slot_ids=[5, 8])
        # Different escort indices on the same 10-node layout → different seats.
        payload_b = _shadows_payload(slot_ids=[3, 9])
        a = resolve_slot_escort_seats(payload_a, 1919)
        b = resolve_slot_escort_seats(payload_b, 1919)
        self.assertEqual(a.position_ids, frozenset({4, 6}))
        # index 3 → seat 5 (Kyre), index 9 → seat 12 (Baldric) with this board.
        self.assertEqual(b.position_ids, frozenset({5, 12}))
        self.assertNotEqual(a.position_ids, b.position_ids)


class UnresolvedAndConflictTests(unittest.TestCase):
    """7–8. Unresolved escort refs; champion/escort conflict."""

    def test_unresolvable_escort_index_is_explicit_not_free(self) -> None:
        payload = _shadows_payload(slot_ids=[5, 99], include_formation=True)
        resolution = resolve_slot_escort_seats(payload, 1919)
        self.assertIn(99, resolution.unresolved_indices)
        self.assertFalse(resolution.mapping_reliable)
        # Index 5 still resolves to 6.
        self.assertIn(6, resolution.position_ids)

        states = build_slot_states(
            _SHADOWS_LAYOUT,
            champion_by_position=_SHADOWS_CHAMPIONS,
            reserved_seats=resolution.position_ids,
            placeability_known=True,
            escort_mapping_unreliable=True,
        )
        derived = derive_position_id_lists(states)
        by_id = {s["position_id"]: s for s in states}
        self.assertEqual(by_id[6]["placeability"], "blocked")
        # Position 4 must not be silently free when mapping is unreliable.
        self.assertEqual(by_id[4]["placeability"], "unknown")
        self.assertEqual(derived["available_position_ids"], [])

    def test_champion_escort_conflict_keeps_champion_and_flags(self) -> None:
        # Force reserved seats onto live champion seats (mapping bug remnant).
        states = build_slot_states(
            _SHADOWS_LAYOUT,
            champion_by_position=_SHADOWS_CHAMPIONS,
            reserved_seats=[5, 8],
            placeability_known=True,
        )
        by_id = {s["position_id"]: s for s in states}
        self.assertEqual(by_id[5]["occupancy"], "champion")
        self.assertEqual(by_id[5]["conflict"], "champion_vs_slot_escort")
        self.assertIn("Conflict", by_id[5]["reason"])
        # Empty true NPC seats are still free under this wrong reserved set —
        # that is intentional for the conflict unit; the resolver fix prevents
        # this reserved set for Shadows.
        self.assertEqual(by_id[4]["occupancy"], "empty")


class FreeSeatsAndIntegrationTests(unittest.TestCase):
    """9–10. Two free seats; preview/export/validator agree."""

    def test_two_confirmed_free_positions_still_available(self) -> None:
        layout = list(range(1, 10))
        champs = {i: 100 + i for i in range(1, 8)}
        states = build_slot_states(
            layout,
            champion_by_position=champs,
            reserved_seats=[],
            placeability_known=True,
        )
        derived = derive_position_id_lists(states)
        self.assertEqual(derived["available_position_ids"], [8, 9])

    def test_preview_export_validator_share_npc_blocks(self) -> None:
        payload = _shadows_payload()
        resolution = resolve_slot_escort_seats(payload, 1919)
        states = build_slot_states(
            _SHADOWS_LAYOUT,
            champion_by_position=_SHADOWS_CHAMPIONS,
            reserved_seats=resolution.position_ids,
            placeability_known=True,
            escort_meta_by_position=resolution.meta_by_position,
            display_by_position={4: "2-1", 6: "3-1"},
        )
        derived = derive_position_id_lists(states)
        export = _export_from_states(
            layout=_SHADOWS_LAYOUT,
            champions=_SHADOWS_CHAMPIONS,
            slot_states=states,
        )

        overlay = build_slot_overlay_nodes(
            states,
            {
                4: (20.0, 50.0, "mid"),
                6: (40.0, 20.0, "mid"),
            },
        )
        overlay_seats = {n.seat for n in overlay}
        self.assertEqual(overlay_seats & {4, 6}, {4, 6})
        self.assertEqual(set(derived["blocked_position_ids"]), {4, 6})
        self.assertEqual(export["formation"]["available_position_ids"], [])

        # Reject add onto NPC seats (Avren=19, Skylla=55 as stand-ins).
        add_npc = [
            (hid, pos) for pos, hid in sorted(_SHADOWS_CHAMPIONS.items())
        ]
        # Replace two champs with moves onto NPC seats while keeping set size —
        # use same champion set, illegal positions.
        add_npc[0] = (165, 4)
        add_npc[1] = (166, 6)
        rejected = validate_proposal_against_export(
            _proposal(add_npc),
            export,
            api_sources=(),
            formation_fingerprint_at_request="fp",
            current_formation_fingerprint="fp",
        )
        self.assertFalse(rejected.can_apply)
        self.assertTrue(
            any("4" in e or "6" in e or "blocked" in e.lower() for e in rejected.errors)
        )

        # Valid replacement on an existing champion seat remains allowed.
        swap = [(hid, pos) for pos, hid in sorted(_SHADOWS_CHAMPIONS.items())]
        # Swap Baldric (12) and Anson (1) positions.
        swap = [
            (171, 12),
            (165, 1),
            (168, 9),
            (179, 3),
            (172, 5),
            (164, 8),
            (166, 10),
            (34, 2),
        ]
        allowed = validate_proposal_against_export(
            _proposal(swap),
            export,
            api_sources=(),
            formation_fingerprint_at_request="fp",
            current_formation_fingerprint="fp",
        )
        self.assertTrue(allowed.can_apply, allowed.errors)


class FormationBlockShadowsIntegrationTests(unittest.TestCase):
    def test_formation_block_shadows_of_the_past(self) -> None:
        from ic_gamedata.formation_advisor.context_builder import (
            build_formation_layout_context,
        )
        from ic_gamedata.formation_ai_advice.export import _formation_block
        from ic_gamedata.party_advisor_models import FormationHero

        payload = _shadows_payload()
        heroes = tuple(
            FormationHero(
                hero_id=hid,
                name=f"H{hid}",
                seat=seat,
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
            for hid, seat in _SHADOWS_SEAT_BY_HERO.items()
        )
        ctx = build_formation_layout_context(
            payload, heroes, goal="push", context="campaign"
        )
        block = _formation_block(payload, ctx, adventure_id=1919)
        states = {s["position_id"]: s for s in (block.get("slot_states") or [])}
        self.assertEqual(states[4]["occupancy"], "escort")
        self.assertEqual(states[6]["occupancy"], "escort")
        self.assertEqual(states[4]["placeability"], "blocked")
        self.assertEqual(states[6]["placeability"], "blocked")
        self.assertEqual(block.get("available_position_ids") or [], [])
        self.assertEqual(sorted(block.get("blocked_position_ids") or []), [4, 6])
        self.assertNotIn("conflict", states[5])
        self.assertNotIn("conflict", states[8])
        self.assertEqual(states[5]["occupancy"], "champion")
        self.assertEqual(states[8]["occupancy"], "champion")
        # Corrected geometry excerpt for the fixture.
        excerpt = {
            "valid_position_ids": block["valid_position_ids"],
            "blocked_position_ids": block.get("blocked_position_ids"),
            "available_position_ids": block.get("available_position_ids"),
            "escort_source_indices": block.get("escort_source_indices"),
            "slot_states_4_6": {
                4: {
                    "occupancy": states[4]["occupancy"],
                    "placeability": states[4]["placeability"],
                },
                6: {
                    "occupancy": states[6]["occupancy"],
                    "placeability": states[6]["placeability"],
                },
            },
        }
        self.assertEqual(excerpt["escort_source_indices"], [5, 8])
        self.assertIsNone(excerpt["available_position_ids"])


if __name__ == "__main__":
    unittest.main()
